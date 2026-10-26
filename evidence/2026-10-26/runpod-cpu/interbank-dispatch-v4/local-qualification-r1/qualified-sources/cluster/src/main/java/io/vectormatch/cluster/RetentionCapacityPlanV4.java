package io.vectormatch.cluster;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import java.util.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Admission for one fixed V4 workload. Bounds are not a capacity measurement. */
public final class RetentionCapacityPlanV4 {
    public static final int CUT=1536,READ_WINDOW=32,EVENT_PAGE=32,CHUNK=6144,WARMUP_RPC_LIMIT=1024;
    public static final long RAW_LIMIT=2L*1024*1024*1024,WRITER_LIMIT=1024L*1024*1024;
    public static final long FREE_FLOOR=1024L*1024*1024,NATIVE_RESERVE=512L*1024*1024;
    public record Config(int rate,boolean continueDuringFileWork){
        public Config{if(rate!=500&&rate!=1000&&rate!=2000&&rate!=4000&&rate!=6000)throw new IllegalArgumentException("V4 fixed20s rate500|1000|2000|4000|6000 required");}
        public int arrivals(){return Math.multiplyExact(rate,20);}
        public long windowNs(){return 20_000_000_000L;}
        public long offsetNs(int index){if(index<0||index>=arrivals())throw new IllegalArgumentException("finite arrival index");return 1_000_000_000L*index/rate;}
        public String policy(){return continueDuringFileWork?"CONTINUE":"PAUSE";}
    }
    public record Plan(int arrivals,int cycles,int maximumEntryBytes,int archiveHeaderBytes,
                       long maximumEvents,long maximumMaintenanceRpcs,long negativeOfferLimit,
                       long maximumArchiveBytes,long maximumEventBytes,long maximumReadYieldTurns,long writerPayloadBytes,int writerPayloadFiles,
                       long coordinatorTraceBytes,long allRawBytes,long allocatedGrowthBytes,long initialFreeBytes,
                       long journalRecords,long journalBytes,int maximumSingleBusinessRequest,int maximumSingleBusinessReply,
                       int maximumMaintenanceRequest,int maximumMaintenanceReply,List<String> rejections){
        public Plan{rejections=List.copyOf(rejections);}
        public boolean admitted(){return rejections.isEmpty();}
        public void requireAdmitted(){if(!admitted())throw new IllegalArgumentException("V4 finite admission refused:"+rejections);}
        public Map<String,Object> observation(){var m=new LinkedHashMap<String,Object>();m.put("schema","retention-v4-capacity-admission-1");m.put("arrivals",arrivals);m.put("cycles",cycles);m.put("cutCommands",CUT);m.put("readWindow",READ_WINDOW);m.put("eventPage",EVENT_PAGE);m.put("archiveChunkBytes",CHUNK);m.put("allocatedLogicalWorkers",128);m.put("activeLoadWorkers",127);m.put("reservedBootstrapWorker",0);m.put("allocatedQueuePositions",8192);m.put("activeLoadQueuePositions",8128);m.put("maximumEntryBytes",maximumEntryBytes);m.put("archiveHeaderBytes",archiveHeaderBytes);m.put("maximumEvents",maximumEvents);m.put("maximumMaintenanceRpcs",maximumMaintenanceRpcs);m.put("negativeOfferLimit",negativeOfferLimit);m.put("maximumReadYieldTurns",maximumReadYieldTurns);m.put("maximumReadYieldPhaseFrames",3L*maximumReadYieldTurns);m.put("maximumPositiveOffersPerOriginal",4);m.put("maximumArchiveBytes",maximumArchiveBytes);m.put("maximumEventBytes",maximumEventBytes);m.put("writerPayloadBytes",writerPayloadBytes);m.put("writerPayloadFiles",writerPayloadFiles);m.put("writerFilesIncludingReceipts",writerPayloadFiles*2);m.put("coordinatorTraceBytes",coordinatorTraceBytes);m.put("allRawBytes",allRawBytes);m.put("allocatedGrowthBytes",allocatedGrowthBytes);m.put("initialFreeBytes",initialFreeBytes);m.put("runtimeFreeFloor",FREE_FLOOR);m.put("journalRecords",journalRecords);m.put("journalBytes",journalBytes);m.put("maximumSingleBusinessRequest",maximumSingleBusinessRequest);m.put("maximumSingleBusinessReply",maximumSingleBusinessReply);m.put("maximumMaintenanceRequest",maximumMaintenanceRequest);m.put("maximumMaintenanceReply",maximumMaintenanceReply);m.put("admissionRejections",rejections);m.put("capacityProven",false);return Collections.unmodifiableMap(m);}
    }
    private record Witness(int header,int setupBytes,int maximumEntry,int singleRequest,int singleReply,
                           int maintenanceRequest,int maintenanceReply,int archiveOperation,int eventOperation){}
    private RetentionCapacityPlanV4(){}
    private static long ceil(long n,long d){return Math.floorDiv(Math.addExact(n,d-1),d);}
    public static Plan plan(Config config,RetentionServiceV3.Profile profile){
        Objects.requireNonNull(config);Objects.requireNonNull(profile);var w=witness(profile);int n=config.arrivals(),cycles=Math.toIntExact(ceil(n+3L,CUT));
        long archives=Math.addExact((long)n*w.maximumEntry+w.setupBytes,(long)cycles*w.header);
        long totalEvents=2L*n+3;
        // Per-cycle ceil adds at most one page/chunk;all cycles include their own headers.
        long chunks=ceil(archives,CHUNK)+cycles,fetches=ceil(totalEvents,EVENT_PAGE)+cycles;
        long rpcs=1L+WARMUP_RPC_LIMIT+chunks+fetches+3L*cycles;
        // Sum of per-cycle ceil(bank/page) is bounded by the aggregate ceil plus one per cycle.
        // Every nonfinal bank may add YIELD,DRAIN,resume; both controls reserve the same bytes.
        long readYieldTurns=ceil(chunks,READ_WINDOW)+ceil(fetches,READ_WINDOW)+2L*cycles;
        int eventReply=maxEncodedEventsReplyBytes(EVENT_PAGE);
        long eventBytes=fetches*(4L+eventReply);
        long intentBytes=cycles*2L*(32+MAX_REQUEST_BYTES);
        int jobs=4*cycles;long writerBytes=archives+eventBytes+intentBytes;
        long journalRecords=8L*cycles,journalBytes=4L*cycles*(w.archiveOperation+w.eventOperation+2048L);
        long frames=n+rpcs,negatives=frames;
        // Original requests are recorded once per correlation;all four possible replies and every offer code remain.
        long network=(long)n*(w.singleRequest+12L+4L*(w.singleReply+12L))
                +rpcs*(w.maintenanceRequest+12L+4L*(w.maintenanceReply+12L));
        long logical=rpcs*(48L+w.maintenanceRequest+w.maintenanceReply+3L*(24+2048))
                +(long)cycles*(24L*(24+2048)+4L*(24+8192))+3L*readYieldTurns*(24+2048)+1024L*1024;
        long raw=network+logical+frames*(128L+5L*128)+(long)n*640+4L*1024*1024;
        long allocation=raw+writerBytes+jobs*1024L+2048L*4096+NATIVE_RESERVE;
        var failures=new ArrayList<String>();
        if(cycles>128||jobs>512||journalRecords>Math.min(1024,profile.maxMaintenanceJournalRecords())||journalBytes>profile.maxMaintenanceJournalBytes())failures.add("finite cut/file/four-offer journal bound");
        if(writerBytes>WRITER_LIMIT||raw>RAW_LIMIT||logical>512L*1024*1024||allocation>5L*1024*1024*1024/2)failures.add("finite payload/raw/trace/2.5GiB growth bound");
        if(profile.core().maxPendingCommands()<4096||profile.core().maxPendingEvents()<8192||profile.outboxCapacity()<8192||profile.core().limits().maxProducers()<128)failures.add("exact finite profile headroom");
        if(w.header+(long)CUT*w.maximumEntry+w.setupBytes>profile.core().maxPendingSerializedBytes()+1024L)failures.add("largest canonical prefix allocation cap");
        if(w.maintenanceReply>MAX_REPLY_BYTES||w.maintenanceRequest>MAX_REQUEST_BYTES)failures.add("complete bounded wire envelope");
        return new Plan(n,cycles,w.maximumEntry,w.header,totalEvents,rpcs,negatives,archives,eventBytes,readYieldTurns,writerBytes,jobs,logical,raw,allocation,allocation+FREE_FLOOR,journalRecords,journalBytes,w.singleRequest,w.singleReply,w.maintenanceRequest,w.maintenanceReply,failures);
    }
    private static Witness witness(RetentionServiceV3.Profile profile){
        String lineage="p".repeat(64);var scope=new Scope(profile.fingerprint(),lineage);var engine=new RetentionEngineV3(profile.core(),lineage);
        var commands=List.<Command>of(new Deposit(1,"maker",1,Asset.BASE,2),new Deposit(2,"load-w1",1,Asset.QUOTE,20),
                RetentionEngineV3.place(1,"maker",2,Side.SELL,10,2,TimeInForce.GTC),
                RetentionEngineV3.place(2,"load-w127",Long.MAX_VALUE-1,Side.BUY,10,1,TimeInForce.IOC),RetentionEngineV3.place(2,"load-w127",Long.MAX_VALUE,Side.BUY,10,1,TimeInForce.IOC));
        for(var command:commands)if(!engine.execute(command).result().accepted())throw new IllegalArgumentException("profile cannot execute exact V4 codec witness");
        var entries=engine.pendingHistory();int retained=0,setup=0;
        for(int i=0;i<entries.size();i++){int bytes=entries.get(i).canonicalBytes().length+36;retained+=bytes;if(i<3)setup+=bytes;}
        if(entries.get(3).execution().events().size()!=2||entries.get(4).execution().events().size()!=2||entries.get(3).terminalOrders().size()!=1||entries.get(4).terminalOrders().size()!=2)throw new IllegalStateException("V4 one-unit/final-maker witness changed");
        var archive=engine.archiveThrough(5);var ack=archive.acknowledgementAfterExternalVerification();int header=archive.canonicalBytes().length-retained;
        int entry=Math.max(entries.get(3).canonicalBytes().length,entries.get(4).canonicalBytes().length)+36;
        int single=RetentionWireV3.encode(new Request(scope,Long.MAX_VALUE,new BusinessBatch(List.of(commands.get(4))))).length;
        int reply=maxEncodedBatchReplyBytes(1);
        var batch=new ArrayList<Command>();for(int i=0;i<4;i++)batch.add(RetentionEngineV3.place(2,"load-w"+(124+i),Long.MAX_VALUE,Side.BUY,10,1,TimeInForce.IOC));
        for(int count=1;count<=4;count++)if(RetentionWireV3.encode(new Request(scope,1,new BusinessBatch(batch.subList(0,count)))).length>(long)count*single||maxEncodedBatchReplyBytes(count)>(long)count*reply)throw new IllegalStateException("per-logical-command batch envelope inequality changed");
        var archiveOp=new ArchiveCommit(new MaintenanceIdentity("archive",Long.MAX_VALUE),ack);var eventOp=new EventAck(new MaintenanceIdentity("projector",Long.MAX_VALUE),Long.MAX_VALUE);
        int request=0;for(var op:List.<Operation>of(new PrepareArchive(Long.MAX_VALUE),new ArchiveChunk(ack,CHUNK+1,0,CHUNK),new FetchEvents(1,EVENT_PAGE),new Position(),archiveOp,eventOp))request=Math.max(request,RetentionWireV3.encode(new Request(scope,Long.MAX_VALUE,op)).length);
        return new Witness(header,setup,entry,single,reply,request,Math.max(maxEncodedArchiveChunkReplyBytes(CHUNK),maxEncodedEventsReplyBytes(EVENT_PAGE)),RetentionWireV3.encodeOperation(archiveOp).length,RetentionWireV3.encodeOperation(eventOp).length);
    }
}
