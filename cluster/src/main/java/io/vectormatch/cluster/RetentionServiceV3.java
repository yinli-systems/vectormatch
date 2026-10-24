package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;

import java.io.*;
import java.security.MessageDigest;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;

/**
 * Explicit in-process, single-writer V3 state-machine skeleton. It is not wired
 * into ClusterNodeMain or the default MatchingClusteredService. No external I/O.
 */
public final class RetentionServiceV3 {
    private static final int MAGIC = 0x564d5333, VERSION = 1;
    public static final int MAX_COMBINED_BYTES = 64 * 1024 * 1024;
    private static final int JOURNAL_OVERHEAD_RESERVE = 1024;
    private static final String CONTRACT = "single-writer-retention-service-v3-prototype-1";

    public record Profile(String name, RetentionEngineV3.Profile core,
                          int outboxCapacity, int maxMaintenanceProducers,
                          int maintenanceCachePerProducer, int maxMaintenanceCachedResults,
                          int maxMaintenanceJournalRecords, long maxMaintenanceJournalBytes,
                          int maxCombinedSnapshotBytes) {
        public Profile {
            if (name == null || !name.matches("[A-Za-z0-9_.-]{1,64}"))
                throw new IllegalArgumentException("invalid V3 service profile name");
            Objects.requireNonNull(core, "core");
            if (outboxCapacity < 1 || outboxCapacity > 1_000_000
                    || maxMaintenanceProducers < 1 || maxMaintenanceProducers > 10_000
                    || maintenanceCachePerProducer < 1 || maintenanceCachePerProducer > 10_000
                    || maxMaintenanceCachedResults < 1 || maxMaintenanceCachedResults > 10_000
                    || maxMaintenanceJournalRecords < 1 || maxMaintenanceJournalRecords > 10_000
                    || maxMaintenanceJournalBytes < 4096 || maxMaintenanceJournalBytes > MAX_COMBINED_BYTES
                    || maxCombinedSnapshotBytes < 4096 || maxCombinedSnapshotBytes > MAX_COMBINED_BYTES)
                throw new IllegalArgumentException("invalid V3 service bounds");
            MatchingEngine.Limits limits = core.limits();
            long coreUpper = 8192L + limits.maxAccounts() * 64L + limits.maxProducers() * 256L
                    + limits.maxRetainedOrders() * 528L + limits.maxCachedResults() * 1024L
                    + core.maxPendingSerializedBytes();
            long combinedUpper = 16384L + coreUpper + outboxCapacity * 1024L
                    + maxMaintenanceProducers * 128L + maxMaintenanceCachedResults * 8192L
                    + maxMaintenanceJournalBytes;
            if (combinedUpper > maxCombinedSnapshotBytes)
                throw new IllegalArgumentException("V3 combined snapshot conservative budget exceeds profile");
        }
        public String fingerprint() { return hash(profileBytes(this)); }
    }

    public enum MaintenanceCode { APPLIED, REJECTED, IDEMPOTENCY_CONFLICT, STALE_SEQUENCE }
    public record MaintenanceResult(MaintenanceCode code, RetentionEngineV3.CompactionResult compaction,
                                    long exportedEventSeq, String error, boolean replayed) {
        public MaintenanceResult {
            Objects.requireNonNull(code); Objects.requireNonNull(error);
            if (exportedEventSeq < 0 || error.length() > 128)
                throw new IllegalArgumentException("invalid maintenance result");
        }
        MaintenanceResult replay() { return new MaintenanceResult(code, compaction, exportedEventSeq, error, true); }
    }
    public record Reply(long correlationId, long applicationMutation, long businessSeq,
                        long coreMaintenanceSeq, long acceptedPlaceCount,
                        MatchingEngine.Execution execution, MaintenanceResult maintenance) {}

    /** Admission failure is nonmutating, including the application-mutation counter. */
    public static final class AdmissionRejectedException extends IllegalStateException {
        private static final long serialVersionUID = 1L;
        AdmissionRejectedException(String reason) { super(reason); }
    }
    public static final class Admission {
        private final RetentionServiceV3 owner;
        private final Request request;
        private final long applicationMutation;
        private final RetentionEngineV3.Admission core;
        private final long journalReserve;
        private boolean applied;
        private Admission(RetentionServiceV3 owner, Request request,
                          RetentionEngineV3.Admission core, long reserve) {
            this.owner = owner; this.request = request; this.core = core;
            this.applicationMutation = owner.applicationMutation; this.journalReserve = reserve;
        }
    }
    public static final class JournalEntry {
        private final long applicationMutation;
        private final Operation operation;
        private final MaintenanceResult result;
        private final String previousHash, chainHash;
        private final byte[] canonicalBytes;
        private JournalEntry(long mutation, Operation operation, MaintenanceResult result, String previousHash) {
            this.applicationMutation = mutation; this.operation = operation; this.result = result;
            this.previousHash = previousHash;
            canonicalBytes = encode(out -> {
                out.writeLong(mutation); blob(out, encodeOperation(operation)); writeResult(out, result);
            });
            chainHash = chain(previousHash, canonicalBytes);
        }
        public long applicationMutation() { return applicationMutation; }
        public Operation operation() { return operation; }
        public MaintenanceResult result() { return result; }
        public String previousHash() { return previousHash; }
        public String chainHash() { return chainHash; }
        public byte[] canonicalBytes() { return canonicalBytes.clone(); }
        long retainedBytes() { return canonicalBytes.length + 4L + 2L * (2 + 64); }
    }
    private static final class Producer {
        long highWater;
        final NavigableMap<Long, Cached> cached = new TreeMap<>();
    }
    private record Cached(long applicationMutation, Operation operation, MaintenanceResult result) {}

    private final Profile profile;
    private final String lineageId;
    private final Scope scope;
    private final Thread writer = Thread.currentThread();
    private RetentionEngineV3 core;
    private ReplicatedOutbox outbox;
    private long applicationMutation, journalBytes;
    private final NavigableMap<String, Producer> producers = new TreeMap<>();
    private final NavigableMap<Long, Cached> cacheByMutation = new TreeMap<>();
    private final List<JournalEntry> journal = new ArrayList<>();
    private final String journalGenesis, coreGenesis;
    private String journalHead;

    public RetentionServiceV3(Profile profile, String lineageId) {
        this.profile = Objects.requireNonNull(profile);
        this.scope = new Scope(profile.fingerprint(), lineageId);
        this.lineageId = lineageId;
        this.core = new RetentionEngineV3(profile.core(), lineageId);
        this.outbox = new ReplicatedOutbox(profile.outboxCapacity());
        this.coreGenesis = core.archivedChainHash();
        this.journalGenesis = hash(encode(out -> {
            out.writeUTF(CONTRACT); out.writeUTF(scope.profileHash()); out.writeUTF(lineageId);
        }));
        this.journalHead = journalGenesis;
    }
    private void requireWriter() {
        if (Thread.currentThread() != writer) throw new IllegalStateException("V3 service requires its owning writer thread");
    }
    private void requireScope(Request request) {
        Objects.requireNonNull(request, "request");
        if (!scope.equals(request.scope())) throw new IllegalArgumentException("V3 service profile/lineage mismatch");
        // Direct in-process calls obey the same bounded wire contract as a future decoder path.
        RetentionWireV3.encode(request);
    }

    /** Joint core-history/outbox/journal admission; never mutates any state. */
    public Admission previewAdmission(Request request) {
        requireWriter(); requireScope(request);
        if (request.operation() instanceof Position)
            throw new IllegalArgumentException("position is read-only, not an application mutation");
        if (applicationMutation == Long.MAX_VALUE)
            throw new AdmissionRejectedException("V3 application-mutation counter exhausted");
        if (request.operation() instanceof Business business) {
            RetentionEngineV3.Admission reservation = core.previewAdmission(business.command());
            if (!outbox.hasCapacity(reservation.eventCount())) throw new AdmissionRejectedException("V3 outbox full");
            return new Admission(this, request, reservation, 0);
        }
        MaintenanceIdentity id = identity(request.operation());
        if (!producers.containsKey(id.producerId()) && producers.size() >= profile.maxMaintenanceProducers())
            throw new AdmissionRejectedException("V3 permanent maintenance producer capacity reached");
        long reserve = encodeOperation(request.operation()).length + (long) JOURNAL_OVERHEAD_RESERVE;
        if (journal.size() >= profile.maxMaintenanceJournalRecords()
                || reserve > profile.maxMaintenanceJournalBytes() - journalBytes)
            throw new AdmissionRejectedException("V3 maintenance journal full; no automatic eviction");
        return new Admission(this, request, null, reserve);
    }

    public Reply handle(Request request) {
        requireWriter(); requireScope(request);
        if (request.operation() instanceof Position) return reply(request.correlationId(), null, null);
        return apply(previewAdmission(request));
    }
    public Reply apply(Admission admission) {
        requireWriter(); Objects.requireNonNull(admission);
        if (admission.owner != this || admission.applied || admission.applicationMutation != applicationMutation)
            throw new IllegalStateException("stale, foreign, or consumed V3 service admission");
        admission.applied = true;
        Request request = admission.request;
        if (request.operation() instanceof Business) {
            MatchingEngine.Execution result = core.apply(admission.core);
            outbox.append(result.events());
            applicationMutation++;
            return reply(request.correlationId(), result, null);
        }
        Operation operation = request.operation();
        MaintenanceIdentity id = identity(operation);
        Producer producer = producers.get(id.producerId());
        MaintenanceResult result;
        boolean fresh = producer == null || id.requestSeq() > producer.highWater;
        if (!fresh) {
            Cached cached = producer.cached.get(id.requestSeq());
            if (cached == null) result = new MaintenanceResult(MaintenanceCode.STALE_SEQUENCE, null,
                    outbox.exportedSeq(), "sequence no longer retained; not executed", false);
            else if (!cached.operation.equals(operation))
                result = new MaintenanceResult(MaintenanceCode.IDEMPOTENCY_CONFLICT, null,
                        outbox.exportedSeq(), "same maintenance identity has different payload", false);
            else result = cached.result.replay();
        } else result = performMaintenance(operation);
        long next = applicationMutation + 1;
        JournalEntry entry = new JournalEntry(next, operation, result, journalHead);
        if (entry.retainedBytes() > admission.journalReserve)
            throw new IllegalStateException("V3 maintenance pre-mutation byte bound violated");
        if (fresh) {
            if (producer == null) { producer = new Producer(); producers.put(id.producerId(), producer); }
            producer.highWater = id.requestSeq();
            Cached cached = new Cached(next, operation, result);
            producer.cached.put(id.requestSeq(), cached); cacheByMutation.put(next, cached);
            while (producer.cached.size() > profile.maintenanceCachePerProducer()) {
                Cached removed = producer.cached.pollFirstEntry().getValue(); cacheByMutation.remove(removed.applicationMutation);
            }
            while (cacheByMutation.size() > profile.maxMaintenanceCachedResults()) {
                Cached removed = cacheByMutation.pollFirstEntry().getValue();
                MaintenanceIdentity removedId = identity(removed.operation);
                producers.get(removedId.producerId()).cached.remove(removedId.requestSeq());
            }
        }
        journal.add(entry); journalBytes += entry.retainedBytes(); journalHead = entry.chainHash;
        applicationMutation = next;
        return reply(request.correlationId(), null, result);
    }
    private MaintenanceResult performMaintenance(Operation operation) {
        try {
            if (operation instanceof ArchiveCommit archive)
                return new MaintenanceResult(MaintenanceCode.APPLIED, core.compactThrough(archive.acknowledgement()),
                        outbox.exportedSeq(), "", false);
            EventAck ack = (EventAck) operation;
            return new MaintenanceResult(MaintenanceCode.APPLIED, null,
                    outbox.acknowledge(ack.throughEventSeq()), "", false);
        } catch (IllegalArgumentException invalid) {
            return new MaintenanceResult(MaintenanceCode.REJECTED, null, outbox.exportedSeq(),
                    operation instanceof ArchiveCommit ? "INVALID_ARCHIVE_COMMIT" : "INVALID_EVENT_ACK", false);
        }
    }
    private Reply reply(long correlation, MatchingEngine.Execution execution, MaintenanceResult maintenance) {
        return new Reply(correlation, applicationMutation, core.lastCommandSeq(), core.maintenanceSeq(),
                core.acceptedPlaceCount(), execution, maintenance);
    }
    static MaintenanceIdentity identity(Operation operation) {
        if (operation instanceof ArchiveCommit archive) return archive.identity();
        if (operation instanceof EventAck ack) return ack.identity();
        throw new IllegalArgumentException("not a maintenance operation");
    }

    public Scope scope() { return scope; }
    public Profile profile() { return profile; }
    public String lineageId() { return lineageId; }
    public long applicationMutation() { return applicationMutation; }
    public long businessSeq() { return core.lastCommandSeq(); }
    public long eventSeq() { return core.lastEventSeq(); }
    public long marketSeq() { return core.lastMarketSeq(); }
    public long coreMaintenanceSeq() { return core.maintenanceSeq(); }
    public long archivedThroughCommandSeq() { return core.archivedThroughCommandSeq(); }
    public long acceptedPlaceCount() { return core.acceptedPlaceCount(); }
    public long exportedEventSeq() { return outbox.exportedSeq(); }
    public int outboxSize() { return outbox.size(); }
    public int pendingHistoryCount() { return core.pendingCommandCount(); }
    public long maintenanceHighWater(String producer) { Producer p = producers.get(producer); return p == null ? 0 : p.highWater; }
    public int maintenanceProducerCount() { return producers.size(); }
    public int maintenanceCacheSize() { return cacheByMutation.size(); }
    public long maintenanceJournalBytes() { return journalBytes; }
    public List<JournalEntry> maintenanceJournal() { return List.copyOf(journal); }
    public RetentionEngineV3.ArchiveBatch archiveThrough(long through) { requireWriter(); return core.archiveThrough(through); }
    public MatchingEngine.AccountView account(long account) { return core.account(account); }
    public MatchingEngine.BookView book(int depth) { return core.book(depth); }
    public Optional<MatchingEngine.OrderView> hotOrder(long orderId) { return core.hotOrder(orderId); }
    public EventBatch fetchEvents(long fromSeq, int count) { requireWriter(); return outbox.fetch(fromSeq, count); }
    public byte[] coreSnapshot() { requireWriter(); return core.snapshot(); }

    public byte[] snapshot() {
        requireWriter(); checkInvariants();
        byte[] bytes = encode(out -> {
            out.writeInt(MAGIC); out.writeInt(VERSION); blob(out, profileBytes(profile)); out.writeUTF(lineageId);
            blob(out, core.snapshot()); outbox.write(out); out.writeLong(applicationMutation);
            out.writeInt(producers.size());
            for (Map.Entry<String, Producer> e : producers.entrySet()) { out.writeUTF(e.getKey()); out.writeLong(e.getValue().highWater); }
            out.writeInt(cacheByMutation.size());
            for (Cached cached : cacheByMutation.values()) {
                out.writeLong(cached.applicationMutation); blob(out, encodeOperation(cached.operation)); writeResult(out, cached.result);
            }
            out.writeInt(journal.size());
            for (JournalEntry entry : journal) {
                blob(out, entry.canonicalBytes); out.writeUTF(entry.previousHash); out.writeUTF(entry.chainHash);
            }
        });
        if ((long) bytes.length + 32 > profile.maxCombinedSnapshotBytes())
            throw new IllegalStateException("V3 combined snapshot budget proof violated");
        return appendDigest(bytes);
    }
    public static RetentionServiceV3 restore(byte[] snapshot, Profile expected, String lineageId) {
        Objects.requireNonNull(snapshot); Objects.requireNonNull(expected);
        if (snapshot.length < 44 || snapshot.length > expected.maxCombinedSnapshotBytes())
            throw new IllegalArgumentException("invalid V3 service snapshot length");
        byte[] bytes = Arrays.copyOf(snapshot, snapshot.length - 32);
        if (!MessageDigest.isEqual(digest(bytes), Arrays.copyOfRange(snapshot, bytes.length, snapshot.length)))
            throw new IllegalArgumentException("V3 service snapshot checksum mismatch");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes))) {
            if (in.readInt() != MAGIC || in.readInt() != VERSION
                    || !Arrays.equals(readBlob(in, 4096), profileBytes(expected)) || !in.readUTF().equals(lineageId))
                throw new IOException("V3 service snapshot contract/profile/lineage mismatch");
            RetentionServiceV3 restored = new RetentionServiceV3(expected, lineageId);
            restored.core = RetentionEngineV3.restore(readBlob(in, RetentionEngineV3.MAX_SNAPSHOT_BYTES), expected.core(), lineageId);
            restored.outbox = ReplicatedOutbox.read(in, restored.core.lastEventSeq());
            if (restored.outbox.capacity() != expected.outboxCapacity()) throw new IOException("wrong V3 outbox capacity");
            restored.applicationMutation = in.readLong();
            int producers = count(in, expected.maxMaintenanceProducers());
            for (int i = 0; i < producers; i++) {
                String id = in.readUTF(); new MaintenanceIdentity(id, 1);
                Producer producer = new Producer(); producer.highWater = in.readLong();
                if (producer.highWater <= 0 || restored.producers.put(id, producer) != null)
                    throw new IOException("invalid V3 maintenance producer registry");
            }
            int cached = count(in, expected.maxMaintenanceCachedResults());
            for (int i = 0; i < cached; i++) {
                long mutation = in.readLong(); Operation op = decodeOperation(readBlob(in, MAX_REQUEST_BYTES));
                MaintenanceIdentity id = identity(op); MaintenanceResult result = readResult(in);
                Producer producer = restored.producers.get(id.producerId());
                Cached row = new Cached(mutation, op, result);
                if (producer == null || producer.cached.put(id.requestSeq(), row) != null
                        || restored.cacheByMutation.put(mutation, row) != null)
                    throw new IOException("invalid V3 maintenance retry cache");
            }
            int records = count(in, expected.maxMaintenanceJournalRecords());
            for (int i = 0; i < records; i++) {
                byte[] payload = readBlob(in, MAX_REQUEST_BYTES + JOURNAL_OVERHEAD_RESERVE);
                JournalEntry entry;
                try (DataInputStream row = new DataInputStream(new ByteArrayInputStream(payload))) {
                    long mutation = row.readLong(); Operation op = decodeOperation(readBlob(row, MAX_REQUEST_BYTES));
                    identity(op); MaintenanceResult result = readResult(row);
                    entry = new JournalEntry(mutation, op, result, in.readUTF());
                    if (row.available() != 0 || !Arrays.equals(payload, entry.canonicalBytes)
                            || !entry.chainHash.equals(in.readUTF())) throw new IOException("invalid V3 journal record hash");
                }
                restored.journal.add(entry); restored.journalBytes += entry.retainedBytes(); restored.journalHead = entry.chainHash;
                if (restored.journalBytes > expected.maxMaintenanceJournalBytes()) throw new IOException("V3 journal bytes exceed profile");
            }
            if (in.available() != 0) throw new IOException("trailing V3 service snapshot bytes");
            restored.checkInvariants();
            if (!Arrays.equals(restored.snapshot(), snapshot)) throw new IOException("noncanonical V3 service snapshot");
            return restored;
        } catch (IOException | IllegalStateException invalid) {
            throw new IllegalArgumentException("invalid V3 service snapshot", invalid);
        }
    }

    public void checkInvariants() {
        requireWriter(); core.checkInvariants();
        if (outbox.capacity() != profile.outboxCapacity() || outbox.lastEventSeq() != core.lastEventSeq()
                || outbox.exportedSeq() < 0 || outbox.lastEventSeq() - outbox.exportedSeq() != outbox.size()
                || applicationMutation < journal.size() || core.lastCommandSeq() > applicationMutation - journal.size()
                || producers.size() > profile.maxMaintenanceProducers() || cacheByMutation.size() > profile.maxMaintenanceCachedResults()
                || journal.size() > profile.maxMaintenanceJournalRecords() || journalBytes > profile.maxMaintenanceJournalBytes())
            throw new IllegalStateException("invalid V3 combined counters/bounds");
        long previousMutation = 0, bytes = 0, derivedExported = 0, derivedCoreMaintenance = 0, derivedArchiveCut = 0;
        String previousHash = journalGenesis, derivedArchiveHash = coreGenesis;
        RetentionEngineV3.ArchiveAck latestEffectiveArchive = null;
        NavigableMap<String, Producer> derivedProducers = new TreeMap<>();
        NavigableMap<Long, Cached> derivedCache = new TreeMap<>();
        for (JournalEntry entry : journal) {
            if (entry.applicationMutation <= previousMutation || entry.applicationMutation > applicationMutation
                    || !entry.previousHash.equals(previousHash)
                    || !entry.chainHash.equals(chain(previousHash, entry.canonicalBytes)))
                throw new IllegalStateException("invalid V3 maintenance journal continuity");
            validateResult(entry.result);
            MaintenanceIdentity id = identity(entry.operation);
            Producer derived = derivedProducers.get(id.producerId());
            boolean fresh = derived == null || id.requestSeq() > derived.highWater;
            if (fresh) {
                if (entry.result.replayed || (entry.result.code != MaintenanceCode.APPLIED && entry.result.code != MaintenanceCode.REJECTED))
                    throw new IllegalStateException("invalid fresh maintenance journal result");
                if (entry.result.code == MaintenanceCode.REJECTED) {
                    String error = entry.operation instanceof ArchiveCommit ? "INVALID_ARCHIVE_COMMIT" : "INVALID_EVENT_ACK";
                    if (entry.result.compaction != null || !entry.result.error.equals(error))
                        throw new IllegalStateException("invalid rejected maintenance payload/result");
                } else if (!entry.result.error.isEmpty()) {
                    throw new IllegalStateException("successful maintenance has an error");
                } else if (entry.operation instanceof ArchiveCommit archive) {
                    RetentionEngineV3.CompactionResult c = entry.result.compaction;
                    RetentionEngineV3.ArchiveAck ack = archive.acknowledgement();
                    if (c == null || !ack.profileHash().equals(profile.core().fingerprint())
                            || !ack.lineageId().equals(lineageId) || c.archivedThroughCommandSeq() != ack.throughCommandSeq())
                        throw new IllegalStateException("archive journal payload/result binding differs");
                    if (c.replayed()) {
                        if (!ack.equals(latestEffectiveArchive) || c.maintenanceSeq() != derivedCoreMaintenance
                                || c.removedTerminalOrders() != 0 || c.releasedHistoryCommands() != 0)
                            throw new IllegalStateException("invalid latest archive ACK no-op journal");
                    } else {
                        if (c.maintenanceSeq() != derivedCoreMaintenance + 1 || ack.firstCommandSeq() != derivedArchiveCut + 1
                                || !ack.previousChainHash().equals(derivedArchiveHash)
                                || c.releasedHistoryCommands() != ack.throughCommandSeq() - derivedArchiveCut)
                            throw new IllegalStateException("archive journal cursor discontinuity");
                        derivedCoreMaintenance++; derivedArchiveCut = ack.throughCommandSeq();
                        derivedArchiveHash = ack.chainHash(); latestEffectiveArchive = ack;
                    }
                } else {
                    EventAck ack = (EventAck) entry.operation;
                    if (entry.result.compaction != null || ack.throughEventSeq() > core.lastEventSeq())
                        throw new IllegalStateException("invalid event ACK journal payload/result");
                    derivedExported = Math.max(derivedExported, ack.throughEventSeq());
                }
                if (entry.result.exportedEventSeq != derivedExported)
                    throw new IllegalStateException("maintenance journal projection cursor discontinuity");
                if (derived == null) { derived = new Producer(); derivedProducers.put(id.producerId(), derived); }
                derived.highWater = id.requestSeq();
                Cached cached = new Cached(entry.applicationMutation, entry.operation, entry.result);
                derived.cached.put(id.requestSeq(), cached); derivedCache.put(entry.applicationMutation, cached);
                while (derived.cached.size() > profile.maintenanceCachePerProducer()) {
                    Cached removed = derived.cached.pollFirstEntry().getValue(); derivedCache.remove(removed.applicationMutation);
                }
                while (derivedCache.size() > profile.maxMaintenanceCachedResults()) {
                    Cached removed = derivedCache.pollFirstEntry().getValue(); MaintenanceIdentity removedId = identity(removed.operation);
                    derivedProducers.get(removedId.producerId()).cached.remove(removedId.requestSeq());
                }
            } else {
                Cached cached = derived.cached.get(id.requestSeq());
                MaintenanceResult expected;
                if (cached == null) expected = new MaintenanceResult(MaintenanceCode.STALE_SEQUENCE, null,
                        derivedExported, "sequence no longer retained; not executed", false);
                else if (!cached.operation.equals(entry.operation)) expected = new MaintenanceResult(MaintenanceCode.IDEMPOTENCY_CONFLICT,
                        null, derivedExported, "same maintenance identity has different payload", false);
                else expected = cached.result.replay();
                if (!expected.equals(entry.result)) throw new IllegalStateException("maintenance replay/conflict/stale journal differs");
            }
            previousMutation = entry.applicationMutation; previousHash = entry.chainHash; bytes += entry.retainedBytes();
        }
        if (!previousHash.equals(journalHead) || bytes != journalBytes || derivedProducers.size() != producers.size()
                || derivedExported != outbox.exportedSeq() || derivedCoreMaintenance != core.maintenanceSeq()
                || derivedArchiveCut != core.archivedThroughCommandSeq() || !derivedArchiveHash.equals(core.archivedChainHash())
                || !derivedCache.equals(cacheByMutation))
            throw new IllegalStateException("V3 maintenance journal does not prove current caches/cursors");
        for (Map.Entry<String, Producer> p : producers.entrySet()) {
            Producer derived = derivedProducers.get(p.getKey());
            if (derived == null || derived.highWater != p.getValue().highWater || !derived.cached.equals(p.getValue().cached))
                throw new IllegalStateException("invalid V3 permanent maintenance high-water/cache");
        }
    }
    private void validateResult(MaintenanceResult result) {
        if (result.exportedEventSeq > outbox.exportedSeq()) throw new IllegalStateException("maintenance event ACK anchor exceeds current cursor");
        RetentionEngineV3.CompactionResult c = result.compaction;
        if (c != null && (c.maintenanceSeq() <= 0 || c.maintenanceSeq() > core.maintenanceSeq()
                || c.archivedThroughCommandSeq() <= 0 || c.archivedThroughCommandSeq() > core.archivedThroughCommandSeq()
                || c.removedTerminalOrders() < 0 || c.removedTerminalOrders() > profile.core().limits().maxRetainedOrders()
                || c.releasedHistoryCommands() < 0 || c.releasedHistoryCommands() > profile.core().maxPendingCommands()))
            throw new IllegalStateException("invalid maintenance compaction result anchor");
    }

    private static byte[] profileBytes(Profile p) {
        return encode(out -> {
            out.writeUTF(CONTRACT); out.writeUTF(p.name()); out.writeUTF(p.core().fingerprint());
            out.writeInt(p.outboxCapacity()); out.writeInt(p.maxMaintenanceProducers());
            out.writeInt(p.maintenanceCachePerProducer()); out.writeInt(p.maxMaintenanceCachedResults());
            out.writeInt(p.maxMaintenanceJournalRecords()); out.writeLong(p.maxMaintenanceJournalBytes());
            out.writeInt(p.maxCombinedSnapshotBytes());
        });
    }
    private static void writeResult(DataOutputStream out, MaintenanceResult result) throws IOException {
        out.writeByte(result.code.ordinal()); out.writeBoolean(result.replayed); out.writeLong(result.exportedEventSeq);
        out.writeUTF(result.error); out.writeBoolean(result.compaction != null);
        if (result.compaction != null) {
            RetentionEngineV3.CompactionResult c = result.compaction;
            out.writeLong(c.maintenanceSeq()); out.writeLong(c.archivedThroughCommandSeq());
            out.writeInt(c.removedTerminalOrders()); out.writeInt(c.releasedHistoryCommands()); out.writeBoolean(c.replayed());
        }
    }
    private static MaintenanceResult readResult(DataInputStream in) throws IOException {
        int code = in.readUnsignedByte(); if (code >= MaintenanceCode.values().length) throw new IOException("invalid maintenance result code");
        boolean replayed = flag(in); long exported = in.readLong(); String error = in.readUTF();
        RetentionEngineV3.CompactionResult compaction = null;
        if (flag(in)) compaction = new RetentionEngineV3.CompactionResult(in.readLong(), in.readLong(), in.readInt(), in.readInt(), flag(in));
        return new MaintenanceResult(MaintenanceCode.values()[code], compaction, exported, error, replayed);
    }
    private static boolean flag(DataInputStream in) throws IOException {
        int value = in.readUnsignedByte(); if (value > 1) throw new IOException("noncanonical boolean"); return value == 1;
    }
    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }
    private static byte[] encode(Writer writer) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream(); DataOutputStream out = new DataOutputStream(bytes);
            writer.write(out); out.flush();
            if (bytes.size() > MAX_COMBINED_BYTES) throw new IllegalArgumentException("V3 service encoding exceeds whole-array cap");
            return bytes.toByteArray();
        } catch (IOException impossible) { throw new UncheckedIOException(impossible); }
    }
    private static void blob(DataOutputStream out, byte[] bytes) throws IOException { out.writeInt(bytes.length); out.write(bytes); }
    private static byte[] readBlob(DataInputStream in, int max) throws IOException {
        int length = in.readInt(); if (length < 0 || length > max || length > in.available()) throw new IOException("invalid bounded V3 blob length");
        return in.readNBytes(length);
    }
    private static int count(DataInputStream in, int max) throws IOException {
        int count = in.readInt(); if (count < 0 || count > max) throw new IOException("invalid bounded V3 collection count"); return count;
    }
    private static byte[] digest(byte[] bytes) { return ClusterStateSnapshot.digest(bytes); }
    private static String hash(byte[] bytes) { return HexFormat.of().formatHex(digest(bytes)); }
    private static String chain(String previousHash, byte[] bytes) {
        byte[] previous = HexFormat.of().parseHex(previousHash); byte[] combined = Arrays.copyOf(previous, previous.length + bytes.length);
        System.arraycopy(bytes, 0, combined, previous.length, bytes.length); return hash(combined);
    }
    private static byte[] appendDigest(byte[] bytes) {
        byte[] result = Arrays.copyOf(bytes, bytes.length + 32); System.arraycopy(digest(bytes), 0, result, bytes.length, 32); return result;
    }
}
