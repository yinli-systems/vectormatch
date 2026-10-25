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
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Actual UDP three-JVM correctness experiment,not a capacity or physical-host isolation test. */
public final class RetentionAsyncAeronSmokeV4 {
    private static final int LOAD_ORDERS=1000,MAX_IO_RECORDS=20000;
    private static final Duration TIMEOUT=Duration.ofSeconds(20);
    private record Owned(Process process,Instant started,String command,List<String> arguments,Path log,int member,int generation) {}
    private final Path root;
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    private final String code=RetentionNodeMainV3.codeFingerprint(),lineage="async-v4-"+UUID.randomUUID();
    private final int ports;
    private final List<Owned> owned=new ArrayList<>();
    private boolean allOwnedStopped=true;
    private int generation;
    private final long[] sequences=new long[128];
    private int orders;
    private long business;
    private RetentionAsyncAeronSmokeV4(Path newRoot)throws Exception{
        root=newRoot.toAbsolutePath().normalize();for(Path path=root;path!=null;path=path.getParent())require(!Files.isSymbolicLink(path),"symlink smoke root refused");
        Files.createDirectory(root);require(Files.getFileStore(root).getUsableSpace()>=768L*1024*1024,"768MiB free guard");ports=ports();writeArtifactInventory();
        writeJson("registration.json",Map.of("schema","async-v4-udp-functional-1","profile",profile.fingerprint(),"lineage",lineage,"code",code,
                "loadOrders",LOAD_ORDERS,"ports",ports,"syncLevel",2,"appointedLeader",0,"independentHosts",false,"capacityClaim",false));
    }
    public static void main(String[] args)throws Exception{
        if(args.length!=1)throw new IllegalArgumentException("RetentionAsyncAeronSmokeV4 <new-state-directory>");
        var smoke=new RetentionAsyncAeronSmokeV4(Path.of(args[0]));Throwable failure=null;boolean passed=false;
        try{smoke.exercise();passed=true;}
        catch(Throwable error){failure=error;
            if(error instanceof RetentionAsyncMaintenanceV4.Failure unresolved)try(var out=smoke.stream("failure-original-wires.bin")){for(byte[] wire:unresolved.originalWires())frame(out,wire);}
            if(error instanceof RetentionBatchOwnerV3.UnresolvedCommandException unresolved&&unresolved.originalWire()!=null)Files.write(smoke.root.resolve("failure-original-business-wire.bin"),unresolved.originalWire(),StandardOpenOption.CREATE_NEW);
            var text=new StringWriter();error.printStackTrace(new PrintWriter(text));smoke.writeNew("failure.txt",text.toString());throw error;}
        finally{try{smoke.stopOwned();}catch(Throwable cleanup){if(failure!=null)failure.addSuppressed(cleanup);else throw cleanup;}
            finally{smoke.writeJson("completion.json",Map.of("passed",passed&&smoke.allOwnedStopped,"allOwnedStopped",smoke.allOwnedStopped,
                    "independentHosts",false,"capacityOrEnduranceProven",false,"fundedExternalOrders",false));}}
        System.out.println("VECTOR_ASYNC_V4_UDP_FUNCTIONAL_PASS evidence="+smoke.root);
    }
    private void exercise()throws Exception{
        startOwned();var recording=new AtomicReference<RecordingIO>();var blocked=new CountDownLatch(1);var release=new CountDownLatch(1);
        var owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile,lineage,4),()->{
            var transport=new RetentionBatchAeronTransportV3(root.resolve("owner-driver"),ports,profile,lineage,true,6144);
            try{var io=new RecordingIO(transport);recording.set(io);return io;}catch(IOException error){transport.close();throw new UncheckedIOException(error);}
        });
        String finalHash;byte[] canonical;
        try(var preparation=new RetentionArchivePreparationV4(Math.toIntExact(profile.core().maxPendingSerializedBytes()+1024),64L*1024*1024,4);
            var writer=new RetentionDurableWriterV3(root.resolve("writer"),profile.core().maxPendingSerializedBytes()+1024,128L*1024*1024,16,path->{
                if(path.getFileName().toString().equals("0001-archive.bin")){blocked.countDown();try{if(!release.await(10,TimeUnit.SECONDS))throw new IOException("functional original archive gate expired");}
                    catch(InterruptedException error){Thread.currentThread().interrupt();throw new IOException(error);}}
            });var pipeline=new RetentionPrefixPersistenceV4(preparation,writer,profile,lineage,4);
            var coordinator=new RetentionAsyncMaintenanceV4(owner,writer,pipeline,profile,lineage,root.resolve("logical-trace-v4.bin"),4,32,6144,32,10000,16L*1024*1024)){
            try{
                drive(coordinator,RetentionAsyncMaintenanceV4.Phase.IDLE);
                business(coordinator,0,new Deposit(1,"maker",++sequences[0],Asset.BASE,LOAD_ORDERS));
                business(coordinator,1,new Deposit(2,"load-w1",++sequences[1],Asset.QUOTE,10L*LOAD_ORDERS));
                business(coordinator,0,RetentionEngineV3.place(1,"maker",++sequences[0],Side.SELL,10,LOAD_ORDERS,TimeInForce.GTC));
                loadThrough(coordinator,512);coordinator.start(512);drive(coordinator,RetentionAsyncMaintenanceV4.Phase.FILE_WAIT);
                require(blocked.await(2,TimeUnit.SECONDS),"original archive force gate not entered");
                require(!Files.exists(root.resolve("writer/0001-archive.bin.verified.txt")),"archive readback receipt must still be withheld");
                loadThrough(coordinator,640);
                require(recording.get().acceptedSnapshot().stream().noneMatch(request->request.operation() instanceof ArchiveCommit),"ACK escaped before original file proof");
                writeJson("held-original-file-business-progress.json",Map.of("passed",true,"firstCut",512,"knownBusinessSeq",business,
                        "extraDefinitelyAcceptedBusiness",128,"archiveReceiptStillAbsent",!Files.exists(root.resolve("writer/0001-archive.bin.verified.txt")),
                        "intentionalCorrectnessGate",true,"capacityClaim",false,"coordinator",coordinator.snapshot()));
                release.countDown();drive(coordinator,RetentionAsyncMaintenanceV4.Phase.IDLE);require(coordinator.takeCompleted().orElseThrow().acknowledgement().throughCommandSeq()==512,"first cut differs");
                require(((Number)coordinator.snapshot().get("reservedCommands")).intValue()==128,"later business must remain retained after prefix ACK");
                coordinator.start(640);drive(coordinator,RetentionAsyncMaintenanceV4.Phase.IDLE);coordinator.takeCompleted().orElseThrow();
                loadThrough(coordinator,1003);coordinator.start(1003);drive(coordinator,RetentionAsyncMaintenanceV4.Phase.IDLE);coordinator.takeCompleted().orElseThrow();
                require(((Number)coordinator.snapshot().get("reservedCommands")).intValue()==0,"all credits must clear after exact final ACK pair");
                Reply barrier=owner.exchangeMaintenance(new Position(),TIMEOUT);require(barrier.error().isEmpty(),"same-session final barrier failed");
                var reference=new RetentionClusteredServiceV3(profile,lineage,true);reference.onStart(null,null);
                var expected=new HashMap<Long,ArrayDeque<byte[]>>();
                for(var request:recording.get().acceptedSnapshot())expected.computeIfAbsent(request.correlationId(),key->new ArrayDeque<>()).add(reference.dispatch(request));
                for(var reply:recording.get().replySnapshot()){
                    var queue=expected.get(reply.correlationId());require(queue!=null&&!queue.isEmpty(),"reply lacks positive original offer");
                    require(Arrays.equals(queue.removeFirst(),RetentionReplyV3.encode(reply)),"actual network reply differs from canonical physical-order replay");
                }
                require(expected.values().stream().allMatch(ArrayDeque::isEmpty),"positive original offers lack complete replies");
                Field field=RetentionClusteredServiceV3.class.getDeclaredField("state");field.setAccessible(true);var state=(RetentionServiceV3)field.get(reference);
                canonical=state.snapshot();finalHash=sha(canonical);require(finalHash.equals(barrier.counters().stateHash()),"full combined final state differs");
                require(state.businessSeq()==1003&&state.eventSeq()==2003&&state.marketSeq()==2001&&state.acceptedPlaceCount()==1001,"exact command/trade fixture counters differ");
                require(state.pendingHistoryCount()==0&&state.outboxSize()==0&&state.exportedEventSeq()==2003,"exact final history/outbox release differs");
                require(state.account(2).base().available()==1000&&state.account(2).quote().available()==0&&state.account(1).quote().available()==10000,"matched balances differ");
                var restored=RetentionServiceV3.restore(canonical,profile,lineage);require(Arrays.equals(canonical,restored.snapshot()),"offline binary combined restore differs");
                Files.write(root.resolve("canonical-final-combined.bin"),canonical,StandardOpenOption.CREATE_NEW);
                writeJson("coordinator-final.json",coordinator.snapshot());writeJson("writer-final.json",writer.snapshot());
                require(barrier.counters().coreMaintenanceSeq()==3,"exact three archive cycles required");
                writeJson("network-replay.json",Map.of("passed",true,"allPositiveOffersAndRepliesMatched",true,"finalCombinedSha256",finalHash,
                        "businessSeq",state.businessSeq(),"eventSeq",state.eventSeq(),"marketSeq",state.marketSeq(),"loadOrders",orders,
                        "sameAdapterPhysicalOrderReplay",true,"independentAlgorithm",false));
            }finally{release.countDown();}
        }finally{release.countDown();try{writeJson("owner-before-close.json",owner.snapshot());}finally{owner.close();writeJson("owner-after-close.json",owner.snapshot());}}
        require(!Boolean.TRUE.equals(owner.snapshot().get("ownerThreadAlive")),"owned network thread still alive");
        try(var client=new RetentionClientV3(root.resolve("control-snapshot"),ports,profile,lineage)){
            Reply position=client.exchange(new Position(),TIMEOUT);require(position.error().isEmpty()&&position.counters().stateHash().equals(finalHash),"post-owner final state differs");snapshot(client.leaderMemberId(),finalHash);
        }
        stopOwned();startOwned();
        try(var client=new RetentionClientV3(root.resolve("control-cold"),ports,profile,lineage)){
            Reply position=client.exchange(new Position(),TIMEOUT);require(position.error().isEmpty()&&position.counters().stateHash().equals(finalHash),"actual three-node cold restore differs");
            for(int node=0;node<3;node++)require(Files.readString(log(node)).contains("restored=true hash="+finalHash),"each actual service must restore the same combined state");
        }
        writeJson("result.json",Map.of("passed",true,"independentHosts",false,"capacityOrEnduranceProven",false,"loadOrders",orders,
                "extraCommandsDuringHeldOriginalFile",128,"allThreeSnapshotHashesMatched",true,"allThreeColdRestoreHashesMatched",true,
                "finalCombinedSha256",finalHash,"clientRecoveryOrNewOrdersAfterColdRestore",false,"independentStorageDurabilityProven",false));
    }
    private void business(RetentionAsyncMaintenanceV4 coordinator,int worker,Command command)throws Exception{
        var ticket=coordinator.trySubmit(worker,command,System.nanoTime()+TIMEOUT.toNanos()).orElseThrow();var outcome=ticket.await(TIMEOUT);
        require(outcome.terminal()==RetentionBatchOwnerV3.Terminal.APPLIED&&outcome.result().accepted(),"business must be definitely accepted");business++;coordinator.step();
    }
    private void loadThrough(RetentionAsyncMaintenanceV4 coordinator,long target)throws Exception{
        while(business<target){int count=(int)Math.min(127,target-business);var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();
            for(int n=0;n<count;n++){int worker=1+(orders%127);var command=RetentionEngineV3.place(2,"load-w"+worker,++sequences[worker],Side.BUY,10,1,TimeInForce.IOC);
                tickets.add(coordinator.trySubmit(worker,command,System.nanoTime()+TIMEOUT.toNanos()).orElseThrow());orders++;}
            for(var ticket:tickets){var outcome=ticket.await(TIMEOUT);require(outcome.terminal()==RetentionBatchOwnerV3.Terminal.APPLIED&&outcome.result().accepted(),"load command not definitely accepted");business++;}
            coordinator.step();
        }
    }
    private void drive(RetentionAsyncMaintenanceV4 coordinator,RetentionAsyncMaintenanceV4.Phase target)throws Exception{
        long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(20);
        while(!coordinator.snapshot().get("phase").equals(target.name())){require(System.nanoTime()<end,"finite coordinator phase deadline:"+target);coordinator.step();Thread.sleep(1);}
    }
    private final class RecordingIO implements RetentionBatchOwnerIOV3 {
        private final RetentionBatchOwnerIOV3 delegate;
        private final List<Request> accepted=new ArrayList<>();private final List<Reply> replies=new ArrayList<>();
        private final DataOutputStream attempts,positive,egress;private final BufferedWriter codes;
        private int offers;
        RecordingIO(RetentionBatchOwnerIOV3 delegate)throws IOException{
            this.delegate=delegate;var opened=new ArrayList<Closeable>();
            try{
                attempts=stream("wire-attempts.bin");opened.add(attempts);positive=stream("wire-positive-offers.bin");opened.add(positive);egress=stream("wire-replies.bin");opened.add(egress);
                codes=Files.newBufferedWriter(root.resolve("offer-codes.csv"),StandardOpenOption.CREATE_NEW);opened.add(codes);codes.write("attempt,original_code,offer_called_monotonic_ns,offer_returned_monotonic_ns\n");
            }catch(IOException|RuntimeException|Error error){for(var stream:opened)try{stream.close();}catch(IOException close){error.addSuppressed(close);}throw error;}
        }
        public long offer(byte[] bytes){try{require(++offers<=MAX_IO_RECORDS,"finite original offer bound");frame(attempts,bytes);attempts.flush();long called=System.nanoTime();long value=delegate.offer(bytes);long returned=System.nanoTime();codes.write(offers+","+value+","+called+","+returned+"\n");codes.flush();
            if(value>=0){synchronized(this){accepted.add(RetentionWireV3.decode(bytes));}frame(positive,bytes);positive.flush();}return value;
        }catch(IOException error){throw new UncheckedIOException(error);}}
        public int poll(Consumer<Reply> consumer){return delegate.poll(reply->{try{require(replies.size()<MAX_IO_RECORDS,"finite reply bound");synchronized(this){replies.add(reply);}frame(egress,RetentionReplyV3.encode(reply));egress.flush();consumer.accept(reply);}catch(IOException error){throw new UncheckedIOException(error);}});}
        synchronized List<Request> acceptedSnapshot(){return List.copyOf(accepted);}synchronized List<Reply> replySnapshot(){return List.copyOf(replies);}
        public Map<String,Object> observation(){return delegate.observation();}
        public void close(){Throwable failure=null;try{writeJson("actual-transport-before-close.json",delegate.observation());}catch(Throwable error){failure=error;}
            try{delegate.close();}catch(Throwable error){if(failure==null)failure=error;else failure.addSuppressed(error);}
            for(var stream:List.of(attempts,positive,egress,codes))try{stream.close();}catch(Throwable error){if(failure==null)failure=error;else failure.addSuppressed(error);}
            if(failure!=null)throw new IllegalStateException("recording transport cleanup failed",failure);}
    }
    private DataOutputStream stream(String name)throws IOException{return new DataOutputStream(Files.newOutputStream(root.resolve(name),StandardOpenOption.CREATE_NEW));}
    private static void frame(DataOutputStream out,byte[] bytes)throws IOException{out.writeInt(bytes.length);out.write(bytes);}
    private void writeJson(String name,Object value)throws IOException{writeNew(name,RetentionCapacityJsonV3.json(value)+"\n");}
    private Path log(int node) { return root.resolve("node-" + node + "-g" + generation + ".log"); }
    private void startOwned() throws Exception {
        generation++; LinkedHashSet<String> classpath = new LinkedHashSet<>();
        for (Class<?> type : List.of(RetentionNodeMainV3.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class))
            classpath.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        for (int member = 0; member < 3; member++) {
            List<String> argv = List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED", "-Xmx256m",
                    "-Daeron.cluster.appointed.leader.id=0", "-cp", String.join(File.pathSeparator, classpath), RetentionNodeMainV3.class.getName(),
                    Integer.toString(member), root.toString(), Integer.toString(ports), "2", RetentionBatchProfilesV3.PROFILE_ID, lineage, profile.fingerprint(), code, "bounded-maintenance-v1");
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
    private static int ports() throws Exception {
        for (int attempt = 0; attempt < 30; attempt++) {
            int base = ThreadLocalRandom.current().nextInt(35000, 55000); List<DatagramSocket> sockets = new ArrayList<>();
            try {
                for (int member = 0; member < 3; member++) for (int offset = 1; offset <= 5; offset++)
                    sockets.add(new DatagramSocket(base + member * 100 + offset, InetAddress.getByName("127.0.0.1")));
                return base;
            } catch (BindException occupied) { /* No state/commands exist yet; choose an unused port range. */ }
            finally { sockets.forEach(DatagramSocket::close); }
        }
        throw new IllegalStateException("no separated loopback UDP port range available");
    }
    private static void require(boolean condition, String message) { if (!condition) throw new IllegalStateException(message); }
}
