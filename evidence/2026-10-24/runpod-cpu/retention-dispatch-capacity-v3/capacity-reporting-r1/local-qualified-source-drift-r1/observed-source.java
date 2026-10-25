package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import java.io.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;
import java.util.function.Consumer;
import static io.vectormatch.cluster.RetentionCapacityLedgerV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Deterministic finite open-loop V3 source. Maintenance may stop dispatch, never its arrival clock. */
public final class RetentionCapacityExperimentV3 {
    public static final long TASK_LIFETIME_NS=TimeUnit.SECONDS.toNanos(90),RPC_PERMIT_NS=TimeUnit.SECONDS.toNanos(2),DRAIN_NS=TimeUnit.SECONDS.toNanos(90);
    public record Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope,boolean commonReadWindow32Envelope,boolean maintainedCapacityPreset,boolean commonReadWindow128Envelope,boolean rotatingDispatch,boolean fineDispatchCapacityPreset){
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope,boolean commonReadWindow32Envelope,boolean maintainedCapacityPreset,boolean commonReadWindow128Envelope,boolean rotatingDispatch){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,eventFetchCount,commonEventFetchEnvelope,commonReadWindow32Envelope,maintainedCapacityPreset,commonReadWindow128Envelope,rotatingDispatch,false);}
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope,boolean commonReadWindow32Envelope,boolean maintainedCapacityPreset,boolean commonReadWindow128Envelope){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,eventFetchCount,commonEventFetchEnvelope,commonReadWindow32Envelope,maintainedCapacityPreset,commonReadWindow128Envelope,false);}
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope,boolean commonReadWindow32Envelope,boolean maintainedCapacityPreset){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,eventFetchCount,commonEventFetchEnvelope,commonReadWindow32Envelope,maintainedCapacityPreset,false);}
        public static Config readWindow128Capacity(int window){return new Config(20000,1000,4,MAX_SUPPORTED_ARCHIVE_CHUNK,window,true,32,false,false,false,true);}
        public static Config maintainedReadWindow128Capacity(int rate){int arrivals=maintainedCapacityArrivals(rate);return new Config(arrivals,rate,4,MAX_SUPPORTED_ARCHIVE_CHUNK,128,true,32,false,false,true,true);}
        public static Config read128DispatchFairness(boolean rotating){return new Config(160000,8000,4,MAX_SUPPORTED_ARCHIVE_CHUNK,128,true,32,false,false,true,true,rotating);}
        public static Config read128DispatchCapacity(int rate,boolean rotating){return new Config(dispatchCapacityArrivals(rate),rate,4,MAX_SUPPORTED_ARCHIVE_CHUNK,128,true,32,false,false,true,true,rotating,true);}
        static int dispatchCapacityArrivals(int rate){if(rate!=4000&&rate!=6000&&rate!=7000&&rate!=7500&&rate!=8000)throw new IllegalArgumentException("dispatch capacity requires explicit4000|6000|7000|7500|8000 rate preset");return Math.multiplyExact(rate,20);}

        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope,boolean commonReadWindow32Envelope){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,eventFetchCount,commonEventFetchEnvelope,commonReadWindow32Envelope,false);}
        public static Config maintainedCapacity(int rate){int arrivals=maintainedCapacityArrivals(rate);return new Config(arrivals,rate,4,MAX_SUPPORTED_ARCHIVE_CHUNK,32,true,32,false,true,true);}
        static int maintainedCapacityArrivals(int rate){if(rate!=500&&rate!=1000&&rate!=2000&&rate!=4000&&rate!=8000&&rate!=16000)throw new IllegalArgumentException("maintained capacity requires explicit500|1000|2000|4000|8000|16000 rate preset");return Math.multiplyExact(rate,20);}
        /** Source-compatible existing eight-credit/page experiment configuration. */
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,eventFetchCount,commonEventFetchEnvelope,false);}
        public static Config readWindow32LongCuts(int page,int window){return new Config(33792,500,4,MAX_SUPPORTED_ARCHIVE_CHUNK,window,true,page,false,true);}
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,DEFAULT_EVENT_FETCH_COUNT,false);}
        /** Opt-in single-factor event-page experiment, fixed cap4/chunk6144/read8. */
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,int eventFetchCount){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,true,eventFetchCount,true);}
        public Config(int arrivals,int rate,int batchCap){this(arrivals,rate,batchCap,DEFAULT_ARCHIVE_CHUNK,1,false);}
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes){this(arrivals,rate,batchCap,archiveChunkBytes,1,false);}
        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,true);}
        public Config{
            if(fineDispatchCapacityPreset&&(!commonReadWindow128Envelope||!maintainedCapacityPreset))throw new IllegalArgumentException("fine dispatch capacity requires explicit maintained read128 envelope");
            if(rotatingDispatch&&(!commonReadWindow128Envelope||!maintainedCapacityPreset||(fineDispatchCapacityPreset?arrivals!=dispatchCapacityArrivals(rate):(arrivals!=160000||rate!=8000))))throw new IllegalArgumentException("rotating dispatch requires explicit read128 fairness or fine capacity configuration");
            requireArchiveChunkBytes(archiveChunkBytes);
            if(commonReadWindow128Envelope){
                RetentionCapacityPlanV3.requireReadWindow128(readWindow);
                if(commonReadWindow32Envelope||(maintainedCapacityPreset?(arrivals!=(fineDispatchCapacityPreset?dispatchCapacityArrivals(rate):maintainedCapacityArrivals(rate))||readWindow!=128):(arrivals!=20000||rate!=1000))||batchCap!=4||archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK||!commonReadWindowEnvelope||commonEventFetchEnvelope||eventFetchCount!=32)throw new IllegalArgumentException("read128 requires fixed20000@1000/cap4/chunk6144/page32 and exclusive128 envelope");
            }else if(commonReadWindow32Envelope){
                RetentionCapacityPlanV3.requireReadWindow32(readWindow);
                if((maintainedCapacityPreset?(arrivals!=maintainedCapacityArrivals(rate)||eventFetchCount!=32||readWindow!=32):(arrivals!=33792||rate!=500))||batchCap!=4||archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK||!commonReadWindowEnvelope||commonEventFetchEnvelope)throw new IllegalArgumentException("read-window32 requires fixed LONG33792@500/cap4/chunk6144 and one explicit fixed page");
            }else{if(maintainedCapacityPreset)throw new IllegalArgumentException("capacity preset requires explicit32-credit envelope");RetentionCapacityPlanV3.requireReadWindow(readWindow);}
            requireEventFetchCount(eventFetchCount);
            if((commonEventFetchEnvelope&&(!commonReadWindowEnvelope||batchCap!=4||archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK||readWindow!=8))||(!commonEventFetchEnvelope&&!commonReadWindow32Envelope&&!commonReadWindow128Envelope&&eventFetchCount!=DEFAULT_EVENT_FETCH_COUNT))throw new IllegalArgumentException("event-page selection requires explicit fixed cap4/chunk6144/read8 common envelope");
            if(arrivals<1||arrivals>MAX_ARRIVALS||rate<1||(batchCap!=1&&batchCap!=4)||1_000_000_000L*arrivals/rate<TimeUnit.SECONDS.toNanos(10)||1_000_000_000L*arrivals/rate>TimeUnit.SECONDS.toNanos(120)
                    ||(commonReadWindowEnvelope&&(batchCap!=4||archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK))||(!commonReadWindowEnvelope&&readWindow!=1))
                throw new IllegalArgumentException("finite source10..120sec; explicit read-window experiment requires cap4/chunk6144/window1or8");
        }
        public long windowNs(){return 1_000_000_000L*arrivals/rate;}
        public String dispatchOrderPolicy(){return rotatingDispatch?"ROTATING_CONTINUE":"FIXED_ZERO_START";}
        public long offsetNs(int index){return 1_000_000_000L*index/rate;}
    }
    public record Result(Path directory,Map<String,Object> summary){}
    private final Path root,stateRoot;
    private final Config config;
    private final RetentionServiceV3.Profile profile;
    private final String lineage;
    private final RetentionCapacityPlanV3.Plan plan;
    private final RetentionCapacityDiskGuardV3 disk;
    private final RetentionIdlePolicyV3.Selection idleSelection;
    private final RetentionOwnerPollPolicyV3.Selection ownerPollSelection;
    private final RetentionCapacityLedgerV3 rows;
    private final AtomicReference<Throwable> abort=new AtomicReference<>();
    private final AtomicBoolean stopping=new AtomicBoolean(),schedulerDone=new AtomicBoolean();
    private final AtomicInteger pendingCount=new AtomicInteger(),phase=new AtomicInteger();
    private final RetentionBatchOwnerV3.Ticket[] pending=new RetentionBatchOwnerV3.Ticket[WORKERS];
    private final int[] pendingRows=new int[WORKERS];
    private final List<long[]> backlog=new ArrayList<>(256);
    private final RawBudget rawBudget;
    private final Tape tape;
    private RetentionBatchOwnerV3 owner;
    private RetentionDurableWriterV3 writer;
    private RetentionBatchMaintenanceV3 maintenance;
    private Thread scheduler,sampler;
    private long origin,windowEnd,latestBusiness=3,exposureEnd=MISSING,drainEnd=MISSING;
    private String originUtc;
    private final RetentionBatchMaintenanceV3.RunBudget journalBudget;
    private int cycles;
    private Throwable primary;

    private RetentionCapacityExperimentV3(Path newRoot,Path ownedStateRoot,Config config,RetentionServiceV3.Profile profile,String lineage,RetentionCapacityPlanV3.Plan plan,RetentionCapacityDiskGuardV3 disk)throws IOException{
        ownerPollSelection=RetentionOwnerPollPolicyV3.systemSelection();
        idleSelection=RetentionIdlePolicyV3.systemSelection();
        this.config=Objects.requireNonNull(config);this.profile=Objects.requireNonNull(profile);this.plan=Objects.requireNonNull(plan);plan.requireAdmitted();this.disk=Objects.requireNonNull(disk);
        if(plan.arrivals()!=config.arrivals()||plan.batchCap()!=config.batchCap()||plan.archiveChunkBytes()!=config.archiveChunkBytes()||plan.requestedReadWindow()!=config.readWindow()||plan.commonReadWindowEnvelope()!=config.commonReadWindowEnvelope()||plan.eventFetchCount()!=config.eventFetchCount()||plan.commonEventFetchEnvelope()!=config.commonEventFetchEnvelope()||plan.commonReadWindow32Envelope()!=config.commonReadWindow32Envelope()||!disk.plan().equals(plan)||!disk.ownedRoot().equals(ownedStateRoot.toAbsolutePath().normalize()))throw new IllegalArgumentException("exact config/plan/full-owned-root disk binding required");
        this.lineage=new Scope(profile.fingerprint(),lineage).lineageId();
        root=newRoot.toAbsolutePath().normalize();stateRoot=ownedStateRoot.toAbsolutePath().normalize();Files.createDirectory(root);
        rows=new RetentionCapacityLedgerV3(config.arrivals());journalBudget=new RetentionBatchMaintenanceV3.RunBudget(profile);
        rawBudget=new RawBudget(plan.maximumRawTraceBytes(),Math.addExact(4096L,640L*config.arrivals()));tape=new Tape();
    }
    public static Result run(Path newRoot,Path ownedStateRoot,Config config,RetentionServiceV3.Profile profile,String lineage,RetentionBatchOwnerV3.IOFactory factory)throws Exception{
        throw new IllegalArgumentException("full-owned-root fresh DiskGuard/codec Plan must be supplied via explicit overload before nodes start");
    }
    public static Result run(Path newRoot,Path ownedStateRoot,Config config,RetentionServiceV3.Profile profile,String lineage,RetentionBatchOwnerV3.IOFactory factory,RetentionCapacityPlanV3.Plan plan,RetentionCapacityDiskGuardV3 disk)throws Exception{
        var run=new RetentionCapacityExperimentV3(newRoot,ownedStateRoot,config,profile,lineage,plan,disk);return run.execute(factory);
    }
    public static RetentionCapacityPlanV3.Plan boundedPlan(Config config,RetentionServiceV3.Profile profile){
        var full=RetentionCapacityPlanV3.plan(config.arrivals(),config.batchCap(),profile);
        if(config.commonReadWindow128Envelope()&&config.maintainedCapacityPreset())return RetentionCapacityPlanV3.maintainedReadWindow128Plan(config.rate(),profile,config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
        if(config.commonReadWindow128Envelope())return RetentionCapacityPlanV3.commonReadWindow128Plan(config.readWindow(),profile,config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
        if(config.maintainedCapacityPreset())return RetentionCapacityPlanV3.maintainedCapacityPlan(config.rate(),profile,config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
        if(config.commonReadWindow32Envelope())return RetentionCapacityPlanV3.commonReadWindow32Plan(config.arrivals(),config.batchCap(),profile,config.eventFetchCount(),config.readWindow(),config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
        if(config.commonEventFetchEnvelope())return RetentionCapacityPlanV3.commonEventFetchPlan(config.arrivals(),config.batchCap(),profile,config.eventFetchCount(),config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
        if(config.commonReadWindowEnvelope())return RetentionCapacityPlanV3.commonReadWindowPlan(config.arrivals(),config.batchCap(),profile,config.readWindow(),config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
        return RetentionCapacityPlanV3.commonChunkPlan(config.arrivals(),config.batchCap(),profile,config.archiveChunkBytes(),config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
    }
    private Result execute(RetentionBatchOwnerV3.IOFactory factory)throws Exception{
        boolean arraysSaved=false;
        try{
            // Exact finite admission/disk plan is recorded separately; no cloud resource is created here.
            disk.check();RetentionCapacityJsonV3.writeNew(root.resolve("admission-plan.json"),plan.observation());
            writer=new RetentionDurableWriterV3(root.resolve("writer"),profile.core().maxPendingSerializedBytes()+1024,1024L*1024*1024,512);
            owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile,lineage,config.batchCap()),()->tape.attach(factory.open()),ownerPollSelection.effectiveMaximumParkNs());
            maintenance=new RetentionBatchMaintenanceV3(owner,writer,profile,lineage,root.resolve("maintenance"),journalBudget,plan.maximumLogicalMaintenanceRpcs(),config.archiveChunkBytes(),config.readWindow(),config.eventFetchCount(),config.commonReadWindow32Envelope(),config.commonReadWindow128Envelope());
            Instant wall=Instant.now();long mono=System.nanoTime();origin=mono+TimeUnit.SECONDS.toNanos(1);originUtc=wall.plusNanos(origin-mono).toString();windowEnd=origin+config.windowNs();
            writeConfiguration();scheduler=new Thread(this::schedule,"v3-capacity-arrivals");sampler=new Thread(this::sample,"v3-capacity-backlog-observer");scheduler.start();sampler.start();
            dispatch();drainEnd=System.nanoTime();
        }catch(Throwable failure){primary=failure;abort.compareAndSet(null,failure);}
        finally{
            stopping.set(true);joinOwned(scheduler,5);joinOwned(sampler,5);
            long now=System.nanoTime();rows.rejectQueued(now,primary==null?HARD_DRAIN:RUN_ABORTED);
            for(int worker=0;worker<WORKERS;worker++)if(pending[worker]!=null){int index=pendingRows[worker];observe(index,pending[worker]);rows.status[index]=UNKNOWN_FINAL;if(rows.unknownObserved[index]==MISSING)rows.unknownObserved[index]=now;pending[worker].revoke();}
            if(owner!=null){
                try{RetentionCapacityJsonV3.writeNew(root.resolve("owner-before-close.json"),owner.snapshot());}catch(Throwable failure){recordFailure(failure);}
                try{owner.close();}catch(Throwable failure){recordFailure(failure);}
                try{RetentionCapacityJsonV3.writeNew(root.resolve("transport-observations.json"),owner.transportSamples());}catch(Throwable failure){recordFailure(failure);}
                try{RetentionCapacityJsonV3.writeNew(root.resolve("owner-after-close.json"),owner.snapshot());}catch(Throwable failure){recordFailure(failure);}
            }
            if(maintenance!=null)try{maintenance.close();}catch(Throwable failure){recordFailure(failure);}
            if(writer!=null){try{writer.close();}catch(Throwable failure){recordFailure(failure);}finally{try{RetentionCapacityJsonV3.writeNew(root.resolve("writer-after-close.json"),writer.snapshot());}catch(Throwable failure){recordFailure(failure);}}}
            try{tape.closeFiles();}catch(Throwable failure){recordFailure(failure);}
            try{saveArrivals();arraysSaved=true;}catch(Throwable failure){recordFailure(failure);}
        }
        Map<String,Object> summary=summary();summary.put("perArrivalCsvComplete",arraysSaved);summary.put("sourceFailureType",primary==null?null:primary.getClass().getName());
        RetentionCapacityJsonV3.writeNew(root.resolve(primary==null?"load-result.json":"failure.json"),summary);
        if(primary!=null){if(primary instanceof Exception error)throw error;if(primary instanceof Error error)throw error;throw new IllegalStateException(primary);}
        return new Result(root,Collections.unmodifiableMap(summary));
    }
    private void recordFailure(Throwable failure){if(primary==null)primary=failure;else if(primary!=failure)primary.addSuppressed(failure);}
    private void writeConfiguration()throws IOException{
        var values=new LinkedHashMap<String,Object>();values.put("schema","retention-v3-openloop-capacity-v1");values.put("dispatchOrderPolicy",config.dispatchOrderPolicy());values.put("arrivals",config.arrivals());values.put("ratePerSecond",config.rate());values.put("windowSeconds",config.windowNs()/1e9);values.put("batchCap",config.batchCap());values.put("archiveChunkBytes",config.archiveChunkBytes());values.put("eventFetchCount",config.eventFetchCount());if(config.commonEventFetchEnvelope())values.put("commonEventFetchEnvelope",true);if(config.commonReadWindow32Envelope())values.put("commonReadWindow32Envelope",true);if(config.commonReadWindow128Envelope())values.put("commonReadWindow128Envelope",true);if(config.maintainedCapacityPreset())values.put("maintainedCapacityPreset",true);values.put("commonChunkEnvelope",plan.commonChunkEnvelope());values.put("readWindow",config.readWindow());values.put("commonReadWindowEnvelope",plan.commonReadWindowEnvelope());values.put("maintenanceTimingSchema","13cols-correlation-phase-window-v1");values.put("readCreditPolicy","reserve+flush before arm; completed-unconsumed holds credit; consume after reply/timing flush");values.put("logicalWorkers",WORKERS);values.put("taskQueueCapacityPerWorker",QUEUE_CAPACITY);values.put("externalQueuePositions",8192);values.put("internalPendingCapacity",128);values.put("physicalSessions",1);values.put("sharedMediaDrivers",1);values.put("producerIdentityRule","worker=index%128;sequence=1+index/128;queue rejection leaves a legal gap");values.put("taskLifetimeNs",TASK_LIFETIME_NS);values.put("physicalOfferPermitNsFromDispatch",RPC_PERMIT_NS);values.put("physicalAdmissionTimestampSemantics","monotonic return observation after the first nonnegative publication.offer; not an exact internal Aeron admission instant");values.put("drainAdmissionNs",DRAIN_NS);values.put("batchFlushNs",50000);values.put("profileSha256",profile.fingerprint());values.put("actualCodeSha256",RetentionNodeMainV3.codeFingerprint());values.put("lineage",lineage);values.put("scheduledOriginUTC",originUtc);values.put("scheduledOriginMonotonicNs",origin);values.put("primitiveArrivalColumnBytes",rows.primitiveColumnBytes());values.put("arrivalClockPausesForMaintenance",false);values.put("maintenanceDispatchPolicy","drain pending while arrivals keep enqueuing/rejecting; exactprefix force/readback thenACK");values.put("scope","Finite openloop source; external canonical/leader/config proof required before any stability or capacity claim");if(idleSelection.explicit())values.put("retentionIdleSelection",idleSelection.observation());if(ownerPollSelection.explicit()){values.put("ownerPollSelection",ownerPollSelection.observation());values.put("ownerPollActual",ownerPollSelection.actualObservation(owner));}RetentionCapacityJsonV3.writeNew(root.resolve("configuration.json"),values);
    }
    private void schedule(){
        try{
            for(int index=0;index<config.arrivals()&&!stopping.get();index++){
                long target=origin+config.offsetNs(index);while(!stopping.get()){long wait=target-System.nanoTime();if(wait<=0)break;LockSupport.parkNanos(Math.min(wait,1_000_000));}
                if(stopping.get())break;rows.release(index,target,System.nanoTime());
            }
            while(!stopping.get()&&System.nanoTime()-windowEnd<0)LockSupport.parkNanos(Math.min(1_000_000,windowEnd-System.nanoTime()));
            exposureEnd=System.nanoTime();schedulerDone.set(true);
        }catch(Throwable failure){abort.compareAndSet(null,failure);schedulerDone.set(true);}
    }
    private void dispatch()throws Exception{
        boolean requestMaintenance=false;
        var dispatchOrder=new RetentionCapacityDispatchOrderV3(config.rotatingDispatch());
        while(true){
            Throwable failure=abort.get();if(failure!=null)throw new IllegalStateException("source/observer abort",failure);
            long now=System.nanoTime();int work=completePending(now);
            if(now-windowEnd>=DRAIN_NS)break;
            long pendingN=pendingCount.get();
            if(latestBusiness-journalBudget.archivedThrough()+pendingN>=RetentionBatchMaintenanceV3.COMMAND_CUT)requestMaintenance=true;
            boolean finalEmpty=schedulerDone.get()&&rows.queued()==0&&pendingN==0;
            if(requestMaintenance&&pendingN==0&&!finalEmpty&&latestBusiness-journalBudget.archivedThrough()<RetentionBatchMaintenanceV3.COMMAND_CUT)requestMaintenance=false;
            if((requestMaintenance||finalEmpty)&&pendingN==0&&latestBusiness>journalBudget.archivedThrough()){
                phase.set(1);maintenance.exportThrough(latestBusiness);cycles++;phase.set(0);requestMaintenance=false;work++;
            }
            if(finalEmpty&&latestBusiness==journalBudget.archivedThrough())break;
            if(!requestMaintenance){
                int firstWorker=dispatchOrder.begin();
                for(int offset=0;offset<WORKERS;offset++){int worker=RetentionCapacityDispatchOrderV3.worker(firstWorker,offset);if(pending[worker]==null){
                    if(latestBusiness-journalBudget.archivedThrough()+pendingCount.get()+1>RetentionBatchMaintenanceV3.COMMAND_CUT){dispatchOrder.deferredAtCut(worker);requestMaintenance=true;break;}
                    Integer index=rows.poll(worker);if(index==null)continue;now=System.nanoTime();rows.dispatch[index]=now;
                    dispatchOrder.taken(worker);
                    if(now-(origin+config.offsetNs(index)+TASK_LIFETIME_NS)>=0){rows.status[index]=NOT_SENT;rows.reason[index]=EXPIRED_BEFORE_DISPATCH;rows.end[index]=now;continue;}
                    Command command=command(index);long deadline=Math.min(origin+config.offsetNs(index)+TASK_LIFETIME_NS,now+RPC_PERMIT_NS);
                    rows.submit[index]=System.nanoTime();pending[worker]=owner.submit(worker,command,deadline);pendingRows[worker]=index;pendingCount.incrementAndGet();rows.status[index]=PENDING;work++;
                }}
            }
            if(work==0)LockSupport.parkNanos(50_000);
        }
    }
    private Command command(int index){return RetentionEngineV3.place(2,producer(worker(index)),producerSequence(index),Side.BUY,10,1,TimeInForce.IOC);}
    private int completePending(long now){
        int count=0;for(int worker=0;worker<WORKERS;worker++)if(pending[worker]!=null){
            int index=pendingRows[worker];var ticket=pending[worker];
            if(ticket.isDone()){
                var outcome=ticket.await(Duration.ofMillis(1));observe(index,ticket);
                if(outcome.terminal()==RetentionBatchOwnerV3.Terminal.NOT_SENT){rows.status[index]=NOT_SENT;rows.reason[index]=EXPIRED_BEFORE_DISPATCH;if(rows.end[index]==MISSING)rows.end[index]=now;}
                else{rows.status[index]=APPLIED;var result=outcome.result();rows.resultCode[index]=(byte)result.code().ordinal();rows.replayed[index]=(byte)(outcome.replayed()?1:0);rows.commandSeq[index]=result.commandSeq();rows.orderId[index]=result.orderId();rows.remaining[index]=result.remainingQuantity();rows.tradeCount[index]=result.tradeCount();latestBusiness=Math.max(latestBusiness,outcome.frontier().businessSeq());}
                if(rows.correlation[index]!=MISSING)tape.retireBusiness(rows.correlation[index]);pending[worker]=null;pendingCount.decrementAndGet();count++;
            }else if(rows.unknownObserved[index]==MISSING&&rows.submit[index]!=MISSING&&now-rows.submit[index]>=RPC_PERMIT_NS){observe(index,ticket);rows.unknownObserved[index]=now;ticket.revoke();}
        }return count;
    }
    private void observe(int index,RetentionBatchOwnerV3.Ticket ticket){Map<String,Object> view=ticket.observation();rows.firstOffer[index]=number(view,"firstWireOfferCallNs");rows.firstPhysicalAdmission[index]=number(view,"firstPhysicalAdmissionNs");rows.end[index]=number(view,"replyCompletionNs");rows.correlation[index]=number(view,"correlationId");Object batch=view.get("batchIndex");rows.batchIndex[index]=batch==null?-1:((Number)batch).intValue();rows.admittedPhysicalOffers[index]=((Number)view.get("admittedPhysicalOfferCount")).longValue();Object initial=view.get("initialAdmissionStatus");if(initial!=null)rows.serverAdmission[index]=(byte)BatchStatus.valueOf(initial.toString()).ordinal();}
    private static long number(Map<String,Object> map,String key){Object value=map.get(key);return value==null?MISSING:((Number)value).longValue();}
    private void sample(){
        try(var stream=new DataOutputStream(rawBudget.open(root.resolve("backlog.csv"),false))){
            stream.writeBytes("offset_ns,queued,pending,maintenance_phase,released,usable_bytes,owned_allocated_bytes,disk_observer_elapsed_ns\n");
            while(!stopping.get()){
                long now=System.nanoTime();int queued=rows.queued(),pendingN=pendingCount.get();long free=Files.getFileStore(stateRoot).getUsableSpace();
                long checkStart=System.nanoTime();var allocated=disk.check();long observerNs=System.nanoTime()-checkStart;
                if(free<plan.minimumFreeRuntimeBytes())throw new IOException("SOURCE_DISK_FREE_FLOOR");
                long[] sample={now-origin,queued,pendingN,phase.get(),rows.released.get(),free};synchronized(backlog){if(backlog.size()>=256)throw new IOException("bounded sampler rows exceeded");backlog.add(sample);}
                stream.writeBytes(sample[0]+","+queued+","+pendingN+","+sample[3]+","+sample[4]+","+free+","+allocated.allocatedBytes()+","+observerNs+"\n");stream.flush();LockSupport.parkNanos(TimeUnit.SECONDS.toNanos(1));
            }
        }catch(Throwable failure){abort.compareAndSet(null,failure);}
    }
    private void joinOwned(Thread thread,int seconds){if(thread==null)return;if(thread==scheduler||thread==sampler)LockSupport.unpark(thread);boolean interrupted=Thread.interrupted();long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(seconds);while(thread.isAlive()&&System.nanoTime()-until<0)try{thread.join(20);}catch(InterruptedException error){interrupted=true;}if(interrupted)Thread.currentThread().interrupt();if(thread.isAlive())recordFailure(new IllegalStateException("owned source thread did not stop: "+thread.getName()));}
    private void saveArrivals()throws IOException{
        try(var stream=new BufferedOutputStream(Files.newOutputStream(root.resolve("arrivals.csv"),StandardOpenOption.CREATE_NEW),65536)){
            stream.write("arrival_index,worker,producer,request_seq,command_sha256,scheduled_offset_ns,arrival_offset_ns,dispatch_offset_ns,submit_offset_ns,first_wire_offer_call_offset_ns,first_successful_offer_return_offset_ns,reply_completion_offset_ns,unknown_observed_offset_ns,correlation_id,batch_index,admitted_physical_offers,status,not_sent_reason,result_code,initial_server_admission_status,reply_replayed,command_seq,order_id,remaining_quantity,trade_count\n".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
            for(int i=0;i<config.arrivals();i++){
                String line=i+","+worker(i)+","+producer(worker(i))+","+producerSequence(i)+","+businessCanonicalSha256(command(i))+","+config.offsetNs(i)+","+offset(rows.arrival[i])+","+offset(rows.dispatch[i])+","+offset(rows.submit[i])+","+offset(rows.firstOffer[i])+","+offset(rows.firstPhysicalAdmission[i])+","+offset(rows.end[i])+","+offset(rows.unknownObserved[i])+","+absolute(rows.correlation[i])+","+(rows.batchIndex[i]<0?"":rows.batchIndex[i])+","+rows.admittedPhysicalOffers[i]+","+status(rows.status[i])+","+rows.reason[i]+","+(rows.resultCode[i]<0?"":ResultCode.values()[rows.resultCode[i]].name())+","+(rows.serverAdmission[i]<0?"":BatchStatus.values()[rows.serverAdmission[i]].name())+","+(rows.replayed[i]!=0)+","+absolute(rows.commandSeq[i])+","+absolute(rows.orderId[i])+","+absolute(rows.remaining[i])+","+absolute(rows.tradeCount[i])+"\n";
                byte[] bytes=line.getBytes(java.nio.charset.StandardCharsets.US_ASCII);if(bytes.length>640)throw new IOException("bounded per-arrival row exceeded640bytes");rawBudget.csvBytes+=bytes.length;stream.write(bytes);
            }
        }
    }
    private String offset(long value){return value==MISSING?"":Long.toString(value-origin);}
    private static String absolute(long value){return value==MISSING?"":Long.toString(value);}
    private static String status(byte value){return switch(value){case QUEUED->"QUEUED";case PENDING->"PENDING";case APPLIED->"APPLIED";case NOT_SENT->"NOT_SENT";case UNKNOWN_FINAL->"UNKNOWN_FINAL";default->"UNRELEASED_RUN_ABORT";};}
    private Map<String,Object> summary(){
        int applied=0,notSent=0,unknown=0,unknownObserved=0,replay=0,serverRejected=0,admissionRejected=0,notAttempted=0,uniqueAccepted=0,duplicateOrder=0,withinWindow=0;
        long[] confirmed=new long[rows.arrivals()],accepted=new long[rows.arrivals()];int cn=0,an=0;long lastEnd=windowEnd;BitSet seen=new BitSet(config.arrivals()+2);
        var rejectCodes=new TreeMap<String,Integer>();
        for(int i=0;i<config.arrivals();i++){
            if(rows.unknownObserved[i]!=MISSING)unknownObserved++;
            if(rows.serverAdmission[i]==BatchStatus.ADMISSION_REJECTED.ordinal())admissionRejected++;
            if(rows.serverAdmission[i]==BatchStatus.NOT_ATTEMPTED.ordinal())notAttempted++;
            if(rows.status[i]==NOT_SENT)notSent++;else if(rows.status[i]==UNKNOWN_FINAL||rows.status[i]==PENDING)unknown++;
            if(rows.status[i]==APPLIED){applied++;if(rows.replayed[i]!=0)replay++;if(rows.end[i]!=MISSING){confirmed[cn++]=rows.end[i]-(origin+config.offsetNs(i));lastEnd=Math.max(lastEnd,rows.end[i]);}
                if(rows.resultCode[i]==ResultCode.ACCEPTED.ordinal()){
                    if(rows.orderId[i]<2||rows.orderId[i]>config.arrivals()+1){duplicateOrder++;continue;}int id=(int)rows.orderId[i];if(seen.get(id)){duplicateOrder++;continue;}seen.set(id);uniqueAccepted++;if(rows.end[i]!=MISSING){accepted[an++]=rows.end[i]-(origin+config.offsetNs(i));if(rows.end[i]-windowEnd<=0)withinWindow++;}
                }else{serverRejected++;String key=rows.resultCode[i]<0?"MISSING":ResultCode.values()[rows.resultCode[i]].name();rejectCodes.merge(key,1,Integer::sum);}
            }
        }
        var out=new LinkedHashMap<String,Object>();if(idleSelection.explicit())out.put("retentionIdleSelection",idleSelection.observation());if(ownerPollSelection.explicit()){out.put("ownerPollSelection",ownerPollSelection.observation());out.put("ownerPollActual",ownerPollSelection.actualObservation(owner));}out.put("schema","retention-v3-openloop-capacity-v1");out.put("dispatchOrderPolicy",config.dispatchOrderPolicy());out.put("scheduledArrivals",config.arrivals());out.put("releasedArrivals",rows.released.get());out.put("ratePerSecond",config.rate());out.put("batchCap",config.batchCap());out.put("archiveChunkBytes",config.archiveChunkBytes());out.put("eventFetchCount",config.eventFetchCount());if(config.commonEventFetchEnvelope())out.put("commonEventFetchEnvelope",true);if(config.commonReadWindow32Envelope())out.put("commonReadWindow32Envelope",true);if(config.commonReadWindow128Envelope())out.put("commonReadWindow128Envelope",true);if(config.maintainedCapacityPreset())out.put("maintainedCapacityPreset",true);out.put("commonChunkEnvelope",plan.commonChunkEnvelope());out.put("readWindow",config.readWindow());out.put("commonReadWindowEnvelope",plan.commonReadWindowEnvelope());out.put("arrivalWindowSeconds",config.windowNs()/1e9);out.put("scheduledOriginUTC",originUtc);out.put("scheduledOriginMonotonicNs",origin);
        out.put("schedulerLatenessOver20ms",rows.lateOver20ms);out.put("schedulerMaxLatenessNs",rows.maxSchedulerLateness);out.put("schedulerTimingValid",rows.lateOver20ms==0&&rows.released.get()==config.arrivals()&&exposureEnd-origin>=config.windowNs());out.put("arrivalClockPausedForMaintenance",false);
        out.put("completedLogicalReplies",applied);out.put("notSent",notSent);out.put("unknownObserved",unknownObserved);out.put("unknownFinal",unknown);out.put("serverRejected",serverRejected);out.put("serverAdmissionRejectedObserved",admissionRejected);out.put("serverNotAttemptedObserved",notAttempted);out.put("serverRejectionCodes",rejectCodes);out.put("replyReplayed",replay);out.put("confirmedAcceptedUniqueOrders",uniqueAccepted);out.put("duplicateOrOutOfRangeAcceptedOrderIds",duplicateOrder);out.put("setupBusinessCommands",3);out.put("setupAcceptedOrders",1);out.put("acceptedOrdersInArrivalWindow",withinWindow);out.put("arrivalWindowGoodputPerSecond",withinWindow/(config.windowNs()/1e9));out.put("lastKnownReplyDrainNs",Math.max(0,lastEnd-windowEnd));out.put("totalSourceDrainNs",drainEnd==MISSING?null:Math.max(0,drainEnd-windowEnd));out.put("completedReplyConditionalP99Ns",quantile(confirmed,cn,0.99));out.put("acceptedOrderConditionalP99Ns",quantile(accepted,an,0.99));out.put("allArrivalReplyP99Ns",notSent==0&&unknown==0&&applied==config.arrivals()?quantile(confirmed,cn,0.99):null);Long allAcceptedP99=allAcceptedP99(config.arrivals(),applied,notSent,unknown,serverRejected,duplicateOrder,uniqueAccepted,accepted,an);out.put("allArrivalAcceptedOrderP99Ns",allAcceptedP99);out.put("allArrivalP99Ns",allAcceptedP99);out.put("allArrivalP99Policy","all planned arrivals must each confirm one distinct ACCEPTED order; null on notSent, unknown, unreleased, business rejection or duplicate/out-of-range orderId; allArrivalReplyP99Ns instead includes finite business-reject replies");
        out.put("maintenanceCycles",cycles);out.put("maintenanceRpcMetrics",maintenance==null?null:maintenance.snapshot());out.put("diskGuard",disk.snapshot());out.put("journalRunBudget",journalBudget.snapshot());out.put("maximumObservedQueueSizePerWorker",rows.queueHighWater);out.put("primitiveArrivalColumnBytes",rows.primitiveColumnBytes());out.put("traceBytes",rawBudget.used.get());out.put("arrivalCsvBytes",rawBudget.csvBytes);out.put("rawTraceByteLimit",rawBudget.limit);out.put("physicalOfferTape",tape.snapshot());out.put("externalCorrectnessVerificationRequired",true);out.put("finiteStabilityClaimed",false);out.put("scope","Finite same-system openloop source; no percentile SLA, sustained/infinite capacity or 100M claim. All-arrival p99 undefined when any arrival is notSent/unknown/unreleased.");return out;
    }
    static Long allAcceptedP99(int planned,int applied,int notSent,int unknown,int rejected,int duplicate,int unique,long[] accepted,int count){return applied==planned&&notSent==0&&unknown==0&&rejected==0&&duplicate==0&&unique==planned&&count==planned?quantile(accepted,count,0.99):null;}
    static Long quantile(long[] values,int count,double p){if(count==0)return null;long[] sorted=Arrays.copyOf(values,count);Arrays.sort(sorted);return sorted[Math.max(0,(int)Math.ceil(p*count)-1)];}

    private static final class RawBudget{
        final long limit,reservedCsv;final AtomicLong used=new AtomicLong();volatile long csvBytes;
        RawBudget(long limit,long reservedCsv){if(reservedCsv>=limit)throw new IllegalArgumentException("CSV reserve exceeds trace envelope");this.limit=limit;this.reservedCsv=reservedCsv;}
        OutputStream open(Path file,boolean network)throws IOException{
            FileChannel channel=FileChannel.open(file,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);var buffer=new BufferedOutputStream(Channels.newOutputStream(channel),65536);
            return new OutputStream(){public void write(int b)throws IOException{reserve(1);buffer.write(b);}public void write(byte[] b,int off,int n)throws IOException{reserve(n);buffer.write(b,off,n);}private void reserve(int n)throws IOException{if(used.addAndGet(n)>limit-reservedCsv)throw new IOException("SOURCE_RAW_BYTE_BUDGET; preserve partial trace, no capacity success");}public void flush()throws IOException{buffer.flush();}public void close()throws IOException{try{buffer.flush();channel.force(true);}finally{buffer.close();}}};
        }
    }
    private final class Tape implements RetentionBatchOwnerIOV3{
        private record Recorded(String sha,long offset,int members,boolean business,boolean readOnly,int admissions){}
        private final Map<Long,Recorded> active=new HashMap<>();
        private final DataOutputStream requests,replies;
        private final OutputStream codes,index;
        private RetentionBatchOwnerIOV3 delegate;
        private int readOnlyRegistryHighWater;
        private long requestOffset,frames,attempts,positive,negative,replyCount,extraPositive,initialTerm=Long.MIN_VALUE;private Map<String,Object> lastObservation=Map.of();
        Tape()throws IOException{requests=new DataOutputStream(rawBudget.open(root.resolve("physical-requests.bin"),true));replies=new DataOutputStream(rawBudget.open(root.resolve("physical-replies.bin"),true));codes=rawBudget.open(root.resolve("physical-offer-codes.csv"),true);index=rawBudget.open(root.resolve("physical-request-index.csv"),true);codes.write("attempt,correlation_id,wire_offset,offset_ns,return_code\n".getBytes(java.nio.charset.StandardCharsets.US_ASCII));index.write("frame,correlation_id,wire_offset,wire_length,first_offer_offset_ns,members,wire_sha256\n".getBytes(java.nio.charset.StandardCharsets.US_ASCII));}
        RetentionBatchOwnerIOV3 attach(RetentionBatchOwnerIOV3 io){delegate=Objects.requireNonNull(io);return this;}
        public synchronized long offer(byte[] bytes){try{
            if(abort.get()!=null)throw new IOException("source guard aborted before next offer");Request request=RetentionWireV3.decode(bytes);String sha=HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes));Recorded record=active.get(request.correlationId());
            if(record==null){if(active.size()>=129)throw new IOException("bounded active tape registry129 exceeded");boolean business=request.operation() instanceof BusinessBatch,readOnly=request.operation() instanceof ArchiveChunk||request.operation() instanceof FetchEvents;
                if(readOnly&&active.values().stream().anyMatch(v->!v.readOnly)||!readOnly&&active.values().stream().anyMatch(v->v.readOnly))throw new IOException("read-only phase overlaps business/control in physical tape");
                if(readOnly&&active.size()>=config.readWindow())throw new IOException("selected read-only physical registry window exceeded");
                int members=business?((BusinessBatch)request.operation()).commands().size():1;record=new Recorded(sha,requestOffset,members,business,readOnly,0);active.put(request.correlationId(),record);if(readOnly)readOnlyRegistryHighWater=Math.max(readOnlyRegistryHighWater,active.size());requests.writeLong(System.nanoTime()-origin);requests.writeInt(bytes.length);requests.write(bytes);requestOffset+=12L+bytes.length;frames++;index.write((frames+","+request.correlationId()+","+record.offset+","+bytes.length+","+(System.nanoTime()-origin)+","+members+","+sha+"\n").getBytes(java.nio.charset.StandardCharsets.US_ASCII));}
            else if(!record.sha.equals(sha))throw new IOException("original correlation payload changed");
            if(negative>=plan.maximumNegativeOfferAttempts()||record.admissions>=4)throw new IOException("SOURCE_FINITE_OFFER_BUDGET");
            boolean extra=record.admissions>0;
            if(extra&&extraPositive>=plan.maximumExtraPositiveOffers())throw new IOException("SOURCE_GLOBAL_RETRY_BUDGET");
            if(extra)extraPositive++;
            long code=delegate.offer(bytes);attempts++;if(code>=0){positive++;active.put(request.correlationId(),new Recorded(record.sha,record.offset,record.members,record.business,record.readOnly,record.admissions+1));}else{negative++;if(extra)extraPositive--;}codes.write((attempts+","+request.correlationId()+","+record.offset+","+(System.nanoTime()-origin)+","+code+"\n").getBytes(java.nio.charset.StandardCharsets.US_ASCII));return code;
        }catch(IOException error){throw new UncheckedIOException(error);}}
        public int poll(Consumer<Reply> consumer){if(abort.get()!=null)throw new IllegalStateException("source/observer guard abort",abort.get());return delegate.poll(reply->{try{synchronized(this){byte[] bytes=RetentionReplyV3.encode(reply);replies.writeLong(System.nanoTime()-origin);replies.writeInt(bytes.length);replies.write(bytes);replyCount++;Recorded record=active.get(reply.correlationId());if(record!=null&&(!(reply.payload() instanceof Batch batch)||batch.entries().stream().allMatch(e->e.status()==BatchStatus.APPLIED)))active.remove(reply.correlationId());}consumer.accept(reply);}catch(IOException error){throw new UncheckedIOException(error);}});}
        synchronized void retireBusiness(long correlation){Recorded record=active.get(correlation);if(record!=null&&record.business){if(record.members<=1)active.remove(correlation);else active.put(correlation,new Recorded(record.sha,record.offset,record.members-1,true,false,record.admissions));}}
        public synchronized Map<String,Object> observation(){Map<String,Object> actual=delegate.observation();lastObservation=actual;Object leader=actual.get("leaderMemberId"),term=actual.get("leadershipTermId");if(leader instanceof Number id&&id.intValue()!=0)throw new IllegalStateException("FIXED_LEADER_CHANGED");if(term instanceof Number value){if(initialTerm==Long.MIN_VALUE)initialTerm=value.longValue();else if(value.longValue()!=initialTerm)throw new IllegalStateException("FIXED_TERM_CHANGED");}Object events=actual.get("newLeaderEvents");if(events instanceof Iterable<?> list)for(Object event:list)if(event instanceof Map<?,?> row){Object eventLeader=row.get("leaderMemberId"),eventTerm=row.get("leadershipTermId");if(!(eventLeader instanceof Number id)||id.intValue()!=0||!(eventTerm instanceof Number value)||value.longValue()!=initialTerm)throw new IllegalStateException("FIXED_LEADER_EVENT_CHANGED");}return actual;}
        public void close(){if(delegate!=null){delegate.close();delegate=null;}}
        synchronized void closeFiles()throws IOException{try{requests.close();}finally{try{replies.close();}finally{try{codes.close();}finally{index.close();}}}}
        synchronized Map<String,Object> snapshot(){var out=new LinkedHashMap<String,Object>();out.put("uniqueRecordedRequests",frames);out.put("physicalOfferAttempts",attempts);out.put("successfulPhysicalAdmissions",positive);out.put("negativePhysicalOffers",negative);out.put("recordedReplies",replyCount);out.put("boundedActiveRegistry",129);out.put("extraSuccessfulPhysicalAdmissions",extraPositive);out.put("lastActualTransportObservation",lastObservation);out.put("readWindow",config.readWindow());out.put("readOnlyRawRegistryHighWater",readOnlyRegistryHighWater);out.put("readBusinessControlPhaseExclusionEnforced",true);return Collections.unmodifiableMap(out);}
    }
}
