package io.vectormatch.cluster;

import io.aeron.Publication;
import io.vectormatch.core.MatchingEngine.Command;
import io.vectormatch.core.MatchingEngine.Result;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.LockSupport;
import java.util.function.LongSupplier;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Bounded async functional owner. No arrival scheduler, persistence or capacity claim. */
public final class RetentionBatchOwnerV3 implements AutoCloseable {
    private static final long RESEND_NS = TimeUnit.MILLISECONDS.toNanos(500);
    private static final long NEGATIVE_RETRY_NS = TimeUnit.MICROSECONDS.toNanos(100);
    private static final long MAX_PERMIT_NS = TimeUnit.MINUTES.toNanos(2);
    private static final long MAX_PARK_NS = TimeUnit.MILLISECONDS.toNanos(1);
    public record Config(RetentionServiceV3.Profile profile, String lineage, int logicalWorkers,
                         int taskQueueCapacityPerWorker, int batchCap, long flushDelayNs) {
        public Config {
            Objects.requireNonNull(profile); new Scope(profile.fingerprint(), lineage);
            if (logicalWorkers != 128 || taskQueueCapacityPerWorker != 64 || (batchCap != 1 && batchCap != 4)
                    || flushDelayNs < 0 || flushDelayNs > MAX_PARK_NS
                    || profile.core().limits().maxProducers() < logicalWorkers
                    || profile.core().limits().maxCachedResults() < logicalWorkers
                    || profile.core().maxPendingCommands() < logicalWorkers || profile.outboxCapacity() < logicalWorkers)
                throw new IllegalArgumentException("explicit bounded W128/Q64 profile and batch1|4 required");
        }
        public static Config forBatch(RetentionServiceV3.Profile profile, String lineage, int batchCap) {
            return new Config(profile, lineage, 128, 64, batchCap, 50_000);
        }
        public int globalCreditCapacity() { return profile.core().limits().maxCachedResults(); }
        public int perProducerCreditCapacity() { return profile.core().resultCachePerProducer(); }
    }
    @FunctionalInterface public interface IOFactory { RetentionBatchOwnerIOV3 open(); }
    public enum Terminal { APPLIED, NOT_SENT }
    public record Outcome(BusinessIdentity identity, String commandSha256, Terminal terminal, Result result,
                          boolean replayed, Frontier frontier, String localReason) {
        public Outcome {
            Objects.requireNonNull(identity); Objects.requireNonNull(commandSha256); Objects.requireNonNull(terminal);
            if (terminal == Terminal.APPLIED && (result == null || frontier == null || !localReason.isEmpty())
                    || terminal == Terminal.NOT_SENT && (result != null || frontier != null || replayed || localReason.isEmpty()))
                throw new IllegalArgumentException("invalid functional owner terminal outcome");
        }
    }
    public static final class OwnerFailure extends Error {
        private static final long serialVersionUID = 1L;
        OwnerFailure(Throwable cause) { super("V3 batch network owner failed; retain all identities and evidence", cause); }
    }
    @SuppressWarnings("serial")
    public static final class UnresolvedCommandException extends IllegalStateException {
        private static final long serialVersionUID = 1L;
        private final BusinessIdentity identity;
        private final String commandSha256;
        private final byte[] originalWire;
        private final boolean mayHaveExecuted, mayStillBeOffered;
        UnresolvedCommandException(Slot slot, boolean canStillOffer, Throwable cause) {
            super("V3_UNRESOLVED: not a rejection or rollback; preserve original identity/payload. Wait timeout does not renew or revoke its absolute offer permit", cause);
            identity = slot.identity; commandSha256 = slot.commandSha;
            originalWire = slot.frame == null ? null : slot.frame.bytes.clone();
            mayHaveExecuted = slot.ordinal != 0; mayStillBeOffered = canStillOffer;
        }
        public BusinessIdentity identity() { return identity; }
        public String commandSha256() { return commandSha256; }
        public byte[] originalWire() { return originalWire == null ? null : originalWire.clone(); }
        public boolean mayHaveExecuted() { return mayHaveExecuted; }
        public boolean mayStillBeOffered() { return mayStillBeOffered; }
    }
    public final class Ticket {
        private final Slot slot;
        private final RetentionBatchOwnerV3 ticketOwner = RetentionBatchOwnerV3.this;
        private Ticket(Slot slot) { this.slot = slot; }
        public Outcome await(Duration timeout) {
            if (timeout == null || timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofMinutes(2)) > 0)
                throw new IllegalArgumentException("bounded positive wait required");
            try { return slot.completion.get(timeout.toNanos(), TimeUnit.NANOSECONDS); }
            catch (TimeoutException timeoutError) { synchronized (lock) { throw unresolved(slot, timeoutError); } }
            catch (InterruptedException cancelled) {
                Thread.currentThread().interrupt(); synchronized (lock) { throw unresolved(slot, cancelled); }
            } catch (ExecutionException failed) {
                if (failed.getCause() instanceof OwnerFailure fatal) throw fatal;
                synchronized (lock) { throw unresolved(slot, failed.getCause()); }
            }
        }
        public void revoke() { RetentionBatchOwnerV3.this.revoke(this); }
        public boolean isDone() { return slot.completion.isDone(); }
        public byte[] originalWire() { synchronized (lock) { return slot.frame == null ? null : slot.frame.bytes.clone(); } }
        public BusinessIdentity identity() { return slot.identity; }
        public String commandSha256() { return slot.commandSha; }
        public boolean admissionObserved() { synchronized (lock) { return slot.admissionObserved; } }
    }
    /** Exactly one bounded maintenance RPC shares this owner's session and correlation space. */
    public final class MaintenanceTicket {
        private final MaintenanceSlot slot;
        private MaintenanceTicket(MaintenanceSlot slot) { this.slot = slot; }
        public Reply await(Duration timeout) {
            if (timeout == null || timeout.isZero() || timeout.isNegative() || timeout.compareTo(Duration.ofMinutes(2)) > 0)
                throw new IllegalArgumentException("bounded positive maintenance wait required");
            try { return slot.completion.get(timeout.toNanos(), TimeUnit.NANOSECONDS); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw maintenanceUnknown(slot, interrupted); }
            catch (ExecutionException | TimeoutException error) { throw maintenanceUnknown(slot, error); }
        }
        public byte[] originalWire() { return slot.bytes.clone(); }
    }
    public static final class UnknownMaintenanceException extends IllegalStateException {
        private static final long serialVersionUID = 1L;
        private final byte[] originalWire;
        private final boolean mayHaveExecuted;
        UnknownMaintenanceException(MaintenanceSlot slot, Throwable cause) {
            super("V3_MAINTENANCE_UNKNOWN: retain exact original wire/maintenance identity; no implicit ACK success or fresh-key reissue", cause);
            originalWire = slot.bytes.clone(); mayHaveExecuted = slot.possiblyOffered;
        }
        public byte[] originalWire() { return originalWire.clone(); }
        public boolean mayHaveExecuted() { return mayHaveExecuted; }
    }
    private static final class MaintenanceSlot {
        final Request request;
        final byte[] bytes;
        final long deadline, mutationReserveBytes;
        final boolean mutating;
        final CompletableFuture<Reply> completion = new CompletableFuture<>();
        long nextOffer;
        int possibleOffers;
        boolean possiblyOffered, disabled;
        MaintenanceSlot(Request request, long now, long deadline) {
            this.request = request; this.deadline = deadline; nextOffer = now;
            bytes = RetentionWireV3.encode(request);
            mutating = request.operation() instanceof ArchiveCommit || request.operation() instanceof EventAck;
            mutationReserveBytes = mutating ? RetentionWireV3.encodeOperation(request.operation()).length + 1024L : 0;
        }
    }
    private UnknownMaintenanceException maintenanceUnknown(MaintenanceSlot slot, Throwable cause) {
        synchronized (lock) { return new UnknownMaintenanceException(slot, cause); }
    }
    public MaintenanceTicket submitMaintenance(Operation operation, long absoluteOfferDeadlineNs) {
        synchronized (lock) {
            healthy();
            if (closing || maintenanceStopped) throw new IllegalStateException("maintenance closed; preserve unresolved evidence");
            Objects.requireNonNull(operation);
            if (operation instanceof Business || operation instanceof BusinessBatch)
                throw new IllegalArgumentException("business must use producer-bound logical slots");
            long now = clock.getAsLong(), remaining = absoluteOfferDeadlineNs - now;
            if (remaining <= 0 || remaining > MAX_PERMIT_NS) throw new IllegalArgumentException("bounded absolute maintenance permit required");
            if (maintenance != null) {
                if (!maintenance.request.operation().equals(operation)) throw new IllegalStateException("one unresolved maintenance RPC; cannot change payload/identity");
                return new MaintenanceTicket(maintenance); // No implicit permit renewal.
            }
            if (nextCorrelation == Long.MAX_VALUE) throw new IllegalStateException("transport correlation exhausted");
            maintenance = new MaintenanceSlot(new Request(scope, ++nextCorrelation, operation), now, absoluteOfferDeadlineNs);
            wake(); return new MaintenanceTicket(maintenance);
        }
    }
    public Reply exchangeMaintenance(Operation operation, Duration timeout) {
        if (timeout == null || timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofMinutes(2)) > 0)
            throw new IllegalArgumentException("bounded maintenance timeout required");
        return submitMaintenance(operation, clock.getAsLong() + timeout.toNanos()).await(timeout);
    }
    private int offerMaintenance(RetentionBatchOwnerIOV3 io, long now) {
        MaintenanceSlot slot = maintenance;
        if (slot == null || slot.disabled) return 0;
        if (now - slot.deadline >= 0 || slot.possibleOffers >= 4) {
            slot.disabled = true; maintenanceStopped = true;
            slot.completion.completeExceptionally(new UnknownMaintenanceException(slot, null)); return 0;
        }
        if (now - slot.nextOffer < 0) return 0;
        if (slot.mutating && (maintenanceMutationOffers >= Math.min(1024, config.profile().maxMaintenanceJournalRecords())
                || slot.mutationReserveBytes > config.profile().maxMaintenanceJournalBytes() - maintenanceMutationReserveBytes)) {
            slot.disabled = true; maintenanceStopped = true;
            slot.completion.completeExceptionally(new UnknownMaintenanceException(slot, null)); return 0;
        }
        byte[] offerBytes = slot.bytes.clone();
        now = clock.getAsLong(); if (closing || now - slot.deadline >= 0) return 0;
        boolean earlierPossible = slot.possiblyOffered;
        slot.possiblyOffered = true; slot.possibleOffers++;
        if (slot.mutating) { maintenanceMutationOffers++; maintenanceMutationReserveBytes += slot.mutationReserveBytes; }
        long result = io.offer(offerBytes); // Throwing offers remain possibly executed and consume journal budget.
        if (result < 0) {
            slot.possibleOffers--; slot.possiblyOffered = earlierPossible;
            if (slot.mutating) { maintenanceMutationOffers--; maintenanceMutationReserveBytes -= slot.mutationReserveBytes; }
            maintenanceNegativeOffers++; slot.nextOffer = now + NEGATIVE_RETRY_NS;
            if (result == Publication.CLOSED || result == Publication.MAX_POSITION_EXCEEDED)
                throw new IllegalStateException("fatal maintenance offer code " + result);
            return 0;
        }
        maintenanceAcceptedOffers++; slot.nextOffer = now + RESEND_NS; return 1;
    }
    private void receiveMaintenance(Reply reply) {
        MaintenanceSlot slot = maintenance;
        if (!slot.possiblyOffered) throw new IllegalStateException("maintenance reply precedes offer");
        if (!reply.error().isEmpty()) {
            if (slot.mutating) throw new IllegalStateException("maintenance mutation error remains unresolved: " + reply.error());
        } else {
            Operation operation = slot.request.operation(); Payload payload = reply.payload();
            if (operation instanceof PrepareArchive prepare) {
                if (!(payload instanceof Descriptor descriptor) || descriptor.acknowledgement().throughCommandSeq() != prepare.throughCommandSeq()
                        || !descriptor.acknowledgement().profileHash().equals(config.profile().core().fingerprint())
                        || !descriptor.acknowledgement().lineageId().equals(scope.lineageId())) throw new IllegalStateException("maintenance descriptor binding differs");
            } else if (operation instanceof ArchiveChunk requested) {
                if (!(payload instanceof Chunk chunk) || !chunk.acknowledgement().equals(requested.acknowledgement())
                        || chunk.totalBytes() != requested.totalBytes() || chunk.offset() != requested.offset()
                        || chunk.data().length != Math.min(requested.count(), requested.totalBytes() - requested.offset()))
                    throw new IllegalStateException("maintenance chunk binding differs");
            } else if (operation instanceof FetchEvents requested) {
                if (!(payload instanceof Events events) || events.batch().events().size() > requested.count()
                        || (!events.batch().events().isEmpty() && events.batch().events().getFirst().eventSeq() != requested.fromEventSeq()))
                    throw new IllegalStateException("maintenance event prefix binding differs");
            } else if (!(payload instanceof State state) || state.result() != null || state.replayed()
                    || (slot.mutating && state.maintenance() == null) || (!slot.mutating && state.maintenance() != null))
                throw new IllegalStateException("maintenance state reply binding differs");
            if (slot.mutating) {
                var result = ((State)payload).maintenance();
                if (result.exportedEventSeq() > reply.counters().exportedEventSeq()) throw new IllegalStateException("maintenance exported frontier exceeds counters");
                if (result.code() == RetentionServiceV3.MaintenanceCode.APPLIED) {
                    if (!result.error().isEmpty()) throw new IllegalStateException("applied maintenance cannot claim error");
                    if (operation instanceof ArchiveCommit archive) {
                        var compact = result.compaction();
                        if (compact == null || compact.archivedThroughCommandSeq() != archive.acknowledgement().throughCommandSeq()
                                || compact.maintenanceSeq() > reply.counters().coreMaintenanceSeq()
                                || (!result.replayed() && compact.maintenanceSeq() != reply.counters().coreMaintenanceSeq()))
                            throw new IllegalStateException("archive ACK result target differs");
                    } else if (operation instanceof EventAck event && (result.compaction() != null
                            || result.exportedEventSeq() < event.throughEventSeq()
                            || (!result.replayed() && result.exportedEventSeq() != reply.counters().exportedEventSeq())))
                        throw new IllegalStateException("event ACK result target/shape differs");
                } else if (result.compaction() != null || result.error().isEmpty()) throw new IllegalStateException("failed maintenance shape differs");
            }
        }
        maintenanceReplies++; slot.completion.complete(reply); maintenance = null;
    }
    private static final class Slot {
        final int worker;
        final Command command;
        final BusinessIdentity identity;
        final String commandSha;
        final long readyNs, permitDeadline;
        final CompletableFuture<Outcome> completion = new CompletableFuture<>();
        boolean revoked, admissionObserved;
        long ordinal;
        Frame frame;
        Outcome terminal;
        Slot(int worker, Command command, long ready, long deadline) {
            this.worker = worker; this.command = command; identity = businessIdentity(command);
            commandSha = businessCanonicalSha256(command); readyNs = ready; permitDeadline = deadline;
        }
    }
    private static final class Frame {
        final long correlation;
        final List<Slot> slots;
        final BusinessBatch batch;
        final byte[] bytes;
        final String wireSha;
        long nextOffer, acceptedOffers;
        boolean mayHaveExecuted, disabled;
        Frame(long correlation, Scope scope, List<Slot> slots) {
            this.correlation = correlation; this.slots = List.copyOf(slots); nextOffer = slots.getFirst().readyNs;
            batch = new BusinessBatch(slots.stream().map(s -> s.command).toList());
            Request request = new Request(scope, correlation, batch); validateBatchReplyBudget(request);
            bytes = RetentionWireV3.encode(request); wireSha = hash(bytes);
            for (Slot slot : slots) slot.frame = this;
        }
    }
    private record Producer(long account, String producer) {}
    private final Object lock = new Object();
    private final Config config;
    private final Scope scope;
    private final LongSupplier clock;
    private final Slot[] slots;
    private final Producer[] workerProducers;
    private final Map<Producer, Integer> producerWorkers = new HashMap<>();
    private final ArrayDeque<Slot> ready = new ArrayDeque<>();
    private final LinkedHashMap<Long, Frame> frames = new LinkedHashMap<>();
    private final NavigableMap<Long, Slot> unresolvedOrdinals = new TreeMap<>();
    private final CompletableFuture<Void> started = new CompletableFuture<>();
    private final Thread owner;
    private boolean closing, admissionStopped, maintenanceStopped;
    private MaintenanceSlot maintenance;
    private long maintenanceMutationOffers, maintenanceMutationReserveBytes, maintenanceAcceptedOffers, maintenanceNegativeOffers, maintenanceReplies;
    private Throwable failure;
    private Map<String, Object> transportObservation = Map.of("available", false, "reason", "not_ready");
    private long nextCorrelation, lastOrdinal, acceptedLogical, acceptedPhysical, resends, unaccepted,
            applied, notSent, creditBlocked, lateReplies, admissionReplies, retiredFrames;
    private int pendingHighWater, frameHighWater;

    public RetentionBatchOwnerV3(Config config, IOFactory factory) { this(config, factory, System::nanoTime); }
    RetentionBatchOwnerV3(Config config, IOFactory factory, LongSupplier clock) {
        this.config = Objects.requireNonNull(config); this.scope = new Scope(config.profile().fingerprint(), config.lineage());
        this.clock = Objects.requireNonNull(clock); Objects.requireNonNull(factory);
        slots = new Slot[config.logicalWorkers()]; workerProducers = new Producer[slots.length];
        owner = new Thread(() -> own(factory), "retention-v3-batch-network-owner"); owner.start();
        try { started.get(25, TimeUnit.SECONDS); }
        catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt(); close(); throw new IllegalStateException("owner startup interrupted", interrupted);
        } catch (ExecutionException | TimeoutException error) { close(); throw new OwnerFailure(error); }
    }
    /** No permit renewal on duplicate submit. Same-key callers receive the same pending logical operation. */
    public Ticket submit(int worker, Command command, long absoluteOfferDeadlineNs) {
        synchronized (lock) {
            healthy();
            if (closing || admissionStopped || maintenanceStopped) throw new IllegalStateException("owner closed to new business; retained unknowns require explicit closure");
            if (worker < 0 || worker >= slots.length) throw new IllegalArgumentException("invalid logical worker");
            long now = clock.getAsLong(), remaining = absoluteOfferDeadlineNs - now;
            if (remaining <= 0 || remaining > MAX_PERMIT_NS) throw new IllegalArgumentException("absolute offer permit must be within two minutes");
            BusinessIdentity id = businessIdentity(command); businessCanonicalSha256(command);
            Producer producer = new Producer(id.accountId(), id.producerId());
            if (workerProducers[worker] != null && !workerProducers[worker].equals(producer))
                throw new IllegalArgumentException("logical worker cannot switch producer");
            Integer bound = producerWorkers.get(producer);
            if (bound != null && bound != worker) throw new IllegalArgumentException("producer already belongs to another logical worker");
            Slot pending = slots[worker];
            if (pending != null) {
                if (!pending.command.equals(command)) throw new IllegalStateException("one unresolved command per producer; retain original payload");
                return new Ticket(pending);
            }
            workerProducers[worker] = producer; producerWorkers.put(producer, worker);
            Slot slot = new Slot(worker, command, now, absoluteOfferDeadlineNs); slots[worker] = slot; ready.addLast(slot);
            pendingHighWater = Math.max(pendingHighWater, pendingCount()); wake(); return new Ticket(slot);
        }
    }
    public void revoke(Ticket ticket) {
        Objects.requireNonNull(ticket);
        synchronized (lock) {
            if (ticket.ticketOwner != this || ticket.slot.worker >= slots.length
                    || (slots[ticket.slot.worker] != ticket.slot && ticket.slot.terminal == null))
                throw new IllegalArgumentException("foreign ticket");
            ticket.slot.revoked = true; wake();
        }
    }
    private void healthy() { if (failure != null) throw new OwnerFailure(failure); }
    private UnresolvedCommandException unresolved(Slot slot, Throwable cause) {
        long now = clock.getAsLong();
        boolean canOffer = !closing && !admissionStopped && !maintenanceStopped && slot.terminal == null && permitted(slot, now)
                && (slot.frame == null || (!slot.frame.disabled && framePermitted(slot.frame, now)));
        return new UnresolvedCommandException(slot, canOffer, cause);
    }
    private static String hash(byte[] bytes) { return HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)); }
    private int pendingCount() { int count = 0; for (Slot slot : slots) if (slot != null) count++; return count; }
    private boolean permitted(Slot slot, long now) { return !slot.revoked && now - slot.permitDeadline < 0; }
    private boolean framePermitted(Frame frame, long now) { return frame.slots.stream().allMatch(s -> permitted(s, now)); }
    private long creditSpan() { return unresolvedOrdinals.isEmpty() ? 0 : lastOrdinal - unresolvedOrdinals.firstKey() + 1; }
    private boolean creditAllows(int count) { return count <= config.globalCreditCapacity() - creditSpan(); }
    private void reserve(Frame frame) {
        if (!creditAllows(frame.slots.size()) || lastOrdinal > Long.MAX_VALUE - frame.slots.size())
            throw new IllegalStateException("global credit/rank reservation exceeds bound");
        for (Slot slot : frame.slots) { slot.ordinal = ++lastOrdinal; unresolvedOrdinals.put(slot.ordinal, slot); }
        frame.mayHaveExecuted = true; // Reserve BEFORE offer: a throwing offer is conservatively ambiguous.
    }
    private void releaseDefiniteNegative(Frame frame) {
        for (int index = frame.slots.size() - 1; index >= 0; index--) {
            Slot slot = frame.slots.get(index);
            if (slot.ordinal != lastOrdinal || unresolvedOrdinals.remove(lastOrdinal) != slot)
                throw new IllegalStateException("negative offer credit rollback must be the exact owned tail");
            lastOrdinal--; slot.ordinal = 0;
        }
        frame.mayHaveExecuted = false;
    }
    private void terminal(Slot slot, Outcome outcome) {
        if (slot.terminal != null) return;
        slot.terminal = outcome;
        if (slot.ordinal != 0) unresolvedOrdinals.remove(slot.ordinal);
        if (slots[slot.worker] != slot) throw new IllegalStateException("logical slot ownership changed");
        slots[slot.worker] = null; slot.completion.complete(outcome);
    }
    private void notSent(Slot slot, String why) {
        if (slot.ordinal != 0) throw new IllegalStateException("possibly executed request cannot become NOT_SENT");
        terminal(slot, new Outcome(slot.identity, slot.commandSha, Terminal.NOT_SENT, null, false, null, why)); notSent++;
    }
    private void abortUnaccepted(Frame frame, String why) {
        if (frame.mayHaveExecuted) throw new IllegalStateException("cannot abort an accepted/ambiguous frame");
        frame.disabled = true; for (Slot slot : frame.slots) notSent(slot, why);
    }
    private void receive(Reply reply) {
        synchronized (lock) {
            if (!scope.equals(reply.scope())) throw new IllegalStateException("reply scope differs");
            if (maintenance != null && maintenance.request.correlationId() == reply.correlationId()) { receiveMaintenance(reply); return; }
            Frame frame = frames.get(reply.correlationId());
            if (frame == null) { lateReplies++; return; }
            if (!frame.mayHaveExecuted) throw new IllegalStateException("reply precedes any possibly accepted offer");
            RetentionClientV3.validateBatchResponse(frame.batch, reply);
            if (!reply.error().isEmpty() || !(reply.payload() instanceof Batch batch))
                throw new IllegalStateException("batch outcome lacks a complete terminal result set: " + reply.error());
            // Validate the entire set before publishing even the first per-command completion.
            for (BatchEntry entry : batch.entries()) {
                Slot slot = frame.slots.get(entry.index());
                if (!entry.identity().equals(slot.identity) || !entry.commandSha256().equals(slot.commandSha))
                    throw new IllegalStateException("per-command reply binding differs");
            }
            for (BatchEntry entry : batch.entries()) {
                Slot slot = frame.slots.get(entry.index());
                if (slot.terminal != null) continue; // A late duplicate may legitimately be stale after its captured result was consumed.
                if (entry.status() == BatchStatus.APPLIED) {
                    terminal(slot, new Outcome(slot.identity, slot.commandSha, Terminal.APPLIED, entry.result(), entry.replayed(), entry.frontier(), "")); applied++;
                } else {
                    slot.admissionObserved = true; admissionStopped = true; frame.disabled = true;
                }
            }
            if (admissionStopped) { admissionReplies++; for (Frame pending : frames.values()) pending.disabled = true; }
        }
    }
    private void build(long now) {
        for (var iterator = ready.iterator(); iterator.hasNext();) {
            Slot slot = iterator.next();
            if (!permitted(slot, now)) { iterator.remove(); notSent(slot, "PERMIT_REVOKED_OR_EXPIRED_BEFORE_FRAME"); }
        }
        while (!admissionStopped && !maintenanceStopped && !ready.isEmpty() && frames.size() < slots.length) {
            Slot first = ready.peekFirst();
            if (ready.size() < config.batchCap() && now - first.readyNs < config.flushDelayNs()) break;
            int count = Math.min(config.batchCap(), ready.size()); var group = new ArrayList<Slot>(count);
            for (int i = 0; i < count; i++) group.add(ready.removeFirst());
            if (nextCorrelation == Long.MAX_VALUE) throw new IllegalStateException("transport correlation exhausted");
            Frame frame = new Frame(++nextCorrelation, scope, group); frames.put(frame.correlation, frame);
            frameHighWater = Math.max(frameHighWater, frames.size());
        }
    }
    private int offerFrames(RetentionBatchOwnerIOV3 io) {
        int work = 0;
        for (Frame frame : frames.values()) {
            if (closing || admissionStopped || maintenanceStopped || frame.disabled || frame.slots.stream().allMatch(s -> s.terminal != null)) continue;
            long now = clock.getAsLong();
            if (!framePermitted(frame, now)) {
                frame.disabled = true;
                if (!frame.mayHaveExecuted) abortUnaccepted(frame, "FRAME_PERMIT_REVOKED_OR_EXPIRED_BEFORE_FIRST_ACCEPTED_OFFER");
                continue;
            }
            if (now - frame.nextOffer < 0) continue;
            boolean first = !frame.mayHaveExecuted;
            if (first && !creditAllows(frame.slots.size())) { creditBlocked++; continue; }
            if (!hash(frame.bytes).equals(frame.wireSha)) throw new IllegalStateException("original wire was mutated");
            byte[] offerBytes = frame.bytes.clone(); // The IO boundary cannot mutate the retained original.
            if (first) reserve(frame);
            // Revoke holds the same monitor across this fresh check and nonblocking offer.
            now = clock.getAsLong();
            if (!framePermitted(frame, now) || closing) {
                if (first) releaseDefiniteNegative(frame);
                frame.disabled = true;
                if (first) abortUnaccepted(frame, "FRAME_PERMIT_EXPIRED_BEFORE_OFFER_CALL");
                continue;
            }
            long offered = io.offer(offerBytes); // Throwable keeps the pre-reserved credit as possibly executed.
            if (offered >= 0) {
                if (first) acceptedLogical += frame.slots.size();
                else resends++;
                acceptedPhysical++; frame.acceptedOffers++; frame.nextOffer = now + RESEND_NS; work++;
            } else {
                if (first) releaseDefiniteNegative(frame);
                unaccepted++; frame.nextOffer = now + NEGATIVE_RETRY_NS;
                if (offered == Publication.CLOSED || offered == Publication.MAX_POSITION_EXCEEDED)
                    throw new IllegalStateException("fatal physical publication offer code " + offered);
            }
        }
        return work;
    }
    private long parkDuration(long now) {
        long delay = MAX_PARK_NS;
        if (!admissionStopped && !maintenanceStopped && !ready.isEmpty()) delay = Math.min(delay, Math.max(0, config.flushDelayNs() - (now - ready.peekFirst().readyNs)));
        for (Slot slot : ready) delay = Math.min(delay, Math.max(0, slot.permitDeadline - now));
        for (Frame frame : frames.values()) {
            if (frame.disabled || maintenanceStopped) continue;
            if (frame.mayHaveExecuted || creditAllows(frame.slots.size())) delay = Math.min(delay, Math.max(0, frame.nextOffer - now));
            for (Slot slot : frame.slots) delay = Math.min(delay, Math.max(0, slot.permitDeadline - now));
        }
        if (maintenance != null && !maintenance.disabled) delay = Math.min(delay, Math.max(0, Math.min(maintenance.nextOffer, maintenance.deadline) - now));
        return Math.max(1, delay);
    }
    private void own(IOFactory factory) {
        RetentionBatchOwnerIOV3 io = null;
        try {
            io = factory.open(); synchronized (lock) { transportObservation = Map.copyOf(io.observation()); }
            started.complete(null);
            while (true) {
                synchronized (lock) { if (closing) break; }
                int work = io.poll(this::receive); long pause;
                synchronized (lock) {
                    long now = clock.getAsLong(); build(now); work += offerMaintenance(io, now); work += offerFrames(io);
                    for (var iterator = frames.entrySet().iterator(); iterator.hasNext();) {
                        Frame f = iterator.next().getValue();
                        if (f.slots.stream().allMatch(s -> s.terminal != null)) { iterator.remove(); retiredFrames++; }
                    }
                    pause = parkDuration(clock.getAsLong());
                }
                if (work == 0) LockSupport.parkNanos(pause);
            }
        } catch (Throwable error) {
            synchronized (lock) { failure = error; closing = true; }
            started.completeExceptionally(error);
        } finally {
            synchronized (lock) {
                closing = true;
                if (maintenance != null) maintenance.completion.completeExceptionally(new UnknownMaintenanceException(maintenance, failure));
                for (Slot slot : slots) if (slot != null) {
                    if (slot.ordinal == 0) notSent(slot, "OWNER_CLOSED_BEFORE_ACCEPTED_OFFER");
                    else slot.completion.completeExceptionally(failure == null ? unresolved(slot, null) : new OwnerFailure(failure));
                }
            }
            if (io != null) try { io.close(); } catch (Throwable closeError) {
                synchronized (lock) { if (failure == null) failure = closeError; else failure.addSuppressed(closeError); }
            }
        }
    }
    void wake() { LockSupport.unpark(owner); }
    public Map<String, Object> snapshot() {
        synchronized (lock) {
            var out = new LinkedHashMap<String, Object>();
            out.put("logicalWorkers", slots.length); out.put("taskQueueCapacityPerWorker", config.taskQueueCapacityPerWorker());
            out.put("externalTaskQueuePositions", (long) slots.length * config.taskQueueCapacityPerWorker());
            out.put("taskQueueOwnership", "external scheduler; this owner allocates no task FIFO");
            out.put("internalPendingCapacity", slots.length); out.put("maximumFrames", slots.length); out.put("batchCap", config.batchCap());
            out.put("flushDeadlineNs", config.flushDelayNs()); out.put("waitPolicy", "deadline-aware park up to 1ms; OS lateness is not bounded");
            out.put("globalCreditCapacity", config.globalCreditCapacity()); out.put("perProducerCreditCapacity", config.perProducerCreditCapacity());
            out.put("pendingLogicalCommands", pendingCount()); out.put("readyLogicalCommands", ready.stream().filter(s -> s.terminal == null).count());
            out.put("activeFrames", frames.values().stream().filter(f -> f.slots.stream().anyMatch(s -> s.terminal == null)).count());
            out.put("unresolvedPossiblyExecutedLogicalCommands", unresolvedOrdinals.size()); out.put("globalCreditSpan", creditSpan());
            out.put("oldestUnresolvedFirstOfferOrdinal", unresolvedOrdinals.isEmpty() ? null : unresolvedOrdinals.firstKey()); out.put("lastPossiblyExecutedFirstOfferOrdinal", lastOrdinal);
            out.put("firstAcceptedLogicalCommands", acceptedLogical); out.put("acceptedPhysicalOffers", acceptedPhysical); out.put("physicalResends", resends);
            out.put("unacceptedPhysicalOffers", unaccepted); out.put("logicalAppliedResults", applied); out.put("logicalNotSent", notSent);
            out.put("creditBlockedOfferChecks", creditBlocked); out.put("ignoredLateReplies", lateReplies); out.put("admissionReplyObservations", admissionReplies);
            out.put("retiredFrames", retiredFrames); out.put("pendingHighWater", pendingHighWater); out.put("frameHighWater", frameHighWater);
            out.put("newBusinessAdmissionStopped", admissionStopped); out.put("closed", closing); out.put("ownerThreadAlive", owner.isAlive());
            out.put("failureType", failure == null ? null : failure.getClass().getName()); out.put("transportObservation", transportObservation);
            out.put("maintenanceRpcCapacity", 1); out.put("maintenancePending", maintenance != null);
            out.put("maintenanceStopped", maintenanceStopped); out.put("maintenanceAcceptedOffers", maintenanceAcceptedOffers);
            out.put("maintenanceNegativeOffers", maintenanceNegativeOffers); out.put("maintenanceReplies", maintenanceReplies);
            out.put("possibleMaintenanceMutationOffers", maintenanceMutationOffers); out.put("maintenanceMutationReserveBytes", maintenanceMutationReserveBytes);
            out.put("maintenanceMutationOfferLimit", Math.min(1024, config.profile().maxMaintenanceJournalRecords()));
            out.put("maintenancePossibleOfferLimitPerRpc", 4);
            out.put("scope", "Bounded singleowner functional contract; no persistence/cold recovery/arrival scheduler/capacity or endurance proof");
            return Collections.unmodifiableMap(out);
        }
    }
    @Override public void close() {
        synchronized (lock) { closing = true; }
        wake();
        if (Thread.currentThread() == owner) throw new IllegalStateException("owner cannot join itself");
        boolean interrupted = Thread.interrupted(); long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(25);
        while (owner.isAlive() && System.nanoTime() - end < 0) {
            try { owner.join(50); } catch (InterruptedException error) { interrupted = true; }
        }
        if (interrupted) Thread.currentThread().interrupt();
        if (owner.isAlive()) throw new IllegalStateException("owned network thread did not close; preserve evidence, no unrelated cleanup");
        synchronized (lock) { healthy(); } // Closing transport failures are not successful cleanup.
    }
}
