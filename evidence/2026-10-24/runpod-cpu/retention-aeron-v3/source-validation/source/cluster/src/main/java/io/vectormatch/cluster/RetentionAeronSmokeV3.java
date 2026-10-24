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

/** Small real local 3-JVM correctness smoke; no rate/endurance/external durability claim. */
public final class RetentionAeronSmokeV3 {
    private static final Duration TIMEOUT = Duration.ofSeconds(20);
    private record Owned(Process process, Instant started, String command, List<String> arguments, Path log, int member, int generation) {}
    private final Path root;
    private final RetentionServiceV3.Profile profile = RetentionNodeMainV3.smokeProfile();
    private final String code = RetentionNodeMainV3.codeFingerprint(), lineage = "local-" + UUID.randomUUID();
    private final int ports;
    private final List<Owned> owned = new ArrayList<>();
    private final MatchingEngine reference = new MatchingEngine(8, profile.core().limits());
    private final List<Event> events = new ArrayList<>();
    private boolean allOwnedStopped = true;
    private int generation;
    private RetentionAeronSmokeV3(Path root) throws Exception {
        this.root = root.toAbsolutePath().normalize(); Files.createDirectory(this.root);
        if (Files.getFileStore(root).getUsableSpace() < 512L * 1024 * 1024) throw new IllegalStateException("local smoke requires 512MiB free guard");
        ports = ports();
        writeArtifactInventory();
        writeNew("registration.txt", "scope=LOCAL_THREE_JVM_LOOPBACK_V3_CORRECTNESS\nprofile=" + profile.fingerprint()
                + "\nlineage=" + lineage + "\ncode=" + code + "\nports=" + ports + "\nsync=2\nindependentHosts=false\n");
    }
    public static Path run(Path newRoot) throws Exception {
        RetentionAeronSmokeV3 smoke = new RetentionAeronSmokeV3(newRoot);
        boolean passed = false; Throwable failure = null;
        try { smoke.exercise(); passed = true; }
        catch (Throwable error) { failure = error; throw error; }
        finally {
            try { smoke.stopOwned(); }
            catch (Throwable cleanup) { if (failure != null) failure.addSuppressed(cleanup); else throw cleanup; }
            finally {
                smoke.writeNew("completion.json", "{\n  \"scope\": \"LOCAL_THREE_JVM_LOOPBACK_V3_CORRECTNESS\",\n  \"passed\": " + (passed && smoke.allOwnedStopped)
                        + ",\n  \"allOwnedStopped\": " + smoke.allOwnedStopped + ",\n  \"independentHosts\": false,\n  \"externalArchiveDurabilityProven\": false\n}\n");
            }
        }
        return smoke.root;
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("RetentionAeronSmokeV3 <new-state-directory>");
        System.out.println("VECTOR_V3_SMOKE_PASS evidence=" + run(Path.of(args[0])));
    }
    private void exercise() throws Exception {
        startOwned(); String checkpoint;
        try (var client = connect()) {
            boolean malformedRejected = false;
            try { client.exchange(new Business(new Deposit(1, "x".repeat(513), 1, Asset.BASE, 1)), TIMEOUT); }
            catch (IllegalArgumentException malformed) { malformedRejected = true; }
            require(malformedRejected && success(client.exchange(new Position(), TIMEOUT)).counters().applicationMutation() == 0,
                    "local encoding failure must release the one-inflight client slot without reaching business state");
            check(client, new Deposit(1, "fund", 1, Asset.BASE, 100));
            check(client, new Deposit(2, "fund", 1, Asset.QUOTE, 10_000));
            check(client, RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 40, TimeInForce.GTC));
            check(client, RetentionEngineV3.place(2, "orders", 1, Side.BUY, 10, 10, TimeInForce.IOC));
            Place maker = RetentionEngineV3.place(1, "orders", 2, Side.SELL, 10, 5, TimeInForce.GTC);
            check(client, maker); check(client, maker);
            for (int i = 1; i <= 40; i++) check(client, new Deposit(1, "trace", i, Asset.BASE, 1));
            var prepared = success(client.exchange(new PrepareArchive(reference.lastCommandSeq()), TIMEOUT));
            Descriptor descriptor = (Descriptor) prepared.payload(); require(descriptor.totalBytes() > MAX_ARCHIVE_CHUNK, "multi-chunk prefix required");
            check(client, new Deposit(1, "fund", 2, Asset.BASE, 1));
            byte[] archive = client.readArchive(descriptor, profile.maxCombinedSnapshotBytes(), TIMEOUT);
            Files.write(root.resolve("prepared-prefix.bin"), archive, StandardOpenOption.CREATE_NEW);
            require(Arrays.equals(archive, Files.readAllBytes(root.resolve("prepared-prefix.bin"))), "local smoke byte read-back differs");
            // This is a test assertion after local read-back, not evidence of external archive durability.
            var commit = new ArchiveCommit(new MaintenanceIdentity("archive", 1), descriptor.acknowledgement());
            var committed = success(client.exchange(commit, TIMEOUT)); require(committed.counters().coreMaintenanceSeq() == 1, "core ACK not applied");
            var stale = client.exchange(new ArchiveChunk(descriptor.acknowledgement(), descriptor.totalBytes(), 0, 32), TIMEOUT);
            require(stale.error().equals("ARCHIVE_STALE"), "freed archive bytes must be explicitly stale");
            var replay = success(client.exchange(commit, TIMEOUT)); require(((State) replay.payload()).maintenance().replayed(), "maintenance retry not cached");
            List<Event> fetched = new ArrayList<>();
            for (long from = 1; from <= reference.lastEventSeq();) {
                Events batch = (Events) success(client.exchange(new FetchEvents(from, 16), TIMEOUT)).payload();
                require(!batch.batch().events().isEmpty(), "event fetch gap"); fetched.addAll(batch.batch().events());
                from = batch.batch().events().getLast().eventSeq() + 1;
            }
            require(fetched.equals(events), "bounded event stream differs from independent matching reference");
            success(client.exchange(new EventAck(new MaintenanceIdentity("projector", 1), reference.lastEventSeq()), TIMEOUT));
            var position = success(client.exchange(new Position(), TIMEOUT));
            require(position.counters().acceptedPlaceCount() == 3, "maintenance/retry counted as new orders");
            Files.write(root.resolve("reference-before-checkpoint-v2.bin"), reference.snapshot(), StandardOpenOption.CREATE_NEW);
            checkpoint = position.counters().stateHash(); snapshot(client.leaderMemberId(), checkpoint);
        }
        stopOwned(); startOwned();
        try (var client = connect()) {
            var restored = success(client.exchange(new Position(), TIMEOUT));
            require(restored.counters().stateHash().equals(checkpoint), "cold restore combined canonical hash differs");
            for (int i = 0; i < 3; i++) require(Files.readString(log(i)).contains("restored=true hash=" + checkpoint), "all three nodes must restore this combined snapshot");
            check(client, RetentionEngineV3.place(1, "orders", 2, Side.SELL, 10, 5, TimeInForce.GTC));
            check(client, RetentionEngineV3.place(2, "orders", 2, Side.BUY, 10, 4, TimeInForce.GTC));
            var finalPosition = success(client.exchange(new Position(), TIMEOUT));
            require(finalPosition.counters().acceptedPlaceCount() == 4, "lineage accepted order total differs");
            Files.write(root.resolve("reference-final-v2.bin"), reference.snapshot(), StandardOpenOption.CREATE_NEW);
            snapshot(client.leaderMemberId(), finalPosition.counters().stateHash());
            writeNew("result.json", "{\n  \"passed\": true,\n  \"scope\": \"LOCAL_THREE_JVM_LOOPBACK_V3_CORRECTNESS\",\n  \"profileSha256\": \"" + profile.fingerprint()
                    + "\",\n  \"codeSha256\": \"" + code + "\",\n  \"lineage\": \"" + lineage + "\",\n  \"businessSeq\": " + reference.lastCommandSeq()
                    + ",\n  \"eventSeq\": " + reference.lastEventSeq() + ",\n  \"firstAcceptedPlaces\": 4,\n  \"preparedArchiveBytes\": " + Files.size(root.resolve("prepared-prefix.bin"))
                    + ",\n  \"checkpointSha256\": \"" + checkpoint + "\",\n  \"finalCombinedSha256\": \"" + finalPosition.counters().stateHash()
                    + "\",\n  \"allThreeNodeSnapshotsMatched\": true,\n  \"externalArchiveDurabilityProven\": false,\n  \"independentHosts\": false\n}\n");
        }
    }
    private RetentionClientV3 connect() { return new RetentionClientV3(root.resolve("client-" + generation), ports, profile, lineage); }
    private void check(RetentionClientV3 client, Command command) throws IOException {
        // Lossless framed command bytes plus complete readable reference outcomes.
        byte[] encoded = CommandCodec.request(0, command);
        try (var out = new DataOutputStream(Files.newOutputStream(root.resolve("reference-inputs-v2.bin"), StandardOpenOption.CREATE, StandardOpenOption.APPEND))) {
            out.writeInt(encoded.length); out.write(encoded);
        }
        Execution expected = reference.execute(command); events.addAll(expected.events());
        Files.writeString(root.resolve("reference-outcomes.txt"), command + "\n" + expected + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        Reply actual = success(client.exchange(new Business(command), TIMEOUT)); State state = (State) actual.payload();
        require(expected.result().equals(state.result()), "business result differs from uncompacted reference: " + command);
        if (expected.replayed()) require(state.replayed(), "business retry not deduplicated");
        require(reference.lastCommandSeq() == actual.counters().businessSeq() && reference.lastEventSeq() == actual.counters().eventSeq()
                && reference.lastMarketSeq() == actual.counters().marketSeq(), "business/event/market cursors differ");
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
