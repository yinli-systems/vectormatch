package io.vectormatch.cluster;

import io.aeron.cluster.ClusterTool;
import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.agrona.DirectBuffer;

import java.io.*;
import java.lang.reflect.Field;
import java.net.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Fresh three-JVM functional validation of the continuously scheduled source. No capacity promotion. */
public final class RetentionCapacityAeronPilotV3 {
    private static final Duration TIMEOUT=Duration.ofSeconds(25);
    private static final int ARRIVALS=6400,RATE=500;
    private record Owned(Process process,Instant started,String command,List<String> arguments,int member,Path log){}
    private final Path root;
    private final int cap,ports,archiveChunkBytes,readWindow;
    private final boolean readWindowExperiment;
    private final String lineage="capacity-pilot-"+UUID.randomUUID();
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    private final String code=RetentionNodeMainV3.codeFingerprint();
    private final List<Owned> owned=new ArrayList<>();
    private final RetentionCapacityPlanV3.Plan plan;
    private final RetentionCapacityDiskGuardV3 disk;
    private final RetentionClusteredServiceV3 reference;
    private boolean allOwnedStopped=true;

    private RetentionCapacityAeronPilotV3(Path freshRoot,int cap,int ports)throws Exception{
        this(freshRoot,cap,ports,DEFAULT_ARCHIVE_CHUNK,false);
    }
    private RetentionCapacityAeronPilotV3(Path freshRoot,int cap,int ports,int archiveChunkBytes,boolean commonEnvelope)throws Exception{
        this(freshRoot,cap,ports,archiveChunkBytes,commonEnvelope,1,false);
    }
    private RetentionCapacityAeronPilotV3(Path freshRoot,int cap,int ports,int archiveChunkBytes,boolean commonEnvelope,int readWindow,boolean readWindowExperiment)throws Exception{
        this.readWindow=RetentionCapacityPlanV3.requireReadWindow(readWindow);this.readWindowExperiment=readWindowExperiment;
        this.archiveChunkBytes=requireArchiveChunkBytes(archiveChunkBytes);this.cap=cap;this.ports=ports;root=freshRoot.toAbsolutePath().normalize();Files.createDirectory(root);
        var base=RetentionCapacityPlanV3.plan(ARRIVALS,cap,profile);
        plan=readWindowExperiment?RetentionCapacityExperimentV3.boundedPlan(experimentConfig(),profile):commonEnvelope?RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(ARRIVALS,RATE,cap,archiveChunkBytes),profile):
                RetentionCapacityPlanV3.planWithOfferBudget(ARRIVALS,cap,profile,ARRIVALS/4L,ARRIVALS+base.maximumLogicalMaintenanceRpcs());plan.requireAdmitted();
        // Must precede the very first registration, node log, artifact receipt or load file.
        disk=RetentionCapacityDiskGuardV3.openFresh(root,plan);
        reference=new RetentionClusteredServiceV3(profile,lineage,true);reference.onStart(null,null);
        var registration=new LinkedHashMap<String,Object>(Map.of("scope","LOCAL_THREE_JVM_CONTINUOUS_ARRIVAL_FUNCTIONAL_PILOT",
                "arrivals",ARRIVALS,"rate",RATE,"batchCap",cap,"appointedLeader",0,"sync",2,
                "profileSha256",profile.fingerprint(),"codeSha256",code,"lineage",lineage,"ports",ports));
        registration.put("archiveChunkBytes",archiveChunkBytes);registration.put("eventFetchCount",16);registration.put("commonChunkEnvelope",commonEnvelope);registration.put("readWindow",readWindow);registration.put("commonReadWindowEnvelope",readWindowExperiment);
        write("registration.json",registration);writeArtifactInventory();
    }
    public static Path run(Path newPairRoot)throws Exception{
        Path pair=newPairRoot.toAbsolutePath().normalize();Files.createDirectory(pair);int ports=ports();
        for(int cap:List.of(1,4)){
            var pilot=new RetentionCapacityAeronPilotV3(pair.resolve("cap-"+cap),cap,ports);
            Throwable failure=null;boolean passed=false;
            try{pilot.exercise();passed=true;}
            catch(Throwable error){failure=error;pilot.failure(error);throw error;}
            finally{
                try{pilot.stopOwned();}catch(Throwable cleanup){if(failure!=null)failure.addSuppressed(cleanup);else throw cleanup;}
                finally{pilot.write("completion.json",Map.of("passed",passed&&pilot.allOwnedStopped,"allOwnedStopped",pilot.allOwnedStopped,
                        "independentHosts",false,"capacityOrEnduranceProven",false,"fixedLeader",0));}
            }
        }
        RetentionCapacityJsonV3.writeNew(pair.resolve("pair-completion.json"),Map.of("passed",true,"arms",List.of(1,4),
                "scope","Functional source/correctness pilot only; distinct fresh lineages are not cumulative endurance"));
        return pair;
    }
    /** Single factor: both arms cap4, all operational caps from the same union envelope. */
    public static Path runArchiveChunks(Path newPairRoot)throws Exception{return runArchiveChunks(newPairRoot,ports());}
    public static Path runArchiveChunks(Path newPairRoot,int ports)throws Exception{
        verifyChunkPorts(ports); // Explicit occupied port fails before any registration/business; no fallback.
        Path pair=newPairRoot.toAbsolutePath().normalize();Files.createDirectory(pair);
        for(int chunk:List.of(DEFAULT_ARCHIVE_CHUNK,MAX_SUPPORTED_ARCHIVE_CHUNK)){
            var pilot=new RetentionCapacityAeronPilotV3(pair.resolve("chunk-"+chunk),4,ports,chunk,true);
            Throwable failure=null;boolean passed=false;
            try{pilot.exercise();passed=true;}catch(Throwable error){failure=error;pilot.failure(error);throw error;}
            finally{try{pilot.stopOwned();}catch(Throwable cleanup){if(failure!=null)failure.addSuppressed(cleanup);else throw cleanup;}
                finally{pilot.write("completion.json",Map.of("passed",passed&&pilot.allOwnedStopped,"allOwnedStopped",pilot.allOwnedStopped,"independentHosts",false,"capacityOrEnduranceProven",false,"fixedLeader",0,"archiveChunkBytes",chunk));}}
        }
        RetentionCapacityJsonV3.writeNew(pair.resolve("pair-completion.json"),Map.of("passed",true,"archiveChunkBytes",List.of(DEFAULT_ARCHIVE_CHUNK,MAX_SUPPORTED_ARCHIVE_CHUNK),"fixedBusinessBatchCap",4,"scope","Single-factor local functional chunk comparison; not a capacity or speedup proof"));return pair;
    }
    /** Single factor: same cap4/chunk6144 artifact, exclusive read window1 versus8. */
    public static Path runReadWindows(Path pair)throws Exception{return runReadWindows(pair,ports());}
    public static Path runReadWindows(Path newPairRoot,int ports)throws Exception{
        verifyChunkPorts(ports);Path pair=newPairRoot.toAbsolutePath().normalize();Files.createDirectory(pair);
        for(int window:List.of(1,8)){
            var pilot=new RetentionCapacityAeronPilotV3(pair.resolve("window-"+window),4,ports,MAX_SUPPORTED_ARCHIVE_CHUNK,false,window,true);
            Throwable failure=null;boolean passed=false;
            try{pilot.exercise();passed=true;}catch(Throwable error){failure=error;pilot.failure(error);throw error;}
            finally{try{pilot.stopOwned();}catch(Throwable cleanup){if(failure!=null)failure.addSuppressed(cleanup);else throw cleanup;}
                finally{pilot.write("completion.json",Map.of("passed",passed&&pilot.allOwnedStopped,"allOwnedStopped",pilot.allOwnedStopped,"independentHosts",false,"capacityOrEnduranceProven",false,"fixedLeader",0,"archiveChunkBytes",MAX_SUPPORTED_ARCHIVE_CHUNK,"readWindow",window));}}
        }
        RetentionCapacityJsonV3.writeNew(pair.resolve("pair-completion.json"),Map.of("passed",true,"readWindows",List.of(1,8),"archiveChunkBytes",MAX_SUPPORTED_ARCHIVE_CHUNK,"fixedBusinessBatchCap",4,"scope","Local functional exclusive read-window comparison; no capacity or speedup claim"));return pair;
    }
    private RetentionCapacityExperimentV3.Config experimentConfig(){return readWindowExperiment?
            new RetentionCapacityExperimentV3.Config(ARRIVALS,RATE,cap,archiveChunkBytes,readWindow):new RetentionCapacityExperimentV3.Config(ARRIVALS,RATE,cap,archiveChunkBytes);}
    public static void main(String[] args)throws Exception{
        if(args.length!=1&&!((args.length==2||args.length==3)&&(args[1].equals("archive-chunks")||args[1].equals("read-windows"))))throw new IllegalArgumentException("RetentionCapacityAeronPilotV3 <new-pair-directory> [archive-chunks|read-windows [fixed-port-base]]");
        if(args.length==3&&!args[2].matches("[1-9][0-9]{3,4}"))throw new IllegalArgumentException("canonical fixed UDP port base required");
        Path result=args.length==1?run(Path.of(args[0])):args[1].equals("read-windows")?(args.length==2?runReadWindows(Path.of(args[0])):runReadWindows(Path.of(args[0]),Integer.parseInt(args[2]))):(args.length==2?runArchiveChunks(Path.of(args[0])):runArchiveChunks(Path.of(args[0]),Integer.parseInt(args[2])));
        System.out.println("VECTOR_V3_CAPACITY_SOURCE_PILOT_PASS evidence="+result);
    }
    private Scope scope(){return new Scope(profile.fingerprint(),lineage);}
    private RetentionClientV3 client(String label){return new RetentionClientV3(root.resolve("control-"+label),ports,profile,lineage);}
    private RetentionServiceV3 referenceState()throws Exception{
        Field field=RetentionClusteredServiceV3.class.getDeclaredField("state");field.setAccessible(true);return (RetentionServiceV3)field.get(reference);
    }
    private void exercise()throws Exception{
        startOwned();
        try(var client=client("setup");var requests=new DataOutputStream(Files.newOutputStream(root.resolve("setup-requests.bin"),StandardOpenOption.CREATE_NEW));
            var replies=new DataOutputStream(Files.newOutputStream(root.resolve("setup-replies.bin"),StandardOpenOption.CREATE_NEW))){
            for(Command command:List.of(new Deposit(1,"fund",1,Asset.BASE,ARRIVALS),new Deposit(2,"fund",1,Asset.QUOTE,ARRIVALS*10L),
                    RetentionEngineV3.place(1,"seed",1,Side.SELL,10,ARRIVALS,TimeInForce.GTC))){
                Reply actual=client.exchange(new Business(command),TIMEOUT);require(actual.error().isEmpty(),"setup reply error");
                Request request=new Request(scope(),actual.correlationId(),new Business(command));byte[] wire=RetentionWireV3.encode(request);
                byte[] received=RetentionReplyV3.encode(actual);record(requests,wire);record(replies,received);
                require(Arrays.equals(reference.dispatch(request),received),"setup differs from reference");
            }
            require(client.leaderMemberId()==0,"appointed leader0 required before arrivals");verifyPosition(client,"setup");
        }
        disk.check();
        var result=RetentionCapacityExperimentV3.run(root.resolve("load"),root,experimentConfig(),
                profile,lineage,()->new RetentionBatchAeronTransportV3(root.resolve("owner-driver"),ports,profile,lineage,true,archiveChunkBytes),plan,disk);
        require(((Number)result.summary().get("confirmedAcceptedUniqueOrders")).longValue()==ARRIVALS && ((Number)result.summary().get("notSent")).longValue()==0,"functional pilot must preserve all original planned orders");
        require(((Number)result.summary().get("unknownFinal")).longValue()==0,"functional pilot has final UNKNOWN; retained raw evidence");
        require(((Number)result.summary().get("maintenanceCycles")).longValue()>=(readWindowExperiment?3:2),"must cross declared maintenance cycles");
        Map<String,Object> actualEgress=verifiedEgress(result.summary());
        reconcilePhysicalTape(root.resolve("load"));
        try(var client=client("final")){
            require(client.leaderMemberId()==0,"appointed leader0 required after arrivals");Reply position=verifyPosition(client,"final");
            require(position.counters().exportedEventSeq()==position.counters().eventSeq(),"final full prefix not exported");
            require(referenceState().pendingHistoryCount()==0&&referenceState().outboxSize()==0,"final bounded history/outbox not reclaimed");
            Files.write(root.resolve("reference-final.bin"),referenceState().snapshot(),StandardOpenOption.CREATE_NEW);
            snapshot(0,position.counters().stateHash());
            var functional=new LinkedHashMap<String,Object>(Map.of("passed",true,"businessSeq",position.counters().businessSeq(),"eventSeq",position.counters().eventSeq(),
                    "acceptedPlaceCount",position.counters().acceptedPlaceCount(),"finalCombinedSha256",position.counters().stateHash(),
                    "allThreeSnapshotLogsMatched",true,"noCapacityPromotion",true,"actualSourceSummary",result.summary(),"actualEgressBounds",actualEgress,"archiveChunkBytes",archiveChunkBytes));
            functional.put("readWindow",readWindow);functional.put("commonReadWindowEnvelope",readWindowExperiment);write("functional-result.json",functional);
        }
        disk.check();write("disk-after-functional.json",disk.snapshot());
    }
    static Map<String,Object> verifiedEgress(Map<String,Object> summary){
        if(!(summary.get("physicalOfferTape") instanceof Map<?,?> tape)||!(tape.get("lastActualTransportObservation") instanceof Map<?,?> actual)||!(actual.get("actualEgressBounds") instanceof Map<?,?> bounds))throw new IllegalStateException("terminal proof lacks actual egress evidence");
        if(!(bounds.get("replyHeaderImageAssociations") instanceof Number associations)||!(tape.get("recordedReplies") instanceof Number replies)||associations.longValue()!=replies.longValue()||replies.longValue()<1
                ||!(bounds.get("actualImageObservations") instanceof Number samples)||samples.longValue()<2
                ||!(bounds.get("requiredApplicationReplyBytes") instanceof Number app)||app.intValue()!=RetentionReplyV3.maxEncodedArchiveChunkReplyBytes(MAX_SUPPORTED_ARCHIVE_CHUNK)
                ||!(bounds.get("requiredCompleteMessageBytes") instanceof Number complete)||complete.intValue()!=app.intValue()+32
                ||!(bounds.get("minimumActualDerivedMaxMessageLength") instanceof Number limit)||limit.longValue()<complete.longValue()
                ||!(bounds.get("activeImageCorrelations") instanceof List<?> active)||active.isEmpty()
                ||!Boolean.FALSE.equals(bounds.get("defaultMetadataSubstituted")))throw new IllegalStateException("terminal egress geometry/header association proof differs");
        var copied=new LinkedHashMap<String,Object>();for(var entry:bounds.entrySet()){if(!(entry.getKey() instanceof String key))throw new IllegalStateException("invalid egress evidence key");copied.put(key,entry.getValue());}return Collections.unmodifiableMap(copied);
    }
    private Reply verifyPosition(RetentionClientV3 client,String label)throws Exception{
        Reply actual=client.exchange(new Position(),TIMEOUT);require(actual.error().isEmpty(),"position reply failed");
        byte[] expected=reference.dispatch(new Request(scope(),actual.correlationId(),new Position()));
        require(Arrays.equals(expected,RetentionReplyV3.encode(actual)),label+" full counters/hash differ from physical-order reference");
        write(label+"-position.json",Map.of("leaderMemberId",client.leaderMemberId(),"businessSeq",actual.counters().businessSeq(),
                "eventSeq",actual.counters().eventSeq(),"marketSeq",actual.counters().marketSeq(),"exportedEventSeq",actual.counters().exportedEventSeq(),
                "combinedSha256",actual.counters().stateHash()));return actual;
    }
    private void reconcilePhysicalTape(Path load)throws Exception{
        long offers=0,missing=0,compared=0;Map<Long,ArrayDeque<byte[]>> replies=new HashMap<>();
        try(var wires=new RandomAccessFile(load.resolve("physical-requests.bin").toFile(),"r");var codes=Files.newBufferedReader(load.resolve("physical-offer-codes.csv"))){
            require(codes.readLine().equals("attempt,correlation_id,wire_offset,offset_ns,return_code"),"physical offer tape header differs");
            String line;while((line=codes.readLine())!=null){String[] col=line.split(",",-1);require(col.length==5,"physical offer row malformed");
                if(Long.parseLong(col[4])<0)continue;offers++;long correlation=Long.parseLong(col[1]),offset=Long.parseLong(col[2]);
                require(offset>=0&&offset+12<=wires.length(),"physical wire offset outside tape");wires.seek(offset);wires.readLong();int length=wires.readInt();
                require(length>0&&length<=MAX_REQUEST_BYTES&&length<=wires.length()-wires.getFilePointer(),"physical wire length outside bounds");
                byte[] bytes=new byte[length];wires.readFully(bytes);Request request=RetentionWireV3.decode(bytes);require(request.correlationId()==correlation,"wire correlation/index differs");
                byte[] expected=reference.dispatch(request);replies.computeIfAbsent(correlation,x->new ArrayDeque<>()).add(expected);
            }
        }
        try(var in=new DataInputStream(Files.newInputStream(load.resolve("physical-replies.bin")))){
            while(in.available()>0){in.readLong();int length=in.readInt();require(length>0&&length<=MAX_REPLY_BYTES,"raw physical reply size");byte[] raw=in.readNBytes(length);require(raw.length==length,"truncated physical reply");
                Reply actual=RetentionReplyV3.decode(raw);ArrayDeque<byte[]> expected=replies.get(actual.correlationId());require(expected!=null&&!expected.isEmpty(),"reply lacks an admitted original wire");
                boolean match=false;while(!expected.isEmpty()){if(Arrays.equals(expected.removeFirst(),raw)){match=true;break;}missing++;}
                require(match,"actual reply not equal to any ordered original/replayed service response");compared++;
            }
        }
        long remaining=replies.values().stream().mapToLong(ArrayDeque::size).sum();
        write("physical-reference-reconciliation.json",Map.of("passed",true,"successfulPublicationAdmissions",offers,"actualRepliesCompared",compared,
                "earlierAdmittedRepliesNotObserved",missing,"remainingAdmittedRepliesNotObserved",remaining,
                "reference","same candidate adapter in actual positive-offer order; not independent algorithm","performedOutsideArrivalWindow",true));
    }
    private void startOwned()throws Exception{
        var classpath=new LinkedHashSet<String>();for(Class<?> type:List.of(RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class))
            classpath.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        for(int member=0;member<3;member++){
            Path log=root.resolve("node-"+member+".log");List<String> argv=List.of(Path.of(System.getProperty("java.home"),"bin/java").toString(),
                    "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED","--add-opens=java.base/java.util.zip=ALL-UNNAMED","-Xmx256m",
                    "-Daeron.cluster.appointed.leader.id=0","-cp",String.join(File.pathSeparator,classpath),RetentionNodeMainV3.class.getName(),
                    Integer.toString(member),root.toString(),Integer.toString(ports),"2",RetentionBatchProfilesV3.PROFILE_ID,lineage,profile.fingerprint(),code,"bounded-maintenance-v1");
            var builder=new ProcessBuilder(argv).redirectErrorStream(true).redirectOutput(log.toFile());
            for(String name:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))builder.environment().remove(name);
            Process child=builder.start();int index=owned.size();owned.add(new Owned(child,null,"",List.of(),member,log));allOwnedStopped=false;
            var info=child.info();Owned record=new Owned(child,info.startInstant().orElseThrow(),info.command().orElseThrow(),List.of(info.arguments().orElseThrow()),member,log);owned.set(index,record);
            var identity=new LinkedHashMap<String,Object>();identity.put("pid",child.pid());identity.put("started",record.started.toString());identity.put("command",record.command);identity.put("arguments",record.arguments);
            if(System.getProperty("os.name").equals("Linux")){
                Path proc=Path.of("/proc",Long.toString(child.pid()));String stat=Files.readString(proc.resolve("stat"));String[] fields=stat.substring(stat.lastIndexOf(')')+2).split(" ");
                byte[] raw=Files.readAllBytes(proc.resolve("cmdline"));require(raw.length>0,"live Linux node argv required");
                identity.put("linuxStartTicks",Long.parseLong(fields[19]));identity.put("linuxCommandSha256",sha(raw));
                require(child.isAlive()&&child.info().startInstant().map(record.started::equals).orElse(false),"owned node identity changed during Linux registration");
            }
            write("node-"+member+"-identity.json",identity);
        }
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(30);
        while(true){boolean ready=true;for(Owned record:owned){require(record.process.isAlive(),"owned node exited; retain log");String text=Files.readString(record.log);
            ready&=text.contains("VECTOR_V3_NODE_READY node="+record.member+" pid="+record.process.pid()+" profile="+profile.fingerprint()+" lineage="+lineage+" code="+code)
                    &&text.contains("preparedArchiveCacheEnabled=true");}
            if(ready)return;require(System.nanoTime()<deadline,"three-node startup deadline");Thread.sleep(20);
        }
    }
    private void snapshot(int leader,String hash)throws Exception{
        require(ClusterTool.snapshot(root.resolve("node-"+leader+"/cluster").toFile(),System.out),"snapshot toggle failed");
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(30);
        while(true){boolean all=true;for(Owned record:owned){require(record.process.isAlive(),"owned node exited before checkpoint");all&=Files.readString(record.log).contains(
                "VECTOR_V3_SNAPSHOT_WRITTEN profile="+profile.fingerprint()+" lineage="+lineage+" hash="+hash);}
            if(all)return;require(System.nanoTime()<deadline,"all-three canonical checkpoint log deadline");Thread.sleep(20);
        }
    }
    private void stopOwned()throws Exception{
        boolean clean=true,interrupted=Thread.interrupted();var reports=new ArrayList<Map<String,Object>>();
        try{for(Owned record:owned){Process child=record.process;
            if(!child.isAlive()){reports.add(Map.of("pid",child.pid(),"alreadyExited",true));continue;}
            var info=child.info();boolean same=record.started!=null&&info.startInstant().map(record.started::equals).orElse(false)
                    &&info.command().map(record.command::equals).orElse(false)&&info.arguments().map(a->List.of(a).equals(record.arguments)).orElse(false);
            if(!same){clean=false;reports.add(Map.of("pid",child.pid(),"identityMismatchNoSignal",true));continue;}
            child.destroy();long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(30);
            while(child.isAlive()&&System.nanoTime()<deadline)try{child.waitFor(50,TimeUnit.MILLISECONDS);}catch(InterruptedException e){interrupted=true;}
            if(child.isAlive())clean=false;reports.add(Map.of("pid",child.pid(),"stopped",!child.isAlive(),"forcedKill",false));
        }}finally{allOwnedStopped=clean&&owned.stream().noneMatch(r->r.process.isAlive());write("owned-stop.json",Map.of("allOwnedStopped",allOwnedStopped,"reports",reports,"forcedKill",false));if(interrupted)Thread.currentThread().interrupt();}
        require(allOwnedStopped,"owned clean stop unconfirmed; no further benchmark");
    }
    private void writeArtifactInventory()throws Exception{
        var values=new ArrayList<Map<String,Object>>();for(Class<?> type:List.of(RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)){
            Path source=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if(Files.isDirectory(source)){try(var walk=Files.walk(source)){for(Path path:walk.filter(p->p.toString().endsWith(".class")).sorted().toList())values.add(Map.of("type",type.getName(),"path",path.toString(),"bytes",Files.size(path),"sha256",sha(Files.readAllBytes(path))));}}
            else values.add(Map.of("type",type.getName(),"path",source.toString(),"bytes",Files.size(source),"sha256",sha(Files.readAllBytes(source))));
        }write("artifact-inventory.json",Map.of("codeFingerprint",code,"actualFiles",values));
    }
    private void failure(Throwable error)throws IOException{var out=new StringWriter();error.printStackTrace(new PrintWriter(out));Files.writeString(root.resolve("failure.txt"),out.toString(),StandardOpenOption.CREATE_NEW);}
    private void write(String name,Object value)throws IOException{RetentionCapacityJsonV3.writeNew(root.resolve(name),value);}
    private static void record(DataOutputStream out,byte[] bytes)throws IOException{out.writeInt(bytes.length);out.write(bytes);out.flush();}
    private static String sha(byte[] bytes){return HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes));}
    static void verifyChunkPorts(int ports)throws IOException{
        ClusterTopology.local(ports);var sockets=new ArrayList<DatagramSocket>();
        try{for(int member=0;member<3;member++)for(int offset=1;offset<=5;offset++)sockets.add(new DatagramSocket(ports+member*100+offset,InetAddress.getByName("127.0.0.1")));}
        finally{sockets.forEach(DatagramSocket::close);}
    }
    private static int ports()throws IOException{
        for(int attempt=0;attempt<30;attempt++){int base=java.util.concurrent.ThreadLocalRandom.current().nextInt(35000,55000);var sockets=new ArrayList<DatagramSocket>();
            try{for(int member=0;member<3;member++)for(int offset=1;offset<=5;offset++)sockets.add(new DatagramSocket(base+member*100+offset,InetAddress.getByName("127.0.0.1")));return base;}
            catch(BindException occupied){/* Fresh unused range, before registration/business. */}finally{sockets.forEach(DatagramSocket::close);}}
        throw new IOException("no loopback UDP range");
    }
    private static void require(boolean ok,String reason){if(!ok)throw new IllegalStateException(reason);}
}
