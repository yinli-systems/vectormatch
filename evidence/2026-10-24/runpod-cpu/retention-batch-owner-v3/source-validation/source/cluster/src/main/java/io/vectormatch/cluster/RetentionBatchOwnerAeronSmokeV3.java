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
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Fresh W128 owner transport/continuation fixture, not an arrival-rate or capacity experiment. */
public final class RetentionBatchOwnerAeronSmokeV3 {
    private static final Duration TIMEOUT = Duration.ofSeconds(20);
    private static final int WORKERS = 128, MAX_IO_RECORDS = 4096;
    private static final String SCOPE_LABEL = "LOCAL_THREE_JVM_LOOPBACK_V3_W128_OWNER_FUNCTIONAL";
    private record Owned(Process process, Instant started, String command, List<String> arguments, Path log, int member, int generation) {}
    private final Path root;
    private final int batchCap;
    private final RetentionServiceV3.Profile profile = RetentionBatchProfilesV3.finiteLoadProfile();
    private final String code = RetentionNodeMainV3.codeFingerprint(), lineage = "owner-local-" + UUID.randomUUID();
    private final int ports;
    private final List<Owned> owned = new ArrayList<>();
    private final MatchingEngine reference = new MatchingEngine(profile.core().resultCachePerProducer(), profile.core().limits());
    private final RetentionServiceV3 singleReference = new RetentionServiceV3(profile, lineage);
    private final List<Event> events = new ArrayList<>();
    private boolean allOwnedStopped = true;
    private int generation;

    private RetentionBatchOwnerAeronSmokeV3(Path root, int batchCap) throws Exception {
        if (batchCap != 1 && batchCap != 4) throw new IllegalArgumentException("owner smoke batch cap must be 1 or 4");
        this.batchCap = batchCap; this.root = root.toAbsolutePath().normalize(); Files.createDirectory(this.root);
        if (Files.getFileStore(this.root).getUsableSpace() < 512L * 1024 * 1024)
            throw new IllegalStateException("local owner smoke requires 512MiB free guard");
        ports = ports(); writeArtifactInventory();
        writeNew("registration.txt", "scope=" + SCOPE_LABEL + "\nbatchCap=" + batchCap + "\nlogicalWorkers=128\nexternalTaskQueueCapacityPerWorker=64"
                + "\nflushDelayNs=50000\nprofile=" + profile.fingerprint() + "\nlineage=" + lineage + "\ncode=" + code + "\nports=" + ports
                + "\nsync=2\nstrictNoPhysicalResends=true\nindependentHosts=false\ncapacityClaim=false\n");
    }
    public static Path run(Path newRoot, int batchCap) throws Exception {
        var smoke = new RetentionBatchOwnerAeronSmokeV3(newRoot, batchCap);
        boolean passed = false; Throwable failure = null;
        try { smoke.exercise(); passed = true; }
        catch (Throwable error) {
            failure = error;
            try { var trace = new StringWriter(); error.printStackTrace(new PrintWriter(trace)); smoke.writeNew("failure.txt", trace.toString()); }
            catch (Throwable receiptFailure) { error.addSuppressed(receiptFailure); }
            throw error;
        } finally {
            try { smoke.stopOwned(); }
            catch (Throwable cleanup) { if (failure != null) failure.addSuppressed(cleanup); else throw cleanup; }
            finally { smoke.writeJson("completion.json", Map.of("scope", SCOPE_LABEL, "batchCap", batchCap,
                    "passed", passed && smoke.allOwnedStopped, "allOwnedStopped", smoke.allOwnedStopped,
                    "independentHosts", false, "capacityOrEnduranceProven", false, "externalArchiveDurabilityProven", false)); }
        }
        return smoke.root;
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("RetentionBatchOwnerAeronSmokeV3 <new-state-directory> <batch-cap:1|4>");
        System.out.println("VECTOR_V3_OWNER_SMOKE_PASS evidence=" + run(Path.of(args[0]), Integer.parseInt(args[1])));
    }
    private RetentionClientV3 control(String label) { return new RetentionClientV3(root.resolve("control-" + label), ports, profile, lineage); }
    private void exercise() throws Exception {
        startOwned();
        try (var client = control("setup")) {
            for (Command command : List.of(new Deposit(1, "fund", 1, Asset.BASE, 256), new Deposit(2, "fund", 1, Asset.QUOTE, 2560),
                    RetentionEngineV3.place(1, "maker", 1, Side.SELL, 10, 128, TimeInForce.GTC),
                    RetentionEngineV3.place(1, "maker", 2, Side.SELL, 10, 128, TimeInForce.GTC))) {
                Reply actual = success(client.exchange(new Business(command), TIMEOUT));
                Execution expected = reference.execute(command); events.addAll(expected.events());
                var sequential = singleReference.handle(new Request(scope(), actual.correlationId(), new Business(command)));
                require(actual.payload() instanceof State state && expected.result().equals(state.result()) && !state.replayed(), "setup single result differs");
                require(actual.counters().applicationMutation() == sequential.applicationMutation(), "setup unexpected replay/mutation");
                appendRecord("setup-wire-requests.bin", RetentionWireV3.encode(new Request(scope(), actual.correlationId(), new Business(command))));
                appendRecord("setup-wire-replies.bin", RetentionReplyV3.encode(actual));
            }
            verifyPosition(client, "setup");
        }
        runOwnerRound(1);
        String checkpoint;
        try (var client = control("checkpoint")) {
            var position = verifyPosition(client, "before-checkpoint"); checkpoint = position.counters().stateHash();
            Files.write(root.resolve("single-reference-before-checkpoint.bin"), singleReference.snapshot(), StandardOpenOption.CREATE_NEW);
            snapshot(client.leaderMemberId(), checkpoint);
        }
        stopOwned(); startOwned();
        try (var client = control("cold-restore")) {
            var restored = verifyPosition(client, "cold-restore");
            require(restored.counters().stateHash().equals(checkpoint), "cold combined checkpoint differs");
            for (int i = 0; i < 3; i++) require(Files.readString(log(i)).contains("restored=true hash=" + checkpoint), "three cold JVMs did not restore exact checkpoint");
        }
        runOwnerRound(2);
        try (var client = control("final")) {
            var position = verifyPosition(client, "final");
            require(position.counters().acceptedPlaceCount() == 258 && position.counters().businessSeq() == 260,
                    "expected exactly 258 first accepted Places and 260 business commands");
            require(position.counters().eventSeq() == 516 && position.counters().marketSeq() == 514, "fixture event totals differ");
            List<Event> fetched = new ArrayList<>();
            for (long from = 1; from <= reference.lastEventSeq();) {
                Reply reply = success(client.exchange(new FetchEvents(from, 16), TIMEOUT));
                appendRecord("final-event-wire-replies.bin", RetentionReplyV3.encode(reply));
                require(reply.payload() instanceof Events, "event payload missing");
                var batch = ((Events) reply.payload()).batch(); require(!batch.events().isEmpty(), "complete event stream has a gap");
                fetched.addAll(batch.events()); from = batch.events().getLast().eventSeq() + 1;
            }
            require(fetched.equals(events), "full FIFO/trade/event stream differs from sequential reference");
            Files.write(root.resolve("single-reference-final.bin"), singleReference.snapshot(), StandardOpenOption.CREATE_NEW);
            Files.write(root.resolve("matching-reference-final-v2.bin"), reference.snapshot(), StandardOpenOption.CREATE_NEW);
            snapshot(client.leaderMemberId(), position.counters().stateHash());
            var result = new LinkedHashMap<String, Object>();
            result.put("passed", true); result.put("scope", SCOPE_LABEL); result.put("batchCap", batchCap);
            result.put("profileSha256", profile.fingerprint()); result.put("codeSha256", code); result.put("lineage", lineage);
            result.put("businessSeq", position.counters().businessSeq()); result.put("eventSeq", position.counters().eventSeq());
            result.put("firstAcceptedPlaces", position.counters().acceptedPlaceCount()); result.put("logicalWorkers", WORKERS);
            result.put("physicalFramesPerRound", WORKERS / batchCap); result.put("strictNoPhysicalResends", true);
            result.put("allThreeNodeSnapshotsMatched", true); result.put("checkpointSha256", checkpoint);
            result.put("finalCombinedSha256", position.counters().stateHash());
            result.put("referenceImplementation", "same MatchingEngine class and sequential RetentionServiceV3, replayed in actual accepted first-offer order; not an independent algorithm");
            result.put("capacityOrEnduranceProven", false); result.put("externalArchiveDurabilityProven", false); result.put("independentHosts", false);
            writeJson("result.json", result);
        }
    }
    private Scope scope() { return new Scope(profile.fingerprint(), lineage); }
    private Reply verifyPosition(RetentionClientV3 client, String label) throws IOException {
        Reply position = success(client.exchange(new Position(), TIMEOUT));
        appendRecord("position-wire-replies.bin", RetentionReplyV3.encode(position));
        require(position.counters().stateHash().equals(sha(singleReference.snapshot())), label + " combined snapshot differs from sequential service");
        require(position.counters().businessSeq() == reference.lastCommandSeq() && position.counters().eventSeq() == reference.lastEventSeq()
                && position.counters().marketSeq() == reference.lastMarketSeq(), label + " matching counters differ");
        return position;
    }
    private void runOwnerRound(int round) throws Exception {
        var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var recording = new AtomicReference<RecordingIO>();
        String prefix = "owner-round-" + round;
        var owner = new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile, lineage, batchCap), () -> {
            var io = new RecordingIO(new RetentionBatchAeronTransportV3(root.resolve(prefix + "-driver"), ports, profile, lineage), prefix, entered, release);
            recording.set(io); return io;
        });
        var tickets = new ArrayList<RetentionBatchOwnerV3.Ticket>(WORKERS);
        var outcomes = new LinkedHashMap<BusinessIdentity, RetentionBatchOwnerV3.Outcome>();
        Map<String, Object> before = Map.of();
        try {
            require(entered.await(5, TimeUnit.SECONDS), "owner did not enter first-poll setup gate");
            long permit = System.nanoTime() + TIMEOUT.toNanos();
            for (int worker = 0; worker < WORKERS; worker++) tickets.add(owner.submit(worker,
                    RetentionEngineV3.place(2, "load-w" + worker, round, Side.BUY, 10, 1, TimeInForce.IOC), permit));
            var gated = owner.snapshot(); writeJson(prefix + "-gated.json", gated);
            require(number(gated, "pendingLogicalCommands") == WORKERS && number(gated, "acceptedPhysicalOffers") == 0,
                    "fixture must enqueue all 128 logical slots before first offer");
            release.countDown(); owner.wake();
            long deadline = System.nanoTime() + TIMEOUT.toNanos();
            for (var ticket : tickets) {
                long remaining = deadline - System.nanoTime(); require(remaining > 0, "bounded owner round deadline");
                RetentionBatchOwnerV3.Outcome outcome;
                try { outcome = ticket.await(Duration.ofNanos(remaining)); }
                catch (RetentionBatchOwnerV3.UnresolvedCommandException unknown) {
                    if (unknown.originalWire() != null) Files.write(root.resolve(prefix + "-unknown-" + ticket.identity().producerId() + ".bin"), unknown.originalWire(), StandardOpenOption.CREATE_NEW);
                    throw unknown;
                }
                require(outcome.terminal() == RetentionBatchOwnerV3.Terminal.APPLIED, "functional load outcome not applied");
                require(outcomes.put(outcome.identity(), outcome) == null, "duplicate logical outcome");
            }
            before = owner.snapshot();
        } finally {
            release.countDown();
            try { writeJson(prefix + "-owner-before-close.json", owner.snapshot()); }
            finally { try { owner.close(); } finally { writeJson(prefix + "-owner-after-close.json", owner.snapshot()); } }
        }
        var after = owner.snapshot();
        require(!Boolean.TRUE.equals(after.get("ownerThreadAlive")) && after.get("failureType") == null, "network owner failed or remained alive");
        require(number(before, "firstAcceptedLogicalCommands") == WORKERS && number(before, "acceptedPhysicalOffers") == WORKERS / batchCap
                && number(before, "physicalResends") == 0 && number(before, "logicalAppliedResults") == WORKERS
                && number(before, "unresolvedPossiblyExecutedLogicalCommands") == 0 && number(before, "logicalNotSent") == 0,
                "strict physical-frame/no-resend/logical-closure fixture contract failed");
        RecordingIO io = Objects.requireNonNull(recording.get());
        require(io.accepted.size() == WORKERS / batchCap && io.replies.size() == io.accepted.size(), "complete actual accepted-wire/reply set missing");
        var replies = new LinkedHashMap<Long, Reply>();
        for (Reply reply : io.replies) require(replies.put(reply.correlationId(), reply) == null, "duplicate actual application reply");
        for (Request request : io.accepted) {
            BusinessBatch batch = (BusinessBatch) request.operation();
            require(batch.commands().size() == batchCap, "gate must form exactly full fixture frames");
            Reply actual = Objects.requireNonNull(replies.remove(request.correlationId()), "actual reply absent");
            RetentionClientV3.validateBatchResponse(batch, actual); Batch actualBatch = (Batch) success(actual).payload();
            for (int index = 0; index < batch.commands().size(); index++) {
                Command command = batch.commands().get(index); Execution expected = reference.execute(command); events.addAll(expected.events());
                var sequential = singleReference.handle(new Request(scope(), request.correlationId(), new Business(command)));
                BatchEntry entry = actualBatch.entries().get(index); var outcome = outcomes.remove(businessIdentity(command));
                Frontier expectedFrontier = new Frontier(sequential.applicationMutation(), singleReference.businessSeq(), singleReference.eventSeq(), singleReference.marketSeq());
                require(entry.status() == BatchStatus.APPLIED && expected.result().equals(entry.result()) && !entry.replayed(), "actual owner result differs from sequential matching");
                require(expectedFrontier.equals(entry.frontier()), "actual per-item frontier differs from sequential service");
                require(outcome != null && outcome.result().equals(expected.result()) && !outcome.replayed()
                        && outcome.commandSha256().equals(businessCanonicalSha256(command)) && outcome.frontier().equals(expectedFrontier), "ticket differs from full bound actual reply");
                Files.writeString(root.resolve("reference-outcomes.txt"), "round=" + round + "\n" + command + "\n" + expected + "\nfrontier=" + expectedFrontier + "\n",
                        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
            }
            require(actual.counters().applicationMutation() == singleReference.applicationMutation()
                    && actual.counters().businessSeq() == reference.lastCommandSeq() && actual.counters().eventSeq() == reference.lastEventSeq()
                    && actual.counters().marketSeq() == reference.lastMarketSeq(), "complete actual frame counters differ");
        }
        require(replies.isEmpty() && outcomes.isEmpty(), "unconsumed actual wire replies or logical outcomes");
    }
    private final class RecordingIO implements RetentionBatchOwnerIOV3 {
        final RetentionBatchOwnerIOV3 delegate;
        final String prefix;
        final CountDownLatch entered, release;
        final List<Request> accepted = new ArrayList<>();
        final List<Reply> replies = new ArrayList<>();
        final Set<Long> acceptedCorrelations = new HashSet<>();
        int offers;
        boolean gated;
        RecordingIO(RetentionBatchOwnerIOV3 delegate, String prefix, CountDownLatch entered, CountDownLatch release) {
            this.delegate = delegate; this.prefix = prefix; this.entered = entered; this.release = release;
        }
        public long offer(byte[] bytes) {
            try {
                require(++offers <= MAX_IO_RECORDS, "bounded functional offer-attempt inventory exceeded");
                appendRecord(prefix + "-wire-offer-attempts.bin", bytes);
                long code = delegate.offer(bytes);
                Files.writeString(root.resolve(prefix + "-offer-codes.csv"), offers + "," + code + "\n", StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                if (code >= 0) {
                    Request request = RetentionWireV3.decode(bytes);
                    require(acceptedCorrelations.add(request.correlationId()), "physical resend violates this functional fixture");
                    require(accepted.size() < WORKERS, "bounded accepted-frame inventory exceeded"); accepted.add(request);
                    appendRecord(prefix + "-wire-accepted-requests.bin", bytes);
                }
                return code;
            } catch (IOException failure) { throw new UncheckedIOException(failure); }
        }
        public int poll(Consumer<Reply> consumer) {
            if (!gated) {
                gated = true; entered.countDown();
                try { require(release.await(5, TimeUnit.SECONDS), "128-submit owner setup gate deadline"); }
                catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new IllegalStateException("owner gate interrupted", interrupted); }
            }
            return delegate.poll(reply -> {
                require(replies.size() < WORKERS, "bounded actual-reply inventory exceeded"); replies.add(reply);
                try { appendRecord(prefix + "-wire-replies.bin", RetentionReplyV3.encode(reply)); }
                catch (IOException failure) { throw new UncheckedIOException(failure); }
                consumer.accept(reply);
            });
        }
        public Map<String, Object> observation() {
            var actual = delegate.observation();
            try { writeJson(prefix + "-actual-observation-open.json", actual); }
            catch (IOException failure) { throw new UncheckedIOException(failure); }
            return actual;
        }
        public void close() {
            try { writeJson(prefix + "-actual-observation-before-transport-close.json", delegate.observation()); }
            catch (IOException failure) { throw new UncheckedIOException(failure); }
            finally { delegate.close(); }
        }
    }
    private static long number(Map<String, Object> map, String key) { return ((Number) map.get(key)).longValue(); }
    private static Reply success(Reply reply) { require(reply.error().isEmpty(), "V3 error " + reply.error()); return reply; }
    private void appendRecord(String file, byte[] bytes) throws IOException {
        try (var out = new DataOutputStream(Files.newOutputStream(root.resolve(file), StandardOpenOption.CREATE, StandardOpenOption.APPEND))) {
            out.writeInt(bytes.length); out.write(bytes);
        }
    }
    private void writeJson(String name, Object value) throws IOException { writeNew(name, json(value) + "\n"); }
    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) return "{" + map.entrySet().stream().map(e -> json(String.valueOf(e.getKey())) + ":" + json(e.getValue()))
                .reduce((a, b) -> a + "," + b).orElse("") + "}";
        if (value instanceof Iterable<?> list) { var values = new ArrayList<String>(); for (Object item : list) values.add(json(item)); return "[" + String.join(",", values) + "]"; }
        String text = value.toString(); var result = new StringBuilder("\"");
        for (int i = 0; i < text.length(); i++) { char ch = text.charAt(i); switch (ch) {
            case '"' -> result.append("\\\""); case '\\' -> result.append("\\\\"); case '\n' -> result.append("\\n");
            case '\r' -> result.append("\\r"); case '\t' -> result.append("\\t");
            default -> { if (ch < 32) result.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) ch)); else result.append(ch); }
        }}
        return result.append('"').toString();
    }
    private Path log(int node) { return root.resolve("node-" + node + "-g" + generation + ".log"); }
    private void startOwned() throws Exception {
        generation++; LinkedHashSet<String> classpath = new LinkedHashSet<>();
        for (Class<?> type : List.of(RetentionNodeMainV3.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class))
            classpath.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        for (int member = 0; member < 3; member++) {
            List<String> argv = List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                    "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED", "-Xmx256m",
                    "-Daeron.cluster.appointed.leader.id=0", "-cp", String.join(File.pathSeparator, classpath), RetentionNodeMainV3.class.getName(),
                    Integer.toString(member), root.toString(), Integer.toString(ports), "2", RetentionBatchProfilesV3.PROFILE_ID, lineage, profile.fingerprint(), code);
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
