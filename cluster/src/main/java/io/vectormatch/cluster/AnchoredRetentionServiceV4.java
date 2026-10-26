package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;

import java.io.*;
import java.security.MessageDigest;
import java.util.*;

import static io.vectormatch.cluster.AnchoredRetentionWireV4.*;

/**
 * Opt-in anchored service, initially in-process. It is not wired
 * into ClusterNodeMain or the default MatchingClusteredService. No external I/O.
 */
public final class AnchoredRetentionServiceV4 {
    private static final int MAGIC = 0x564d5334, VERSION = 2;
    public static final int MAX_COMBINED_BYTES = 64 * 1024 * 1024;
    private static final int JOURNAL_OVERHEAD_RESERVE = 1024;
    private static final int ROLL_RESERVE = MAX_REQUEST_BYTES + JOURNAL_OVERHEAD_RESERVE;
    private static final String CONTRACT = "single-writer-anchored-retention-v4-prototype-1";

    public record Profile(String name, RetentionEngineV3.Profile core,
                          int outboxCapacity, int maxMaintenanceProducers,
                          int maintenanceCachePerProducer, int maxMaintenanceCachedResults,
                          int maxMaintenanceJournalRecords, long maxMaintenanceJournalBytes,
                          int maxCombinedSnapshotBytes) {
        public Profile {
            if (name == null || !name.matches("[A-Za-z0-9_.-]{1,64}"))
                throw new IllegalArgumentException("invalid anchored V4 service profile name");
            Objects.requireNonNull(core, "core");
            if (outboxCapacity < 1 || outboxCapacity > 1_000_000
                    || maxMaintenanceProducers < 1 || maxMaintenanceProducers > 10_000
                    || maintenanceCachePerProducer < 1 || maintenanceCachePerProducer > 10_000
                    || maxMaintenanceCachedResults < 1 || maxMaintenanceCachedResults > 10_000
                    || maxMaintenanceJournalRecords < 4 || maxMaintenanceJournalRecords > 10_000
                    || maxMaintenanceJournalBytes < 16384 || maxMaintenanceJournalBytes > MAX_COMBINED_BYTES
                    || maxCombinedSnapshotBytes < 4096 || maxCombinedSnapshotBytes > MAX_COMBINED_BYTES)
                throw new IllegalArgumentException("invalid anchored V4 service bounds");
            MatchingEngine.Limits limits = core.limits();
            long coreUpper = 8192L + limits.maxAccounts() * 64L + limits.maxProducers() * 256L
                    + limits.maxRetainedOrders() * 528L + limits.maxCachedResults() * 1024L
                    + core.maxPendingSerializedBytes();
            long combinedUpper = 16384L + coreUpper + outboxCapacity * 1024L
                    + maxMaintenanceProducers * 256L + maxMaintenanceCachedResults * 16384L + 8192L
                    + maxMaintenanceJournalBytes;
            if (combinedUpper > maxCombinedSnapshotBytes)
                throw new IllegalArgumentException("anchored V4 combined snapshot conservative budget exceeds profile");
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
        private final AnchoredRetentionServiceV4 owner;
        private final Request request;
        private final long applicationMutation;
        private final RetentionEngineV3.Admission core;
        private final long journalReserve;
        private boolean applied;
        private Anchor nextAnchor;
        private Admission(AnchoredRetentionServiceV4 owner, Request request,
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
    private record FrozenProducer(long highWater, List<Cached> cached) {
        private FrozenProducer { cached = List.copyOf(cached); }
    }
    /** Immutable before-roll projection. Its roll record remains the first journal suffix entry. */
    private final class Anchor {
        final long number, mutation, maintenanceCount, exported, coreMaintenance, archiveCut;
        final String previousAnchor, beforeJournalHead, archiveHash;
        final RetentionEngineV3.ArchiveAck latestArchive;
        final NavigableMap<String,FrozenProducer> registry;
        final byte[] canonical;
        final String hash;
        Anchor(long number,long mutation,long maintenanceCount,String previousAnchor,String beforeJournalHead,
               long exported,long coreMaintenance,long archiveCut,String archiveHash,
               RetentionEngineV3.ArchiveAck latestArchive,Map<String,FrozenProducer> registry) {
            this.number=number;this.mutation=mutation;this.maintenanceCount=maintenanceCount;
            this.previousAnchor=previousAnchor;this.beforeJournalHead=beforeJournalHead;
            this.exported=exported;this.coreMaintenance=coreMaintenance;this.archiveCut=archiveCut;this.archiveHash=archiveHash;
            this.latestArchive=latestArchive;this.registry=Collections.unmodifiableNavigableMap(new TreeMap<>(registry));
            canonical=encode(out->{
                out.writeUTF(scope.profileHash());out.writeUTF(lineageId);out.writeLong(number);out.writeLong(mutation);out.writeLong(maintenanceCount);
                out.writeUTF(previousAnchor);out.writeUTF(beforeJournalHead);out.writeLong(exported);out.writeLong(coreMaintenance);
                out.writeLong(archiveCut);out.writeUTF(archiveHash);out.writeBoolean(latestArchive!=null);
                if(latestArchive!=null)blob(out,encodeOperation(new ArchiveCommit(new MaintenanceIdentity("anchor",1),latestArchive)));
                out.writeInt(this.registry.size());
                for(var e:this.registry.entrySet()) {
                    out.writeUTF(e.getKey());out.writeLong(e.getValue().highWater);out.writeInt(e.getValue().cached.size());
                    for(Cached c:e.getValue().cached) {out.writeLong(c.applicationMutation);blob(out,encodeOperation(c.operation));writeResult(out,c.result);}
                }
            });
            if(canonical.length>anchorByteBound())throw new IllegalArgumentException("anchor exceeds bounded projection");
            hash=hash(canonical);
        }
    }

    private final Profile profile;
    private final String lineageId;
    private final Scope scope;
    private final Thread writer = Thread.currentThread();
    private RetentionEngineV3 core;
    private ReplicatedOutbox outbox;
    private long applicationMutation, journalBytes, maintenanceMutations;
    private Anchor anchor;
    private final NavigableMap<String, Producer> producers = new TreeMap<>();
    private final NavigableMap<Long, Cached> cacheByMutation = new TreeMap<>();
    private final List<JournalEntry> journal = new ArrayList<>();
    private final String journalGenesis, coreGenesis;
    private String journalHead;

    public AnchoredRetentionServiceV4(Profile profile, String lineageId) {
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
        this.anchor = new Anchor(0,0,0,journalGenesis,journalGenesis,0,0,0,coreGenesis,null,Map.of());
    }
    private void requireWriter() {
        if (Thread.currentThread() != writer) throw new IllegalStateException("anchored V4 service requires its owning writer thread");
    }
    private void requireScope(Request request) {
        Objects.requireNonNull(request, "request");
        if (!scope.equals(request.scope())) throw new IllegalArgumentException("anchored V4 service profile/lineage mismatch");
        // Direct in-process calls obey the same bounded wire contract as a future decoder path.
        AnchoredRetentionWireV4.encode(request);
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
        if(maintenanceMutations==Long.MAX_VALUE)throw new AdmissionRejectedException("V4 maintenance counter exhausted");
        if (!producers.containsKey(id.producerId()) && producers.size() >= profile.maxMaintenanceProducers())
            throw new AdmissionRejectedException("V3 permanent maintenance producer capacity reached");
        long reserve = encodeOperation(request.operation()).length + (long) JOURNAL_OVERHEAD_RESERVE;
        Producer existing=producers.get(id.producerId());
        boolean fresh=existing==null||id.requestSeq()>existing.highWater;
        if(fresh&&request.operation() instanceof JournalRoll roll&&matchesRollFrontier(roll)) {
            Admission admitted=new Admission(this,request,null,reserve);admitted.nextAnchor=captureAnchor();return admitted;
        }
        // Only a valid fresh roll can consume the reserved boundary slot and release the old prefix.
        if (journal.size() >= profile.maxMaintenanceJournalRecords()-1
                || reserve+ROLL_RESERVE > profile.maxMaintenanceJournalBytes() - journalBytes)
            throw new AdmissionRejectedException("anchored V4 journal headroom reserved for a verified roll");
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
            throw new IllegalStateException("stale, foreign, or consumed anchored V4 service admission");
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
        } else if(admission.nextAnchor!=null) {
            anchor=admission.nextAnchor;journal.clear();journalBytes=0;journalHead=anchor.beforeJournalHead;
            result=new MaintenanceResult(MaintenanceCode.APPLIED,null,outbox.exportedSeq(),"",false);
        } else result = performMaintenance(operation);
        long next = applicationMutation + 1;
        JournalEntry entry = new JournalEntry(next, operation, result, journalHead);
        if (entry.retainedBytes() > admission.journalReserve)
            throw new IllegalStateException("anchored V4 maintenance pre-mutation byte bound violated");
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
        maintenanceMutations++;
        applicationMutation = next;
        return reply(request.correlationId(), null, result);
    }
    private MaintenanceResult performMaintenance(Operation operation) {
        if(operation instanceof JournalRoll)return new MaintenanceResult(MaintenanceCode.REJECTED,null,
                outbox.exportedSeq(),"INVALID_JOURNAL_ROLL",false);
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
        if (operation instanceof JournalRoll roll) return roll.identity();
        throw new IllegalArgumentException("not a maintenance operation");
    }

    public void validateBatchReplyTextCompatibility() { requireWriter(); core.validateBatchReplyTextCompatibility(); }
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
    public long lifetimeMaintenanceMutations() { return maintenanceMutations; }
    public long anchorNumber() { return anchor.number; }
    public String anchorHash() { return anchor.hash; }
    public String journalHead() { return journalHead; }
    public byte[] anchorBytes() { requireWriter();return anchor.canonical.clone(); }
    public JournalRoll proposedRoll(MaintenanceIdentity identity) {
        requireWriter();return new JournalRoll(identity,applicationMutation,maintenanceMutations,anchor.hash,journalHead,
                core.archivedThroughCommandSeq(),outbox.exportedSeq());
    }
    private long anchorByteBound() {
        return 8192L+profile.maxMaintenanceProducers()*128L+profile.maxMaintenanceCachedResults()*8192L;
    }
    private boolean matchesRollFrontier(JournalRoll roll) {
        return !journal.isEmpty() && core.pendingCommandCount()==0 && outbox.size()==0
                && roll.beforeApplicationMutation()==applicationMutation && roll.beforeMaintenanceMutations()==maintenanceMutations
                && roll.previousAnchorHash().equals(anchor.hash) && roll.previousJournalHead().equals(journalHead)
                && roll.archivedThrough()==core.archivedThroughCommandSeq() && roll.exportedThrough()==outbox.exportedSeq();
    }
    private Anchor captureAnchor() {
        var frozen=new TreeMap<String,FrozenProducer>();
        producers.forEach((id,p)->frozen.put(id,new FrozenProducer(p.highWater,new ArrayList<>(p.cached.values()))));
        RetentionEngineV3.ArchiveAck latest=anchor.latestArchive;
        for(JournalEntry entry:journal)if(entry.operation instanceof ArchiveCommit a
                &&entry.result.code==MaintenanceCode.APPLIED&&!entry.result.replayed)latest=a.acknowledgement();
        return new Anchor(Math.addExact(anchor.number,1),applicationMutation,maintenanceMutations,anchor.hash,journalHead,
                outbox.exportedSeq(),core.maintenanceSeq(),core.archivedThroughCommandSeq(),core.archivedChainHash(),latest,frozen);
    }
    private Anchor readAnchor(byte[] bytes)throws IOException {
        try(var in=new DataInputStream(new ByteArrayInputStream(bytes))) {
            if(!in.readUTF().equals(scope.profileHash())||!in.readUTF().equals(lineageId))throw new IOException("wrong anchor scope");
            long number=in.readLong(),mutation=in.readLong(),count=in.readLong();String previous=in.readUTF(),head=in.readUTF();
            long exported=in.readLong(),maintenance=in.readLong(),cut=in.readLong();String archive=in.readUTF();
            RetentionEngineV3.ArchiveAck latest=null;
            if(in.readBoolean()) {
                Operation op=decodeOperation(readBlob(in,MAX_REQUEST_BYTES));
                if(!(op instanceof ArchiveCommit a)||!a.identity().equals(new MaintenanceIdentity("anchor",1)))throw new IOException("invalid anchor archive binding");
                latest=a.acknowledgement();
            }
            var registry=new TreeMap<String,FrozenProducer>();
            int size=count(in,profile.maxMaintenanceProducers());
            for(int i=0;i<size;i++) {
                String id=in.readUTF();long high=in.readLong();int retained=count(in,profile.maintenanceCachePerProducer());
                var values=new ArrayList<Cached>();
                for(int j=0;j<retained;j++)values.add(new Cached(in.readLong(),decodeOperation(readBlob(in,MAX_REQUEST_BYTES)),readResult(in)));
                if(registry.put(id,new FrozenProducer(high,values))!=null)throw new IOException("duplicate anchor producer");
            }
            Anchor restored=new Anchor(number,mutation,count,previous,head,exported,maintenance,cut,archive,latest,registry);
            if(in.available()!=0||!Arrays.equals(bytes,restored.canonical))throw new IOException("noncanonical anchor");return restored;
        }
    }
    private void validateAnchor() {
        if(anchor.number<0||anchor.mutation<0||anchor.maintenanceCount<0||anchor.maintenanceCount>anchor.mutation
                ||anchor.number>anchor.maintenanceCount||anchor.mutation>applicationMutation
                ||anchor.exported<0||anchor.exported>outbox.exportedSeq()||anchor.coreMaintenance<0||anchor.coreMaintenance>core.maintenanceSeq()
                ||anchor.archiveCut<0||anchor.archiveCut>core.archivedThroughCommandSeq()
                ||anchor.registry.size()>profile.maxMaintenanceProducers())throw new IllegalStateException("invalid anchor counters");
        for(String h:List.of(anchor.previousAnchor,anchor.beforeJournalHead,anchor.archiveHash))new Scope(h,"anchor-validation");
        if(anchor.number==0) {
            if(anchor.mutation!=0||anchor.maintenanceCount!=0||anchor.exported!=0||anchor.coreMaintenance!=0||anchor.archiveCut!=0
                    ||!anchor.previousAnchor.equals(journalGenesis)||!anchor.beforeJournalHead.equals(journalGenesis)
                    ||!anchor.archiveHash.equals(coreGenesis)||anchor.latestArchive!=null||!anchor.registry.isEmpty())
                throw new IllegalStateException("invalid genesis anchor");
        } else {
            if(anchor.maintenanceCount==0||journal.isEmpty()||anchor.archiveCut>anchor.mutation-anchor.maintenanceCount)
                throw new IllegalStateException("invalid rolled anchor boundary");
        }
        if(anchor.archiveCut==0) {
            if(anchor.latestArchive!=null||anchor.coreMaintenance!=0||!anchor.archiveHash.equals(coreGenesis))throw new IllegalStateException("invalid empty archive anchor");
        } else if(anchor.latestArchive==null||anchor.coreMaintenance==0||!anchor.latestArchive.profileHash().equals(profile.core().fingerprint())
                ||!anchor.latestArchive.lineageId().equals(lineageId)||anchor.latestArchive.throughCommandSeq()!=anchor.archiveCut
                ||!anchor.latestArchive.chainHash().equals(anchor.archiveHash))throw new IllegalStateException("invalid archived anchor binding");
        Set<Long> mutations=new HashSet<>();
        for(var entry:anchor.registry.entrySet()) {
            new MaintenanceIdentity(entry.getKey(),entry.getValue().highWater);long previous=0;
            if(entry.getValue().cached.size()>profile.maintenanceCachePerProducer())throw new IllegalStateException("anchor per-producer cache overflow");
            for(Cached cached:entry.getValue().cached) {
                MaintenanceIdentity id=identity(cached.operation);
                if(!id.producerId().equals(entry.getKey())||id.requestSeq()<=previous||id.requestSeq()>entry.getValue().highWater
                        ||cached.applicationMutation<=0||cached.applicationMutation>anchor.mutation||!mutations.add(cached.applicationMutation)
                        ||cached.result.replayed||cached.result.exportedEventSeq>anchor.exported
                        ||!Set.of(MaintenanceCode.APPLIED,MaintenanceCode.REJECTED).contains(cached.result.code))
                    throw new IllegalStateException("invalid anchored original maintenance cache");
                var c=cached.result.compaction;
                if(c!=null&&(c.maintenanceSeq()>anchor.coreMaintenance||c.archivedThroughCommandSeq()>anchor.archiveCut))throw new IllegalStateException("cached result ahead of anchor");
                validateResult(cached.result);previous=id.requestSeq();
            }
            if(previous!=0&&previous!=entry.getValue().highWater)throw new IllegalStateException("anchor high-water cache differs");
        }
        if(mutations.size()>profile.maxMaintenanceCachedResults())throw new IllegalStateException("anchor global cache overflow");
    }
    public List<JournalEntry> maintenanceJournal() { return List.copyOf(journal); }
    public RetentionEngineV3.ArchiveBatch archiveThrough(long through) { requireWriter(); return core.archiveThrough(through); }
    public MatchingEngine.AccountView account(long account) { return core.account(account); }
    public MatchingEngine.BookView book(int depth) { return core.book(depth); }
    public Optional<MatchingEngine.OrderView> hotOrder(long orderId) { return core.hotOrder(orderId); }
    public EventBatch fetchEvents(long fromSeq, int count) { requireWriter(); return outbox.fetchV3(fromSeq, count); }
    public byte[] coreSnapshot() { requireWriter(); return core.snapshot(); }

    public byte[] snapshot() {
        requireWriter(); checkInvariants();
        byte[] bytes = encode(out -> {
            out.writeInt(MAGIC); out.writeInt(VERSION); blob(out, profileBytes(profile)); out.writeUTF(lineageId);
            blob(out, core.snapshot()); outbox.write(out); out.writeLong(applicationMutation);
            out.writeLong(maintenanceMutations);blob(out,anchor.canonical);out.writeUTF(anchor.hash);
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
            throw new IllegalStateException("anchored V4 combined snapshot budget proof violated");
        return appendDigest(bytes);
    }
    public static AnchoredRetentionServiceV4 restore(byte[] snapshot, Profile expected, String lineageId) {
        Objects.requireNonNull(snapshot); Objects.requireNonNull(expected);
        if (snapshot.length < 44 || snapshot.length > expected.maxCombinedSnapshotBytes())
            throw new IllegalArgumentException("invalid anchored V4 service snapshot length");
        byte[] bytes = Arrays.copyOf(snapshot, snapshot.length - 32);
        if (!MessageDigest.isEqual(digest(bytes), Arrays.copyOfRange(snapshot, bytes.length, snapshot.length)))
            throw new IllegalArgumentException("anchored V4 service snapshot checksum mismatch");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes))) {
            if (in.readInt() != MAGIC || in.readInt() != VERSION
                    || !Arrays.equals(readBlob(in, 4096), profileBytes(expected)) || !in.readUTF().equals(lineageId))
                throw new IOException("anchored V4 service snapshot contract/profile/lineage mismatch");
            AnchoredRetentionServiceV4 restored = new AnchoredRetentionServiceV4(expected, lineageId);
            restored.core = RetentionEngineV3.restore(readBlob(in, RetentionEngineV3.MAX_SNAPSHOT_BYTES), expected.core(), lineageId);
            restored.outbox = ReplicatedOutbox.read(in, restored.core.lastEventSeq());
            if (restored.outbox.capacity() != expected.outboxCapacity()) throw new IOException("wrong V3 outbox capacity");
            restored.applicationMutation = in.readLong();
            restored.maintenanceMutations=in.readLong();
            restored.anchor=restored.readAnchor(readBlob(in,Math.toIntExact(restored.anchorByteBound())));
            if(!restored.anchor.hash.equals(in.readUTF()))throw new IOException("anchor hash mismatch");
            restored.journalHead=restored.anchor.beforeJournalHead;
            int producers = count(in, expected.maxMaintenanceProducers());
            for (int i = 0; i < producers; i++) {
                String id = in.readUTF(); new MaintenanceIdentity(id, 1);
                Producer producer = new Producer(); producer.highWater = in.readLong();
                if (producer.highWater <= 0 || restored.producers.put(id, producer) != null)
                    throw new IOException("invalid anchored V4 maintenance producer registry");
            }
            int cached = count(in, expected.maxMaintenanceCachedResults());
            for (int i = 0; i < cached; i++) {
                long mutation = in.readLong(); Operation op = decodeOperation(readBlob(in, MAX_REQUEST_BYTES));
                MaintenanceIdentity id = identity(op); MaintenanceResult result = readResult(in);
                Producer producer = restored.producers.get(id.producerId());
                Cached row = new Cached(mutation, op, result);
                if (producer == null || producer.cached.put(id.requestSeq(), row) != null
                        || restored.cacheByMutation.put(mutation, row) != null)
                    throw new IOException("invalid anchored V4 maintenance retry cache");
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
            if (in.available() != 0) throw new IOException("trailing anchored V4 service snapshot bytes");
            restored.checkInvariants();
            if (!Arrays.equals(restored.snapshot(), snapshot)) throw new IOException("noncanonical anchored V4 service snapshot");
            return restored;
        } catch (IOException | IllegalStateException invalid) {
            throw new IllegalArgumentException("invalid anchored V4 service snapshot", invalid);
        }
    }

    public void checkInvariants() {
        requireWriter(); core.checkInvariants();validateAnchor();
        if (outbox.capacity() != profile.outboxCapacity() || outbox.lastEventSeq() != core.lastEventSeq()
                || outbox.exportedSeq() < 0 || outbox.lastEventSeq() - outbox.exportedSeq() != outbox.size()
                || maintenanceMutations<0||maintenanceMutations>applicationMutation
                ||maintenanceMutations<anchor.maintenanceCount||maintenanceMutations-anchor.maintenanceCount!=journal.size()
                || core.lastCommandSeq() > applicationMutation - maintenanceMutations
                || producers.size() > profile.maxMaintenanceProducers() || cacheByMutation.size() > profile.maxMaintenanceCachedResults()
                || journal.size() > profile.maxMaintenanceJournalRecords() || journalBytes > profile.maxMaintenanceJournalBytes())
            throw new IllegalStateException("invalid anchored V4 combined counters/bounds");
        long previousMutation = anchor.mutation, bytes = 0, derivedExported = anchor.exported,
                derivedCoreMaintenance = anchor.coreMaintenance, derivedArchiveCut = anchor.archiveCut;
        String previousHash = anchor.beforeJournalHead, derivedArchiveHash = anchor.archiveHash;
        RetentionEngineV3.ArchiveAck latestEffectiveArchive = anchor.latestArchive;
        NavigableMap<String, Producer> derivedProducers = new TreeMap<>();
        NavigableMap<Long, Cached> derivedCache = new TreeMap<>();
        for(var e:anchor.registry.entrySet()) {
            Producer p=new Producer();p.highWater=e.getValue().highWater;
            for(Cached c:e.getValue().cached) {p.cached.put(identity(c.operation).requestSeq(),c);derivedCache.put(c.applicationMutation,c);}
            derivedProducers.put(e.getKey(),p);
        }
        for (JournalEntry entry : journal) {
            if (entry.applicationMutation <= previousMutation || entry.applicationMutation > applicationMutation
                    || !entry.previousHash.equals(previousHash)
                    || !entry.chainHash.equals(chain(previousHash, entry.canonicalBytes)))
                throw new IllegalStateException("invalid anchored V4 maintenance journal continuity");
            validateResult(entry.result);
            MaintenanceIdentity id = identity(entry.operation);
            Producer derived = derivedProducers.get(id.producerId());
            boolean fresh = derived == null || id.requestSeq() > derived.highWater;
            if (fresh) {
                if (entry.result.replayed || (entry.result.code != MaintenanceCode.APPLIED && entry.result.code != MaintenanceCode.REJECTED))
                    throw new IllegalStateException("invalid fresh maintenance journal result");
                if (entry.result.code == MaintenanceCode.REJECTED) {
                    String error = entry.operation instanceof ArchiveCommit ? "INVALID_ARCHIVE_COMMIT"
                            : entry.operation instanceof JournalRoll?"INVALID_JOURNAL_ROLL":"INVALID_EVENT_ACK";
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
                } else if(entry.operation instanceof EventAck ack) {
                    if (entry.result.compaction != null || ack.throughEventSeq() > core.lastEventSeq())
                        throw new IllegalStateException("invalid event ACK journal payload/result");
                    derivedExported = Math.max(derivedExported, ack.throughEventSeq());
                } else {
                    JournalRoll roll=(JournalRoll)entry.operation;
                    if(anchor.number==0||entry!=journal.getFirst()||entry.applicationMutation!=anchor.mutation+1
                            ||roll.beforeApplicationMutation()!=anchor.mutation||roll.beforeMaintenanceMutations()!=anchor.maintenanceCount
                            ||!roll.previousAnchorHash().equals(anchor.previousAnchor)||!roll.previousJournalHead().equals(anchor.beforeJournalHead)
                            ||roll.archivedThrough()!=anchor.archiveCut||roll.exportedThrough()!=anchor.exported||entry.result.compaction!=null)
                        throw new IllegalStateException("invalid anchored roll suffix record");
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
            throw new IllegalStateException("anchored V4 maintenance journal does not prove current caches/cursors");
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
            if (bytes.size() > MAX_COMBINED_BYTES) throw new IllegalArgumentException("anchored V4 service encoding exceeds whole-array cap");
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
