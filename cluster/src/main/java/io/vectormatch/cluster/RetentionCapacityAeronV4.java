package io.vectormatch.cluster;
import io.aeron.cluster.ClusterTool;
import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;
import java.io.*;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Finite native V4 capacity experiment; all verification and cold restore occur after arrivals. */
public final class RetentionCapacityAeronV4 {
    private static final Duration TIMEOUT=Duration.ofSeconds(20);
    private record Owned(Process process,Instant started,String command,List<String> arguments,Path log,int member,int generation) {}
    private final Path root;
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    private final String code=RetentionNodeMainV3.codeFingerprint(),lineage="capacity-v4-"+UUID.randomUUID();
    private final int ports=22000;
    private final List<Owned> owned=new ArrayList<>();
    private boolean allOwnedStopped=true;
    private int generation;
    private final RetentionCapacityExperimentV4.Config config;
    private final RetentionIdlePolicyV3.Selection idleSelection=RetentionIdlePolicyV3.systemSelection();
    private final RetentionCapacityPlanV4.Plan plan;
    private final RetentionJfrPolicyV4.Selection jfrSelection;
    private final RetentionSegmentPreparationV4.Selection segmentSelection=RetentionSegmentPreparationV4.systemSelection();
    private final RetentionCapacityDiskGuardV4 disk;
    private RetentionCapacityAeronV4(Path newRoot,int rate,boolean proceed)throws Exception{
        config=new RetentionCapacityExperimentV4.Config(rate,proceed);
        var batchFlushSelection=RetentionBatchFlushPolicyV4.systemSelection();
        var readYieldSelection=RetentionReadYieldPolicyV4.systemSelection();if(readYieldSelection.enabled()&&!proceed)throw new IllegalArgumentException("inter-bank dispatch requires CONTINUE file-work policy");
        plan=RetentionCapacityExperimentV4.boundedPlan(config,profile);plan.requireAdmitted();RetentionLoopbackPortsV4.verifyFixed(ports);
        root=newRoot.toAbsolutePath().normalize();
        jfrSelection=RetentionJfrPolicyV4.systemSelection(root);
        for(Path path=root;path!=null;path=path.getParent())require(!Files.isSymbolicLink(path),"symlink native root refused");
        if(segmentSelection.enabled())require(Files.getFileStore(root.getParent()).getUsableSpace()>=Math.addExact(plan.initialFreeBytes(),3L*RetentionSegmentPreparationV4.SEGMENT_BYTES),"additional first-segment disk reserve refused");
        Files.createDirectory(root);disk=RetentionCapacityDiskGuardV4.openFresh(root,plan);
        writeArtifactInventory();
        var registration=new LinkedHashMap<String,Object>(plan.observation());
        registration.put("schema","capacity-v4-native-1");registration.put("ratePerSecond",rate);
        registration.put("fileWorkDispatchPolicy",proceed?"CONTINUE":"PAUSE");registration.put("profile",profile.fingerprint());registration.put("lineage",lineage);
        registration.put("code",code);registration.put("ports",ports);registration.put("appointedLeader",0);registration.put("syncLevel",2);
        registration.put("activeLoadWorkers",127);registration.put("allocatedLogicalWorkers",128);registration.put("independentHosts",false);
        if(segmentSelection.enabled())registration.put("segmentPreparation",segmentSelection.observation());
        if(batchFlushSelection.explicit())registration.put("batchFlushSelection",batchFlushSelection.observation());if(jfrSelection.enabled())registration.put("jfrDiagnostics",jfrSelection.observation());registration.put("readBankDispatchSelection",readYieldSelection.observation());if(idleSelection.explicit())registration.put("retentionIdleSelection",idleSelection.observation());registration.put("fundedExternalOrders",false);writeJson("registration.json",registration);
    }
    public static void main(String[] args)throws Exception{
        if(args.length!=3||!Set.of("PAUSE","CONTINUE").contains(args[2]))throw new IllegalArgumentException("RetentionCapacityAeronV4 <new-root> <500|1000|2000|4000|6000> <PAUSE|CONTINUE>");
        var run=new RetentionCapacityAeronV4(Path.of(args[0]),Integer.parseInt(args[1]),args[2].equals("CONTINUE"));
        Throwable failure=null;boolean passed=false;
        try{run.exercise();passed=true;}catch(Throwable error){failure=error;var text=new StringWriter();error.printStackTrace(new PrintWriter(text));run.writeNew("failure.txt",text.toString());throw error;}
        finally{try{run.stopOwned();}catch(Throwable cleanup){if(failure!=null)failure.addSuppressed(cleanup);else throw cleanup;}
            finally{run.writeJson("completion.json",Map.of("passed",passed&&run.allOwnedStopped,"allOwnedStopped",run.allOwnedStopped,"independentHosts",false,"sustainedCapacityOr100MProven",false,"fundedExternalOrders",false));}}
        System.out.println("VECTOR_CAPACITY_V4_NATIVE_PASS evidence="+run.root);
    }
    private void exercise()throws Exception{
        startOwned();qualifyReadiness("startup-readiness");disk.check();
        var result=RetentionCapacityExperimentV4.run(root.resolve("load"),root,config,profile,lineage,
                ()->new RetentionBatchAeronTransportV3(root.resolve("owner-driver"),ports,profile,lineage,true,6144),plan,disk,owner->{
                    Reply setup=owner.exchangeMaintenance(new Position(),TIMEOUT);require(setup.error().isEmpty()&&setup.counters().businessSeq()==3,"exact bootstrap readiness differs");
                    long begin=System.nanoTime();Thread.sleep(5000);
                    writeJson("preload-warmup.json",Map.of("requestedMillis",5000,"startedMonotonicNs",begin,"endedMonotonicNs",System.nanoTime(),"outsideArrivalWindow",true,"noSyntheticOrdersDuringWarmup",true));
                    qualifyReadiness("preload-readiness");disk.check();
                });
        var summary=result.summary();RetentionCapacityAeronPilotV3.validateCapacityOutcomes(summary,config.arrivals());
        var egress=RetentionCapacityAeronPilotV3.verifiedEgress(summary);
        var reference=reconcilePhysicalTape();Field field=RetentionClusteredServiceV3.class.getDeclaredField("state");field.setAccessible(true);var state=(RetentionServiceV3)field.get(reference);
        byte[] canonical=state.snapshot();String hash=sha(canonical);
        Reply barrier=RetentionReplyV3.decode(Files.readAllBytes(root.resolve("load/final-source-position.bin")));
        require(barrier.error().isEmpty()&&hash.equals(barrier.counters().stateHash()),"same-session final full state differs from physical-order replay");
        long accepted=((Number)summary.get("confirmedAcceptedUniqueOrders")).longValue();
        require(state.businessSeq()==accepted+3&&state.eventSeq()==2*accepted+3&&state.marketSeq()==2*accepted+1&&state.acceptedPlaceCount()==accepted+1,"exact accepted-command/trade counters differ");
        require(state.pendingHistoryCount()==0&&state.outboxSize()==0&&state.exportedEventSeq()==state.eventSeq(),"final history/outbox must be fully exported");
        require(state.account(2).base().available()==accepted&&state.account(2).quote().available()==10L*(config.arrivals()-accepted)&&state.account(1).quote().available()==10L*accepted,"final exact trade balances differ");
        require(Arrays.equals(canonical,RetentionServiceV3.restore(canonical,profile,lineage).snapshot()),"offline binary restore differs");
        Files.write(root.resolve("canonical-final-combined.bin"),canonical,StandardOpenOption.CREATE_NEW);
        try(var client=new RetentionClientV3(root.resolve("control-snapshot"),ports,profile,lineage)){
            var position=client.exchange(new Position(),TIMEOUT);require(client.leaderMemberId()==0&&position.error().isEmpty()&&position.counters().stateHash().equals(hash),"fixed leader or final state differs");snapshot(0,hash);
        }
        disk.check();stopOwned();startOwned();
        try(var client=new RetentionClientV3(root.resolve("control-cold"),ports,profile,lineage)){
            var position=client.exchange(new Position(),TIMEOUT);require(client.leaderMemberId()==0&&position.error().isEmpty()&&position.counters().stateHash().equals(hash),"three-node cold restore differs");
            for(int node=0;node<3;node++)require(Files.readString(log(node)).contains("restored=true hash="+hash),"each actual node must restore the canonical state");
        }
        disk.check();writeJson("disk-after-native.json",disk.snapshot());
        var verified=new LinkedHashMap<String,Object>();verified.put("passed",true);verified.put("businessSeq",state.businessSeq());verified.put("eventSeq",state.eventSeq());verified.put("marketSeq",state.marketSeq());
        verified.put("loadAcceptedTrades",accepted);verified.put("finalCombinedSha256",hash);verified.put("allThreeSnapshotHashesMatched",true);verified.put("allThreeColdRestoreHashesMatched",true);
        verified.put("actualSourceSummary",summary);verified.put("actualEgressBounds",egress);verified.put("sameAdapterPhysicalOrderReplay",true);verified.put("independentAlgorithm",false);
        verified.put("clientNewOrdersAfterColdRestore",false);verified.put("independentStorageDurabilityProven",false);verified.put("allRestorationOutsideArrivalWindow",true);writeJson("capacity-correctness-result.json",verified);
    }
    private RetentionClusteredServiceV3 reconcilePhysicalTape()throws Exception{
        var reference=new RetentionClusteredServiceV3(profile,lineage,true);reference.onStart(null,null);
        long offers=0,missing=0,compared=0,attempts=0,previousReturned=-1;Map<Long,ArrayDeque<byte[]>> replies=new HashMap<>();
        Path load=root.resolve("load");
        try(var wires=new RandomAccessFile(load.resolve("physical-requests.bin").toFile(),"r");var codes=Files.newBufferedReader(load.resolve("physical-offer-codes.csv"))){
            require(codes.readLine().equals("attempt,correlation_id,wire_offset,offer_call_tape_offset_ns,offer_return_tape_offset_ns,return_code"),"physical offer tape header differs");
            String line;while((line=codes.readLine())!=null){String[] col=line.split(",",-1);require(col.length==6&&Long.parseLong(col[0])==++attempts,"physical offer sequence differs");
                long called=Long.parseLong(col[3]),returned=Long.parseLong(col[4]);require(called>=previousReturned&&returned>=called,"physical offer monotonic timestamps differ");previousReturned=returned;
                long correlation=Long.parseLong(col[1]),offset=Long.parseLong(col[2]);require(offset>=0&&offset+12<=wires.length(),"wire offset outside tape");
                wires.seek(offset);require(wires.readLong()<=called,"original request timestamp after offer");int length=wires.readInt();require(length>0&&length<=MAX_REQUEST_BYTES&&length<=wires.length()-wires.getFilePointer(),"wire length outside bounds");
                byte[] bytes=new byte[length];wires.readFully(bytes);Request request=RetentionWireV3.decode(bytes);require(request.correlationId()==correlation,"original correlation differs");
                if(Long.parseLong(col[5])<0)continue;offers++;replies.computeIfAbsent(correlation,x->new ArrayDeque<>()).add(reference.dispatch(request));
            }
        }
        try(var input=new DataInputStream(Files.newInputStream(load.resolve("physical-replies.bin")))){
            while(input.available()>0){input.readLong();int length=input.readInt();require(length>0&&length<=MAX_REPLY_BYTES,"physical reply bound");byte[] bytes=input.readNBytes(length);require(bytes.length==length,"truncated physical reply");
                Reply reply=RetentionReplyV3.decode(bytes);var expected=replies.get(reply.correlationId());require(expected!=null&&!expected.isEmpty(),"reply lacks positive original admission");
                boolean match=false;while(!expected.isEmpty()){if(Arrays.equals(expected.removeFirst(),bytes)){match=true;break;}missing++;}require(match,"actual reply differs from physical-order canonical replay");compared++;
            }
        }
        long remaining=replies.values().stream().mapToLong(ArrayDeque::size).sum();
        writeJson("physical-reference-reconciliation.json",Map.of("passed",true,"successfulPublicationAdmissions",offers,"actualRepliesCompared",compared,"earlierAdmittedRepliesNotObserved",missing,"remainingAdmittedRepliesNotObserved",remaining,"independentAlgorithm",false,"performedOutsideArrivalWindow",true));return reference;
    }
    private void qualifyReadiness(String observation)throws Exception{
        var nodes=new ArrayList<RetentionStartupReadinessV3.Node>();
        for(Owned record:owned)if(record.generation==generation)nodes.add(new RetentionStartupReadinessV3.Node(record.member,record.process.pid(),root.resolve("node-"+record.member+"/driver"),record.log,()->{
            var info=record.process.info();require(record.process.isAlive()&&info.startInstant().map(record.started::equals).orElse(false)&&info.command().map(record.command::equals).orElse(false)&&info.arguments().map(a->List.of(a).equals(record.arguments)).orElse(false),"original node identity changed during readiness");
        }));RetentionStartupReadinessV3.await(root.resolve(observation),nodes);
    }
    private void writeJson(String name,Object value)throws IOException{writeNew(name,RetentionCapacityJsonV3.json(value)+"\n");}
    private Path log(int node) { return root.resolve("node-" + node + "-g" + generation + ".log"); }
    private void startOwned() throws Exception {
        generation++; LinkedHashSet<String> classpath = new LinkedHashSet<>();
        for (Class<?> type : List.of(RetentionNodeMainV3.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class))
            classpath.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        for (int member = 0; member < 3; member++) {
            List<String> argv = segmentSelection.childArguments(jfrSelection.childArguments(idleSelection.childArguments(List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED", "-Xmx256m",
                    "-Daeron.cluster.appointed.leader.id=0", "-cp", String.join(File.pathSeparator, classpath), RetentionNodeMainV3.class.getName(),
                    Integer.toString(member), root.toString(), Integer.toString(ports), "2", RetentionBatchProfilesV3.PROFILE_ID, lineage, profile.fingerprint(), code, "bounded-maintenance-v1"))));
            ProcessBuilder builder = new ProcessBuilder(argv).redirectErrorStream(true).redirectOutput(log(member).toFile());
            for (String name : List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")) builder.environment().remove(name);
            Process process = builder.start();
            // Register the returned owned Process before any fallible identity/receipt read.
            int index = owned.size(); owned.add(new Owned(process, null, "", List.of(), log(member), member, generation)); allOwnedStopped = false;
            var info = process.info();
            Owned record = new Owned(process, info.startInstant().orElseThrow(), info.command().orElseThrow(), List.of(info.arguments().orElseThrow()), log(member), member, generation);
            owned.set(index, record);
            writeNew("owned-node-" + member + "-g" + generation + ".txt", "pid=" + process.pid() + "\nstarted=" + record.started + "\ncommand=" + record.command
                    + "\narguments=" + record.arguments + "\nargumentsSha256=" + sha(String.join("\u0000", record.arguments).getBytes(java.nio.charset.StandardCharsets.UTF_8)) + "\nexpectedProfile=" + profile.fingerprint() + "\nexpectedCode=" + code + "\n");
        }
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        while (true) {
            boolean ready = true;
            for (Owned record : owned) if (record.generation == generation) {
                require(record.process.isAlive(), "node exited; retain " + record.log);
                String logs = Files.exists(record.log) ? Files.readString(record.log) : "";
                String expected = "VECTOR_V3_NODE_READY node=" + record.member + " pid=" + record.process.pid() + " profile=" + profile.fingerprint()
                        + " lineage=" + lineage + " code=" + code;
                ready &= logs.contains(expected) && logs.contains("VECTOR_V3_SERVICE_READY profile=" + profile.fingerprint() + " lineage=" + lineage)
                        && logs.contains("preparedArchiveCacheEnabled=true");
            }
            if (ready) break;
            require(System.nanoTime() < deadline, "all three actual profile/lineage/code readiness deadline exceeded"); Thread.sleep(20);
        }
    }
    private void snapshot(int leader, String expectedHash) throws Exception {
        require(ClusterTool.snapshot(root.resolve("node-" + leader).resolve("cluster").toFile(), System.out), "V3 snapshot request failed");
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        while (true) {
            boolean all = true;
            for (int node = 0; node < 3; node++) all &= Files.readString(log(node)).contains("VECTOR_V3_SNAPSHOT_WRITTEN profile="
                    + profile.fingerprint() + " lineage=" + lineage + " hash=" + expectedHash);
            if (all) return;
            require(System.nanoTime() < deadline, "all three combined snapshots did not match canonical hash"); Thread.sleep(20);
        }
    }
    private void stopOwned() throws Exception {
        boolean interrupted = Thread.interrupted(); boolean clean = true; List<String> reports = new ArrayList<>();
        try {
            for (Owned record : owned) {
                if (!record.process.isAlive()) { reports.add(record.process.pid() + ":alreadyStopped"); continue; }
                var info = record.process.info();
                boolean same = record.started != null && info.startInstant().map(record.started::equals).orElse(false)
                        && info.command().map(record.command::equals).orElse(false)
                        && info.arguments().map(args -> List.of(args).equals(record.arguments)).orElse(false);
                if (!same) { clean = false; reports.add(record.process.pid() + ":identityMismatchNoSignal"); continue; }
                record.process.destroy();
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                while (record.process.isAlive() && System.nanoTime() < deadline) {
                    try { record.process.waitFor(50, TimeUnit.MILLISECONDS); }
                    catch (InterruptedException cancelled) { interrupted = true; }
                }
                if (record.process.isAlive()) {
                    info = record.process.info();
                    boolean stillSame = record.started != null && info.startInstant().map(record.started::equals).orElse(false)
                            && info.command().map(record.command::equals).orElse(false)
                            && info.arguments().map(args -> List.of(args).equals(record.arguments)).orElse(false);
                    if (stillSame) record.process.destroyForcibly();
                    deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                    while (record.process.isAlive() && System.nanoTime() < deadline) {
                        try { record.process.waitFor(50, TimeUnit.MILLISECONDS); }
                        catch (InterruptedException cancelled) { interrupted = true; }
                    }
                }
                if (record.process.isAlive()) clean = false;
                reports.add(record.process.pid() + ":stopped=" + !record.process.isAlive());
            }
        } finally {
            allOwnedStopped = clean && owned.stream().noneMatch(r -> r.process.isAlive());
            Files.writeString(root.resolve("cleanup-g" + generation + '-' + UUID.randomUUID() + ".txt"),
                    "allOwnedStopped=" + allOwnedStopped + "\n" + String.join("\n", reports) + "\n", StandardOpenOption.CREATE_NEW);
            if (interrupted) Thread.currentThread().interrupt();
        }
        require(allOwnedStopped, "owned cleanup incomplete; preserve evidence and do not signal unrelated identities");
    }
    private void writeArtifactInventory() throws Exception {
        StringBuilder inventory = new StringBuilder();
        for (Class<?> type : List.of(RetentionNodeMainV3.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class)) {
            Path source = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if (Files.isDirectory(source)) {
                try (var walk = Files.walk(source)) {
                    for (Path file : walk.filter(p -> p.toString().endsWith(".class")).sorted().toList())
                        inventory.append(sha(Files.readAllBytes(file))).append(' ').append(Files.size(file)).append(' ').append(file).append('\n');
                }
            } else inventory.append(sha(Files.readAllBytes(source))).append(' ').append(Files.size(source)).append(' ').append(source).append('\n');
        }
        writeNew("artifact-inventory.sha256", inventory.toString());
    }
    private void writeNew(String name, String contents) throws IOException { Files.writeString(root.resolve(name), contents, StandardOpenOption.CREATE_NEW); }
    private static String sha(byte[] bytes) { return HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)); }
    private static void require(boolean condition,String message){if(!condition)throw new IllegalStateException(message);}
}
