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
        /** Owner-clock observations; missing events are null, not a fabricated zero latency. */
        public Map<String,Object> observation() { synchronized(lock) {
            var value=new LinkedHashMap<String,Object>();
            value.put("correlationId",slot.frame==null?null:slot.frame.correlation);
            value.put("batchIndex",slot.frame==null?null:slot.frame.slots.indexOf(slot));
            value.put("firstWireOfferCallNs",slot.firstOfferNs==Long.MIN_VALUE?null:slot.firstOfferNs);
            value.put("firstPhysicalAdmissionNs",slot.firstAcceptedOfferNs==Long.MIN_VALUE?null:slot.firstAcceptedOfferNs);
            value.put("replyCompletionNs",slot.completionNs==Long.MIN_VALUE?null:slot.completionNs);
            value.put("admittedPhysicalOfferCount",slot.acceptedPhysicalOfferCount);
            value.put("wireSha256",slot.frame==null?null:slot.frame.wireSha);
            value.put("initialAdmissionStatus",slot.initialAdmissionStatus==null?null:slot.initialAdmissionStatus.name());
            return Collections.unmodifiableMap(value);
        }}
    }
    /** Exactly one bounded maintenance RPC shares this owner's session and correlation space. */
    public final class MaintenanceTicket {
        private final MaintenanceSlot slot;
        private MaintenanceTicket(MaintenanceSlot slot) { this.slot = slot; }
        public Reply await(Duration timeout) {
            if (timeout == null || timeout.isZero() || timeout.isNegative() || timeout.compareTo(Duration.ofMinutes(2)) > 0)
                throw new IllegalArgumentException("bounded positive maintenance wait required");
            try { return slot.completion.get(timeout.toNanos(), TimeUnit.NANOSECONDS); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt();if(slot.bank!=null)throw slot.bank.abort(interrupted); throw maintenanceUnknown(slot, interrupted); }
            catch (ExecutionException error) { if(error.getCause() instanceof ReadBankFailureException bundle)throw bundle;throw maintenanceUnknown(slot,error); }
            catch (TimeoutException error) { if(slot.bank!=null)throw slot.bank.abort(error);throw maintenanceUnknown(slot,error); }
        }
        public byte[] originalWire() { return slot.bytes.clone(); }
        public boolean isDone() { return slot.completion.isDone(); }
        public void arm(){synchronized(lock){
            if(slot.bank==null)throw new IllegalStateException("only explicitly reserved bank reads are armed here");
            slot.bank.affinity();if(slot.bank.failure!=null)throw slot.bank.failure;healthy();
            if(readBank!=slot.bank||slot.bank.closed||closing||maintenanceStopped)throw new IllegalStateException("read phase terminal");
            if(slot.armed)return;
            if(clock.getAsLong()-slot.deadline>=0){maintenanceStopped=true;stopReadBank(new TimeoutException("original read permit expired before arm"));throw slot.bank.failure;}
            slot.armed=true;slot.armedNs=clock.getAsLong();observeReadHighWaters();wake();
        }}
        public Map<String,Object> observation() { synchronized(lock) {
            var out=new LinkedHashMap<String,Object>();out.put("correlationId",slot.request.correlationId());out.put("wireSha256",hash(slot.bytes));
            out.put("readPhaseGeneration",slot.bank==null?null:slot.bank.generation);out.put("armedMonotonicNs",slot.armedNs==Long.MIN_VALUE?null:slot.armedNs);out.put("operationKind",slot.request.operation().getClass().getSimpleName());out.put("armed",slot.armed);out.put("consumed",slot.consumed);
            out.put("reservedMonotonicNs",slot.reservedNs);out.put("absoluteOfferDeadlineNs",slot.deadline);out.put("possibleOffers",slot.possibleOffers);out.put("mayHaveExecuted",slot.possiblyOffered);
            out.put("acceptedPhysicalOffers",slot.acceptedOffers);out.put("negativeOffers",slot.negativeOffers);out.put("disabled",slot.disabled);
            out.put("completionDone",slot.completion.isDone());out.put("completionExceptional",slot.completion.isCompletedExceptionally());
            out.put("firstOfferCallNs",slot.firstOfferNs==Long.MIN_VALUE?null:slot.firstOfferNs);out.put("firstSuccessfulOfferReturnNs",slot.firstAcceptedNs==Long.MIN_VALUE?null:slot.firstAcceptedNs);
            out.put("replyCompletionNs",slot.completedNs==Long.MIN_VALUE?null:slot.completedNs);return Collections.unmodifiableMap(out);
        }}
    }
    /** Immutable bounded all-slot bundle survives a broken evidence filesystem. */
    public static final class ReadBankFailureException extends IllegalStateException {
        private static final long serialVersionUID=1L;
        private final List<byte[]> wires;
        private final List<Map<String,Object>> observations;
        private ReadBankFailureException(List<MaintenanceSlot> slots,Throwable cause,RetentionBatchOwnerV3 owner){
            super("V3_READ_BANK_FAILED: all retained original wires remain authoritative; no ACK, fresh correlation or implicit rollback",cause);
            wires=slots.stream().map(slot->slot.bytes.clone()).toList();
            observations=slots.stream().map(slot->owner.new MaintenanceTicket(slot).observation()).toList();
        }
        public List<byte[]> originalWires(){return wires.stream().map(byte[]::clone).toList();}
        public List<Map<String,Object>> observations(){return observations;}
    }
    /** Exclusive lease; reserved, active and completed-unconsumed reads all occupy a credit. */
    public final class ReadBank implements AutoCloseable {
        private final int limit;
        private final long generation=++readPhaseGeneration;
        private final Thread caller=Thread.currentThread();
        private final LinkedHashMap<Long,MaintenanceSlot> pending=new LinkedHashMap<>();
        private boolean closed;
        private Class<?> kind;
        private ReadBankFailureException failure;
        private ReadBank(int limit){this.limit=limit;}
        private void affinity(){if(Thread.currentThread()!=caller)throw new IllegalStateException("one read-bank caller required");}
        public MaintenanceTicket reserve(Operation operation,long deadline) {
            affinity();synchronized(lock){if(failure!=null)throw failure;healthy();
                if(closed||readBank!=this||closing||maintenanceStopped)throw new IllegalStateException("read bank terminal; retain every original wire");
                if(!(operation instanceof ArchiveChunk)&&!(operation instanceof FetchEvents))throw new IllegalArgumentException("read bank permits only archive chunks and event fetches");
                if(kind!=null&&kind!=operation.getClass())throw new IllegalStateException("one read kind per phase generation");
                if(kind==null)kind=operation.getClass();
                for(var slot:pending.values()){
                    if(slot.request.operation().equals(operation))return new MaintenanceTicket(slot);
                    if(slot.request.operation().getClass()!=operation.getClass())throw new IllegalStateException("chunk and event read phases cannot overlap");
                }
                if(pending.size()>=limit)throw new IllegalStateException("bounded read-bank credits full, including completed-unconsumed");
                long now=clock.getAsLong(),remaining=deadline-now;
                if(remaining<=0||remaining>MAX_PERMIT_NS)throw new IllegalArgumentException("bounded absolute read permit required");
                if(nextCorrelation==Long.MAX_VALUE)throw new IllegalStateException("transport correlation exhausted");
                var slot=new MaintenanceSlot(new Request(scope,++nextCorrelation,operation),now,deadline);slot.bank=this;slot.armed=false;pending.put(slot.request.correlationId(),slot);
                readOnlyRetainedHighWater=Math.max(readOnlyRetainedHighWater,pending.size());readOnlySubmitted++;return new MaintenanceTicket(slot);
            }
        }
        public void consume(MaintenanceTicket ticket){affinity();synchronized(lock){
            if(ticket==null||ticket.slot.bank!=this)throw new IllegalArgumentException("foreign read ticket");
            var slot=ticket.slot;if(slot.consumed)return;if(failure!=null)throw failure;healthy();
            if(closed||readBank!=this||!slot.completion.isDone()||slot.completion.isCompletedExceptionally())throw new IllegalStateException("only a definite recorded read reply can release a credit");
            if(pending.remove(slot.request.correlationId())!=slot)throw new IllegalStateException("read credit ownership differs");slot.consumed=true;
            retiredReadCorrelations.add(slot.request.correlationId());if(retiredReadCorrelations.size()>256)retiredReadCorrelations.remove(retiredReadCorrelations.iterator().next());
            wake();
        }}
        public List<Map<String,Object>> outstandingObservations(){synchronized(lock){return pending.values().stream().map(slot->new MaintenanceTicket(slot).observation()).toList();}}
        public ReadBankFailureException abort(Throwable cause){affinity();synchronized(lock){if(closed||readBank!=this)throw new IllegalStateException("retired read bank cannot abort another generation");maintenanceStopped=true;stopReadBank(cause);wake();return failure;}}
        @Override public void close(){affinity();synchronized(lock){
            if(closed)return;if(failure!=null)throw failure;
            if(readBank!=this||!pending.isEmpty())throw new IllegalStateException("unresolved/unconsumed reads fence control/ACK and new cycles");
            closed=true;readBank=null;wake();
        }}
    }
    public ReadBank openReadBank(int window){
        RetentionCapacityPlanV3.requireReadWindow(window);return openReadBank(window,8);
    }
    /** Explicit opt-in, preserving the old API's eight-credit ceiling. */
    public ReadBank openReadBank32(int window){
        RetentionCapacityPlanV3.requireReadWindow32(window);return openReadBank(window,32);
    }
    /** Isolated32/128 experiment; existing1/8 and8/32 APIs retain their ceilings. */
    public ReadBank openReadBank128(int window){
        RetentionCapacityPlanV3.requireReadWindow128(window);return openReadBank(window,128);
    }
    private ReadBank openReadBank(int window,int hardCapacity){synchronized(lock){healthy();
        if(closing||maintenanceStopped||readBank!=null||maintenance!=null||pendingCount()!=0)throw new IllegalStateException("read bank requires definite business/control closure");
        readBank=new ReadBank(window);selectedReadWindow=window;readOnlyHardCapacity=hardCapacity;return readBank;
    }}
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
        final long deadline, mutationReserveBytes,reservedNs;
        final boolean mutating;
        final CompletableFuture<Reply> completion = new CompletableFuture<>();
        long nextOffer;
        long armedNs=Long.MIN_VALUE,firstOfferNs=Long.MIN_VALUE,firstAcceptedNs=Long.MIN_VALUE,completedNs=Long.MIN_VALUE,acceptedOffers,negativeOffers;
        int possibleOffers;
        boolean possiblyOffered, disabled,armed=true,consumed;
        ReadBank bank;
        MaintenanceSlot(Request request, long now, long deadline) {
            this.request = request; this.deadline = deadline;reservedNs=now; nextOffer = now;
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
            if(readBank!=null)throw new IllegalStateException("read bank must close before serial control/ACK");
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
        return offerMaintenanceSlot(io,maintenance,now);
    }
    private int offerMaintenanceSlot(RetentionBatchOwnerIOV3 io,MaintenanceSlot slot,long now) {
        if (slot == null || slot.disabled || !slot.armed || slot.completion.isDone() || maintenanceStopped || closing) return 0;
        if (now - slot.deadline >= 0 || slot.possibleOffers >= 4) {
            slot.disabled = true; maintenanceStopped = true;
            if(slot.bank!=null)stopReadBank(new TimeoutException("original read deadline or four-offer budget exhausted"));else slot.completion.completeExceptionally(new UnknownMaintenanceException(slot,null)); return 0;
        }
        if (now - slot.nextOffer < 0) return 0;
        if (slot.mutating && (maintenanceMutationOffers >= Math.min(1024, config.profile().maxMaintenanceJournalRecords())
                || slot.mutationReserveBytes > config.profile().maxMaintenanceJournalBytes() - maintenanceMutationReserveBytes)) {
            slot.disabled = true; maintenanceStopped = true;
            if(slot.bank!=null)stopReadBank(new TimeoutException("original read deadline or four-offer budget exhausted"));else slot.completion.completeExceptionally(new UnknownMaintenanceException(slot,null)); return 0;
        }
        byte[] offerBytes = slot.bytes.clone();
        now = clock.getAsLong();if(closing)return 0;
        if(now-slot.deadline>=0){slot.disabled=true;maintenanceStopped=true;
            if(slot.bank!=null)stopReadBank(new TimeoutException("original read permit expired before offer call"));
            else slot.completion.completeExceptionally(new UnknownMaintenanceException(slot,null));return 0;
        }
        boolean earlierPossible = slot.possiblyOffered;
        slot.possiblyOffered = true; slot.possibleOffers++;
        if (slot.mutating) { maintenanceMutationOffers++; maintenanceMutationReserveBytes += slot.mutationReserveBytes; }
        if(slot.firstOfferNs==Long.MIN_VALUE)slot.firstOfferNs=now;
        long result = io.offer(offerBytes); // Throwing offers remain possibly executed and consume journal budget.
        if (result < 0) {
            slot.possibleOffers--; slot.possiblyOffered = earlierPossible;
            if (slot.mutating) { maintenanceMutationOffers--; maintenanceMutationReserveBytes -= slot.mutationReserveBytes; }
            maintenanceNegativeOffers++; slot.negativeOffers++; slot.nextOffer = now + NEGATIVE_RETRY_NS;
            if (result == Publication.CLOSED || result == Publication.MAX_POSITION_EXCEEDED)
                throw new IllegalStateException("fatal maintenance offer code " + result);
            return 0;
        }
        maintenanceAcceptedOffers++;slot.acceptedOffers++;observeReadHighWaters();if(slot.firstAcceptedNs==Long.MIN_VALUE)slot.firstAcceptedNs=clock.getAsLong(); slot.nextOffer = now + RESEND_NS; return 1;
    }
    private void receiveMaintenance(Reply reply,MaintenanceSlot slot) {
        if (!slot.possiblyOffered) throw new IllegalStateException("maintenance reply precedes offer");
        if(slot.completion.isDone()){readOnlyDuplicateOrLateReplies++;return;}
        if (!reply.error().isEmpty()) {
            if(slot.bank!=null){maintenanceStopped=true;stopReadBank(new IllegalStateException("read reply error: "+reply.error()));return;}
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
        maintenanceReplies++;slot.completedNs=clock.getAsLong();slot.completion.complete(reply);
        if(slot==maintenance)maintenance=null;
        else {readOnlyCompleted++;}
    }
    private void observeReadHighWaters(){
        if(readBank==null)return;
        int armed=0,offered=0;for(var slot:readBank.pending.values())if(!slot.completion.isDone()){
            if(slot.armed)armed++;if(slot.acceptedOffers>0)offered++;
        }
        readOnlyInFlightHighWater=Math.max(readOnlyInFlightHighWater,armed);readOnlyOfferedInFlightHighWater=Math.max(readOnlyOfferedInFlightHighWater,offered);
    }
    private void stopReadBank(Throwable cause){
        if(readBank==null)return;
        for(var slot:readBank.pending.values())slot.disabled=true;
        if(readBank.failure==null)readBank.failure=new ReadBankFailureException(List.copyOf(readBank.pending.values()),cause,this);
        for(var slot:readBank.pending.values())slot.completion.completeExceptionally(readBank.failure);
    }
    private int offerReadBank(RetentionBatchOwnerIOV3 io){
        if(readBank==null||maintenanceStopped)return 0;int work=0;
        for(var slot:readBank.pending.values()){work+=offerMaintenanceSlot(io,slot,clock.getAsLong());if(maintenanceStopped)break;}
        return work;
    }
    private static final class Slot {
        final int worker;
        final Command command;
        final BusinessIdentity identity;
        final String commandSha;
        final long readyNs, permitDeadline;
        final CompletableFuture<Outcome> completion = new CompletableFuture<>();
        boolean revoked, admissionObserved;
        BatchStatus initialAdmissionStatus;
        long ordinal;
        long firstOfferNs=Long.MIN_VALUE,firstAcceptedOfferNs=Long.MIN_VALUE,completionNs=Long.MIN_VALUE,acceptedPhysicalOfferCount;
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
    private ReadBank readBank;
    private final LinkedHashSet<Long> retiredReadCorrelations=new LinkedHashSet<>();
    private int readOnlyHardCapacity=8,selectedReadWindow=1,readOnlyRetainedHighWater,readOnlyInFlightHighWater,readOnlyOfferedInFlightHighWater;
    private long readOnlySubmitted,readOnlyCompleted,readOnlyDuplicateOrLateReplies,readPhaseGeneration;
    private long maintenanceMutationOffers, maintenanceMutationReserveBytes, maintenanceAcceptedOffers, maintenanceNegativeOffers, maintenanceReplies;
    private Throwable failure;
    private Map<String, Object> transportObservation = Map.of("available", false, "reason", "not_ready");
    private long transportObservedAtNs;
    private final List<Map<String,Object>> transportSamples=new ArrayList<>();
    private long nextCorrelation, lastOrdinal, acceptedLogical, acceptedPhysical, resends, unaccepted,
            applied, notSent, creditBlocked, lateReplies, admissionReplies, retiredFrames;
    private int pendingHighWater, frameHighWater;
    private final long ownerPollMaxParkNs;

    public RetentionBatchOwnerV3(Config config, IOFactory factory) { this(config, factory, System::nanoTime, MAX_PARK_NS); }
    /** Explicit load-owner polling cap; Config.flushDelayNs retains its independent legacy1ms bound. */
    public RetentionBatchOwnerV3(Config config, IOFactory factory, long ownerPollMaxParkNs) { this(config, factory, System::nanoTime, ownerPollMaxParkNs); }
    RetentionBatchOwnerV3(Config config, IOFactory factory, LongSupplier clock) { this(config, factory, clock, MAX_PARK_NS); }
    RetentionBatchOwnerV3(Config config, IOFactory factory, LongSupplier clock, long ownerPollMaxParkNs) {
        this.ownerPollMaxParkNs = RetentionOwnerPollPolicyV3.requireMaximum(ownerPollMaxParkNs);
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
            if (closing || admissionStopped || maintenanceStopped || readBank!=null) throw new IllegalStateException("owner closed to new business; retained unknowns require explicit closure");
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
        slot.completionNs=clock.getAsLong(); slot.terminal = outcome;
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
            if(reply.correlationId()<=0||reply.correlationId()>nextCorrelation)throw new IllegalStateException("reply correlation exceeds allocated monotonic high-water");
            if (maintenance != null && maintenance.request.correlationId() == reply.correlationId()) { receiveMaintenance(reply,maintenance); return; }
            if(readBank!=null){var slot=readBank.pending.get(reply.correlationId());if(slot!=null){receiveMaintenance(reply,slot);return;}}
            if(retiredReadCorrelations.contains(reply.correlationId())){readOnlyDuplicateOrLateReplies++;return;}
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
                    slot.admissionObserved = true; if(slot.initialAdmissionStatus==null)slot.initialAdmissionStatus=entry.status(); admissionStopped = true; frame.disabled = true;
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
        while (!admissionStopped && !maintenanceStopped && readBank==null && !ready.isEmpty() && frames.size() < slots.length) {
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
            if (closing || admissionStopped || maintenanceStopped || readBank!=null || frame.disabled || frame.slots.stream().allMatch(s -> s.terminal != null)) continue;
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
            for(Slot slot:frame.slots)if(slot.firstOfferNs==Long.MIN_VALUE)slot.firstOfferNs=now;
            long offered = io.offer(offerBytes); // Throwable keeps the pre-reserved credit as possibly executed.
            if (offered >= 0) {
                long returnedAt=clock.getAsLong();
                for(Slot slot:frame.slots){if(slot.firstAcceptedOfferNs==Long.MIN_VALUE)slot.firstAcceptedOfferNs=returnedAt;slot.acceptedPhysicalOfferCount++;}
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
    long parkDuration(long now) {
        long delay = ownerPollMaxParkNs;
        if (!admissionStopped && !maintenanceStopped && !ready.isEmpty()) delay = Math.min(delay, Math.max(0, config.flushDelayNs() - (now - ready.peekFirst().readyNs)));
        for (Slot slot : ready) delay = Math.min(delay, Math.max(0, slot.permitDeadline - now));
        for (Frame frame : frames.values()) {
            if (frame.disabled || maintenanceStopped) continue;
            if (frame.mayHaveExecuted || creditAllows(frame.slots.size())) delay = Math.min(delay, Math.max(0, frame.nextOffer - now));
            for (Slot slot : frame.slots) delay = Math.min(delay, Math.max(0, slot.permitDeadline - now));
        }
        if (maintenance != null && !maintenance.disabled) delay = Math.min(delay, Math.max(0, Math.min(maintenance.nextOffer, maintenance.deadline) - now));
        if(readBank!=null)for(var slot:readBank.pending.values())if(slot.armed&&!slot.disabled&&!slot.completion.isDone())delay=Math.min(delay,Math.max(0,Math.min(slot.nextOffer,slot.deadline)-now));
        return Math.max(1, delay);
    }
    private void own(IOFactory factory) {
        RetentionBatchOwnerIOV3 io = null;
        try {
            io = factory.open(); captureTransport(io);started.complete(null);
            while (true) {
                synchronized (lock) { if (closing) break; }
                int work = io.poll(this::receive); long pause;
                if(clock.getAsLong()-transportObservedAtNs>=TimeUnit.SECONDS.toNanos(1))captureTransport(io);
                synchronized (lock) {
                    long now = clock.getAsLong(); build(now); work += offerMaintenance(io, now);work+=offerReadBank(io); work += offerFrames(io);
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
                stopReadBank(failure);
                for (Slot slot : slots) if (slot != null) {
                    if (slot.ordinal == 0) notSent(slot, "OWNER_CLOSED_BEFORE_ACCEPTED_OFFER");
                    else slot.completion.completeExceptionally(failure == null ? unresolved(slot, null) : new OwnerFailure(failure));
                }
            }
            if(io!=null)try{captureTransport(io);}catch(Throwable finalObservationError){synchronized(lock){if(failure==null)failure=finalObservationError;else failure.addSuppressed(finalObservationError);}}
            if (io != null) try { io.close(); } catch (Throwable closeError) {
                synchronized (lock) { if (failure == null) failure = closeError; else failure.addSuppressed(closeError); }
            }
        }
    }
    private void captureTransport(RetentionBatchOwnerIOV3 io){
        Map<String,Object> actual=Map.copyOf(io.observation());long now=clock.getAsLong();
        synchronized(lock){if(transportSamples.size()>=256)throw new IllegalStateException("bounded transport observation inventory exhausted");transportObservation=actual;transportObservedAtNs=now;var sample=new LinkedHashMap<String,Object>(actual);sample.put("observedAtMonotonicNs",now);transportSamples.add(Collections.unmodifiableMap(sample));}
    }
    public List<Map<String,Object>> transportSamples(){synchronized(lock){return List.copyOf(transportSamples);}}
    void wake() { LockSupport.unpark(owner); }
    public Map<String, Object> snapshot() {
        synchronized (lock) {
            var out = new LinkedHashMap<String, Object>();
            out.put("logicalWorkers", slots.length); out.put("taskQueueCapacityPerWorker", config.taskQueueCapacityPerWorker());
            out.put("externalTaskQueuePositions", (long) slots.length * config.taskQueueCapacityPerWorker());
            out.put("taskQueueOwnership", "external scheduler; this owner allocates no task FIFO");
            out.put("internalPendingCapacity", slots.length); out.put("maximumFrames", slots.length); out.put("batchCap", config.batchCap());
            out.put("flushDeadlineNs", config.flushDelayNs());
            out.put("ownerPollMaxParkNs", ownerPollMaxParkNs);
            out.put("ownerPollRequestedSleepOnly", true);out.put("ownerPollOsLatenessBounded", false);
            out.put("waitPolicy", ownerPollMaxParkNs==MAX_PARK_NS ? "deadline-aware park up to 1ms; OS lateness is not bounded" : "deadline-aware park up to 100us; OS lateness is not bounded");
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
            out.put("failureType", failure == null ? null : failure.getClass().getName()); out.put("transportObservation", transportObservation);out.put("transportObservedAtMonotonicNs",transportObservedAtNs);
            out.put("selectedReadWindow",selectedReadWindow);out.put("readOnlyHardCapacity",readOnlyHardCapacity);out.put("readBankOpen",readBank!=null);
            out.put("readOnlyRetained",readBank==null?0:readBank.pending.size());out.put("readOnlyInFlight",readBank==null?0:readBank.pending.values().stream().filter(slot->slot.armed&&!slot.completion.isDone()).count());out.put("readOnlyCompletedUnconsumed",readBank==null?0:readBank.pending.values().stream().filter(slot->slot.completion.isDone()&&!slot.completion.isCompletedExceptionally()).count());out.put("readOnlyRetainedHighWater",readOnlyRetainedHighWater);out.put("readOnlyInFlightHighWater",readOnlyInFlightHighWater);out.put("readOnlyOfferedAwaitingReplyHighWater",readOnlyOfferedInFlightHighWater);
            out.put("queuedReads",readBank==null?0:readBank.pending.values().stream().filter(s->!s.possiblyOffered).count());
            out.put("readOnlySubmitted",readOnlySubmitted);out.put("readOnlyCompleted",readOnlyCompleted);out.put("ignoredRetiredReadDuplicateOrLateReplies",readOnlyDuplicateOrLateReplies);
            out.put("retiredReadCorrelationCount",retiredReadCorrelations.size());out.put("retiredReadCorrelationCapacity",256);
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
