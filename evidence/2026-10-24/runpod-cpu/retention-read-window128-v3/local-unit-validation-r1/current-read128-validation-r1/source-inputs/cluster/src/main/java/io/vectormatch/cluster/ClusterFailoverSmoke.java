package io.vectormatch.cluster;

import io.aeron.cluster.ClusterTool;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/** Real three-process smoke test: replication, SIGKILL leader, idempotent retries, snapshot, cold restart. */
public final class ClusterFailoverSmoke {
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(30);
    private final List<Process> nodes = new ArrayList<>(3);
    private final Path evidence;
    private final int ports;
    private final int sync;
    private final MatchingEngine expected = ClusterCapacity.newEngine();
    private final List<Event> expectedEvents = new ArrayList<>();

    private ClusterFailoverSmoke(Path evidence, int ports, int sync) {
        this.evidence = evidence;
        this.ports = ports;
        this.sync = sync;
        for (int i = 0; i < LocalTopology.NODE_COUNT; i++) nodes.add(null);
    }

    public static void main(String[] args) throws Exception {
        Path evidence = args.length > 0 ? Path.of(args[0]).toAbsolutePath()
                : Path.of("build", "failover-smoke", "run-" + Instant.now().toEpochMilli()).toAbsolutePath();
        int ports = args.length > 1 ? Integer.parseInt(args[1]) : 24000;
        int sync = args.length > 2 ? Integer.parseInt(args[2]) : 2;
        Files.createDirectories(evidence);
        ClusterFailoverSmoke smoke = new ClusterFailoverSmoke(evidence, ports, sync);
        System.out.println("VECTOR_FAILOVER_EVIDENCE " + evidence);
        try { smoke.run(); }
        finally { smoke.stopNodes(); }
    }

    private void run() throws Exception {
        startNodes();
        int oldLeader;
        int newLeader;
        long failoverNanos;
        String finalHash;
        String checkpointHash;
        Deposit blocked = new Deposit(1, "smoke", 4, Asset.QUOTE, 1);
        try (ClusterClient client = connect()) {
            assertState(client);
            check(client, new Deposit(1, "smoke", 1, Asset.QUOTE, 1_000_000));
            check(client, new Deposit(2, "smoke", 1, Asset.BASE, 10_000));
            CommandCodec.Reply resting = check(client,
                    new Place(2, "smoke", 2, "maker-1", Side.SELL, 100, 100, TimeInForce.GTC));
            Place beforeFailure = new Place(1, "smoke", 2, "taker-1", Side.BUY, 101, 40, TimeInForce.GTC);
            check(client, beforeFailure);
            assertState(client);

            oldLeader = client.leaderMemberId();
            long started = System.nanoTime();
            Process killed = nodes.get(oldLeader);
            System.out.printf("VECTOR_KILL_LEADER member=%d pid=%d%n", oldLeader, killed.pid());
            killed.destroyForcibly();
            if (!killed.waitFor(10, TimeUnit.SECONDS)) throw new IllegalStateException("Leader did not terminate");
            check(client, new Place(1, "smoke", 3, "taker-2", Side.BUY, 100, 10, TimeInForce.GTC));
            failoverNanos = System.nanoTime() - started;
            newLeader = client.leaderMemberId();
            require(oldLeader != newLeader, "Leadership must move away from the killed process");
            check(client, beforeFailure); // confirmed-before-failure result is still deduplicated.
            check(client, new Place(1, "smoke", 2, "changed-payload", Side.BUY, 999, 1, TimeInForce.GTC));
            assertState(client);

            startNode(oldLeader); // catch-up from the two surviving members.
            check(client, new Cancel(2, "smoke", 3, resting.result().orderId()));
            assertState(client);
            require(client.fetchEvents(1, 100, REQUEST_TIMEOUT).events().equals(expectedEvents),
                    "Unacknowledged events differ from produced events");
            require(client.fetchEvents(1, 100, REQUEST_TIMEOUT).events().equals(expectedEvents),
                    "Fetching must not consume unacknowledged events");
            CommandCodec.Reply full = client.execute(blocked, REQUEST_TIMEOUT);
            require("OUTBOX_FULL".equals(full.error()) && full.result() == null,
                    "A full outbox must reject before mutating the core");
            assertState(client);
            check(client, beforeFailure); // Deduplicated results remain available even with a full outbox.
            require(client.ackExport(3, REQUEST_TIMEOUT) == 3, "Acknowledgement did not advance");
            require(client.ackExport(3, REQUEST_TIMEOUT) == 3, "Acknowledgement retry was not idempotent");
            require(client.fetchEvents(4, 100, REQUEST_TIMEOUT).events().equals(expectedEvents.subList(3, 8)),
                    "Partial acknowledgement lost pending events");
            expectAcknowledgedRangeUnavailable(client);
            // ClusterTool waits for snapshot completion. Each node's service log is additionally checked below.
            require(ClusterTool.snapshot(evidence.resolve("node-" + client.leaderMemberId())
                    .resolve("cluster").toFile(), System.out), "Snapshot request failed");
            awaitSnapshotLogs("VECTOR_SNAPSHOT_WRITTEN", expected.stateHash());
            checkpointHash = expected.stateHash();
        }

        stopNodes();
        startNodes();
        try (ClusterClient recovered = connect()) {
            assertState(recovered);
            awaitSnapshotLogs("VECTOR_SNAPSHOT_RESTORED", checkpointHash);
            require(recovered.fetchEvents(4, 100, REQUEST_TIMEOUT).events().equals(expectedEvents.subList(3, 8)),
                    "Outbox events/watermark were not restored with the checkpoint");
            require(recovered.ackExport(2, REQUEST_TIMEOUT) == 3, "Acknowledgement watermark regressed");
            expectAcknowledgedRangeUnavailable(recovered);
            check(recovered, new Place(1, "smoke", 2, "taker-1", Side.BUY, 101, 40, TimeInForce.GTC));
            check(recovered, blocked); // The earlier OUTBOX_FULL did not consume its idempotency sequence.
            for (long seq = 1; seq <= 50; seq++) {
                check(recovered, new Deposit(3, "chunked-snapshot", seq, Asset.QUOTE, 1));
                recovered.ackExport(expected.lastEventSeq(), REQUEST_TIMEOUT);
            }
            byte[] snapshot = recovered.readSnapshot(REQUEST_TIMEOUT);
            require(snapshot.length > CommandCodec.MAX_SNAPSHOT_CHUNK, "Smoke must exercise multiple wire snapshot chunks");
            require(MatchingEngine.restore(snapshot).stateHash().equals(expected.stateHash()),
                    "Wire snapshot was not a consistent canonical core snapshot");
            assertState(recovered);
            finalHash = expected.stateHash();
        }
        String json = String.format(Locale.ROOT, """
                {
                  "test": "three-local-process-failover-snapshot-restart",
                  "passed": true,
                  "independentMachines": false,
                  "syncLevel": %d,
                  "oldLeader": %d,
                  "newLeader": %d,
                  "killToNextConfirmedCommandMs": %.3f,
                  "finalCommandSeq": %d,
                  "finalEventSeq": %d,
                  "finalMarketSeq": %d,
                  "outboxBackpressureAndRecovery": true,
                  "chunkedCoreSnapshotVerified": true,
                  "stateHash": "%s"
                }
                """, sync, oldLeader, newLeader, failoverNanos / 1_000_000.0,
                expected.lastCommandSeq(), expected.lastEventSeq(), expected.lastMarketSeq(), finalHash);
        Files.writeString(evidence.resolve("result.json"), json);
        System.out.println("VECTOR_FAILOVER_PASS " + json.replace('\n', ' '));
    }

    private CommandCodec.Reply check(ClusterClient client, Command command) {
        Execution wanted = expected.apply(command);
        expectedEvents.addAll(wanted.events());
        CommandCodec.Reply actual = client.execute(command, REQUEST_TIMEOUT);
        require(actual.error().isEmpty(), "Cluster error " + actual.error());
        require(wanted.result().equals(actual.result()), "Result differs for " + command + ": " + actual);
        // A first response can be lost and the transport retry can legitimately return replayed=true.
        if (wanted.replayed()) require(actual.replayed(), "A repeated business command must be deduplicated");
        require(expected.lastCommandSeq() == actual.commandSeq(), "Command sequence differs");
        require(expected.lastEventSeq() == actual.eventSeq(), "Event sequence differs");
        require(expected.lastMarketSeq() == actual.marketSeq(), "Market sequence differs");
        System.out.println("VECTOR_COMMAND_CHECK seq=" + command.requestSeq() + " result=" + actual.result().code()
                + " replayed=" + actual.replayed());
        return actual;
    }

    private void assertState(ClusterClient client) {
        CommandCodec.Reply actual = client.state(REQUEST_TIMEOUT);
        require(expected.stateHash().equals(actual.stateHash()), "Canonical state differs: " + actual.stateHash());
    }

    private ClusterClient connect() {
        return new ClusterClient(evidence.resolve("client-driver"), ports);
    }

    private void startNodes() throws Exception {
        for (int node = 0; node < LocalTopology.NODE_COUNT; node++) startNode(node);
    }

    private void startNode(int node) throws Exception {
        Process previous = nodes.get(node);
        if (previous != null && previous.isAlive()) throw new IllegalStateException("Node already running " + node);
        String java = Path.of(System.getProperty("java.home"), "bin", "java").toString();
        List<String> command = List.of(java,
                "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED",
                "--add-opens=java.base/java.util.zip=ALL-UNNAMED",
                "-cp", System.getProperty("java.class.path"), ClusterNodeMain.class.getName(),
                Integer.toString(node), evidence.toString(), Integer.toString(ports), Integer.toString(sync), "8");
        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .redirectOutput(ProcessBuilder.Redirect.appendTo(evidence.resolve("node-" + node + ".log").toFile()))
                .start();
        nodes.set(node, process);
        System.out.printf("VECTOR_START_NODE member=%d pid=%d%n", node, process.pid());
    }

    private void awaitSnapshotLogs(String marker, String hash) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
        while (System.nanoTime() < deadline) {
            boolean all = true;
            for (int node = 0; node < LocalTopology.NODE_COUNT; node++) {
                Process process = nodes.get(node);
                require(process != null && process.isAlive(), "Node exited; see node-" + node + ".log");
                String text = Files.readString(evidence.resolve("node-" + node + ".log"));
                all &= text.contains(marker + " hash=" + hash);
            }
            if (all) return;
            Thread.sleep(50);
        }
        throw new IllegalStateException("Not every node produced " + marker + "; inspect " + evidence);
    }

    private void stopNodes() {
        for (Process process : nodes) if (process != null && process.isAlive()) process.destroy();
        for (Process process : nodes) {
            if (process == null) continue;
            try {
                if (!process.waitFor(10, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }
            } catch (InterruptedException interrupted) {
                process.destroyForcibly();
                Thread.currentThread().interrupt();
            }
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private void expectAcknowledgedRangeUnavailable(ClusterClient client) {
        try {
            client.fetchEvents(1, 16, REQUEST_TIMEOUT);
            throw new IllegalStateException("Fetching reclaimed events must explicitly fail");
        } catch (IllegalStateException expectedFailure) {
            require(expectedFailure.getMessage().contains("EVENTS_ALREADY_ACKNOWLEDGED"),
                    "Unexpected failure for reclaimed event range: " + expectedFailure.getMessage());
        }
    }
}
