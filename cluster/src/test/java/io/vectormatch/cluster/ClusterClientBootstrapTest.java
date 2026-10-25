package io.vectormatch.cluster;

import io.aeron.driver.MediaDriver;
import io.aeron.exceptions.TimeoutException;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.agrona.DirectBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.io.File;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class ClusterClientBootstrapTest {
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(25);
    private static final ClientEndpoint EGRESS = new ClientEndpoint("127.0.0.1", 0);
    private static final NetworkTransport TRANSPORT = new NetworkTransport(1248);
    @TempDir Path temporary;

    @Test @Timeout(65)
    void borrowedDriverSurvivesFailedAndClosedClientsWithIndependentSessionsAndAeron() throws Exception {
        Path run = temporary.resolve("shared-client-regression");
        Files.createDirectories(run);
        ClusterTopology topology = ClusterTopology.local(availablePortBase());
        List<Process> nodes = new ArrayList<>();
        Path driverDirectory = run.resolve("shared-driver");
        try {
            for (int member = 0; member < topology.memberCount(); member++) nodes.add(startNode(run, topology, member));
            awaitStarted(run, nodes);
            try (MediaDriver shared = ClusterClient.launchDriver(driverDirectory, TRANSPORT)) {
                assertThrows(IllegalArgumentException.class, () -> new ClusterClient(shared, topology,
                        new ClientEndpoint("127.0.0.1", 32123), TRANSPORT));
                assertThrows(IllegalArgumentException.class, () -> new ClusterClient(shared, topology,
                        EGRESS, new NetworkTransport(1408)));
                AtomicReference<Throwable> failed = new AtomicReference<>();
                AtomicReference<Boolean> preservedInterrupt = new AtomicReference<>(false);
                ClusterTopology unavailable = ClusterTopology.local(availablePortBase());
                Thread connecting = new Thread(() -> {
                    Thread.currentThread().interrupt();
                    try (ClusterClient ignored = new ClusterClient(shared, unavailable, EGRESS, TRANSPORT)) {
                        failed.set(new AssertionError("Unexpected connection to " + ignored.leaderMemberId()));
                    } catch (Throwable error) {
                        failed.set(error); preservedInterrupt.set(Thread.currentThread().isInterrupted());
                    }
                }, "borrowed-interrupted-bootstrap");
                connecting.start(); connecting.join(5000);
                assertFalse(connecting.isAlive());
                assertNotNull(failed.get());
                assertTrue(preservedInterrupt.get());
                assertTrue(Files.exists(driverDirectory.resolve("cnc.dat")), "Failed borrower must not delete its owner driver");

                MatchingEngine reference = ClusterCapacity.newEngine();
                Deposit firstCommand = new Deposit(1, "shared-first", 1, Asset.QUOTE, 1234);
                Deposit secondCommand = new Deposit(2, "shared-second", 1, Asset.QUOTE, 5678);
                try (ClusterClient second = new ClusterClient(shared, topology, EGRESS, TRANSPORT)) {
                    try (ClusterClient first = new ClusterClient(shared, topology, EGRESS, TRANSPORT)) {
                        assertNotEquals(first.clusterSessionId(), second.clusterSessionId());
                        assertNotEquals(first.aeronClientId(), second.aeronClientId(), "Factor B must retain one Aeron per client");
                        assertNotEquals(first.resolvedEgressChannel(), second.resolvedEgressChannel(), "Port-zero borrowers need distinct actual response endpoints");
                        assertEquals(reference.apply(firstCommand).result(), first.execute(firstCommand, REQUEST_TIMEOUT).result());
                        assertEquals(reference.apply(secondCommand).result(), second.execute(secondCommand, REQUEST_TIMEOUT).result());
                    }
                    assertTrue(Files.exists(driverDirectory.resolve("cnc.dat")), "Closing one borrower must preserve the owner driver");
                    CommandCodec.Reply replay = second.execute(firstCommand, REQUEST_TIMEOUT);
                    assertTrue(replay.replayed());
                    assertEquals(reference.lastCommandSeq(), replay.commandSeq());
                    assertEquals(reference.stateHash(), second.state(REQUEST_TIMEOUT).stateHash());
                }
                assertTrue(Files.exists(driverDirectory.resolve("cnc.dat")), "All borrowers closed; only owner may delete driver");
                try (ClusterClient later = new ClusterClient(shared, topology, EGRESS, TRANSPORT)) {
                    assertEquals(reference.stateHash(), later.state(REQUEST_TIMEOUT).stateHash());
                }
            }
            assertFalse(Files.exists(driverDirectory), "Owner must close and delete its driver last");
        } finally { stop(nodes); }
    }

    @Test @Timeout(90)
    void freshClientConnectsAfterLeaderDiesAndReplaysConfirmedIdentityBeforeNewWrite() throws Exception {
        Path run = Path.of("build", "bootstrap-regression", "run-" + System.currentTimeMillis()).toAbsolutePath();
        Files.createDirectories(run);
        ClusterTopology topology = ClusterTopology.local(availablePortBase());
        List<Process> nodes = new ArrayList<>();
        MatchingEngine reference = ClusterCapacity.newEngine();
        Deposit deposit = new Deposit(1, "bootstrap", 1, Asset.QUOTE, 1_000_000);
        Place order = new Place(1, "bootstrap", 2, "confirmed-before-kill", Side.BUY, 100, 5, TimeInForce.GTC);
        int originalLeader;
        CommandCodec.Reply original;
        try {
            for (int member = 0; member < topology.memberCount(); member++) nodes.add(startNode(run, topology, member));
            awaitStarted(run, nodes);
            try (ClusterClient first = connect(run.resolve("first-client"), topology)) {
                assertEquals(reference.apply(deposit).result(), first.execute(deposit, REQUEST_TIMEOUT).result());
                assertEquals(reference.apply(order).result(), (original = first.execute(order, REQUEST_TIMEOUT)).result());
                assertEquals(reference.stateHash(), first.state(REQUEST_TIMEOUT).stateHash());
                originalLeader = first.leaderMemberId();
            }

            Process killed = nodes.get(originalLeader);
            killed.destroyForcibly();
            assertTrue(killed.waitFor(10, TimeUnit.SECONDS), "Killed leader did not exit");
            long started = System.nanoTime();
            // Construct immediately: surviving members can still redirect to the now-dead leader.
            try (ClusterClient fresh = connect(run.resolve("fresh-client"), topology)) {
                long bootstrapMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
                assertNotEquals(originalLeader, fresh.leaderMemberId());
                CommandCodec.Reply replay = fresh.execute(order, REQUEST_TIMEOUT);
                assertTrue(replay.replayed(), "Confirmed identity must survive an entirely new client session");
                assertEquals(original.result(), replay.result());
                assertEquals(reference.lastCommandSeq(), replay.commandSeq());
                Cancel cancel = new Cancel(1, "bootstrap", 3, original.result().orderId());
                assertEquals(reference.apply(cancel).result(), fresh.execute(cancel, REQUEST_TIMEOUT).result());
                assertEquals(reference.stateHash(), fresh.state(REQUEST_TIMEOUT).stateHash());
                reference.checkInvariants();
                assertFalse(killed.isAlive(), "The original leader must remain down throughout validation");
                String result = "originalLeader=" + originalLeader + " freshLeader=" + fresh.leaderMemberId()
                        + " bootstrapMillis=" + bootstrapMillis + " stateHash=" + reference.stateHash();
                Files.writeString(run.resolve("result.txt"), result + System.lineSeparator());
                System.out.println("VECTOR_FRESH_CLIENT_BOOTSTRAP_PASS " + result + " evidence=" + run);
            }
        } finally {
            stop(nodes);
        }
    }

    @Test @Timeout(35)
    void unavailableMembersShareOneTwentySecondBudgetAndReleaseDriver() throws Exception {
        Path directory = temporary.resolve("all-dead-driver");
        ClusterTopology topology = ClusterTopology.local(availablePortBase());
        long started = System.nanoTime();
        TimeoutException failure = assertThrows(TimeoutException.class, () -> connect(directory, topology));
        long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);
        assertTrue(elapsedMillis >= 19_000 && elapsedMillis < 28_000,
                "All seeds must share a single 20s timeout; observed " + elapsedMillis + "ms");
        assertTrue(failure.getMessage().contains("Cluster bootstrap timed out after 20s"));
        assertFalse(Files.exists(directory), "Failed constructor must close and delete its embedded driver");
    }

    @Test @Timeout(15)
    void interruptionStopsBootstrapWithoutClearingInterruptAndReleasesDriver() throws Exception {
        Path directory = temporary.resolve("interrupted-driver");
        ClusterTopology topology = ClusterTopology.local(availablePortBase());
        AtomicReference<Throwable> failure = new AtomicReference<>();
        AtomicReference<Boolean> interrupted = new AtomicReference<>(false);
        Thread connecting = new Thread(() -> {
            try (ClusterClient ignored = connect(directory, topology)) {
                failure.set(new AssertionError("Unexpected connection to unavailable cluster member " + ignored.leaderMemberId()));
            } catch (Throwable error) {
                failure.set(error);
                interrupted.set(Thread.currentThread().isInterrupted());
            }
        }, "interrupted-bootstrap-test");
        connecting.start();
        long waitUntil = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!Files.exists(directory.resolve("cnc.dat")) && System.nanoTime() < waitUntil) Thread.sleep(10);
        try {
            connecting.interrupt();
            connecting.join(5000);
            assertFalse(connecting.isAlive(), "Interrupted bootstrap must terminate promptly");
            assertNotNull(failure.get());
            assertTrue(interrupted.get(), "Bootstrap must preserve the caller's interrupt status");
            assertFalse(Files.exists(directory), "Interrupted constructor must close its embedded driver");
        } finally {
            if (connecting.isAlive()) { connecting.interrupt(); connecting.join(5000); }
        }
    }

    private static ClusterClient connect(Path directory, ClusterTopology topology) {
        return new ClusterClient(directory, topology, EGRESS, TRANSPORT);
    }

    private static Process startNode(Path run, ClusterTopology topology, int member) throws Exception {
        String java = Path.of(System.getProperty("java.home"), "bin", "java").toString();
        List<String> command = List.of(java,
                "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED",
                "--add-opens=java.base/java.util.zip=ALL-UNNAMED",
                "-cp", nodeClasspath(), ClusterNodeMain.class.getName(),
                Integer.toString(member), run.toString(), Integer.toString(topology.portBase()), "2", "65536",
                "127.0.0.1,127.0.0.1,127.0.0.1");
        ProcessBuilder builder = new ProcessBuilder(command).redirectErrorStream(true)
                .redirectOutput(run.resolve("node-" + member + ".log").toFile());
        builder.environment().put(NetworkTransport.MTU_ENV, "1248");
        return builder.start();
    }

    private static String nodeClasspath() throws Exception {
        LinkedHashSet<String> entries = new LinkedHashSet<>();
        for (Class<?> type : List.of(ClusterNodeMain.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class)) {
            entries.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        }
        return String.join(File.pathSeparator, entries);
    }

    private static void awaitStarted(Path run, List<Process> nodes) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
        while (System.nanoTime() < deadline) {
            boolean ready = true;
            for (int member = 0; member < nodes.size(); member++) {
                assertTrue(nodes.get(member).isAlive(), "Node exited; inspect " + run.resolve("node-" + member + ".log"));
                Path log = run.resolve("node-" + member + ".log");
                ready &= Files.exists(log) && Files.readString(log).contains("VECTOR_CLUSTER_STARTED");
            }
            if (ready) return;
            Thread.sleep(20);
        }
        fail("Nodes did not start; inspect " + run);
    }

    private static int availablePortBase() throws Exception {
        return RetentionLoopbackPortsV4.availableBase();
    }

    private static void stop(List<Process> nodes) {
        nodes.stream().filter(Process::isAlive).forEach(Process::destroy);
        for (Process node : nodes) {
            try {
                if (!node.waitFor(5, TimeUnit.SECONDS)) {
                    node.destroyForcibly();
                    node.waitFor(5, TimeUnit.SECONDS);
                }
            } catch (InterruptedException interrupted) {
                node.destroyForcibly();
                Thread.currentThread().interrupt();
            }
        }
    }
}
