from pathlib import Path
import zipfile,subprocess
B=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/cloud/cpu-20261024/read-window32-v3-worktree')
S=B.parent/'read-window32-local-preparation-r1'
paths=['RetentionCapacityPlanV3.java','RetentionCapacityExperimentV3.java','RetentionBatchMaintenanceV3.java','RetentionBatchOwnerV3.java','RetentionCapacityAeronPilotV3.java']
D=B/'cluster/src/main/java/io/vectormatch/cluster'
with zipfile.ZipFile(S/'baseline-sources.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
 for name in paths:z.write(D/name,str((D/name).relative_to(B)))
def edit(name,fn):
 p=D/name;p.write_text(fn(p.read_text()))
def replace(s,old,new):
 assert old in s,old[:120]
 return s.replace(old,new)
def plan(s):
 s=replace(s,'public static final int MAX_READ_ONLY_IN_FLIGHT = 8;','public static final int MAX_READ_ONLY_IN_FLIGHT = 8;\n    /** Only the explicitly named read-window32 experiment may reserve this envelope. */\n    public static final int EXPERIMENT_READ_ONLY_IN_FLIGHT = 32;')
 s=replace(s,'public int maximumPhysicalOffersPerRpc()', 'public boolean commonReadWindow32Envelope() { return maxReadOnlyInFlight == EXPERIMENT_READ_ONLY_IN_FLIGHT; }\n        public int maximumPhysicalOffersPerRpc()')
 s=replace(s,'out.put("readOnlyStagingBytes",readOnlyStagingBytes);','if(commonReadWindow32Envelope())out.put("commonReadWindow32Envelope",true);\n            out.put("readOnlyStagingBytes",readOnlyStagingBytes);')
 marker='    private static Plan calculate(int arrivals,int batchCap,RetentionServiceV3.Profile profile,long extras,long negatives,int archiveChunkBytes) {'
 method='''    public static int requireReadWindow32(int readWindow) {
        if(readWindow!=8&&readWindow!=EXPERIMENT_READ_ONLY_IN_FLIGHT)
            throw new IllegalArgumentException("explicit read-window32 experiment requires8 or32 credits");
        return readWindow;
    }
    /** Fixed page and cut; both selected windows reserve exactly the same32-credit failure/staging envelope. */
    public static Plan commonReadWindow32Plan(int arrivals,int batchCap,RetentionServiceV3.Profile profile,
                                             int eventFetchCount,int readWindow,long extras,long negatives) {
        requireReadWindow32(readWindow);requireEventFetchCount(eventFetchCount);
        if(arrivals!=33792||batchCap!=4)throw new IllegalArgumentException("read-window32 requires fixed LONG33792/cap4");
        Plan base=readWindowPlan(arrivals,batchCap,profile,8,extras,negatives,eventFetchCount);
        Probe p=probe(profile,batchCap,MAX_SUPPORTED_ARCHIVE_CHUNK,true,eventFetchCount);
        long staging=4L*EXPERIMENT_READ_ONLY_IN_FLIGHT*(p.readOnlyRequest+p.readOnlyReply)+READ_ONLY_FAILURE_METADATA_BYTES;
        long failure=EXPERIMENT_READ_ONLY_IN_FLIGHT*(p.readOnlyRequest+(long)RAW_FRAME_PREFIX_BYTES+256L)+READ_ONLY_FAILURE_METADATA_BYTES;
        long extraFailure=Math.subtractExact(failure,base.readOnlyFailureTraceReserveBytes());
        long raw=Math.addExact(base.maximumRawTraceBytes(),extraFailure);
        long allocation=Math.addExact(base.maximumAllocatedGrowthBytes(),Math.addExact(extraFailure,Math.subtractExact(staging,base.readOnlyStagingBytes())));
        var rejected=new ArrayList<>(base.admissionRejections());
        if(raw>RAW_TRACE_LIMIT&&!rejected.contains("derived raw trace exceeds finite 2GiB cap"))rejected.add("derived raw trace exceeds finite 2GiB cap");
        if(allocation>ALLOCATED_GROWTH_LIMIT&&!rejected.contains("derived payload/trace/native-reserve allocation exceeds 2.5GiB growth cap"))rejected.add("derived payload/trace/native-reserve allocation exceeds 2.5GiB growth cap");
        return new Plan(arrivals,batchCap,base.maximumMaintenanceCycles(),base.maximumEvents(),base.maximumLogicalMaintenanceRpcs(),base.maximumBusinessFrames(),extras,negatives,
                base.maximumWriterPayloadBytes(),base.maximumWriterPayloadFiles(),Math.addExact(base.noRetryRawTraceBytes(),extraFailure),Math.addExact(base.worstFourOfferRawTraceBytes(),extraFailure),raw,allocation,
                base.minimumFreeRuntimeBytes(),base.maximumJournalRecords(),base.maximumJournalBytes(),base.maximumArchiveEntryBytes(),base.archiveHeaderBytes(),base.maximumArchivePayloadBytes(),base.maximumEventPayloadBytes(),
                base.maximumArchiveChunkRpcs(),base.maximumEventFetchRpcs(),base.largestReplyBytes(),MAX_SUPPORTED_ARCHIVE_CHUNK,false,base.selectedMaximumLogicalMaintenanceRpcs(),base.selectedMaximumArchiveChunkRpcs(),rejected,
                readWindow,EXPERIMENT_READ_ONLY_IN_FLIGHT,true,staging,failure,eventFetchCount,false,base.selectedMaximumEventFetchRpcs());
    }
'''
 return replace(s,marker,method+marker)
edit('RetentionCapacityPlanV3.java',plan)
def experiment(s):
 s=replace(s,'int eventFetchCount,boolean commonEventFetchEnvelope){','int eventFetchCount,boolean commonEventFetchEnvelope,boolean commonReadWindow32Envelope){\n        /** Source-compatible existing eight-credit/page experiment configuration. */\n        public Config(int arrivals,int rate,int batchCap,int archiveChunkBytes,int readWindow,boolean commonReadWindowEnvelope,int eventFetchCount,boolean commonEventFetchEnvelope){this(arrivals,rate,batchCap,archiveChunkBytes,readWindow,commonReadWindowEnvelope,eventFetchCount,commonEventFetchEnvelope,false);}\n        public static Config readWindow32LongCuts(int page,int window){return new Config(33792,500,4,MAX_SUPPORTED_ARCHIVE_CHUNK,window,true,page,false,true);}')
 s=replace(s,'requireArchiveChunkBytes(archiveChunkBytes);RetentionCapacityPlanV3.requireReadWindow(readWindow);requireEventFetchCount(eventFetchCount);','requireArchiveChunkBytes(archiveChunkBytes);\n            if(commonReadWindow32Envelope){\n                RetentionCapacityPlanV3.requireReadWindow32(readWindow);\n                if(arrivals!=33792||rate!=500||batchCap!=4||archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK||!commonReadWindowEnvelope||commonEventFetchEnvelope)throw new IllegalArgumentException("read-window32 requires fixed LONG33792@500/cap4/chunk6144 and one explicit fixed page");\n            }else RetentionCapacityPlanV3.requireReadWindow(readWindow);\n            requireEventFetchCount(eventFetchCount);')
 s=replace(s,'(!commonEventFetchEnvelope&&eventFetchCount!=DEFAULT_EVENT_FETCH_COUNT)','(!commonEventFetchEnvelope&&!commonReadWindow32Envelope&&eventFetchCount!=DEFAULT_EVENT_FETCH_COUNT)')
 s=replace(s,'plan.commonEventFetchEnvelope()!=config.commonEventFetchEnvelope()||','plan.commonEventFetchEnvelope()!=config.commonEventFetchEnvelope()||plan.commonReadWindow32Envelope()!=config.commonReadWindow32Envelope()||')
 s=replace(s,'if(config.commonEventFetchEnvelope())return RetentionCapacityPlanV3.commonEventFetchPlan','if(config.commonReadWindow32Envelope())return RetentionCapacityPlanV3.commonReadWindow32Plan(config.arrivals(),config.batchCap(),profile,config.eventFetchCount(),config.readWindow(),config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());\n        if(config.commonEventFetchEnvelope())return RetentionCapacityPlanV3.commonEventFetchPlan')
 s=replace(s,'config.archiveChunkBytes(),config.readWindow(),config.eventFetchCount());','config.archiveChunkBytes(),config.readWindow(),config.eventFetchCount(),config.commonReadWindow32Envelope());')
 s=replace(s,'if(config.commonEventFetchEnvelope())values.put("commonEventFetchEnvelope",true);','if(config.commonEventFetchEnvelope())values.put("commonEventFetchEnvelope",true);if(config.commonReadWindow32Envelope())values.put("commonReadWindow32Envelope",true);')
 s=replace(s,'if(config.commonEventFetchEnvelope())out.put("commonEventFetchEnvelope",true);','if(config.commonEventFetchEnvelope())out.put("commonEventFetchEnvelope",true);if(config.commonReadWindow32Envelope())out.put("commonReadWindow32Envelope",true);')
 return s
edit('RetentionCapacityExperimentV3.java',experiment)
def owner(s):
 s=replace(s,'public ReadBank openReadBank(int window){synchronized(lock){healthy();\n        if(window!=1&&window!=8)throw new IllegalArgumentException("read window must be1or8");', '''public ReadBank openReadBank(int window){
        RetentionCapacityPlanV3.requireReadWindow(window);return openReadBank(window,8);
    }
    /** Explicit opt-in, preserving the old API's eight-credit ceiling. */
    public ReadBank openReadBank32(int window){
        RetentionCapacityPlanV3.requireReadWindow32(window);return openReadBank(window,32);
    }
    private ReadBank openReadBank(int window,int hardCapacity){synchronized(lock){healthy();''')
 s=replace(s,'readBank=new ReadBank(window);selectedReadWindow=window;return readBank;','readBank=new ReadBank(window);selectedReadWindow=window;readOnlyHardCapacity=hardCapacity;return readBank;')
 s=replace(s,'private int selectedReadWindow=1,','private int readOnlyHardCapacity=8,selectedReadWindow=1,')
 return replace(s,'out.put("readOnlyHardCapacity",8);','out.put("readOnlyHardCapacity",readOnlyHardCapacity);')
edit('RetentionBatchOwnerV3.java',owner)
def maintenance(s):
 s=replace(s,'private final int archiveChunkBytes,readWindow,eventFetchCount;','private final int archiveChunkBytes,readWindow,eventFetchCount;\n    private final boolean commonReadWindow32Envelope;')
 sig='''public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes,int readWindow,int eventFetchCount)throws IOException{
'''
 new=sig+'''        this(owner,writer,profile,lineage,newRawDir,budget,maximumLogicalRpcs,archiveChunkBytes,readWindow,eventFetchCount,false);
    }
    /** Explicit isolated experiment; legacy constructors retain their original1|8 window admission. */
    public RetentionBatchMaintenanceV3(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
                                      RetentionServiceV3.Profile profile,String lineage,Path newRawDir,RunBudget budget,long maximumLogicalRpcs,int archiveChunkBytes,int readWindow,int eventFetchCount,boolean commonReadWindow32Envelope)throws IOException{
        this.commonReadWindow32Envelope=commonReadWindow32Envelope;
'''
 s=replace(s,sig,new)
 s=replace(s,'this.readWindow=RetentionCapacityPlanV3.requireReadWindow(readWindow);','this.readWindow=commonReadWindow32Envelope?RetentionCapacityPlanV3.requireReadWindow32(readWindow):RetentionCapacityPlanV3.requireReadWindow(readWindow);\n        if(commonReadWindow32Envelope&&archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK)throw new IllegalArgumentException("read-window32 requires unchanged chunk6144");')
 s=replace(s,'activeReadBank=owner.openReadBank(readWindow);','activeReadBank=commonReadWindow32Envelope?owner.openReadBank32(readWindow):owner.openReadBank(readWindow);')
 s=replace(s,'result.put("archiveChunkBytes",archiveChunkBytes);','if(commonReadWindow32Envelope)result.put("commonReadWindow32Envelope",true);result.put("archiveChunkBytes",archiveChunkBytes);')
 return s
edit('RetentionBatchMaintenanceV3.java',maintenance)
def pilot(s):
 s=replace(s,'private final boolean eventFetchExperiment;','private final boolean eventFetchExperiment;\n    private final boolean readWindow32Experiment;')
 sig='''private RetentionCapacityAeronPilotV3(Path freshRoot,int cap,int ports,int archiveChunkBytes,boolean commonEnvelope,int readWindow,boolean readWindowExperiment,Workload workload,int eventFetchCount,boolean eventFetchExperiment)throws Exception{
'''
 s=replace(s,sig,sig+'''        this(freshRoot,cap,ports,archiveChunkBytes,commonEnvelope,readWindow,readWindowExperiment,workload,eventFetchCount,eventFetchExperiment,false);
    }
    private RetentionCapacityAeronPilotV3(Path freshRoot,int cap,int ports,int archiveChunkBytes,boolean commonEnvelope,int readWindow,boolean readWindowExperiment,Workload workload,int eventFetchCount,boolean eventFetchExperiment,boolean readWindow32Experiment)throws Exception{
        this.readWindow32Experiment=readWindow32Experiment;
        if(readWindow32Experiment&&(eventFetchExperiment||cap!=4||archiveChunkBytes!=MAX_SUPPORTED_ARCHIVE_CHUNK||!readWindowExperiment||workload!=Workload.LONG_CUTS))throw new IllegalArgumentException("read-window32 requires fixed long/cap4/chunk6144 and explicit page/window");
''')
 s=replace(s,'this.readWindow=RetentionCapacityPlanV3.requireReadWindow(readWindow);','this.readWindow=readWindow32Experiment?RetentionCapacityPlanV3.requireReadWindow32(readWindow):RetentionCapacityPlanV3.requireReadWindow(readWindow);')
 s=replace(s,'if(eventFetchExperiment)registration.put("commonEventFetchEnvelope",true);','if(eventFetchExperiment)registration.put("commonEventFetchEnvelope",true);if(readWindow32Experiment)registration.put("commonReadWindow32Envelope",true);')
 s=replace(s,'private RetentionCapacityExperimentV3.Config experimentConfig(){if(eventFetchExperiment)','private RetentionCapacityExperimentV3.Config experimentConfig(){if(readWindow32Experiment)return readWindow32Config(eventFetchCount,readWindow);if(eventFetchExperiment)')
 marker='    /** Explicit one-arm page-size candidate;'
 method='''    static RetentionCapacityExperimentV3.Config readWindow32Config(int page,int window){return RetentionCapacityExperimentV3.Config.readWindow32LongCuts(page,window);}
    /** One arm only. A controller must keep the selected page fixed when comparing8/32/8/32. */
    public static Path runReadWindow32LongCuts(Path newArmRoot,int ports,int page,int window)throws Exception{
        readWindow32Config(page,window); // Reject the entire experiment selection before ports/filesystem access.
        var idle=RetentionIdlePolicyV3.systemSelection();var owner=RetentionOwnerPollPolicyV3.systemSelection();
        if(!idle.explicit()||idle.maximumParkNs()!=100000L||owner.effectiveMaximumParkNs()!=1000000L)
            throw new IllegalArgumentException("read-window32 requires explicit server/driver100us and unchanged owner1ms");
        if(ports!=42000)throw new IllegalArgumentException("read-window32 requires fixed42000 ports");
        verifyChunkPorts(ports);
        var pilot=new RetentionCapacityAeronPilotV3(newArmRoot,4,ports,MAX_SUPPORTED_ARCHIVE_CHUNK,false,window,true,Workload.LONG_CUTS,page,false,true);
        Throwable failure=null;boolean passed=false;
        try{pilot.exercise();passed=true;}catch(Throwable error){failure=error;pilot.failure(error);throw error;}
        finally{try{pilot.stopOwned();}catch(Throwable cleanup){if(failure!=null)failure.addSuppressed(cleanup);else throw cleanup;}
            finally{pilot.write("completion.json",Map.of("passed",passed&&pilot.allOwnedStopped,"allOwnedStopped",pilot.allOwnedStopped,
                    "independentHosts",false,"capacityOrEnduranceProven",false,"fixedLeader",0,"archiveChunkBytes",MAX_SUPPORTED_ARCHIVE_CHUNK,
                    "readWindow",window,"eventFetchCount",page,"commonReadWindow32Envelope",true));}}
        return pilot.root;
    }
'''
 s=replace(s,marker,method+marker)
 marker='        if(args.length>=2 && args[1].equals("event-fetch-page-long-cuts")){'
 s=replace(s,marker,'''        if(args.length>=2 && args[1].equals("read-window32-long-cuts")){
            if(args.length!=5||(!args[2].equals("16")&&!args[2].equals("32"))||(!args[3].equals("8")&&!args[3].equals("32"))||!args[4].equals("42000"))throw new IllegalArgumentException("read-window32-long-cuts requires explicit page16|32, window8|32 and42000");
            Path result=runReadWindow32LongCuts(Path.of(args[0]),Integer.parseInt(args[4]),Integer.parseInt(args[2]),Integer.parseInt(args[3]));
            System.out.println("VECTOR_V3_CAPACITY_SOURCE_PILOT_PASS evidence="+result);return;
        }
'''+marker)
 s=replace(s,'if(eventFetchExperiment)functional.put("commonEventFetchEnvelope",true);','if(eventFetchExperiment)functional.put("commonEventFetchEnvelope",true);if(readWindow32Experiment)functional.put("commonReadWindow32Envelope",true);')
 return s
edit('RetentionCapacityAeronPilotV3.java',pilot)
(S/'initial-production.diff').write_bytes(subprocess.check_output(['git','diff','--no-ext-diff'],cwd=B))
print('production edits captured; no build invoked')
