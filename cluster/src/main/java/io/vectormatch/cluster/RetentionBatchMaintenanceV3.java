package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;

import java.io.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Finite functional maintenance coordinator. No arrival scheduler or background capacity claim. */
public final class RetentionBatchMaintenanceV3 implements AutoCloseable {
    private static final Duration RPC_TIMEOUT=Duration.ofSeconds(20);
    public static final int COMMAND_CUT=3072;
    /** Retained across the smoke's definite owner stop/node restart; not persistent client recovery. */
    public static final class RunBudget {
        private final RetentionServiceV3.Profile profile;
        private long reservedJournalRecords,reservedJournalBytes,archiveSeq,eventSeq;
        private RetentionEngineV3.ArchiveAck lastArchive;
        private long lastEvent;
        public RunBudget(RetentionServiceV3.Profile profile){this.profile=Objects.requireNonNull(profile);}
        MaintenanceIdentity reserve(boolean archive,java.util.function.Function<MaintenanceIdentity,Operation> operation){
            long seq=archive?archiveSeq+1:eventSeq+1;MaintenanceIdentity id=new MaintenanceIdentity(archive?"archive":"projector",seq);
            long bytes=4L*(RetentionWireV3.encodeOperation(operation.apply(id)).length+1024L);
            if(reservedJournalRecords>Math.min(1024,profile.maxMaintenanceJournalRecords())-4L
                    ||bytes>profile.maxMaintenanceJournalBytes()-reservedJournalBytes)
                throw new IllegalStateException("finite run journal retry budget exhausted before ACK offer");
            reservedJournalRecords+=4;reservedJournalBytes+=bytes;
            if(archive)archiveSeq=seq;else eventSeq=seq;return id;
        }
        public long archivedThrough(){return lastArchive==null?0:lastArchive.throughCommandSeq();}
        public Map<String,Object> snapshot(){return Map.of("reservedJournalRecords",reservedJournalRecords,"reservedJournalBytes",reservedJournalBytes,
                "recordLimit",Math.min(1024,profile.maxMaintenanceJournalRecords()),"byteLimit",profile.maxMaintenanceJournalBytes(),
                "maximumPossibleOffersPerMutatingRpc",4,"archiveIdentities",archiveSeq,"eventIdentities",eventSeq,"archivedThrough",archivedThrough(),"exportedEventSeq",lastEvent);}
    }
    public record Cycle(RetentionEngineV3.ArchiveAck acknowledgement,Path archiveFile,Path eventFile,
                        List<RetentionEngineV3.HistoryEntry> entries,long throughEventSeq){
        public Cycle{entries=List.copyOf(entries);}
    }
    private final RetentionBatchOwnerV3 owner;
    private final RetentionDurableWriterV3 writer;
    private final RetentionServiceV3.Profile profile;
    private final String lineage;
    private final Scope scope;
    private final RunBudget budget;
    private final Thread caller=Thread.currentThread();
    private final Path rawRoot;
    private final DataOutputStream requests,replies,timings;
    private final long maximumLogicalRpcs;
    private final int archiveChunkBytes;
    private final Map<String,long[]> rpcKinds=new LinkedHashMap<>();
    private long rpcCount,cycleCount;
    private byte[] latestOriginalWire;
    private boolean latestRawFlushed;
    public static final class EvidenceWriteException extends IOException {
        private static final long serialVersionUID=1L;
        private final byte[] wire;
        EvidenceWriteException(byte[] wire,IOException cause){super("Maintenance raw evidence write failed after submit; preserve original bytes and stop, no fresh-key reissue",cause);this.wire=wire.clone();}
        public byte[] originalWire(){return wire.clone();}
    }
    private boolean failed,closed;
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget)throws IOException{
        this(owner,writer,profile,lineage,newRawDir,budget,50000);
    }
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs)throws IOException{
        this(owner,writer,profile,lineage,newRawDir,budget,maximumLogicalRpcs,DEFAULT_ARCHIVE_CHUNK);
    }
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes)throws IOException{
        this.archiveChunkBytes=requireArchiveChunkBytes(archiveChunkBytes);
        if(maximumLogicalRpcs<1||maximumLogicalRpcs>250000)throw new IllegalArgumentException("explicit finite logical RPC cap1..250000 required");this.maximumLogicalRpcs=maximumLogicalRpcs;
        this.owner=Objects.requireNonNull(owner);this.writer=Objects.requireNonNull(writer);this.profile=Objects.requireNonNull(profile);
        this.lineage=lineage;scope=new Scope(profile.fingerprint(),lineage);this.budget=Objects.requireNonNull(budget);
        if(!budget.profile.equals(profile))throw new IllegalArgumentException("run journal budget profile mismatch");
        rawRoot=newRawDir.toAbsolutePath().normalize();Files.createDirectory(rawRoot);
        DataOutputStream openedRequests=new DataOutputStream(Files.newOutputStream(rawRoot.resolve("logical-rpc-requests.bin"),StandardOpenOption.CREATE_NEW));
        try{replies=new DataOutputStream(Files.newOutputStream(rawRoot.resolve("logical-rpc-replies.bin"),StandardOpenOption.CREATE_NEW));}
        catch(IOException error){try{openedRequests.close();}catch(IOException cleanup){error.addSuppressed(cleanup);}throw error;}
        requests=openedRequests;
        try{timings=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(rawRoot.resolve("logical-rpc-timings.csv"),StandardOpenOption.CREATE_NEW),65536));timings.writeBytes("rpc,kind,correlation_id,start_monotonic_ns,end_monotonic_ns,elapsed_ns,completed,archive_chunk_requested_bytes,event_fetch_requested_count\n");}
        catch(IOException error){try{requests.close();}finally{replies.close();}throw error;}
    }
    private void affinity(){if(Thread.currentThread()!=caller)throw new IllegalStateException("one maintenance coordinator caller required");}
    private Reply exchange(Operation operation)throws IOException{
        if(++rpcCount>maximumLogicalRpcs)throw new IllegalStateException("bounded logical maintenance RPC inventory exceeded");
        long rpcStart=System.nanoTime();String kind=operation.getClass().getSimpleName();boolean completed=false;long correlation=Long.MIN_VALUE;
        try{
        var ticket=owner.submitMaintenance(operation,System.nanoTime()+RPC_TIMEOUT.toNanos());byte[] original=ticket.originalWire();
        latestOriginalWire=original.clone();latestRawFlushed=false;correlation=RetentionWireV3.decode(original).correlationId();
        try{requests.writeInt(original.length);requests.write(original);requests.flush();latestRawFlushed=true;}
        catch(IOException writeError){throw new EvidenceWriteException(original,writeError);}
        Reply reply=ticket.await(RPC_TIMEOUT);byte[] raw=RetentionReplyV3.encode(reply);
        try{replies.writeInt(raw.length);replies.write(raw);replies.flush();}catch(IOException writeError){throw new EvidenceWriteException(original,writeError);}
        if(!reply.error().isEmpty())throw new IOException("maintenance reply error, no ACK success: "+reply.error());completed=true;return reply;
        }finally{
            long ended=System.nanoTime(),elapsed=ended-rpcStart;long[] values=rpcKinds.computeIfAbsent(kind,k->new long[4]);values[0]++;values[1]+=elapsed;values[2]=Math.max(values[2],elapsed);if(!completed)values[3]++;
            String timingRow=rpcCount+","+kind+","+correlation+","+rpcStart+","+ended+","+elapsed+","+completed+","+(operation instanceof ArchiveChunk chunk?chunk.count():"")+","+(operation instanceof FetchEvents fetch?fetch.count():"")+"\n";
            if(timingRow.length()>256)throw new IOException("bounded logical maintenance timing row exceeds256bytes");timings.writeBytes(timingRow);timings.flush();
        }
    }
    public Cycle exportThrough(long throughBusinessSeq)throws IOException{
        affinity();if(failed||closed)throw new IllegalStateException("maintenance coordinator terminal; no new attempt or fresh identity reissue");
        latestOriginalWire=null;latestRawFlushed=false;
        try{return export(throughBusinessSeq);}catch(Throwable error){
            failed=true;boolean saved=latestOriginalWire==null||latestRawFlushed;
            if(latestOriginalWire!=null)try{Files.write(rawRoot.resolve("failure-original-request.bin"),latestOriginalWire,StandardOpenOption.CREATE_NEW);saved=true;}catch(IOException rawFailure){error.addSuppressed(rawFailure);}
            try{Files.writeString(rawRoot.resolve("failure.txt"),error.toString()+"\nrawOriginalIdentitiesPreserved="+saved+"\n",StandardOpenOption.CREATE_NEW);}catch(IOException receipt){error.addSuppressed(receipt);}
            if(error instanceof IOException io)throw io;if(error instanceof RuntimeException runtime)throw runtime;if(error instanceof Error fatal)throw fatal;throw new IOException(error);
        }
    }
    private Cycle export(long through)throws IOException{
        long cycleStarted=System.nanoTime(),rpcAtStart=rpcCount;
        long from=budget.archivedThrough()+1,count=through-from+1;
        if(count<1||count>COMMAND_CUT)throw new IllegalArgumentException("nonempty prefix cut must be <=3072 business commands");
        if(((Number)owner.snapshot().get("pendingLogicalCommands")).longValue()!=0)
            throw new IllegalStateException("functional stage requires known business closure before maintenance; future arrivals are a separate harness");
        Reply prepared=exchange(new PrepareArchive(through));if(!(prepared.payload() instanceof Descriptor descriptor))throw new IOException("missing exact prefix descriptor");
        var ack=descriptor.acknowledgement();
        if(ack.firstCommandSeq()!=from||ack.throughCommandSeq()!=through
                ||(budget.lastArchive!=null&&!ack.previousChainHash().equals(budget.lastArchive.chainHash())))throw new IOException("archive chain/range discontinuity");
        long fileLimit=profile.core().maxPendingSerializedBytes()+1024L;
        if(descriptor.totalBytes()>fileLimit)throw new IOException("archive exceeds explicit per-prefix allocation cap");
        byte[] payload=new byte[descriptor.totalBytes()];
        for(int offset=0;offset<payload.length;){
            Reply reply=exchange(new ArchiveChunk(ack,payload.length,offset,Math.min(archiveChunkBytes,payload.length-offset)));
            if(!(reply.payload() instanceof Chunk chunk)||chunk.offset()!=offset)throw new IOException("archive chunk prefix gap");
            byte[] part=chunk.data();System.arraycopy(part,0,payload,offset,part.length);offset+=part.length;
        }
        var verified=RetentionArchiveVerifierV3.verify(payload,profile.core(),lineage,ack);
        if(verified.entries().size()!=count||verified.previousEventSeq()!=budget.lastEvent)throw new IOException("archive exact command/event prefix differs");
        var archiveFile=writer.persistArchive(payload,profile.core(),lineage,ack).await(Duration.ofSeconds(35));
        var expectedEvents=new ArrayList<Event>();for(var entry:verified.entries())expectedEvents.addAll(entry.execution().events());
        long throughEvent=verified.entries().getLast().eventSeqAfter();Path eventFile=null;
        if(throughEvent-budget.lastEvent!=expectedEvents.size())throw new IOException("archive event total/gap differs");
        if(!expectedEvents.isEmpty()){
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);int index=0;
            while(index<expectedEvents.size()){
                Reply reply=exchange(new FetchEvents(budget.lastEvent+index+1,Math.min(16,expectedEvents.size()-index)));
                if(!(reply.payload() instanceof Events events)||events.batch().events().isEmpty())throw new IOException("outbox complete prefix missing");
                for(Event event:events.batch().events())if(index>=expectedEvents.size()||!event.equals(expectedEvents.get(index++)))throw new IOException("outbox/history event differs");
                byte[] raw=RetentionReplyV3.encode(reply);if(bytes.size()+4L+raw.length>fileLimit)throw new IOException("event evidence allocation cap exceeded");out.writeInt(raw.length);out.write(raw);
            }
            eventFile=writer.persistEvents(bytes.toByteArray(),expectedEvents,scope,budget.lastEvent+1,throughEvent).await(Duration.ofSeconds(35)).path();
        }
        // Both immutable payload and exact event prefix are forced/readback verified before either destructive ACK.
        MaintenanceIdentity archiveId=budget.reserve(true,id->new ArchiveCommit(id,ack));
        Reply committed=exchange(new ArchiveCommit(archiveId,ack));
        if(!(committed.payload() instanceof State state)||state.maintenance()==null||state.maintenance().code()!=RetentionServiceV3.MaintenanceCode.APPLIED
                ||state.maintenance().compaction()==null||state.maintenance().compaction().archivedThroughCommandSeq()!=through
                ||state.maintenance().compaction().releasedHistoryCommands()!=count)throw new IOException("archive ACK not exactly applied; stop without fresh key reissue");
        if(!expectedEvents.isEmpty()){
            MaintenanceIdentity eventId=budget.reserve(false,id->new EventAck(id,throughEvent));Reply eventAck=exchange(new EventAck(eventId,throughEvent));
            if(!(eventAck.payload() instanceof State eventState)||eventState.maintenance()==null||eventState.maintenance().code()!=RetentionServiceV3.MaintenanceCode.APPLIED
                    ||eventState.maintenance().exportedEventSeq()!=throughEvent)throw new IOException("event ACK not exactly applied; retain unresolved original identity");
        }
        budget.lastArchive=ack;budget.lastEvent=throughEvent;cycleCount++;
        String receipt="cycle="+cycleCount+"\ncycleStartedMonotonicNs="+cycleStarted+"\ncycleEndedMonotonicNs="+System.nanoTime()+"\nlogicalRpcCountAtStart="+rpcAtStart+"\nlogicalRpcCountAtEnd="+rpcCount+"\narchiveChunkBytes="+archiveChunkBytes+"\neventFetchCount=16\nfirstCommandSeq="+from+"\nthroughCommandSeq="+through+"\nthroughEventSeq="+throughEvent+"\narchiveFile="+archiveFile.path()+"\narchiveSha256="+archiveFile.sha256()+"\neventFile="+eventFile+"\nforceAndReadbackBeforeBothAcks=true\nreservedJournalRecords="+budget.reservedJournalRecords+"\nreservedJournalBytes="+budget.reservedJournalBytes+"\ncapacityClaim=false\n";
        Files.writeString(rawRoot.resolve("cycle-"+cycleCount+".verified.txt"),receipt,StandardOpenOption.CREATE_NEW);
        return new Cycle(ack,archiveFile.path(),eventFile,verified.entries(),throughEvent);
    }
    public Map<String,Object> snapshot(){affinity();var result=new LinkedHashMap<String,Object>(budget.snapshot());result.put("archiveChunkBytes",archiveChunkBytes);result.put("eventFetchCount",16);result.put("logicalRpcCount",rpcCount);result.put("maximumLogicalRpcs",maximumLogicalRpcs);var kinds=new LinkedHashMap<String,Object>();for(var entry:rpcKinds.entrySet()){long[] v=entry.getValue();kinds.put(entry.getKey(),Map.of("count",v[0],"totalElapsedNs",v[1],"maxElapsedNs",v[2],"failed",v[3]));}result.put("rpcKinds",kinds);result.put("completedCycles",cycleCount);result.put("failed",failed);return Collections.unmodifiableMap(result);}
    @Override public void close()throws IOException{affinity();closed=true;try{requests.close();}finally{try{replies.close();}finally{timings.close();}}}
}
