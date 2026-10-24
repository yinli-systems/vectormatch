package io.vectormatch.cluster;

import io.aeron.cluster.ClusterTool;
import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;
import io.vectormatch.core.RetentionEngineV3.HistoryEntry;
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

/** Fresh bounded maintenance/cold-continuation proof. Business pauses at waves and cuts; no capacity claim. */
public final class RetentionBatchMaintenanceAeronSmokeV3 {
    private static final Duration TIMEOUT = Duration.ofSeconds(20);
    private static final int WORKERS = 128, LOAD_ORDERS = 10_000, MAX_IO_RECORDS = 30_000;
    private static final String SCOPE_LABEL = "LOCAL_THREE_JVM_W128_CAP4_BOUNDED_MAINTENANCE_FUNCTIONAL";
    private record Owned(Process process, Instant started, String command, List<String> arguments, Path log, int member, int generation) {}
    private record Expected(Command command, Execution execution, List<OrderView> terminals) {}
    private final Path root;
    private final RetentionServiceV3.Profile profile = RetentionBatchProfilesV3.finiteLoadProfile();
    private final String code = RetentionNodeMainV3.codeFingerprint(), lineage = "maintenance-local-" + UUID.randomUUID();
    private final int ports;
    private final List<Owned> owned = new ArrayList<>();
    // A generous independent instance keeps all 10,001 orders; it deliberately does not copy the finite hot-order cap.
    private final MatchingEngine matching = new MatchingEngine(16);
    private final List<Expected> expected = new ArrayList<>();
    private final Set<Long> expectedTerminalIds = new HashSet<>();
    private final List<RetentionBatchMaintenanceV3.Cycle> cycles = new ArrayList<>();
    private final long[] producerSequences = new long[WORKERS];
    private final RetentionBatchMaintenanceV3.RunBudget budget = new RetentionBatchMaintenanceV3.RunBudget(profile);
    private RetentionClusteredServiceV3 adapter;
    private boolean allOwnedStopped = true, discardedCommitReply, deliveredCommitReplay;
    private long faultCorrelation;
    private byte[] faultOriginal;
    private int faultAcceptedOffers, faultGeneration;
    private long verifiedArchiveCommands, verifiedArchiveEvents;
    private String lastArchiveChain;
    private int generation;

    private RetentionBatchMaintenanceAeronSmokeV3(Path newRoot) throws Exception {
        root = newRoot.toAbsolutePath().normalize(); Files.createDirectory(root);
        if (Files.getFileStore(root).getUsableSpace() < 768L * 1024 * 1024)
            throw new IllegalStateException("local maintenance smoke requires 768MiB free guard");
        ports = ports(); writeArtifactInventory();
        adapter = new RetentionClusteredServiceV3(profile, lineage, true); adapter.onStart(null, null);
        writeNew("registration.txt", "scope=" + SCOPE_LABEL + "\nbatchCap=4\nlogicalWorkers=128\nexternalTaskQueueCapacityPerWorker=64"
                + "\nloadOrders=10000\nsetupBusinessCommands=3\narchiveCuts=3072,6144,9216,10003\nflushDelayNs=50000"
                + "\nprofile=" + profile.fingerprint() + "\nlineage=" + lineage + "\ncode=" + code + "\nports=" + ports
                + "\nsync=2\npreparedArchiveCacheEnabled=true\nbusinessPausedAtWaveAndArchiveBoundaries=true\ncapacityClaim=false"
                + "\nindependentHosts=false\nfileForceScope=FileChannel.force(true) and full logical-byte readback; no independent storage/directory-fsync durability guarantee\n");
    }
    public static Path run(Path newRoot) throws Exception {
        var smoke = new RetentionBatchMaintenanceAeronSmokeV3(newRoot);
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
            finally { smoke.writeJson("completion.json", Map.of("scope", SCOPE_LABEL, "passed", passed && smoke.allOwnedStopped,
                    "allOwnedStopped", smoke.allOwnedStopped, "independentHosts", false, "capacityOrEnduranceProven", false,
                    "independentStorageDurabilityProven", false)); }
        }
        return smoke.root;
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("RetentionBatchMaintenanceAeronSmokeV3 <new-state-directory>");
        System.out.println("VECTOR_V3_MAINTENANCE_SMOKE_PASS evidence=" + run(Path.of(args[0])));
    }
    private Scope scope() { return new Scope(profile.fingerprint(), lineage); }
    private RetentionClientV3 control(String label) { return new RetentionClientV3(root.resolve("control-" + label), ports, profile, lineage); }
    private RetentionServiceV3 referenceState() throws Exception {
        Field field = RetentionClusteredServiceV3.class.getDeclaredField("state"); field.setAccessible(true);
        return (RetentionServiceV3) field.get(adapter);
    }
    private void restoreReference(byte[] snapshot) throws Exception {
        adapter = new RetentionClusteredServiceV3(profile, lineage, true); adapter.onStart(null, null);
        Field field = RetentionClusteredServiceV3.class.getDeclaredField("state"); field.setAccessible(true);
        field.set(adapter, RetentionServiceV3.restore(snapshot, profile, lineage));
        require(Arrays.equals(snapshot, referenceState().snapshot()), "local reference cold canonical restore differs");
    }
    private void exercise() throws Exception {
        startOwned();
        try (var client = control("setup")) {
            for (Command command : List.of(new Deposit(1, "fund", 1, Asset.BASE, LOAD_ORDERS),
                    new Deposit(2, "fund", 1, Asset.QUOTE, LOAD_ORDERS * 10L),
                    RetentionEngineV3.place(1, "maker", 1, Side.SELL, 10, LOAD_ORDERS, TimeInForce.GTC))) {
                Reply actual = success(client.exchange(new Business(command), TIMEOUT));
                Request request = new Request(scope(), actual.correlationId(), new Business(command));
                appendRecord("setup-wire-requests.bin", RetentionWireV3.encode(request));
                appendRecord("setup-wire-replies.bin", RetentionReplyV3.encode(actual));
                Reply local = RetentionReplyV3.decode(adapter.dispatch(request));
                require(Arrays.equals(RetentionReplyV3.encode(actual), RetentionReplyV3.encode(local)), "setup exact service reply differs");
                verifyMatching(command, ((State)local.payload()).result(), ((State)local.payload()).replayed());
            }
            verifyPosition(client, "setup");
        }
        runGeneration(new long[]{3072, 6144});
        byte[] checkpointBytes = referenceState().snapshot(); String checkpoint = sha(checkpointBytes);
        Files.write(root.resolve("reference-before-cold.bin"), checkpointBytes, StandardOpenOption.CREATE_NEW);
        try (var client = control("checkpoint")) {
            Reply position = verifyPosition(client, "before-checkpoint"); snapshot(client.leaderMemberId(), position.counters().stateHash());
        }
        stopOwned(); startOwned(); restoreReference(checkpointBytes);
        try (var client = control("cold-restore")) {
            Reply position = verifyPosition(client, "cold-restore");
            require(position.counters().stateHash().equals(checkpoint), "cold combined checkpoint differs");
            for (int member = 0; member < 3; member++) require(Files.readString(log(member)).contains("restored=true hash=" + checkpoint),
                    "all three cold services must restore exact combined checkpoint");
        }
        runGeneration(new long[]{9216, 10003});
        try (var client = control("final")) {
            Reply position = verifyPosition(client, "final");
            require(position.counters().acceptedPlaceCount() == 10001 && position.counters().businessSeq() == 10003,
                    "expected exactly 10,001 accepted Places and 10,003 business commands");
            require(position.counters().eventSeq() == 20003 && position.counters().marketSeq() == 20001, "exact event/market fixture totals differ");
            require(position.counters().coreMaintenanceSeq() == 4 && position.counters().exportedEventSeq() == 20003,
                    "four complete archive/event ACK cycles did not finish");
            require(referenceState().pendingHistoryCount() == 0 && referenceState().outboxSize() == 0,
                    "finite hot history and outbox not fully reclaimed");
            require(cycles.size() == 4 && verifiedArchiveCommands == 10003 && verifiedArchiveEvents == 20003,
                    "archive chain does not cover every command and event exactly once");
            require(discardedCommitReply && deliveredCommitReplay && faultAcceptedOffers >= 2, "actual lost maintenance reply/replay proof absent");
            Files.write(root.resolve("reference-final.bin"), referenceState().snapshot(), StandardOpenOption.CREATE_NEW);
            Files.write(root.resolve("matching-reference-final-v2.bin"), matching.snapshot(), StandardOpenOption.CREATE_NEW);
            snapshot(client.leaderMemberId(), position.counters().stateHash());
            var result = new LinkedHashMap<String,Object>();
            result.put("passed", true); result.put("scope", SCOPE_LABEL); result.put("profileSha256", profile.fingerprint());
            result.put("codeSha256", code); result.put("lineage", lineage); result.put("batchCap", 4); result.put("logicalWorkers", WORKERS);
            result.put("loadOrders", LOAD_ORDERS); result.put("firstAcceptedPlaces", 10001); result.put("businessSeq", 10003);
            result.put("eventSeq", 20003); result.put("marketSeq", 20001); result.put("archiveCycles", cycles.size());
            result.put("verifiedArchiveCommands", verifiedArchiveCommands); result.put("verifiedArchiveEvents", verifiedArchiveEvents);
            result.put("allThreeNodeSnapshotsMatched", true); result.put("coldCheckpointSha256", checkpoint);
            result.put("finalCombinedSha256", position.counters().stateHash()); result.put("discardedSuccessfulArchiveCommitReplies", 1);
            result.put("originalMaintenanceCorrelation", faultCorrelation); result.put("sameOriginalCommitAcceptedOffers", faultAcceptedOffers);
            result.put("maintenanceReplayObserved", true); result.put("beforeAckForcedReadbackVerified", true);
            result.put("businessPausedAtWaveAndArchiveBoundaries", true); result.put("capacityOrEnduranceProven", false);
            result.put("independentStorageDurabilityProven", false); result.put("independentHosts", false);
            result.put("referenceImplementation", "same cached adapter replayed in actual positive-offer order, plus separate MatchingEngine(16) with generous default limits; not an independent algorithm");
            result.put("runBudget", budget.snapshot()); writeJson("result.json", result);
        }
    }
    private void runGeneration(long[] cuts) throws Exception {
        String prefix = "owner-g" + generation; Path writerRoot = root.resolve("writer-g" + generation);
        var recording = new AtomicReference<RecordingIO>(); var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var owner = new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile, lineage, 4), () -> {
            var transport = new RetentionBatchAeronTransportV3(root.resolve(prefix + "-driver"), ports, profile, lineage, true);
            try { var io = new RecordingIO(transport, prefix, writerRoot, entered, release); recording.set(io); return io; }
            catch (IOException error) { transport.close(); throw new UncheckedIOException(error); }
            catch (RuntimeException | Error error) { transport.close(); throw error; }
        });
        RetentionDurableWriterV3 writer = null; RetentionBatchMaintenanceV3 maintenance = null;
        Throwable failure = null; int replayedAccepted = 0, replayedReplies = 0; long generationCommands = 0;
        var outstandingExpectedReplies = new HashMap<Long,ArrayDeque<byte[]>>();
        try {
            writer = new RetentionDurableWriterV3(writerRoot, profile.core().maxPendingSerializedBytes() + 1024L, 256L * 1024 * 1024, 64);
            maintenance = new RetentionBatchMaintenanceV3(owner, writer, profile, lineage, root.resolve("maintenance-g" + generation), budget);
            require(entered.await(5, TimeUnit.SECONDS), "owner did not enter first-poll setup gate");
            boolean firstWave = true;
            for (long cut : cuts) {
                while (referenceState().businessSeq() < cut) {
                    int count = (int)Math.min(WORKERS, cut - referenceState().businessSeq());
                    long permit = System.nanoTime() + TIMEOUT.toNanos(); var tickets = new ArrayList<RetentionBatchOwnerV3.Ticket>(count);
                    var ticketOutcomes = new HashMap<BusinessIdentity,RetentionBatchOwnerV3.Outcome>();
                    for (int worker = 0; worker < count; worker++) tickets.add(owner.submit(worker, RetentionEngineV3.place(2,
                            "load-w" + worker, ++producerSequences[worker], Side.BUY, 10, 1, TimeInForce.IOC), permit));
                    if (firstWave) {
                        var gated = owner.snapshot(); writeJson(prefix + "-gated.json", gated);
                        require(count == WORKERS && number(gated,"pendingLogicalCommands") == WORKERS && number(gated,"acceptedPhysicalOffers") == 0,
                                "first wave must fill all 128 slots before any offer");
                        firstWave = false; release.countDown(); owner.wake();
                    }
                    for (var ticket : tickets) {
                        RetentionBatchOwnerV3.Outcome outcome;
                        try { outcome = ticket.await(TIMEOUT); }
                        catch (RetentionBatchOwnerV3.UnresolvedCommandException unknown) {
                            if (unknown.originalWire() != null) Files.write(root.resolve(prefix + "-unknown-" + ticket.identity().producerId() + '-' + ticket.identity().requestSeq() + ".bin"), unknown.originalWire(), StandardOpenOption.CREATE_NEW);
                            throw unknown;
                        }
                        require(outcome.terminal() == RetentionBatchOwnerV3.Terminal.APPLIED && outcome.result().accepted(), "load order not definitely accepted");
                        require(ticketOutcomes.put(outcome.identity(),outcome)==null,"duplicate wave ticket identity");
                    }
                    int[] consumed = replayNew(recording.get(), replayedAccepted, replayedReplies, outstandingExpectedReplies);
                    for (Reply actual : recording.get().replySnapshot().subList(replayedReplies,consumed[1])) if (actual.payload() instanceof Batch batch) {
                        for (BatchEntry entry : batch.entries()) {
                            var outcome = ticketOutcomes.remove(entry.identity()); if (outcome == null) continue;
                            require(entry.status()==BatchStatus.APPLIED && entry.commandSha256().equals(outcome.commandSha256())
                                    &&entry.result().equals(outcome.result())&&entry.replayed()==outcome.replayed()
                                    &&entry.frontier().equals(outcome.frontier()),"ticket identity/hash/result/frontier differs from first bound actual reply");
                        }
                    }
                    require(ticketOutcomes.isEmpty(),"wave tickets lacked actual complete bound replies");
                    replayedAccepted = consumed[0]; replayedReplies = consumed[1]; generationCommands += count;
                    require(number(owner.snapshot(),"pendingLogicalCommands") == 0, "wave business closure missing");
                }
                require(referenceState().businessSeq() == cut, "short wave crossed exact maintenance cut");
                RetentionBatchMaintenanceV3.Cycle cycle = maintenance.exportThrough(cut);
                int[] consumed = replayNew(recording.get(), replayedAccepted, replayedReplies, outstandingExpectedReplies);
                replayedAccepted = consumed[0]; replayedReplies = consumed[1];
                verifyArchive(cycle); cycles.add(cycle);
                Reply position = success(owner.exchangeMaintenance(new Position(), TIMEOUT));
                consumed = replayNew(recording.get(), replayedAccepted, replayedReplies, outstandingExpectedReplies);
                replayedAccepted = consumed[0]; replayedReplies = consumed[1];
                require(position.counters().stateHash().equals(sha(referenceState().snapshot())), "post-ACK full combined state differs from exact physical replay");
                require(referenceState().archivedThroughCommandSeq() == cut && referenceState().pendingHistoryCount() == 0
                        && referenceState().outboxSize() == 0, "maintenance did not clear exact finite prefix");
                writeJson("cycle-through-" + cut + ".json", Map.of("throughBusinessSeq",cut,"throughEventSeq",cycle.throughEventSeq(),
                        "archiveFile",cycle.archiveFile().toString(),"eventFile",cycle.eventFile().toString(),"stateHash",position.counters().stateHash(),
                        "owner",owner.snapshot(),"writer",writer.snapshot(),"maintenance",maintenance.snapshot()));
            }
            require(number(owner.snapshot(),"logicalAppliedResults") == generationCommands && number(owner.snapshot(),"logicalNotSent") == 0
                    && number(owner.snapshot(),"unresolvedPossiblyExecutedLogicalCommands") == 0, "generation logical closure differs");
        } catch (Throwable error) { failure = error; throw error; }
        finally {
            release.countDown(); Throwable cleanupFailure = null;
            try { if (maintenance != null) maintenance.close(); } catch (Throwable error) { cleanupFailure = error; }
            try { writeJson(prefix + "-owner-before-close.json", owner.snapshot()); owner.close(); }
            catch (Throwable error) { if (cleanupFailure == null) cleanupFailure = error; else cleanupFailure.addSuppressed(error); }
            finally { writeJson(prefix + "-owner-after-close.json", owner.snapshot()); }
            if (writer != null) {
                try { writeJson(prefix + "-writer-before-close.json", writer.snapshot()); writer.close(); }
                catch (Throwable error) { if (cleanupFailure == null) cleanupFailure = error; else cleanupFailure.addSuppressed(error); }
                finally { writeJson(prefix + "-writer-after-close.json", writer.snapshot()); }
            }
            if (cleanupFailure != null) {
                if (failure != null) failure.addSuppressed(cleanupFailure);
                else if (cleanupFailure instanceof Exception exception) throw exception;
                else if (cleanupFailure instanceof Error fatal) throw fatal;
                else throw new IllegalStateException(cleanupFailure);
            }
        }
        require(!Boolean.TRUE.equals(owner.snapshot().get("ownerThreadAlive")) && owner.snapshot().get("failureType") == null, "owner failed or remained alive");
        require(writer != null && !Boolean.TRUE.equals(writer.snapshot().get("writerAlive")) && writer.snapshot().get("failureType") == null,
                "writer failed or remained alive");
        int[] consumed = replayNew(recording.get(), replayedAccepted, replayedReplies, outstandingExpectedReplies);
        require(consumed[0] == recording.get().acceptedSnapshot().size() && consumed[1] == recording.get().replySnapshot().size()
                && outstandingExpectedReplies.isEmpty(), "positive offered requests and actual replies did not close exactly");
    }
    private int[] replayNew(RecordingIO io, int acceptedIndex, int replyIndex, Map<Long,ArrayDeque<byte[]>> expectedReplies) throws Exception {
        List<Request> accepted = io.acceptedSnapshot();
        for (; acceptedIndex < accepted.size(); acceptedIndex++) {
            Request request = accepted.get(acceptedIndex); byte[] raw = adapter.dispatch(request); Reply reply = RetentionReplyV3.decode(raw);
            success(reply); expectedReplies.computeIfAbsent(request.correlationId(), ignored -> new ArrayDeque<>()).add(raw);
            if (request.operation() instanceof BusinessBatch batch) {
                RetentionClientV3.validateBatchResponse(batch, reply); Batch values = (Batch)reply.payload();
                for (int index = 0; index < batch.commands().size(); index++) {
                    BatchEntry value = values.entries().get(index); require(value.status() == BatchStatus.APPLIED, "local replay admission failed");
                    verifyMatching(batch.commands().get(index), value.result(), value.replayed());
                }
            }
        }
        List<Reply> replies = io.replySnapshot();
        for (; replyIndex < replies.size(); replyIndex++) {
            Reply actual = replies.get(replyIndex); ArrayDeque<byte[]> values = expectedReplies.get(actual.correlationId());
            require(values != null && !values.isEmpty(), "actual application reply lacks accepted physical request");
            require(Arrays.equals(values.removeFirst(), RetentionReplyV3.encode(actual)), "actual complete reply differs from exact accepted-wire replay");
            if (values.isEmpty()) expectedReplies.remove(actual.correlationId());
        }
        return new int[]{acceptedIndex,replyIndex};
    }
    private void verifyMatching(Command command, Result result, boolean replayed) {
        Execution execution = matching.execute(command);
        require(execution.result().equals(result) && execution.replayed() == replayed, "separate sequential matching result/replay differs");
        if (replayed) return;
        require(execution.result().commandSeq() == expected.size() + 1L && expected.size() < 10003, "fresh matching command sequence/bound differs");
        var touched = new TreeSet<Long>(); if (command instanceof Place && result.accepted()) touched.add(result.orderId());
        for (Event event : execution.events()) {
            if (event.orderId() > 0) touched.add(event.orderId()); if (event.makerOrderId() > 0) touched.add(event.makerOrderId());
            if (event.takerOrderId() > 0) touched.add(event.takerOrderId());
        }
        var terminals = new ArrayList<OrderView>();
        for (long id : touched) {
            OrderView order = matching.order(id).orElseThrow();
            if (order.status() != OrderStatus.OPEN && order.status() != OrderStatus.PARTIALLY_FILLED && expectedTerminalIds.add(id)) terminals.add(order);
        }
        expected.add(new Expected(command,execution,List.copyOf(terminals)));
    }
    private void verifyArchive(RetentionBatchMaintenanceV3.Cycle cycle) throws IOException {
        var ack = cycle.acknowledgement();
        require(ack.firstCommandSeq() == verifiedArchiveCommands + 1 && (lastArchiveChain == null || lastArchiveChain.equals(ack.previousChainHash())),
                "archive full command/chain continuity differs");
        var verified = RetentionArchiveVerifierV3.verify(Files.readAllBytes(cycle.archiveFile()),profile.core(),lineage,ack);
        require(verified.entries().size() == cycle.entries().size() && verified.previousEventSeq() == verifiedArchiveEvents, "archive durable file verification prefix differs");
        var eventValues = new ArrayList<Event>();
        for (HistoryEntry entry : verified.entries()) {
            require(entry.commandSeq() == verifiedArchiveCommands + 1, "archive command gap or duplicate");
            Expected value = expected.get(Math.toIntExact(entry.commandSeq()-1));
            require(entry.command().equals(value.command()) && entry.execution().equals(value.execution())
                    && entry.terminalOrders().equals(value.terminals()), "archive command/result/event/terminal record differs from separate matching instance");
            for (Event event : entry.execution().events()) require(event.eventSeq() == ++verifiedArchiveEvents, "archive event gap or duplicate");
            eventValues.addAll(entry.execution().events()); verifiedArchiveCommands++;
        }
        require(verifiedArchiveCommands == ack.throughCommandSeq() && verifiedArchiveEvents == cycle.throughEventSeq(), "archive final prefix frontier differs");
        require(cycle.eventFile() != null, "fixture must persist a nonempty event prefix");
        RetentionDurableWriterV3.verifyEventFrames(Files.readAllBytes(cycle.eventFile()),eventValues,scope(),verified.previousEventSeq()+1,cycle.throughEventSeq());
        lastArchiveChain = ack.chainHash();
    }
    private Reply verifyPosition(RetentionClientV3 client, String label) throws Exception {
        Reply position = success(client.exchange(new Position(), TIMEOUT)); appendRecord("position-wire-replies.bin",RetentionReplyV3.encode(position));
        require(position.counters().stateHash().equals(sha(referenceState().snapshot())), label + " full combined snapshot differs from exact physical replay");
        require(position.counters().businessSeq() == matching.lastCommandSeq() && position.counters().eventSeq() == matching.lastEventSeq()
                && position.counters().marketSeq() == matching.lastMarketSeq(), label + " separate matching counters differ");
        return position;
    }
    /** Bounded CREATE_NEW evidence for each fresh owner observation, including final capture. */
    static final class ObservationRecorder {
        private final Path root;
        private final String prefix;
        private final java.util.function.Supplier<Map<String, Object>> source;
        private int recorded;
        ObservationRecorder(Path root, String prefix, java.util.function.Supplier<Map<String, Object>> source) {
            this.root = root; this.prefix = prefix; this.source = source;
        }
        Map<String, Object> observation() {
            if (recorded >= 256) throw new IllegalStateException("functional observation evidence limit exceeded");
            Map<String, Object> actual = source.get();
            String suffix = recorded == 0 ? "open" : String.format(Locale.ROOT, "%03d", recorded);
            try { Files.writeString(root.resolve(prefix + "-actual-observation-" + suffix + ".json"),
                    json(actual) + "\n", StandardOpenOption.CREATE_NEW); }
            catch (IOException failure) { throw new UncheckedIOException(failure); }
            recorded++;
            return actual;
        }
    }
    private final class RecordingIO implements RetentionBatchOwnerIOV3 {
        private final RetentionBatchOwnerIOV3 delegate;
        private final String prefix;
        private final ObservationRecorder observations;
        private final Path writerRoot;
        private final CountDownLatch entered,release;
        private final List<Request> accepted = new ArrayList<>();
        private final List<Reply> replies = new ArrayList<>();
        private final Map<Long,Request> originals = new HashMap<>();
        private final Map<RetentionEngineV3.ArchiveAck,Integer> checkedArchives = new LinkedHashMap<>();
        private final DataOutputStream attemptsOut,acceptedOut,repliesOut;
        private boolean gated;
        private int offers;
        RecordingIO(RetentionBatchOwnerIOV3 delegate,String prefix,Path writerRoot,CountDownLatch entered,CountDownLatch release) throws IOException {
            this.delegate=delegate;this.prefix=prefix;this.writerRoot=writerRoot;this.entered=entered;this.release=release;
            observations = new ObservationRecorder(root, prefix, delegate::observation);
            DataOutputStream attempts=null,acceptedStream=null,repliesStream=null;
            try {
                attempts=stream(prefix+"-wire-offer-attempts.bin"); acceptedStream=stream(prefix+"-wire-accepted-requests.bin"); repliesStream=stream(prefix+"-wire-replies.bin");
            } catch (Throwable error) {
                for (DataOutputStream stream : new DataOutputStream[]{attempts,acceptedStream,repliesStream}) if(stream!=null) try{stream.close();}catch(IOException cleanup){error.addSuppressed(cleanup);}
                throw error;
            }
            attemptsOut=attempts;acceptedOut=acceptedStream;repliesOut=repliesStream;
        }
        public long offer(byte[] bytes) {
            try {
                require(++offers <= MAX_IO_RECORDS,"bounded physical offer inventory exceeded"); frame(attemptsOut,bytes); attemptsOut.flush();
                Request request=RetentionWireV3.decode(bytes);
                if(request.operation() instanceof ArchiveCommit commit) verifyBeforeAck(commit);
                long offer=delegate.offer(bytes);
                Files.writeString(root.resolve(prefix+"-offer-codes.csv"),offers+","+offer+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
                if(offer>=0) synchronized(this) {
                    require(accepted.size()<MAX_IO_RECORDS,"bounded accepted physical inventory exceeded");
                    Request original=originals.putIfAbsent(request.correlationId(),request);
                    require(original==null||Arrays.equals(RetentionWireV3.encode(original),bytes),"same transport correlation changed original wire");
                    accepted.add(request);frame(acceptedOut,bytes);acceptedOut.flush();
                    if(faultOriginal!=null&&generation==faultGeneration&&request.correlationId()==faultCorrelation) {
                        require(Arrays.equals(faultOriginal,bytes),"maintenance retry changed original wire");faultAcceptedOffers++;
                    }
                }
                return offer;
            } catch(IOException error){throw new UncheckedIOException(error);}
        }
        private void verifyBeforeAck(ArchiveCommit commit)throws IOException {
            if(checkedArchives.containsKey(commit.acknowledgement()))return;
            int number=checkedArchives.size()+1;Path archive=writerRoot.resolve(String.format(Locale.ROOT,"%04d-archive.bin",number*2-1));
            Path events=writerRoot.resolve(String.format(Locale.ROOT,"%04d-events.bin",number*2));
            byte[] archiveBytes=Files.readAllBytes(archive),eventBytes=Files.readAllBytes(events);
            var verified=RetentionArchiveVerifierV3.verify(archiveBytes,profile.core(),lineage,commit.acknowledgement());
            var eventValues=new ArrayList<Event>();for(var entry:verified.entries())eventValues.addAll(entry.execution().events());
            RetentionDurableWriterV3.verifyEventFrames(eventBytes,eventValues,scope(),verified.previousEventSeq()+1,verified.entries().getLast().eventSeqAfter());
            for(Path path:List.of(archive,events)) {
                String receipt=Files.readString(path.resolveSibling(path.getFileName()+".verified.txt"));
                require(receipt.contains("forceTrueCompleted=true\n")&&receipt.contains("fullReadbackVerified=true\n")
                        &&receipt.contains("sha256="+sha(Files.readAllBytes(path))+"\n"),"both forced/readback prefix receipts must predate first ACK offer");
            }
            Files.writeString(root.resolve(prefix+"-before-ack-ledger.txt"),"firstCommand="+commit.acknowledgement().firstCommandSeq()
                    +" through="+commit.acknowledgement().throughCommandSeq()+" archive="+archive+" sha256="+sha(archiveBytes)
                    +" events="+events+" sha256="+sha(eventBytes)+" verifiedBeforeDelegateOffer=true\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
            checkedArchives.put(commit.acknowledgement(),number);
        }
        public int poll(Consumer<Reply> consumer) {
            if(!gated){gated=true;entered.countDown();try{require(release.await(5,TimeUnit.SECONDS),"128-slot setup gate deadline");}
                catch(InterruptedException error){Thread.currentThread().interrupt();throw new IllegalStateException("owner gate interrupted",error);}}
            return delegate.poll(reply->{
                try {
                    byte[] raw=RetentionReplyV3.encode(reply);Request request;
                    synchronized(this){require(replies.size()<MAX_IO_RECORDS,"bounded actual reply inventory exceeded");replies.add(reply);frame(repliesOut,raw);repliesOut.flush();request=originals.get(reply.correlationId());}
                    if(!discardedCommitReply&&request!=null&&request.operation() instanceof ArchiveCommit&&reply.error().isEmpty()
                            &&reply.payload() instanceof State state&&state.maintenance()!=null
                            &&state.maintenance().code()==RetentionServiceV3.MaintenanceCode.APPLIED&&state.maintenance().compaction()!=null&&!state.maintenance().replayed()) {
                        discardedCommitReply=true;faultGeneration=generation;faultCorrelation=request.correlationId();faultOriginal=RetentionWireV3.encode(request);
                        synchronized(this){faultAcceptedOffers=(int)accepted.stream().filter(value->value.correlationId()==faultCorrelation).count();}
                        Files.write(root.resolve("fault-original-archive-commit.bin"),faultOriginal,StandardOpenOption.CREATE_NEW);
                        Files.write(root.resolve("fault-discarded-success-reply.bin"),raw,StandardOpenOption.CREATE_NEW);
                        return;
                    }
                    if(faultOriginal!=null&&generation==faultGeneration&&reply.correlationId()==faultCorrelation&&reply.payload() instanceof State state
                            &&state.maintenance()!=null&&state.maintenance().replayed()&&!deliveredCommitReplay) {
                        deliveredCommitReplay=true;Files.write(root.resolve("fault-delivered-replayed-reply.bin"),raw,StandardOpenOption.CREATE_NEW);
                    }
                    consumer.accept(reply);
                }catch(IOException error){throw new UncheckedIOException(error);}
            });
        }
        synchronized List<Request> acceptedSnapshot(){return List.copyOf(accepted);}
        synchronized List<Reply> replySnapshot(){return List.copyOf(replies);}
        public Map<String,Object> observation(){return observations.observation();}
        public void close(){
            Throwable failed=null;
            try{writeJson(prefix+"-actual-observation-before-transport-close.json",delegate.observation());}catch(Throwable error){failed=error;}
            try{delegate.close();}catch(Throwable error){if(failed==null)failed=error;else failed.addSuppressed(error);}
            for(var stream:List.of(attemptsOut,acceptedOut,repliesOut))try{stream.close();}catch(Throwable error){if(failed==null)failed=error;else failed.addSuppressed(error);}
            if(failed instanceof RuntimeException runtime)throw runtime;if(failed instanceof Error fatal)throw fatal;if(failed!=null)throw new IllegalStateException(failed);
        }
    }
    private DataOutputStream stream(String name)throws IOException{return new DataOutputStream(Files.newOutputStream(root.resolve(name),StandardOpenOption.CREATE_NEW));}
    private static void frame(DataOutputStream out,byte[] bytes)throws IOException{out.writeInt(bytes.length);out.write(bytes);}
    private static long number(Map<String,Object> values,String key){return ((Number)values.get(key)).longValue();}
    private static Reply success(Reply reply){require(reply.error().isEmpty(),"V3 error "+reply.error());return reply;}
    private void appendRecord(String name,byte[] bytes)throws IOException{try(var out=new DataOutputStream(Files.newOutputStream(root.resolve(name),StandardOpenOption.CREATE,StandardOpenOption.APPEND))){frame(out,bytes);}}
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
