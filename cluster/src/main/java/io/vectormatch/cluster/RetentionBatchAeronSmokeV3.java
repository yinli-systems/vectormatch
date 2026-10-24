package io.vectormatch.cluster;

import io.aeron.cluster.ClusterTool;
import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.agrona.DirectBuffer;

import java.io.*;
import java.net.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Fresh cap4 batch functional smoke; local three JVMs, no capacity/endurance/external durability claim. */
public final class RetentionBatchAeronSmokeV3 {
    private static final Duration TIMEOUT = Duration.ofSeconds(20);
    private record Owned(Process process, Instant started, String command, List<String> arguments, Path log, int member, int generation) {}
    private final Path root;
    private final RetentionServiceV3.Profile profile = RetentionNodeMainV3.smokeProfile();
    private final String code = RetentionNodeMainV3.codeFingerprint(), lineage = "local-" + UUID.randomUUID();
    private final int ports;
    private final List<Owned> owned = new ArrayList<>();
    private final MatchingEngine reference = new MatchingEngine(8, profile.core().limits());
    private final List<Event> events = new ArrayList<>();
    private final RetentionServiceV3 singleReference = new RetentionServiceV3(profile, lineage);
    private boolean allOwnedStopped = true;
    private int generation;
    private RetentionBatchAeronSmokeV3(Path root) throws Exception {
        this.root = root.toAbsolutePath().normalize(); Files.createDirectory(this.root);
        if (Files.getFileStore(root).getUsableSpace() < 512L * 1024 * 1024) throw new IllegalStateException("local smoke requires 512MiB free guard");
        ports = ports();
        writeArtifactInventory();
        writeNew("registration.txt", "scope=LOCAL_THREE_JVM_LOOPBACK_V3_CAP4_BATCH_CORRECTNESS\nprofile=" + profile.fingerprint()
                + "\nlineage=" + lineage + "\ncode=" + code + "\nports=" + ports + "\nsync=2\nindependentHosts=false\n");
    }
    public static Path run(Path newRoot) throws Exception {
        RetentionBatchAeronSmokeV3 smoke = new RetentionBatchAeronSmokeV3(newRoot);
        boolean passed = false; Throwable failure = null;
        try { smoke.exercise(); passed = true; }
        catch (Throwable error) {
            failure = error;
            try {
                var trace = new StringWriter(); error.printStackTrace(new PrintWriter(trace));
                smoke.writeNew("failure.txt", trace.toString());
            } catch (Throwable receiptFailure) { error.addSuppressed(receiptFailure); }
            throw error;
        }
        finally {
            try { smoke.stopOwned(); }
            catch (Throwable cleanup) { if (failure != null) failure.addSuppressed(cleanup); else throw cleanup; }
            finally {
                smoke.writeNew("completion.json", "{\n  \"scope\": \"LOCAL_THREE_JVM_LOOPBACK_V3_CAP4_BATCH_CORRECTNESS\",\n  \"passed\": " + (passed && smoke.allOwnedStopped)
                        + ",\n  \"allOwnedStopped\": " + smoke.allOwnedStopped + ",\n  \"independentHosts\": false,\n  \"externalArchiveDurabilityProven\": false\n}\n");
            }
        }
        return smoke.root;
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("RetentionBatchAeronSmokeV3 <new-state-directory>");
        System.out.println("VECTOR_V3_SMOKE_PASS evidence=" + run(Path.of(args[0])));
    }
    private void exercise() throws Exception {
        startOwned(); String checkpoint;
        List<Command> funding = List.of(new Deposit(1, "fund", 1, Asset.BASE, 100), new Deposit(2, "fund", 1, Asset.QUOTE, 10000),
                new Deposit(3, "fund", 1, Asset.BASE, 100), new Deposit(4, "fund", 1, Asset.QUOTE, 10000));
        List<Command> orders = List.of(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 40, TimeInForce.GTC),
                RetentionEngineV3.place(2, "orders", 1, Side.BUY, 10, 10, TimeInForce.IOC),
                RetentionEngineV3.place(3, "orders", 1, Side.SELL, 10, 5, TimeInForce.GTC),
                RetentionEngineV3.place(4, "orders", 1, Side.BUY, 10, 4, TimeInForce.GTC));
        var discarded = new java.util.concurrent.atomic.AtomicBoolean();
        try (var client = new RetentionClientV3(root.resolve("client-" + generation), ports, profile, lineage,
                reply -> !(reply.payload() instanceof Batch) || !discarded.compareAndSet(false, true))) {
            // Fault injection is an application reply discard, not a UDP-loss or durability experiment.
            var batch = new BusinessBatch(funding); boolean unknown = false;
            try { client.exchange(batch, Duration.ofMillis(250)); }
            catch (RetentionClientV3.UnknownBatchException loss) {
                unknown = true;
                Files.write(root.resolve("discarded-batch-original-request.bin"), loss.originalRequestBytes(), StandardOpenOption.CREATE_NEW);
                require(RetentionWireV3.decode(loss.originalRequestBytes()).operation().equals(batch), "UNKNOWN lost original identities");
                writeNew("unknown-reply.txt", loss.getMessage() + "\ncorrelation=" + loss.correlationId() + "\napplicationReplyDiscard=true\n");
            }
            require(unknown && discarded.get(), "bounded application-layer batch reply loss must produce explicit UNKNOWN");
            boolean fenced = false;
            try { client.exchange(new Business(new Deposit(1, "different", 1, Asset.BASE, 1)), TIMEOUT); }
            catch (IllegalStateException blocked) { fenced = blocked.getMessage().contains("unresolved functional batch"); }
            require(fenced, "unresolved batch must block different business inputs in this single-owner client");
            // Service saw the first copy before the application discarded its reply.
            for (Command command : funding) {
                events.addAll(reference.execute(command).events()); singleReference.handle(new Request(new Scope(profile.fingerprint(), lineage), 0, new Business(command)));
            }
            // Recover exactly the original four keys; only service application-mutation advances on replay.
            checkBatch(client, funding, true);
            checkBatch(client, orders, false);
            checkBatch(client, orders, true);
            var position = success(client.exchange(new Position(), TIMEOUT));
            checkpoint = position.counters().stateHash();
            require(checkpoint.equals(sha(singleReference.snapshot())), "batch vs sequential service canonical snapshot differs");
            Files.write(root.resolve("single-reference-before-checkpoint.bin"), singleReference.snapshot(), StandardOpenOption.CREATE_NEW);
            snapshot(client.leaderMemberId(), checkpoint);
        }
        stopOwned(); startOwned();
        try (var client = connect()) {
            var restored = success(client.exchange(new Position(), TIMEOUT));
            require(restored.counters().stateHash().equals(checkpoint), "cold combined checkpoint differs");
            for (int i = 0; i < 3; i++) require(Files.readString(log(i)).contains("restored=true hash=" + checkpoint), "three-node cold restore evidence missing");
            List<Command> continued = List.of(orders.get(0), RetentionEngineV3.place(2, "orders", 2, Side.BUY, 10, 4, TimeInForce.IOC),
                    orders.get(2), RetentionEngineV3.place(4, "orders", 2, Side.BUY, 10, 4, TimeInForce.GTC));
            checkBatch(client, continued, false);
            var finalPosition = success(client.exchange(new Position(), TIMEOUT));
            require(finalPosition.counters().acceptedPlaceCount() == 6, "retry or batch envelope counted as a fresh order");
            require(finalPosition.counters().stateHash().equals(sha(singleReference.snapshot())), "cold batch continuation canonical mismatch");
            List<Event> fetched = new ArrayList<>();
            for (long from = 1; from <= reference.lastEventSeq();) {
                var batch = (Events) success(client.exchange(new FetchEvents(from, 16), TIMEOUT)).payload();
                require(!batch.batch().events().isEmpty(), "bounded event stream gap"); fetched.addAll(batch.batch().events());
                from = batch.batch().events().getLast().eventSeq() + 1;
            }
            require(fetched.equals(events), "FIFO/trades/event sequence differs from independent single-command engine");
            Files.write(root.resolve("single-reference-final.bin"), singleReference.snapshot(), StandardOpenOption.CREATE_NEW);
            Files.write(root.resolve("matching-reference-final-v2.bin"), reference.snapshot(), StandardOpenOption.CREATE_NEW);
            snapshot(client.leaderMemberId(), finalPosition.counters().stateHash());
            writeNew("result.json", "{\n  \"passed\": true,\n  \"scope\": \"LOCAL_THREE_JVM_LOOPBACK_V3_CAP4_BATCH_CORRECTNESS\",\n  \"profileSha256\": \"" + profile.fingerprint()
                    + "\",\n  \"codeSha256\": \"" + code + "\",\n  \"lineage\": \"" + lineage + "\",\n  \"businessSeq\": " + reference.lastCommandSeq()
                    + ",\n  \"eventSeq\": " + reference.lastEventSeq() + ",\n  \"firstAcceptedPlaces\": 6,\n  \"actualBatchReplyDiscarded\": true,\n  \"originalUnknownRequestRetained\": true,\n  \"allThreeNodeSnapshotsMatched\": true,\n  \"checkpointSha256\": \"" + checkpoint + "\",\n  \"finalCombinedSha256\": \"" + finalPosition.counters().stateHash()
                    + "\",\n  \"externalArchiveDurabilityProven\": false,\n  \"capacityOrRetentionCreditProven\": false,\n  \"independentHosts\": false\n}\n");
        }
    }
    private RetentionClientV3 connect() { return new RetentionClientV3(root.resolve("client-" + generation), ports, profile, lineage); }
    private void checkBatch(RetentionClientV3 client, List<Command> commands, boolean requireAllReplayed) throws IOException {
        var operation = new BusinessBatch(commands);
        Reply actual;
        try { actual = success(client.exchange(operation, TIMEOUT)); }
        catch (RetentionClientV3.UnknownBatchException failure) {
            Files.write(root.resolve("unexpected-unknown-" + UUID.randomUUID() + ".bin"), failure.originalRequestBytes(), StandardOpenOption.CREATE_NEW);
            throw failure;
        }
        byte[] requestBytes = RetentionWireV3.encode(new Request(new Scope(profile.fingerprint(), lineage), actual.correlationId(), operation));
        for (var pair : List.of(Map.entry("wire-requests-v3.bin", requestBytes), Map.entry("wire-replies-v3.bin", RetentionReplyV3.encode(actual)))) {
            try (var out = new DataOutputStream(Files.newOutputStream(root.resolve(pair.getKey()), StandardOpenOption.CREATE, StandardOpenOption.APPEND))) {
                out.writeInt(pair.getValue().length); out.write(pair.getValue());
            }
        }
        RetentionClientV3.validateBatchResponse(operation, actual); Batch result = (Batch) actual.payload();
        for (int i = 0; i < commands.size(); i++) {
            Command command = commands.get(i); Execution expected = reference.execute(command); events.addAll(expected.events());
            var sequential = singleReference.handle(new Request(new Scope(profile.fingerprint(), lineage), actual.correlationId(), new Business(command)));
            BatchEntry entry = result.entries().get(i);
            require(entry.status() == BatchStatus.APPLIED && expected.result().equals(entry.result()), "batch result differs from independent single-command matching reference");
            require(entry.replayed() == expected.replayed() && (!requireAllReplayed || entry.replayed()), "batch retry did not resolve through original cached identity");
            require(entry.frontier().equals(new Frontier(sequential.applicationMutation(), singleReference.businessSeq(), singleReference.eventSeq(), singleReference.marketSeq())), "per-entry application/business/event/market frontier differs");
            Files.writeString(root.resolve("reference-outcomes.txt"), command + "\n" + expected + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        }
        require(actual.counters().businessSeq() == reference.lastCommandSeq() && actual.counters().eventSeq() == reference.lastEventSeq()
                && actual.counters().marketSeq() == reference.lastMarketSeq(), "batch final counters differ");
    }
    private static Reply success(Reply reply) { require(reply.error().isEmpty(), "V3 error " + reply.error()); return reply; }
    private Path log(int node) { return root.resolve("node-" + node + "-g" + generation + ".log"); }
    private void startOwned() throws Exception {
        generation++; LinkedHashSet<String> classpath = new LinkedHashSet<>();
        for (Class<?> type : List.of(RetentionNodeMainV3.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class))
            classpath.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        for (int member = 0; member < 3; member++) {
            List<String> argv = List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED", "-Xmx256m",
                    "-Daeron.cluster.appointed.leader.id=0", "-cp", String.join(File.pathSeparator, classpath), RetentionNodeMainV3.class.getName(),
                    Integer.toString(member), root.toString(), Integer.toString(ports), "2", RetentionNodeMainV3.PROFILE_ID, lineage, profile.fingerprint(), code);
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
                ready &= logs.contains(expected) && logs.contains("VECTOR_V3_SERVICE_READY profile=" + profile.fingerprint() + " lineage=" + lineage);
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
