package io.vectormatch.cluster;

import io.aeron.Aeron;
import io.aeron.AeronCounters;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Paired closed-loop experiments. No latency subtraction, default-node tuning changes, or open-loop claims. */
public final class ReplicatedConcurrencyComparison {
    private static final int TOTAL_WARMUP_CYCLES = 100;
    private static final int TOTAL_MEASURED_CYCLES = 336;
    private static final Duration TIMEOUT = Duration.ofSeconds(30);
    private ReplicatedConcurrencyComparison() {}

    public static void main(String[] args) throws Exception {
        Path root = args.length > 0 ? Path.of(args[0]).toAbsolutePath()
                : Path.of("build", "replicated-concurrency", "run-" + Instant.now().toEpochMilli()).toAbsolutePath();
        if (Files.exists(root)) throw new IllegalArgumentException("Paired experiment requires a fresh state/evidence directory");
        Files.createDirectories(root);
        System.out.println("VECTOR_CONCURRENCY_EVIDENCE " + root);
        Summary one = new Experiment(root.resolve("clients-1"), 1, 28000).run();
        Summary four = new Experiment(root.resolve("clients-4"), 4, 29000).run();
        String json = String.format(Locale.ROOT, """
                {
                  "test": "paired-replicated-closed-loop-concurrency",
                  "passed": true,
                  "sameHarness": true,
                  "loadModel": "CLOSED_LOOP_ONE_INFLIGHT_PER_CLIENT",
                  "syncLevel": 2,
                  "independentMachines": false,
                  "measuredCommandsPerExperiment": 1008,
                  "warmupCommandsPerExperiment": 300,
                  "validationOutsideMeasuredInterval": true,
                  "oneClientConfirmedCommandsPerSecond": %.3f,
                  "fourClientConfirmedCommandsPerSecond": %.3f,
                  "observedAggregateThroughputRatio": %.6f,
                  "oneClientP99Microseconds": %.3f,
                  "fourClientP99Microseconds": %.3f,
                  "oneClientArchiveWriteNanosPerConfirmedCommandAcrossAllReplicas": %.3f,
                  "fourClientArchiveWriteNanosPerConfirmedCommandAcrossAllReplicas": %.3f,
                  "archiveForceCallCountInstrumented": false,
                  "commandsPerForceCall": null,
                  "causalAttribution": "Observed concurrency effect; exact batching/force-call count is not exposed by the collected Archive counters. Scheduling, transport and storage all contribute.",
                  "runOrder": [1, 4],
                  "repetitionsPerConfiguration": 1,
                  "limitation": "Short shared-host exploratory experiment, not a capacity, open-loop, isolated-hardware or statistical-significance result"
                }
                """, one.goodput, four.goodput, four.goodput / one.goodput, one.p99Ns / 1000.0, four.p99Ns / 1000.0,
                one.archiveNanosPerCommand, four.archiveNanosPerCommand);
        Files.writeString(root.resolve("comparison.json"), json);
        System.out.println("VECTOR_CONCURRENCY_PASS " + json.replace('\n', ' '));
    }

    private record Summary(double goodput, long p99Ns, double archiveNanosPerCommand) {}
    private record Observation(int client, boolean measured, Command command, CommandCodec.Reply reply, long rttNs) {}
    private record ArchiveStats(long bytes, long timeNs, long maximumWriteNs) {}

    private static final class Experiment {
        private final Path evidence;
        private final int clients, ports;
        private final List<Process> nodes = new ArrayList<>();
        private final List<Worker> workers = new ArrayList<>();
        private final CountDownLatch warmed;
        private final CountDownLatch start = new CountDownLatch(1);
        private final CountDownLatch completed;
        private final CountDownLatch finish = new CountDownLatch(1);
        private final AtomicReference<Throwable> failure = new AtomicReference<>();

        private Experiment(Path evidence, int clients, int ports) {
            this.evidence = evidence; this.clients = clients; this.ports = ports;
            warmed = new CountDownLatch(clients); completed = new CountDownLatch(clients);
        }

        private Summary run() throws Exception {
            Files.createDirectories(evidence);
            ExecutorService executor = Executors.newFixedThreadPool(clients);
            List<Future<Void>> futures = new ArrayList<>();
            try {
                startNodes();
                for (int id = 0; id < clients; id++) {
                    Worker worker = new Worker(id); workers.add(worker); futures.add(executor.submit(worker));
                }
                require(warmed.await(90, TimeUnit.SECONDS), "Clients did not finish warmup");
                checkFailure();
                Thread.sleep(200); // Let all replica Archive counters catch up; outside the measured interval.
                List<ArchiveStats> archiveBefore = readArchiveStats();
                long startNs = System.nanoTime();
                start.countDown();
                require(completed.await(120, TimeUnit.SECONDS), "Clients did not finish measured commands");
                checkFailure();
                long endNs = workers.stream().mapToLong(worker -> worker.endedNs).max().orElseThrow();
                Thread.sleep(200); // Counter-settle interval is excluded from elapsed command throughput.
                List<ArchiveStats> archiveAfter = readArchiveStats();

                List<Observation> observations = workers.stream().flatMap(worker -> worker.observations.stream())
                        .sorted(Comparator.comparingLong(value -> value.reply.result().commandSeq())).toList();
                MatchingEngine reference = ClusterCapacity.newEngine();
                for (Observation observation : observations) {
                    Execution expected = reference.apply(observation.command);
                    require(expected.result().accepted(), "Reference command unexpectedly rejected: " + observation.command);
                    require(expected.result().equals(observation.reply.result()), "Reference business result differs at "
                            + expected.result().commandSeq());
                    if (!observation.reply.replayed()) {
                        require(reference.lastCommandSeq() == observation.reply.commandSeq()
                                && reference.lastEventSeq() == observation.reply.eventSeq()
                                && reference.lastMarketSeq() == observation.reply.marketSeq(), "Replica sequence differs");
                    }
                }
                reference.checkInvariants();
                try (ClusterClient verifier = new ClusterClient(evidence.resolve("verifier-driver"), ports)) {
                    MatchingEngine restored = MatchingEngine.restore(verifier.readSnapshot(TIMEOUT));
                    restored.checkInvariants();
                    require(reference.stateHash().equals(restored.stateHash()), "Final snapshot state differs from replayed trace");
                    require(reference.stateHash().equals(verifier.state(TIMEOUT).stateHash()), "Live leader state differs");
                }
                return writeResults(observations, reference, startNs, endNs, archiveBefore, archiveAfter);
            } finally {
                try {
                    start.countDown(); finish.countDown();
                    executor.shutdown();
                    if (!executor.awaitTermination(35, TimeUnit.SECONDS)) executor.shutdownNow();
                    for (Future<Void> future : futures) if (future.isDone()) {
                        try { future.get(); } catch (ExecutionException failureIgnoredHere) { /* Raised above with context. */ }
                    }
                } finally {
                    stopNodes();
                }
            }
        }

        private Summary writeResults(List<Observation> observations, MatchingEngine reference, long startNs, long endNs,
                                     List<ArchiveStats> archiveBefore, List<ArchiveStats> archiveAfter) throws Exception {
            List<Observation> measured = observations.stream().filter(Observation::measured).toList();
            require(measured.size() == TOTAL_MEASURED_CYCLES * 3, "Wrong measured command count");
            long trades = measured.stream().mapToLong(value -> value.reply.result().tradeCount()).sum();
            require(trades == TOTAL_MEASURED_CYCLES, "Workload did not produce expected real trades");
            long[] allRtt = measured.stream().mapToLong(Observation::rttNs).sorted().toArray();
            long accepted = 0, resends = 0, unaccepted = 0, unknown = 0;
            StringBuilder workerJson = new StringBuilder();
            for (Worker worker : workers) {
                long[] times = worker.observations.stream().filter(Observation::measured).mapToLong(Observation::rttNs).sorted().toArray();
                long attempts = worker.after.acceptedOffers() - worker.before.acceptedOffers();
                long retries = worker.after.acceptedResends() - worker.before.acceptedResends();
                long misses = worker.after.unacceptedOffers() - worker.before.unacceptedOffers();
                long timeouts = worker.after.requestTimeouts() - worker.before.requestTimeouts();
                accepted += attempts; resends += retries; unaccepted += misses; unknown += timeouts;
                if (!workerJson.isEmpty()) workerJson.append(',');
                workerJson.append(String.format(Locale.ROOT,
                        "{\"client\":%d,\"confirmedCommands\":%d,\"seconds\":%.6f,\"confirmedCommandsPerSecond\":%.3f,\"p50Microseconds\":%.3f,\"p99Microseconds\":%.3f,\"maxMicroseconds\":%.3f,\"transportAcceptedAttempts\":%d,\"transportAcceptedResends\":%d,\"transportUnacceptedOffers\":%d,\"unknownTimeouts\":%d}",
                        worker.id, times.length, (worker.endedNs - worker.startedNs) / 1e9,
                        times.length * 1e9 / (worker.endedNs - worker.startedNs), percentile(times, .5) / 1e3,
                        percentile(times, .99) / 1e3, times[times.length - 1] / 1e3, attempts, retries, misses, timeouts));
            }
            StringBuilder archiveJson = new StringBuilder();
            long totalWriteBytes = 0, totalWriteNanos = 0;
            for (int node = 0; node < LocalTopology.NODE_COUNT; node++) {
                ArchiveStats before = archiveBefore.get(node), after = archiveAfter.get(node);
                long bytes = after.bytes - before.bytes, nanos = after.timeNs - before.timeNs;
                require(bytes >= 0 && nanos >= 0, "Archive counters regressed");
                totalWriteBytes += bytes; totalWriteNanos += nanos;
                if (!archiveJson.isEmpty()) archiveJson.append(',');
                archiveJson.append(String.format(Locale.ROOT,
                        "{\"node\":%d,\"recordingWriteBytesDelta\":%d,\"recordingWriteNanosDelta\":%d,\"lifetimeMaximumWriteNanosAfter\":%d}",
                        node, bytes, nanos, after.maximumWriteNs));
            }
            long replayedReplies = measured.stream().filter(value -> value.reply.replayed()).count();
            double seconds = (endNs - startNs) / 1e9;
            double throughput = measured.size() / seconds;
            String json = String.format(Locale.ROOT, """
                    {
                      "test": "replicated-concurrent-closed-loop",
                      "passed": true,
                      "clients": %d,
                      "loadModel": "CLOSED_LOOP_ONE_INFLIGHT_PER_CLIENT",
                      "maximumBusinessRequestsInFlight": %d,
                      "independentMachines": false,
                      "loadGeneratorSharesClusterHost": true,
                      "clusterProcesses": 3,
                      "archiveFileSyncLevel": 2,
                      "archiveCatalogFileSyncLevel": 2,
                      "consensusFileSyncLevel": 2,
                      "nodeIdleAndHeartbeatDefaultsChanged": false,
                      "warmupCommands": 300,
                      "measuredLogicalCommands": %d,
                      "confirmedAcceptedCommands": %d,
                      "businessRejectedCommands": 0,
                      "transportAcceptedAttempts": %d,
                      "transportAcceptedResends": %d,
                      "transportUnacceptedOffers": %d,
                      "unknownRequestTimeouts": %d,
                      "unresolvedCommands": 0,
                      "measuredReplayedReplies": %d,
                      "duplicateBusinessEffects": 0,
                      "measuredTrades": %d,
                      "measurementSeconds": %.6f,
                      "aggregateConfirmedCommandsPerSecond": %.3f,
                      "clientRttMicroseconds": {"min":%.3f,"p50":%.3f,"p95":%.3f,"p99":%.3f,"p999":%.3f,"max":%.3f},
                      "percentileMethod": "nearest-rank over every measured command; no pause subtraction",
                      "validationOutsideMeasuredInterval": true,
                      "referenceReplayOrder": "server result.commandSeq, including funding and warmup",
                      "rttScope": "client execute call including encode, replication/commit, response, and automatic resends",
                      "aggregateTimeScope": "release of all warmed clients through the last measured reply and in-memory sample capture",
                      "makerLotsPerOrder": 1000000,
                      "buyerLotsPerOrder": 4,
                      "sharedMarketMatching": "Buyers may match another client's maker. Maker size keeps every residual cancellation valid; final reference replays actual global order.",
                      "perClient": [%s],
                      "archiveCounters": [%s],
                      "archiveRecordingWriteBytesDeltaAcrossAllReplicas": %d,
                      "archiveRecordingWriteNanosDeltaAcrossAllReplicas": %d,
                      "archiveWriteNanosPerConfirmedCommandAcrossAllReplicas": %.3f,
                      "archiveForceCallCountInstrumented": false,
                      "counterScope": "Official Archive total recording bytes/time counters; recorder time includes force when syncLevel>0. Read outside measured interval after settle delay. Max is lifetime, not measured-only.",
                      "stateHashVerified": true,
                      "invariantsVerified": true,
                      "finalCommandSeq": %d,
                      "finalEventSeq": %d,
                      "finalMarketSeq": %d,
                      "stateHash": "%s",
                      "javaVersion": "%s",
                      "osName": "%s",
                      "osArch": "%s",
                      "availableProcessors": %d
                    }
                    """, clients, clients, measured.size(), measured.size(), accepted, resends, unaccepted, unknown,
                    replayedReplies, trades, seconds, throughput, allRtt[0] / 1e3, percentile(allRtt, .5) / 1e3,
                    percentile(allRtt, .95) / 1e3, percentile(allRtt, .99) / 1e3, percentile(allRtt, .999) / 1e3,
                    allRtt[allRtt.length - 1] / 1e3, workerJson, archiveJson, totalWriteBytes, totalWriteNanos,
                    totalWriteNanos / (double) measured.size(), reference.lastCommandSeq(), reference.lastEventSeq(),
                    reference.lastMarketSeq(), reference.stateHash(), escape(System.getProperty("java.version")),
                    escape(System.getProperty("os.name")), escape(System.getProperty("os.arch")), Runtime.getRuntime().availableProcessors());
            Files.writeString(evidence.resolve("result.json"), json);
            StringBuilder trace = new StringBuilder("command_seq,client,measured,type,account,producer,request_seq,client_order_id,side,price_ticks,quantity_lots,tif,cancel_order_id,result_order_id,remaining,trade_count,replayed,client_rtt_ns\n");
            for (Observation item : observations) {
                Command command = item.command;
                Place place = command instanceof Place value ? value : null;
                trace.append(item.reply.result().commandSeq()).append(',').append(item.client).append(',').append(item.measured)
                        .append(',').append(command.getClass().getSimpleName()).append(',').append(command.accountId())
                        .append(',').append(command.producerId()).append(',').append(command.requestSeq()).append(',')
                        .append(place == null ? "" : place.clientOrderId()).append(',').append(place == null ? "" : place.side())
                        .append(',').append(place == null ? 0 : place.priceTicks()).append(',').append(place == null ? 0 : place.quantityLots())
                        .append(',').append(place == null ? "" : place.timeInForce()).append(',')
                        .append(command instanceof Cancel cancel ? cancel.orderId() : 0).append(',').append(item.reply.result().orderId())
                        .append(',').append(item.reply.result().remainingQuantity()).append(',').append(item.reply.result().tradeCount())
                        .append(',').append(item.reply.replayed()).append(',').append(item.rttNs).append('\n');
            }
            Files.writeString(evidence.resolve("trace.csv"), trace);
            System.out.printf(Locale.ROOT, "VECTOR_CONCURRENT_RUN_PASS clients=%d confirmed=%d trades=%d goodput=%.3f/s p99=%.3fms resends=%d unknown=%d hash=%s%n",
                    clients, measured.size(), trades, throughput, percentile(allRtt, .99) / 1e6, resends, unknown, reference.stateHash());
            return new Summary(throughput, percentile(allRtt, .99), totalWriteNanos / (double) measured.size());
        }

        private final class Worker implements Callable<Void> {
            private final int id;
            private final List<Observation> observations = new ArrayList<>();
            private long buyerSeq = 1, sellerSeq = 1;
            private long startedNs, endedNs;
            private ClusterClient.TransportCounters before, after;
            private boolean measuring;
            private Worker(int id) { this.id = id; }

            @Override public Void call() throws Exception {
                boolean ready = false, done = false;
                try (ClusterClient client = new ClusterClient(evidence.resolve("client-" + id + "-driver"), ports)) {
                    execute(client, new Deposit(buyer(), producer(), buyerSeq, Asset.QUOTE, 1_000_000_000_000L));
                    execute(client, new Deposit(seller(), producer(), sellerSeq, Asset.BASE, 1_000_000_000L));
                    for (int cycle = 0; cycle < TOTAL_WARMUP_CYCLES / clients; cycle++) cycle(client, cycle);
                    before = client.transportCounters(); ready = true; warmed.countDown();
                    start.await();
                    measuring = true; startedNs = System.nanoTime();
                    for (int cycle = TOTAL_WARMUP_CYCLES / clients;
                         cycle < (TOTAL_WARMUP_CYCLES + TOTAL_MEASURED_CYCLES) / clients; cycle++) cycle(client, cycle);
                    endedNs = System.nanoTime(); measuring = false; after = client.transportCounters();
                    done = true; completed.countDown();
                    while (!finish.await(50, TimeUnit.MILLISECONDS)) client.pollKeepAlive();
                    return null;
                } catch (Throwable error) {
                    failure.compareAndSet(null, error);
                    if (error instanceof Exception exception) throw exception;
                    throw new RuntimeException(error);
                } finally {
                    if (!ready) warmed.countDown();
                    if (!done) completed.countDown();
                }
            }

            private long buyer() { return 100 + id * 2L; }
            private long seller() { return buyer() + 1; }
            private String producer() { return "parallel-" + id; }
            private void cycle(ClusterClient client, int cycle) {
                CommandCodec.Reply maker = execute(client, new Place(seller(), producer(), ++sellerSeq,
                        "maker-" + id + '-' + cycle, Side.SELL, 10_000, 1_000_000, TimeInForce.GTC));
                execute(client, new Place(buyer(), producer(), ++buyerSeq,
                        "taker-" + id + '-' + cycle, Side.BUY, 10_000, 4, TimeInForce.IOC));
                execute(client, new Cancel(seller(), producer(), ++sellerSeq, maker.result().orderId()));
            }
            private CommandCodec.Reply execute(ClusterClient client, Command command) {
                long sent = System.nanoTime();
                CommandCodec.Reply reply = client.execute(command, TIMEOUT);
                long elapsed = System.nanoTime() - sent;
                require(reply.error().isEmpty() && reply.result() != null && reply.result().accepted(),
                        "Expected a valid accepted command: " + command + " -> " + reply);
                observations.add(new Observation(id, measuring, command, reply, elapsed));
                return reply;
            }
        }

        private List<ArchiveStats> readArchiveStats() {
            List<ArchiveStats> result = new ArrayList<>();
            for (int node = 0; node < LocalTopology.NODE_COUNT; node++) {
                long[] values = new long[3];
                boolean[] found = new boolean[3];
                try (Aeron observer = Aeron.connect(new Aeron.Context().aeronDirectoryName(
                        evidence.resolve("node-" + node).resolve("driver").toString()))) {
                    var counters = observer.countersReader();
                    counters.forEach((id, type, key, label) -> {
                        int slot = type == AeronCounters.ARCHIVE_RECORDER_TOTAL_WRITE_BYTES_TYPE_ID ? 0
                                : type == AeronCounters.ARCHIVE_RECORDER_TOTAL_WRITE_TIME_TYPE_ID ? 1
                                : type == AeronCounters.ARCHIVE_RECORDER_MAX_WRITE_TIME_TYPE_ID ? 2 : -1;
                        if (slot >= 0) { found[slot] = true; values[slot] += counters.getCounterValue(id); }
                    });
                }
                require(found[0] && found[1] && found[2], "Official Archive recorder counters missing");
                result.add(new ArchiveStats(values[0], values[1], values[2]));
            }
            return result;
        }

        private void checkFailure() {
            if (failure.get() != null) throw new IllegalStateException("Concurrent worker failed", failure.get());
        }
        private void startNodes() throws Exception {
            String java = Path.of(System.getProperty("java.home"), "bin", "java").toString();
            for (int node = 0; node < LocalTopology.NODE_COUNT; node++) {
                Process process = new ProcessBuilder(java,
                        "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED",
                        "-cp", System.getProperty("java.class.path"), ClusterNodeMain.class.getName(), Integer.toString(node),
                        evidence.toString(), Integer.toString(ports), "2", "65536")
                        .redirectErrorStream(true).redirectOutput(evidence.resolve("node-" + node + ".log").toFile()).start();
                nodes.add(process);
            }
        }
        private void stopNodes() throws InterruptedException {
            for (Process process : nodes) if (process.isAlive()) process.destroy();
            for (Process process : nodes) if (!process.waitFor(10, TimeUnit.SECONDS)) {
                process.destroyForcibly(); process.waitFor(5, TimeUnit.SECONDS);
            }
        }
    }

    private static long percentile(long[] sorted, double percentile) {
        return sorted[Math.max(0, (int) Math.ceil(sorted.length * percentile) - 1)];
    }
    private static void require(boolean condition, String detail) {
        if (!condition) throw new IllegalStateException(detail);
    }
    private static String escape(String value) { return value.replace("\\", "\\\\").replace("\"", "\\\""); }
}
