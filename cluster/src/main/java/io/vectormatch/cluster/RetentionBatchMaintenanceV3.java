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
    private final int archiveChunkBytes,readWindow,eventFetchCount;
    private final boolean commonReadWindow32Envelope;
    private final boolean commonReadWindow128Envelope;
    private final Map<String,long[]> rpcKinds=new LinkedHashMap<>();
    private long rpcCount,cycleCount;
    private byte[] latestOriginalWire;
    private boolean latestRawFlushed;
    private boolean readFailureOriginalsWritten;
    private RetentionBatchOwnerV3.ReadBank activeReadBank;
    private final List<ReadRpc> retainedReads=new ArrayList<>(8);
    private static final class ReadRpc {
        final long number,start,correlation;
        final Operation operation;
        final RetentionBatchOwnerV3.MaintenanceTicket ticket;
        final byte[] original;
        boolean timingAttempted;
        ReadRpc(long number,long start,Operation operation,RetentionBatchOwnerV3.MaintenanceTicket ticket){
            this.number=number;this.start=start;this.operation=operation;this.ticket=ticket;
            original=ticket.originalWire();correlation=RetentionWireV3.decode(original).correlationId();
        }
    }
    @FunctionalInterface private interface ReadConsumer { void accept(Operation operation,Reply reply)throws IOException; }
    /** All retained originals survive a failed raw sink; already-consumed reads remain in the logical tapes. */
    public static final class ReadPhaseFailureException extends IOException {
        private static final long serialVersionUID=1L;
        private final List<byte[]> wires;
        private final List<Map<String,Object>> observations;
        ReadPhaseFailureException(RetentionBatchOwnerV3.ReadBankFailureException bundle,Throwable cause){
            super("Maintenance read phase failed; preserve every retained original and partial evidence; no ACK or fresh-key reissue",cause);
            wires=bundle.originalWires();observations=bundle.observations();
        }
        public List<byte[]> originalWires(){return wires.stream().map(byte[]::clone).toList();}
        public List<Map<String,Object>> observations(){return observations;}
    }
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
        this(owner,writer,profile,lineage,newRawDir,budget,maximumLogicalRpcs,archiveChunkBytes,1);
    }
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes,int readWindow)throws IOException{
        this(owner,writer,profile,lineage,newRawDir,budget,maximumLogicalRpcs,archiveChunkBytes,readWindow,DEFAULT_EVENT_FETCH_COUNT);
    }
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes,int readWindow,int eventFetchCount)throws IOException{
        this(owner,writer,profile,lineage,newRawDir,budget,maximumLogicalRpcs,archiveChunkBytes,readWindow,eventFetchCount,false);
    }
    /** Explicit isolated experiment; legacy constructors retain their original1|8 window admission. */
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes,int readWindow,int eventFetchCount,boolean commonReadWindow32Envelope)throws IOException{
        this(owner,writer,profile,lineage,newRawDir,budget,maximumLogicalRpcs,archiveChunkBytes,readWindow,eventFetchCount,commonReadWindow32Envelope,false);
    }
    /** Explicit128-credit common envelope; both compared windows retain identical resource bounds. */
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes,int readWindow,int eventFetchCount,boolean commonReadWindow32Envelope,boolean commonReadWindow128Envelope)throws IOException{
        if(commonReadWindow32Envelope&&commonReadWindow128Envelope)throw new IllegalArgumentException("ambiguous read envelope");
        this.commonReadWindow128Envelope=commonReadWindow128Envelope;
        this.commonReadWindow32Envelope=commonReadWindow32Envelope;
        this.eventFetchCount=requireEventFetchCount(eventFetchCount);
        this.archiveChunkBytes=requireArchiveChunkBytes(archiveChunkBytes);
        this.readWindow=commonReadWindow128Envelope?RetentionCapacityPlanV3.requireReadWindow128(readWindow):commonReadWindow32Envelope?RetentionCapacityPlanV3.requireReadWindow32(readWindow):RetentionCapacityPlanV3.requireReadWindow(readWindow);
        if((commonReadWindow32Envelope||commonReadWindow128Envelope)&&archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK)throw new IllegalArgumentException("read-window32 requires unchanged chunk6144");
        if(maximumLogicalRpcs<1||maximumLogicalRpcs>250000)throw new IllegalArgumentException("explicit finite logical RPC cap1..250000 required");this.maximumLogicalRpcs=maximumLogicalRpcs;
        this.owner=Objects.requireNonNull(owner);this.writer=Objects.requireNonNull(writer);this.profile=Objects.requireNonNull(profile);
        this.lineage=lineage;scope=new Scope(profile.fingerprint(),lineage);this.budget=Objects.requireNonNull(budget);
        if(!budget.profile.equals(profile))throw new IllegalArgumentException("run journal budget profile mismatch");
        rawRoot=newRawDir.toAbsolutePath().normalize();Files.createDirectory(rawRoot);
        DataOutputStream openedRequests=new DataOutputStream(Files.newOutputStream(rawRoot.resolve("logical-rpc-requests.bin"),StandardOpenOption.CREATE_NEW));
        try{replies=new DataOutputStream(Files.newOutputStream(rawRoot.resolve("logical-rpc-replies.bin"),StandardOpenOption.CREATE_NEW));}
        catch(IOException error){try{openedRequests.close();}catch(IOException cleanup){error.addSuppressed(cleanup);}throw error;}
        requests=openedRequests;
        try{timings=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(rawRoot.resolve("logical-rpc-timings.csv"),StandardOpenOption.CREATE_NEW),65536));timings.writeBytes("rpc,kind,correlation_id,start_monotonic_ns,end_monotonic_ns,elapsed_ns,completed,archive_chunk_requested_bytes,event_fetch_requested_count,read_phase_generation,read_window,armed_monotonic_ns,owner_reply_completed_ns\n");}
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
            String timingRow=rpcCount+","+kind+","+correlation+","+rpcStart+","+ended+","+elapsed+","+completed+","+(operation instanceof ArchiveChunk chunk?chunk.count():"")+","+(operation instanceof FetchEvents fetch?fetch.count():"")+",0,0,,\n";
            if(timingRow.length()>256)throw new IOException("bounded logical maintenance timing row exceeds256bytes");timings.writeBytes(timingRow);timings.flush();
        }
    }
    private void recordReadTiming(ReadRpc rpc,boolean completed)throws IOException{
        if(rpc.timingAttempted)return;rpc.timingAttempted=true;
        long ended=System.nanoTime(),elapsed=ended-rpc.start;String kind=rpc.operation.getClass().getSimpleName();
        long[] values=rpcKinds.computeIfAbsent(kind,k->new long[4]);values[0]++;values[1]+=elapsed;values[2]=Math.max(values[2],elapsed);if(!completed)values[3]++;
        Map<String,Object> observed=rpc.ticket.observation();
        String row=rpc.number+","+kind+","+rpc.correlation+","+rpc.start+","+ended+","+elapsed+","+completed+","+(rpc.operation instanceof ArchiveChunk chunk?chunk.count():"")+","+(rpc.operation instanceof FetchEvents fetch?fetch.count():"")
                +","+observed.get("readPhaseGeneration")+","+readWindow+","+csvValue(observed.get("armedMonotonicNs"))+","+csvValue(observed.get("replyCompletionNs"))+"\n";
        if(row.length()>256)throw new IOException("bounded logical maintenance timing row exceeds256bytes");timings.writeBytes(row);timings.flush();
    }
    private static String csvValue(Object value){return value==null?"":value.toString();}
    /** At most one selected-size wave is retained, including completed replies awaiting evidence consumption. */
    private void readWave(List<? extends Operation> operations,ReadConsumer consumer)throws IOException{
        if(activeReadBank==null||!retainedReads.isEmpty()||operations.isEmpty()||operations.size()>readWindow)
            throw new IllegalStateException("bounded same-kind read wave requires its exclusive phase lease");
        for(Operation operation:operations){
            if(++rpcCount>maximumLogicalRpcs)throw new IllegalStateException("bounded logical maintenance RPC inventory exceeded");
            long start=System.nanoTime();var ticket=activeReadBank.reserve(operation,start+RPC_TIMEOUT.toNanos());
            retainedReads.add(new ReadRpc(rpcCount,start,operation,ticket));
        }
        // No reservation is eligible for offering until every original in this wave has been flushed.
        for(var rpc:retainedReads){requests.writeInt(rpc.original.length);requests.write(rpc.original);}requests.flush();
        for(var rpc:retainedReads)rpc.ticket.arm();
        for(var rpc:retainedReads){
            Reply reply=rpc.ticket.await(RPC_TIMEOUT);
            if(!reply.error().isEmpty())throw new IOException("maintenance read error, no ACK: "+reply.error());
            consumer.accept(rpc.operation,reply);
            byte[] raw=RetentionReplyV3.encode(reply);replies.writeInt(raw.length);replies.write(raw);replies.flush();
            recordReadTiming(rpc,true);activeReadBank.consume(rpc.ticket);
        }
        retainedReads.clear();
    }
    private ReadPhaseFailureException abortReadPhase(Throwable error){
        var bundle=activeReadBank.abort(error);var failure=new ReadPhaseFailureException(bundle,error);
        for(var rpc:retainedReads)if(!rpc.timingAttempted)try{recordReadTiming(rpc,false);}catch(Throwable timingError){failure.addSuppressed(timingError);}
        boolean originalsWritten=false;
        try{try(var output=new DataOutputStream(Files.newOutputStream(rawRoot.resolve("failure-original-requests.bin"),StandardOpenOption.CREATE_NEW))){
            for(byte[] wire:failure.originalWires()){output.writeInt(wire.length);output.write(wire);}output.flush();
            }originalsWritten=true;
        }catch(Throwable rawError){failure.addSuppressed(rawError);}
        readFailureOriginalsWritten=originalsWritten;
        var metadata=new LinkedHashMap<String,Object>();metadata.put("schema","retention-v3-read-phase-failure-v1");
        metadata.put("readWindow",readWindow);metadata.put("retainedOriginalCount",failure.originalWires().size());metadata.put("retainedReads",failure.observations());
        metadata.put("originalsWrittenAndFlushed",originalsWritten);metadata.put("independentDurabilityProven",false);metadata.put("logicalTapesMayBePartial",true);metadata.put("ackAfterFailureAllowed",false);
        metadata.put("errorType",error.getClass().getName());String message=error.toString();metadata.put("error",message.substring(0,Math.min(4096,message.length())));
        try{RetentionCapacityJsonV3.writeNew(rawRoot.resolve("read-phase-failure.json"),metadata);}catch(Throwable metadataError){failure.addSuppressed(metadataError);}
        return failure;
    }
    public Cycle exportThrough(long throughBusinessSeq)throws IOException{
        affinity();if(failed||closed)throw new IllegalStateException("maintenance coordinator terminal; no new attempt or fresh identity reissue");
        latestOriginalWire=null;latestRawFlushed=false;
        try{return export(throughBusinessSeq);}catch(Throwable caught){
            failed=true;
            Throwable error=activeReadBank==null?caught:abortReadPhase(caught);
            boolean saved=activeReadBank==null?(latestOriginalWire==null||latestRawFlushed):readFailureOriginalsWritten;
            if(activeReadBank==null&&latestOriginalWire!=null)try{Files.write(rawRoot.resolve("failure-original-request.bin"),latestOriginalWire,StandardOpenOption.CREATE_NEW);saved=true;}catch(IOException rawFailure){error.addSuppressed(rawFailure);}
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
        activeReadBank=commonReadWindow128Envelope?owner.openReadBank128(readWindow):commonReadWindow32Envelope?owner.openReadBank32(readWindow):owner.openReadBank(readWindow);
        for(int offset=0;offset<payload.length;){
            var wave=new ArrayList<Operation>(readWindow);
            for(int i=0;i<readWindow&&offset<payload.length;i++){
                int length=Math.min(archiveChunkBytes,payload.length-offset);wave.add(new ArchiveChunk(ack,payload.length,offset,length));offset+=length;
            }
            readWave(wave,(operation,reply)->{
                ArchiveChunk requested=(ArchiveChunk)operation;
                if(!(reply.payload() instanceof Chunk chunk)||!chunk.acknowledgement().equals(ack)||chunk.totalBytes()!=payload.length||chunk.offset()!=requested.offset()||chunk.data().length!=requested.count())
                    throw new IOException("archive chunk exact range differs");
                System.arraycopy(chunk.data(),0,payload,requested.offset(),requested.count());
            });
        }
        long archiveVerifyStarted=System.nanoTime();
        var captured=RetentionDurableWriterV3.captureAndVerifyArchive(payload,profile.core(),lineage,ack);
        var verified=captured.verification();
        long coordinatorArchiveVerificationNs=System.nanoTime()-archiveVerifyStarted;
        if(verified.entries().size()!=count||verified.previousEventSeq()!=budget.lastEvent)throw new IOException("archive exact command/event prefix differs");
        var archiveFile=writer.persistVerifiedArchive(captured).await(Duration.ofSeconds(35));
        activeReadBank.close();activeReadBank=null;
        var expectedEvents=new ArrayList<Event>();for(var entry:verified.entries())expectedEvents.addAll(entry.execution().events());
        long throughEvent=verified.entries().getLast().eventSeqAfter();Path eventFile=null;
        RetentionDurableWriterV3.Persisted eventPersisted=null;
        if(throughEvent-budget.lastEvent!=expectedEvents.size())throw new IOException("archive event total/gap differs");
        if(!expectedEvents.isEmpty()){
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);int index=0;
            activeReadBank=commonReadWindow128Envelope?owner.openReadBank128(readWindow):commonReadWindow32Envelope?owner.openReadBank32(readWindow):owner.openReadBank(readWindow);
            while(index<expectedEvents.size()){
                var wave=new ArrayList<Operation>(readWindow);int next=index;
                for(int i=0;i<readWindow&&next<expectedEvents.size();i++){
                    int length=Math.min(eventFetchCount,expectedEvents.size()-next);wave.add(new FetchEvents(budget.lastEvent+next+1,length));next+=length;
                }
                final int waveStart=index;
                readWave(wave,(operation,reply)->{
                    FetchEvents requested=(FetchEvents)operation;int first=Math.toIntExact(requested.fromEventSeq()-budget.lastEvent-1);
                    if(!(reply.payload() instanceof Events events)||events.batch().events().size()!=requested.count()||first<waveStart||first+requested.count()>expectedEvents.size())
                        throw new IOException("outbox complete requested prefix missing");
                    for(int i=0;i<requested.count();i++)if(!events.batch().events().get(i).equals(expectedEvents.get(first+i)))throw new IOException("outbox/history event differs");
                    byte[] raw=RetentionReplyV3.encode(reply);if(bytes.size()+4L+raw.length>fileLimit)throw new IOException("event evidence allocation cap exceeded");out.writeInt(raw.length);out.write(raw);
                });index=next;
            }
            eventPersisted=writer.persistEvents(bytes.toByteArray(),expectedEvents,scope,budget.lastEvent+1,throughEvent).await(Duration.ofSeconds(35));
            eventFile=eventPersisted.path();
            activeReadBank.close();activeReadBank=null;
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
        String receipt="cycle="+cycleCount+"\ncycleStartedMonotonicNs="+cycleStarted+"\ncycleEndedMonotonicNs="+System.nanoTime()+"\nlogicalRpcCountAtStart="+rpcAtStart+"\nlogicalRpcCountAtEnd="+rpcCount+"\narchiveChunkBytes="+archiveChunkBytes+"\neventFetchCount="+eventFetchCount+"\nreadWindow="+readWindow+"\nfirstCommandSeq="+from+"\nthroughCommandSeq="+through+"\nthroughEventSeq="+throughEvent+"\narchiveFile="+archiveFile.path()+"\narchiveSha256="+archiveFile.sha256()+"\neventFile="+eventFile+"\nforceAndReadbackBeforeBothAcks=true\nreservedJournalRecords="+budget.reservedJournalRecords+"\nreservedJournalBytes="+budget.reservedJournalBytes+"\ncapacityClaim=false\n";
        receipt+="writerTimingSchema=1\ncoordinatorArchiveVerificationNs="+coordinatorArchiveVerificationNs+"\n"+writerTiming("archive",archiveFile)+writerTiming("events",eventPersisted);
        Files.writeString(rawRoot.resolve("cycle-"+cycleCount+".verified.txt"),receipt,StandardOpenOption.CREATE_NEW);
        return new Cycle(ack,archiveFile.path(),eventFile,verified.entries(),throughEvent);
    }
    private static String writerTiming(String prefix,RetentionDurableWriterV3.Persisted file){
        if(file==null)return prefix+"WriterPresent=false\n";
        var t=file.phaseTimings();
        return prefix+"WriterPresent=true\n"+prefix+"WriterVerifiedArchiveHandoff="+file.verifiedArchiveHandoff()+"\n"+prefix+"WriterCopyNs="+t.handoffCopyNs()+"\n"+prefix+"WriterQueueWaitNs="+t.queueWaitNs()+"\n"
                +prefix+"WriterPrevalidationNs="+t.prevalidationNs()+"\n"+prefix+"WriterInputHashNs="+t.inputHashNs()+"\n"
                +prefix+"WriterWriteNs="+t.writeNs()+"\n"+prefix+"WriterForceNs="+t.forceNs()+"\n"+prefix+"WriterReadbackNs="+t.readbackNs()+"\n"
                +prefix+"WriterReceiptWriteNs="+t.receiptWriteNs()+"\n"+prefix+"WriterReceiptForceNs="+t.receiptForceNs()+"\n"+prefix+"WriterElapsedNs="+t.writerElapsedNs()+"\n";
    }
    public Map<String,Object> snapshot(){affinity();var result=new LinkedHashMap<String,Object>(budget.snapshot());if(commonReadWindow32Envelope)result.put("commonReadWindow32Envelope",true);if(commonReadWindow128Envelope)result.put("commonReadWindow128Envelope",true);result.put("archiveChunkBytes",archiveChunkBytes);result.put("eventFetchCount",eventFetchCount);result.put("readWindow",readWindow);result.put("logicalRpcCount",rpcCount);result.put("maximumLogicalRpcs",maximumLogicalRpcs);var kinds=new LinkedHashMap<String,Object>();for(var entry:rpcKinds.entrySet()){long[] v=entry.getValue();kinds.put(entry.getKey(),Map.of("count",v[0],"totalElapsedNs",v[1],"maxElapsedNs",v[2],"failed",v[3]));}result.put("rpcKinds",kinds);result.put("completedCycles",cycleCount);result.put("failed",failed);return Collections.unmodifiableMap(result);}
    @Override public void close()throws IOException{affinity();closed=true;try{requests.close();}finally{try{replies.close();}finally{timings.close();}}}
}
