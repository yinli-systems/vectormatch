package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * A correctness-checked closed-loop replication smoke benchmark, not a capacity or open-loop load test.
 * One client request is outstanding at a time; the load generator shares its host with all cluster processes.
 */
public final class ReplicatedBenchmarkSmoke {
    private static final int WARMUP_CYCLES = 100;
    private static final int MEASURED_CYCLES = 334;
    private static final int COMMANDS_PER_CYCLE = 3;
    private static final Duration TIMEOUT = Duration.ofSeconds(30);
    private final Path evidence;
    private final int ports;
    private final List<Process> nodes = new ArrayList<>();
    private final MatchingEngine reference = ClusterCapacity.newEngine();
    private final long[] rttNanos = new long[MEASURED_CYCLES * COMMANDS_PER_CYCLE];
    private final StringBuilder rawSamples = new StringBuilder("index,type,client_rtt_ns,trade_count,replayed\n");
    private long buyerSeq = 1, sellerSeq = 1;
    private long measuredTrades, measuredBaseLots;
    private int samples;
    private boolean measured;

    private ReplicatedBenchmarkSmoke(Path evidence, int ports) {
        this.evidence = evidence;
        this.ports = ports;
    }

    public static void main(String[] args) throws Exception {
        Path evidence = args.length > 0 ? Path.of(args[0]).toAbsolutePath()
                : Path.of("build", "replicated-benchmark", "run-" + Instant.now().toEpochMilli()).toAbsolutePath();
        int ports = args.length > 1 ? Integer.parseInt(args[1]) : 27000;
        if (Files.exists(evidence)) throw new IllegalArgumentException("Benchmark requires a fresh evidence/state directory: " + evidence);
        Files.createDirectories(evidence);
        ReplicatedBenchmarkSmoke smoke = new ReplicatedBenchmarkSmoke(evidence, ports);
        System.out.println("VECTOR_REPLICATED_BENCHMARK_EVIDENCE " + evidence);
        try { smoke.run(); }
        finally { smoke.stopNodes(); }
    }

    private void run() throws Exception {
        startNodes();
        try (ClusterClient client = new ClusterClient(evidence.resolve("client-driver"), ports)) {
            execute(client, new Deposit(1, "replicated-bench", buyerSeq, Asset.QUOTE, 1_000_000_000_000L));
            execute(client, new Deposit(2, "replicated-bench", sellerSeq, Asset.BASE, 1_000_000_000L));
            for (int cycle = 0; cycle < WARMUP_CYCLES; cycle++) cycle(client, cycle);
            require(reference.stateHash().equals(client.state(TIMEOUT).stateHash()), "Warmup state differs");

            ClusterClient.TransportCounters before = client.transportCounters();
            measured = true;
            long start = System.nanoTime();
            for (int cycle = WARMUP_CYCLES; cycle < WARMUP_CYCLES + MEASURED_CYCLES; cycle++) cycle(client, cycle);
            long elapsedNanos = System.nanoTime() - start;
            measured = false;
            ClusterClient.TransportCounters after = client.transportCounters();

            require(samples == MEASURED_CYCLES * COMMANDS_PER_CYCLE, "Missing response samples");
            require(measuredTrades == MEASURED_CYCLES, "Workload did not create its expected valid trades");
            require(measuredBaseLots == MEASURED_CYCLES * 4L, "Executed base quantity differs");
            reference.checkInvariants();
            MatchingEngine restored = MatchingEngine.restore(client.readSnapshot(TIMEOUT));
            restored.checkInvariants();
            require(reference.stateHash().equals(restored.stateHash()), "Replicated snapshot differs from reference state");
            require(reference.stateHash().equals(client.state(TIMEOUT).stateHash()), "Final leader state differs");
            EventBatch pending = client.fetchEvents(1, 16, TIMEOUT);
            require(pending.exportedSeq() == 0 && pending.lastEventSeq() == reference.lastEventSeq(), "Outbox event history differs");

            long acceptedAttempts = after.acceptedOffers() - before.acceptedOffers();
            long resends = after.acceptedResends() - before.acceptedResends();
            long unaccepted = after.unacceptedOffers() - before.unacceptedOffers();
            long unknown = after.requestTimeouts() - before.requestTimeouts();
            long[] sorted = rttNanos.clone(); Arrays.sort(sorted);
            double goodput = samples * 1_000_000_000.0 / elapsedNanos;
            String json = String.format(Locale.ROOT, """
                    {
                      "test": "replicated-matching-closed-loop-smoke",
                      "passed": true,
                      "loadModel": "CLOSED_LOOP_SINGLE_INFLIGHT",
                      "maxInFlight": 1,
                      "independentMachines": false,
                      "loadGeneratorSharesClusterHost": true,
                      "clusterProcesses": 3,
                      "archiveFileSyncLevel": 2,
                      "archiveCatalogFileSyncLevel": 2,
                      "consensusFileSyncLevel": 2,
                      "warmupCommands": %d,
                      "measuredLogicalCommands": %d,
                      "confirmedAcceptedCommands": %d,
                      "businessRejectedCommands": 0,
                      "transportAcceptedAttempts": %d,
                      "transportAcceptedResends": %d,
                      "transportUnacceptedOffers": %d,
                      "unknownRequestTimeouts": %d,
                      "unresolvedCommands": 0,
                      "measuredTrades": %d,
                      "measuredExecutedBaseLots": %d,
                      "measurementSeconds": %.6f,
                      "confirmedCommandsPerSecond": %.3f,
                      "clientRttMicroseconds": {
                        "min": %.3f, "p50": %.3f, "p95": %.3f, "p99": %.3f, "p999": %.3f, "max": %.3f
                      },
                      "percentileMethod": "nearest-rank over all measured command samples",
                      "rttScope": "client execute call, including encode, transport, cluster commit, business processing, response and automatic retries",
                      "throughputScope": "elapsed closed-loop workload, including reference validation and sample recording on the shared load-generator host",
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
                    """, WARMUP_CYCLES * COMMANDS_PER_CYCLE, samples, samples,
                    acceptedAttempts, resends, unaccepted, unknown, measuredTrades, measuredBaseLots,
                    elapsedNanos / 1_000_000_000.0, goodput,
                    sorted[0] / 1000.0, percentile(sorted, 0.50) / 1000.0, percentile(sorted, 0.95) / 1000.0,
                    percentile(sorted, 0.99) / 1000.0, percentile(sorted, 0.999) / 1000.0, sorted[sorted.length - 1] / 1000.0,
                    reference.lastCommandSeq(), reference.lastEventSeq(), reference.lastMarketSeq(), reference.stateHash(),
                    escape(System.getProperty("java.version")), escape(System.getProperty("os.name")),
                    escape(System.getProperty("os.arch")), Runtime.getRuntime().availableProcessors());
            Files.writeString(evidence.resolve("samples.csv"), rawSamples);
            Files.writeString(evidence.resolve("result.json"), json);
            System.out.printf(Locale.ROOT, "VECTOR_REPLICATED_BENCHMARK_PASS commands=%d trades=%d goodput=%.3f/s p50=%.3fus p99=%.3fus unknown=%d resends=%d hash=%s%n",
                    samples, measuredTrades, goodput, percentile(sorted, 0.50) / 1000.0,
                    percentile(sorted, 0.99) / 1000.0, unknown, resends, reference.stateHash());
        }
    }

    private void cycle(ClusterClient client, int cycle) {
        CommandCodec.Reply resting = execute(client, new Place(2, "replicated-bench", ++sellerSeq,
                "maker-" + cycle, Side.SELL, 10_000, 10, TimeInForce.GTC));
        execute(client, new Place(1, "replicated-bench", ++buyerSeq,
                "taker-" + cycle, Side.BUY, 10_000, 4, TimeInForce.IOC));
        execute(client, new Cancel(2, "replicated-bench", ++sellerSeq, resting.result().orderId()));
    }

    private CommandCodec.Reply execute(ClusterClient client, Command command) {
        Execution expected = reference.apply(command);
        require(expected.result().accepted(), "Reference workload command unexpectedly rejected");
        long start = System.nanoTime();
        CommandCodec.Reply actual = client.execute(command, TIMEOUT);
        long duration = System.nanoTime() - start;
        require(actual.error().isEmpty(), "Cluster error: " + actual.error());
        require(expected.result().equals(actual.result()), "Business result differs for " + command);
        require(actual.commandSeq() == reference.lastCommandSeq() && actual.eventSeq() == reference.lastEventSeq()
                && actual.marketSeq() == reference.lastMarketSeq(), "Replicated sequence differs");
        if (measured) {
            rttNanos[samples] = duration;
            rawSamples.append(samples).append(',').append(command.getClass().getSimpleName()).append(',')
                    .append(duration).append(',').append(actual.result().tradeCount()).append(',').append(actual.replayed()).append('\n');
            samples++;
            measuredTrades += actual.result().tradeCount();
            measuredBaseLots += expected.events().stream().filter(e -> e.type() == EventType.TRADE).mapToLong(Event::quantityLots).sum();
        }
        return actual;
    }

    private void startNodes() throws Exception {
        String java = Path.of(System.getProperty("java.home"), "bin", "java").toString();
        for (int node = 0; node < LocalTopology.NODE_COUNT; node++) {
            List<String> command = List.of(java,
                    "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED",
                    "--add-opens=java.base/java.util.zip=ALL-UNNAMED",
                    "-cp", System.getProperty("java.class.path"), ClusterNodeMain.class.getName(),
                    Integer.toString(node), evidence.toString(), Integer.toString(ports), "2", "65536");
            Process process = new ProcessBuilder(command).redirectErrorStream(true)
                    .redirectOutput(evidence.resolve("node-" + node + ".log").toFile()).start();
            nodes.add(process);
        }
    }

    private void stopNodes() {
        for (Process process : nodes) if (process.isAlive()) process.destroy();
        for (Process process : nodes) {
            try {
                if (!process.waitFor(10, TimeUnit.SECONDS)) {
                    process.destroyForcibly(); process.waitFor(5, TimeUnit.SECONDS);
                }
            } catch (InterruptedException interrupted) {
                process.destroyForcibly(); Thread.currentThread().interrupt();
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
