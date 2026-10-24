package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;

import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Codec-derived finite admission arithmetic. A plan is not a completed capacity measurement. */
public final class RetentionCapacityPlanV3 {
    public static final int MAX_ARRIVALS = 350_000, WORKERS = 128, COMMANDS_PER_CYCLE = 3072;
    public static final int MAXIMUM_OFFERS_PER_RPC = 4;
    public static final long WRITER_PAYLOAD_LIMIT = 1024L*1024*1024;
    public static final int WRITER_TOTAL_FILE_LIMIT = 1024;
    public static final long RAW_TRACE_LIMIT = 2L*1024*1024*1024;
    public static final long ALLOCATED_GROWTH_LIMIT = 5L*1024*1024*1024/2;
    public static final long RUNTIME_FREE_FLOOR = 1024L*1024*1024;
    public static final long NATIVE_ALLOCATED_RESERVE = 512L*1024*1024;
    public static final int ARRIVAL_CSV_BYTES = 640, ATTEMPT_CSV_BYTES = 128, INDEX_CSV_BYTES = 128;
    public static final int RAW_FRAME_PREFIX_BYTES = 12;
    public static final long FIXED_TRACE_BYTES = 384L*1024;

    public record Plan(int arrivals, int batchCap, int maximumMaintenanceCycles, long maximumEvents,
                       long maximumLogicalMaintenanceRpcs, long maximumBusinessFrames,
                       long maximumExtraPositiveOffers, long maximumNegativeOfferAttempts,
                       long maximumWriterPayloadBytes, int maximumWriterPayloadFiles,
                       long noRetryRawTraceBytes, long worstFourOfferRawTraceBytes,
                       long maximumRawTraceBytes, long maximumAllocatedGrowthBytes,
                       long minimumFreeRuntimeBytes, long maximumJournalRecords, long maximumJournalBytes,
                       int maximumArchiveEntryBytes, int archiveHeaderBytes,
                       long maximumArchivePayloadBytes, long maximumEventPayloadBytes,
                       long maximumArchiveChunkRpcs, long maximumEventFetchRpcs,
                       int largestReplyBytes, List<String> admissionRejections) {
        public Plan { admissionRejections = List.copyOf(admissionRejections); }
        public boolean admitted() { return admissionRejections.isEmpty(); }
        public int maximumPhysicalOffersPerRpc() { return MAXIMUM_OFFERS_PER_RPC; }
        public int maximumWriterFilesIncludingReceipts() { return Math.multiplyExact(maximumWriterPayloadFiles,2); }
        public void requireAdmitted() {
            if (!admitted()) throw new IllegalArgumentException("finite capacity plan rejected: "+String.join("; ",admissionRejections));
        }
        public Map<String,Object> observation() {
            var out = new LinkedHashMap<String,Object>();
            out.put("arrivals",arrivals); out.put("batchCap",batchCap); out.put("maximumMaintenanceCycles",maximumMaintenanceCycles);
            out.put("maximumEvents",maximumEvents); out.put("maximumLogicalMaintenanceRpcs",maximumLogicalMaintenanceRpcs);
            out.put("maximumBusinessFrames",maximumBusinessFrames); out.put("maximumPhysicalOffersPerRpc",MAXIMUM_OFFERS_PER_RPC);
            out.put("maximumExtraPositiveOffers",maximumExtraPositiveOffers); out.put("maximumNegativeOfferAttempts",maximumNegativeOfferAttempts);
            out.put("maximumWriterPayloadBytes",maximumWriterPayloadBytes); out.put("maximumWriterPayloadFiles",maximumWriterPayloadFiles);
            out.put("maximumWriterFilesIncludingReceipts",maximumWriterFilesIncludingReceipts());
            out.put("noRetryRawTraceBytes",noRetryRawTraceBytes); out.put("worstFourOfferRawTraceBytes",worstFourOfferRawTraceBytes);
            out.put("maximumRawTraceBytes",maximumRawTraceBytes); out.put("maximumAllocatedGrowthBytes",maximumAllocatedGrowthBytes);
            out.put("minimumFreeRuntimeBytes",minimumFreeRuntimeBytes); out.put("nativeAllocatedReserveBytes",NATIVE_ALLOCATED_RESERVE);
            out.put("maximumJournalRecords",maximumJournalRecords); out.put("maximumJournalBytes",maximumJournalBytes);
            out.put("maximumArchiveEntryBytes",maximumArchiveEntryBytes); out.put("archiveHeaderBytes",archiveHeaderBytes);
            out.put("maximumArchivePayloadBytes",maximumArchivePayloadBytes); out.put("maximumEventPayloadBytes",maximumEventPayloadBytes);
            out.put("maximumArchiveChunkRpcs",maximumArchiveChunkRpcs); out.put("maximumEventFetchRpcs",maximumEventFetchRpcs);
            out.put("largestReplyBytes",largestReplyBytes); out.put("admitted",admitted()); out.put("admissionRejections",admissionRejections);
            out.put("witness", "5 real reference commands; 19-digit structured request sequence, longest load-w127 producer; 64-byte lineage; fixed-width numeric codec");
            out.put("scope", "prospective finite storage/RPC bounds with enforced trace/offer/allocated caps; native reserve is a stop threshold, not a proof all arrivals complete under arbitrary packet loss");
            return Collections.unmodifiableMap(out);
        }
    }
    private record Probe(int header,int setupFrames,int normalFrame,int finalExtra,int singleRequest,
                         int singleReply,int setupTrace,long archiveRequest,int descriptorReply,
                         int chunkRequest,int fullChunkReply,int fetchRequest,int eventReplyOverhead,
                         int maxEventWire,int archiveAckRequest,int archiveAckReply,int eventAckRequest,int eventAckReply,
                         int archiveAckOperation,int eventAckOperation) {}
    private RetentionCapacityPlanV3() {}

    /** Full four-offer envelope. Rejected plans retain their arithmetic for inspection. */
    public static Plan plan(int arrivals,int batchCap,RetentionServiceV3.Profile profile) {
        return calculate(arrivals,batchCap,profile,-1,-1);
    }
    /** Explicit global retry/negative-offer budgets; exhaustion must abort the sample before the next physical offer. */
    public static Plan planWithOfferBudget(int arrivals,int batchCap,RetentionServiceV3.Profile profile,
                                          long maximumExtraPositiveOffers,long maximumNegativeOfferAttempts) {
        if(maximumExtraPositiveOffers<0||maximumNegativeOfferAttempts<0)
            throw new IllegalArgumentException("explicit nonnegative global offer budgets required");
        return calculate(arrivals,batchCap,profile,maximumExtraPositiveOffers,maximumNegativeOfferAttempts);
    }
    private static Plan calculate(int arrivals,int batchCap,RetentionServiceV3.Profile profile,long extras,long negatives) {
        Objects.requireNonNull(profile);
        if(arrivals<1||arrivals>MAX_ARRIVALS||(batchCap!=1&&batchCap!=4))
            throw new IllegalArgumentException("finite workload requires 1..350000 arrivals and cap1 or cap4");
        Probe p=probe(profile,batchCap); int loadCycles=ceil(arrivals,COMMANDS_PER_CYCLE),cycles=1+loadCycles;
        long totalEvents=2L*arrivals+3,archiveBytes=p.header+p.setupFrames,eventBytes=0,chunkRpcs=ceil(archiveBytes,MAX_ARCHIVE_CHUNK),fetchRpcs=1;
        // Setup is exported separately. Each load prefix has <=3072 commands and exactly two events per successful buy.
        eventBytes=eventFrameBytes(3,p); long physicalRequestBytes=p.archiveRequest;
        long physicalReplyBytes=p.descriptorReply;
        long setupArchive=archiveBytes;
        physicalRequestBytes+=ceil(setupArchive,MAX_ARCHIVE_CHUNK)*(long)p.chunkRequest;
        physicalReplyBytes+=chunkReplyBytes(setupArchive,p);
        physicalRequestBytes+=p.fetchRequest;
        physicalReplyBytes+=eventBytes-4; // framed writer stores int32 lengths; physical tape has its own 12-byte prefix
        for(int cycle=0,remaining=arrivals;cycle<loadCycles;cycle++) {
            int count=Math.min(COMMANDS_PER_CYCLE,remaining);remaining-=count;
            long bytes=p.header+(long)count*p.normalFrame+(remaining==0?p.finalExtra:0);
            archiveBytes+=bytes; long chunks=ceil(bytes,MAX_ARCHIVE_CHUNK);chunkRpcs+=chunks;
            physicalRequestBytes+=p.archiveRequest+chunks*p.chunkRequest;
            physicalReplyBytes+=p.descriptorReply+chunkReplyBytes(bytes,p);
            long events=2L*count,fetches=ceil(events,16);fetchRpcs+=fetches;
            long framedEvents=eventFrameBytes(events,p);eventBytes+=framedEvents;
            physicalRequestBytes+=fetches*p.fetchRequest;
            physicalReplyBytes+=framedEvents-4L*fetches;
        }
        long logicalRpcs=chunkRpcs+fetchRpcs+3L*cycles;
        physicalRequestBytes+=(long)cycles*(p.archiveAckRequest+p.eventAckRequest);
        physicalReplyBytes+=(long)cycles*(p.archiveAckReply+p.eventAckReply);
        long frames=arrivals+logicalRpcs;
        long maximumExtras=3L*frames;
        if(extras<0)extras=maximumExtras;
        if(negatives<0)negatives=frames;
        if(extras>maximumExtras||negatives>4L*frames)throw new IllegalArgumentException("global offer budget exceeds explicit finite envelope");
        int largestReply=Math.max(p.singleReply,Math.max(p.fullChunkReply,p.eventReplyOverhead+16*p.maxEventWire));
        // One original wire per correlation. Duplicate replies remain raw, as does every physical attempt CSV row.
        long uniqueBusinessRequests=(long)arrivals*(p.singleRequest+RAW_FRAME_PREFIX_BYTES);
        long businessReplies=(long)arrivals*(p.singleReply+RAW_FRAME_PREFIX_BYTES);
        long maintenanceRequests=physicalRequestBytes+RAW_FRAME_PREFIX_BYTES*logicalRpcs;
        long maintenanceReplies=physicalReplyBytes+RAW_FRAME_PREFIX_BYTES*logicalRpcs;
        long helperLogicalCopy=physicalRequestBytes+physicalReplyBytes+8L*logicalRpcs;
        long base=uniqueBusinessRequests+businessReplies+maintenanceRequests+maintenanceReplies+helperLogicalCopy
                +frames*(ATTEMPT_CSV_BYTES+INDEX_CSV_BYTES)+(long)arrivals*ARRIVAL_CSV_BYTES+FIXED_TRACE_BYTES
                +p.setupTrace+cycles*2048L+256L*logicalRpcs; // enforced maintenance timing row cap, plus header in fixed reserve
        long allFour=base+3L*(businessReplies+maintenanceReplies)+3L*frames*ATTEMPT_CSV_BYTES
                +frames*ATTEMPT_CSV_BYTES;
        long extraReplies=Math.min(extras*(largestReply+RAW_FRAME_PREFIX_BYTES),3L*(businessReplies+maintenanceReplies));
        long raw=base+extraReplies+(extras+negatives)*ATTEMPT_CSV_BYTES;
        long payload=archiveBytes+eventBytes,writerJobs=2L*cycles;
        // Native allocation has an independent bounded stop reserve. Never extrapolate a 10k file size to prove 350k native growth.
        long allocation=raw+payload+writerJobs*1024L+RetentionCapacityDiskGuardV3.MAX_ENTRIES*4096L+NATIVE_ALLOCATED_RESERVE;
        long records=cycles*2L*MAXIMUM_OFFERS_PER_RPC;
        long journalBytes=4L*cycles*(p.archiveAckOperation+p.eventAckOperation+2048L);
        var rejected=new ArrayList<String>();
        if(profile.core().maxPendingCommands()<COMMANDS_PER_CYCLE||profile.core().maxPendingEvents()<2*COMMANDS_PER_CYCLE
                ||profile.outboxCapacity()<2*COMMANDS_PER_CYCLE||profile.core().limits().maxProducers()<131)
            rejected.add("profile does not admit the declared finite W128/3072-prefix workload");
        if(p.header+(long)COMMANDS_PER_CYCLE*p.normalFrame+p.finalExtra>profile.core().maxPendingSerializedBytes()+1024L)
            rejected.add("largest serialized workload prefix exceeds profile allocation cap");
        if(payload>WRITER_PAYLOAD_LIMIT||writerJobs*2>WRITER_TOTAL_FILE_LIMIT)rejected.add("writer payload/file hard cap");
        if(records>Math.min(1024,profile.maxMaintenanceJournalRecords())||journalBytes>profile.maxMaintenanceJournalBytes())rejected.add("finite four-offer ACK journal budget");
        if(raw>RAW_TRACE_LIMIT)rejected.add("derived raw trace exceeds finite 2GiB cap");
        if(allocation>ALLOCATED_GROWTH_LIMIT)rejected.add("derived payload/trace/native-reserve allocation exceeds 2.5GiB growth cap");
        return new Plan(arrivals,batchCap,cycles,totalEvents,logicalRpcs,arrivals,extras,negatives,payload,(int)writerJobs,
                base,allFour,raw,allocation,RUNTIME_FREE_FLOOR,records,journalBytes,p.normalFrame+p.finalExtra,p.header,
                archiveBytes,eventBytes,chunkRpcs,fetchRpcs,largestReply,rejected);
    }
    private static long eventFrameBytes(long count,Probe p) {
        long full=count/16,rest=count%16;
        return full*(4L+p.eventReplyOverhead+16L*p.maxEventWire)+(rest==0?0:4L+p.eventReplyOverhead+rest*p.maxEventWire);
    }
    private static long chunkReplyBytes(long archiveBytes,Probe p) {
        long count=ceil(archiveBytes,MAX_ARCHIVE_CHUNK);
        return count*(p.fullChunkReply-MAX_ARCHIVE_CHUNK)+archiveBytes;
    }
    private static int ceil(long count,int unit) { return Math.toIntExact((count+unit-1)/unit); }
    private static Probe probe(RetentionServiceV3.Profile profile,int batchCap) {
        String lineage="p".repeat(64);Scope scope=new Scope(profile.fingerprint(),lineage);
        var engine=new RetentionEngineV3(profile.core(),lineage);
        List<Command> commands=List.of(new Deposit(1,"fund",1,Asset.BASE,2),new Deposit(2,"fund",1,Asset.QUOTE,20),
                RetentionEngineV3.place(1,"seed",1,Side.SELL,10,2,TimeInForce.GTC),
                RetentionEngineV3.place(2,"load-w127",Long.MAX_VALUE-1,Side.BUY,10,1,TimeInForce.IOC),
                RetentionEngineV3.place(2,"load-w127",Long.MAX_VALUE,Side.BUY,10,1,TimeInForce.IOC));
        for(Command command:commands)if(!engine.execute(command).result().accepted())throw new IllegalArgumentException("profile cannot execute the bounded codec witness");
        var history=engine.pendingHistory();long retained=0;int setup=0;
        for(int i=0;i<history.size();i++){int bytes=history.get(i).canonicalBytes().length+36;retained+=bytes;if(i<3)setup+=bytes;}
        var archive=engine.archiveThrough(5);int header=Math.toIntExact(archive.canonicalBytes().length-retained);
        int normal=history.get(3).canonicalBytes().length+36,extra=history.get(4).canonicalBytes().length+36-normal;
        if(header<1||extra<0||history.get(3).execution().events().size()!=2||history.get(4).execution().events().size()!=2
                ||history.get(3).terminalOrders().size()!=1||history.get(4).terminalOrders().size()!=2)
            throw new IllegalStateException("workload codec witness shape changed; rederive capacity admission");
        Counters counters=new Counters(100,100,100,98,0,98,0,"");
        Command buy=commands.get(4);int singleRequest=RetentionWireV3.encode(new Request(scope,1,new BusinessBatch(List.of(buy)))).length;
        int singleReply=batchReplySize(scope,counters,List.of(buy));
        // A maximum cap does not guarantee packed frames: singleton bounds must dominate each possible k-member layout.
        for(int size=1;size<=batchCap;size++) {
            var batch=new ArrayList<Command>();for(int i=0;i<size;i++)batch.add(RetentionEngineV3.place(2,"load-w"+(127-i),Long.MAX_VALUE,Side.BUY,10,1,TimeInForce.IOC));
            if(RetentionWireV3.encode(new Request(scope,1,new BusinessBatch(batch))).length>size*singleRequest
                    ||batchReplySize(scope,counters,batch)>size*singleReply)throw new IllegalStateException("singleton codec bound no longer dominates batch layout");
        }
        int setupTrace=0;for(int i=0;i<3;i++)setupTrace+=RetentionWireV3.encode(new Request(scope,i+1,new Business(commands.get(i)))).length
                +RetentionReplyV3.encode(new Reply(scope,i+1,counters,new State(history.get(i).execution().result(),false,null),"")).length+24+256;
        var ack=archive.acknowledgementAfterExternalVerification();
        int prepareRequest=RetentionWireV3.encode(new Request(scope,1,new PrepareArchive(5))).length;
        int descriptor=RetentionReplyV3.encode(new Reply(scope,1,counters,new Descriptor(ack,4096),"")).length;
        int chunkRequest=RetentionWireV3.encode(new Request(scope,1,new ArchiveChunk(ack,4096,0,MAX_ARCHIVE_CHUNK))).length;
        int chunkReply=RetentionReplyV3.encode(new Reply(scope,1,counters,new Chunk(ack,4096,0,new byte[MAX_ARCHIVE_CHUNK]),"")).length;
        int fetchRequest=RetentionWireV3.encode(new Request(scope,1,new FetchEvents(1,16))).length;
        int eventOverhead=RetentionReplyV3.encode(new Reply(scope,1,counters,new Events(new EventBatch(0,100,List.of())),"")).length;
        int maxEvent=0;for(var entry:history)for(Event event:entry.execution().events())maxEvent=Math.max(maxEvent,
                RetentionReplyV3.encode(new Reply(scope,1,counters,new Events(new EventBatch(0,100,List.of(event))),"")).length-eventOverhead);
        var archiveOperation=new ArchiveCommit(new MaintenanceIdentity("archive",Long.MAX_VALUE),ack);
        var eventOperation=new EventAck(new MaintenanceIdentity("projector",Long.MAX_VALUE),100);
        var maintenance=new RetentionServiceV3.MaintenanceResult(RetentionServiceV3.MaintenanceCode.APPLIED,
                new RetentionEngineV3.CompactionResult(1,5,2,5,false),100,"",false);
        Counters ackCounters=new Counters(100,100,100,98,1,98,100,"");
        int ackReply=RetentionReplyV3.encode(new Reply(scope,1,ackCounters,new State(null,false,maintenance),"")).length;
        int eventAckReply=RetentionReplyV3.encode(new Reply(scope,1,ackCounters,new State(null,false,
                new RetentionServiceV3.MaintenanceResult(RetentionServiceV3.MaintenanceCode.APPLIED,null,100,"",false)),"")).length;
        return new Probe(header,setup,normal,extra,singleRequest,singleReply,setupTrace,prepareRequest,descriptor,chunkRequest,chunkReply,
                fetchRequest,eventOverhead,maxEvent,RetentionWireV3.encode(new Request(scope,1,archiveOperation)).length,ackReply,
                RetentionWireV3.encode(new Request(scope,1,eventOperation)).length,eventAckReply,
                RetentionWireV3.encodeOperation(archiveOperation).length,RetentionWireV3.encodeOperation(eventOperation).length);
    }
    private static int batchReplySize(Scope scope,Counters counters,List<Command> commands) {
        var entries=new ArrayList<BatchEntry>();
        for(int i=0;i<commands.size();i++) {
            Command command=commands.get(i);long seq=100-commands.size()+i+1;
            entries.add(new BatchEntry(i,RetentionWireV3.businessIdentity(command),RetentionWireV3.businessCanonicalSha256(command),
                    new Result(ResultCode.ACCEPTED,"accepted",seq,seq,0,1),false,BatchStatus.APPLIED,new Frontier(seq,seq,seq,seq-2)));
        }
        // Last frontier binds all four monotonic counters in the outer reply.
        Frontier last=entries.getLast().frontier();Counters bound=new Counters(last.applicationMutation(),last.businessSeq(),last.eventSeq(),last.marketSeq(),0,98,0,"");
        return RetentionReplyV3.encode(new Reply(scope,1,bound,new Batch(entries),"")).length;
    }
}
