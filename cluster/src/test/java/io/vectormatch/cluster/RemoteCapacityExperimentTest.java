package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.io.File;
import java.util.concurrent.TimeUnit;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

import static org.junit.jupiter.api.Assertions.*;

class RemoteCapacityExperimentTest {
    @TempDir Path directory;

    private RemoteCapacityExperiment.Options options(int rate, int arrivals, int workers, int queue, int timeout, int drain) {
        return new RemoteCapacityExperiment.Options(directory, 19000, rate, arrivals, workers, queue, timeout, drain, 0, 1000);
    }
    private static RemoteCapacityExperiment.Sample[] samples(int count, int workers) {
        RemoteCapacityExperiment.Sample[] result = new RemoteCapacityExperiment.Sample[count];
        for (int i = 0; i < count; i++) result[i] = new RemoteCapacityExperiment.Sample(i, workers, "test-producer");
        return result;
    }
    private static CommandCodec.Reply accepted(Command command, long commandSeq, boolean replayed) {
        return new CommandCodec.Reply(1, new Result(ResultCode.ACCEPTED, "", commandSeq, commandSeq, 0, 1), replayed,
                commandSeq, commandSeq * 2, commandSeq * 2, "", "");
    }
    private abstract static class FakeTransport implements RemoteCapacityExperiment.Transport {
        public int leader() { return 0; }
        public void idle() {}
        public ClusterClient.TransportCounters counters() { return new ClusterClient.TransportCounters(0, 0, 0, 0); }
        public void close() {}
    }

    @Test void fixedArrivalScheduleDoesNotWaitForSlowRepliesAndAccountsForEveryArrival() throws Exception {
        var opts = options(200, 40, 2, 2, 1000, 1500);
        var samples = samples(40, 2);
        AtomicInteger commandSeq = new AtomicInteger();
        var load = RemoteCapacityExperiment.runLoad(opts, samples, worker -> new FakeTransport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                LockSupport.parkNanos(80_000_000);
                return accepted(command, commandSeq.incrementAndGet(), false);
            }
        });
        Map<String, Object> result = RemoteCapacityExperiment.summarize(load);
        assertEquals(40, load.due.get());
        assertTrue(load.dropped.get() > 10, "Fixed schedule should fill bounded queues while replies are slow");
        assertEquals(40, load.completed.get() + load.dropped.get());
        assertEquals(195_000_000L, samples[39].planned - samples[0].planned);
        assertTrue(samples[39].enqueued - samples[0].planned < 600_000_000L, "Scheduler must not become response-driven");
        assertTrue(Arrays.stream(samples).allMatch(s -> Set.of("CONFIRMED_ACCEPTED", "CLIENT_QUEUE_FULL_NOT_SENT").contains(s.outcome)));
        assertTrue(Arrays.stream(samples).filter(RemoteCapacityExperiment.Sample::hasReply).allMatch(s -> s.confirmed >= s.started && s.started >= s.enqueued && s.enqueued >= s.planned));
        assertEquals(40L - load.completed.get(), ((Number) result.get("clientNotSentCommands")).longValue());
        assertTrue(((Number) result.get("confirmedWithinArrivalWindow")).longValue() < load.completed.get(), "Drain confirmations must not inflate arrival-window goodput");
        assertEquals(load.completed.get(), ((Number) ((Map<?, ?>) result.get("scheduledToConfirmedMicroseconds")).get("count")).intValue());
        assertFalse(load.backlog.isEmpty());
        assertNull(result.get("allOfferedAcceptedP99Microseconds"), "All-offered accepted p99 cannot be inferred when requests were not sent");
    }

    @Test void unknownIsResolvedWithIdenticalIdentityBeforeHigherSequenceAndOriginalTimeoutIsRetained() throws Exception {
        var opts = options(20, 4, 1, 8, 10, 1000);
        var samples = samples(4, 1);
        List<Command> issued = new ArrayList<>();
        var load = RemoteCapacityExperiment.runLoad(opts, samples, worker -> new FakeTransport() {
            boolean first = true;
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                issued.add(command);
                if (first) { first = false; throw new IllegalStateException("Unknown result after timeout"); }
                return accepted(command, command.requestSeq(), command.requestSeq() == 1);
            }
        });
        assertEquals(5, issued.size());
        assertSame(issued.get(0), issued.get(1), "Resolution must use exactly the same command object and business identity");
        assertEquals(List.of(1L, 1L, 2L, 3L, 4L), issued.stream().map(Command::requestSeq).toList());
        assertEquals(1, load.initialUnknown.get());
        assertEquals(0, load.unresolved.get());
        assertEquals(2, samples[0].attempts);
        assertTrue(samples[0].firstUnknown > 0);
        assertTrue(samples[0].confirmed > samples[0].initialEnd);
        assertTrue(samples[0].reply.replayed());
        assertEquals(1L, ((Number) RemoteCapacityExperiment.summarize(load).get("resolvedAfterInitialUnknown")).longValue());
        assertNotNull(RemoteCapacityExperiment.summarize(load).get("allOfferedAcceptedP99Microseconds"));
    }

    @Test void unresolvedIdentityBlocksItsWorkerAndQueuedCommandsAreExplicitlyNeverSent() throws Exception {
        var opts = options(100, 10, 1, 20, 10, 100);
        var samples = samples(10, 1);
        List<Command> issued = new ArrayList<>();
        var load = RemoteCapacityExperiment.runLoad(opts, samples, worker -> new FakeTransport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                issued.add(command);
                LockSupport.parkNanos(Math.min(timeout.toNanos(), 10_000_000));
                throw new IllegalStateException("Unknown result");
            }
        });
        assertFalse(issued.isEmpty());
        assertTrue(issued.stream().allMatch(c -> c.requestSeq() == 1), "Never advance an unresolved producer sequence");
        assertEquals("UNKNOWN_UNRESOLVED", samples[0].outcome);
        assertEquals(1, load.unresolved.get());
        assertEquals(9, load.dropped.get());
        assertTrue(Arrays.stream(samples).skip(1).allMatch(s -> s.outcome.equals("WORKER_BLOCKED_UNKNOWN_NOT_SENT") && s.started == 0 && s.reply == null));
        assertEquals(0, ((Number) ((Map<?, ?>) RemoteCapacityExperiment.summarize(load).get("scheduledToConfirmedMicroseconds")).get("count")).intValue());
    }

    @Test void fractionalRateUsesAbsoluteOffsetsAndPercentilesExcludeInventedZeros() {
        assertEquals(0, RemoteCapacityExperiment.offsetNanos(0, 3));
        assertEquals(333_333_333L, RemoteCapacityExperiment.offsetNanos(1, 3));
        assertEquals(1_000_000_000L, RemoteCapacityExperiment.offsetNanos(3, 3));
        assertEquals(10_000_000_000L, RemoteCapacityExperiment.offsetNanos(30, 3));
        assertEquals(0, RemoteCapacityExperiment.distribution(new long[0]).get("count"));
        assertNull(RemoteCapacityExperiment.distribution(new long[0]).get("p99"));
        assertEquals(99.0, RemoteCapacityExperiment.distribution(java.util.stream.LongStream.rangeClosed(1, 100).map(i -> i * 1000).toArray()).get("p99"));
    }

    @Test void retainedOrderAndOutboxTrialBoundsCannotBeRaisedByAccident() {
        assertThrows(IllegalArgumentException.class, () -> options(100, 30_001, 1, 1, 100, 100));
        assertThrows(IllegalArgumentException.class, () -> options(100, 10, 65, 1, 100, 100));
        assertThrows(IllegalArgumentException.class, () -> options(1, 301, 1, 1, 100, 100));
        assertThrows(IllegalArgumentException.class, () -> options(100, 10, 1, 1, 100, 99));
        assertDoesNotThrow(() -> options(100, 30_000, 64, 1, 100, 100));
    }

    @Test void leaderChangeIsRetainedEvenWhenAllRepliesSucceed() throws Exception {
        var opts = options(100, 2, 1, 4, 10, 100);
        AtomicInteger replies = new AtomicInteger();
        var load = RemoteCapacityExperiment.runLoad(opts, samples(2, 1), worker -> new FakeTransport() {
            public int leader() { return replies.get() == 0 ? 0 : 1; }
            public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, replies.incrementAndGet(), false); }
        });
        assertTrue(load.leaderChanged.get());
        assertEquals(2, load.completed.get());
    }

    @Test void extendedProfileRequiresExplicitOutboxAndDoesNotRaiseBaselineLimits() {
        var baseline = RemoteCapacityExperiment.Profile.BASELINE;
        var extended = RemoteCapacityExperiment.Profile.EXTENDED_90K;
        assertEquals(baseline, options(100, 100, 1, 1, 100, 100).profile());
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(baseline, Map.of()));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(baseline, Map.of("VECTOR_OUTBOX_CAPACITY", "65536")));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(baseline, Map.of("VECTOR_OUTBOX_CAPACITY", "262144")));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(extended, Map.of()));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(extended, Map.of("VECTOR_OUTBOX_CAPACITY", "65536")));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(extended, Map.of("VECTOR_OUTBOX_CAPACITY", "262144")));
        assertEquals(extended, RemoteCapacityExperiment.Profile.parse("extended-90k"));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.Profile.parse("unbounded"));
        assertDoesNotThrow(() -> new RemoteCapacityExperiment.Options(directory, 19000, 3000, 90_000, 64, 64, 2000, 30_000, 0, 20, extended));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 3000, 90_001, 64, 64, 2000, 30_000, 0, 20, extended));
        assertThrows(IllegalArgumentException.class, () -> options(3000, 90_000, 64, 64, 2000, 30_000));
        assertDoesNotThrow(() -> ClusterCapacity.validate(ClusterCapacity.newEngine().limits(), extended.outboxCapacity));
        assertTrue(ClusterCapacity.snapshotBudget(ClusterCapacity.newEngine().limits(), extended.outboxCapacity) < 256L * 1024 * 1024);
    }

    @Test void baselinePreparationRetainsRecordedCanonicalSnapshotHash() {
        MatchingEngine engine = ClusterCapacity.newEngine();
        for (Command command : RemoteCapacityExperiment.preparationCommands(RemoteCapacityExperiment.Profile.BASELINE, "capacity-fixed-v1"))
            assertTrue(engine.apply(command).result().accepted());
        engine.checkInvariants();
        assertEquals(167, engine.lastCommandSeq());
        assertEquals(267, engine.lastEventSeq());
        assertEquals("294d3cc2ff167b78b7045553e744ff5377a0bac636d7cd4ac90f6bd599d6ccbf",
                HexFormat.of().formatHex(ClusterStateSnapshot.digest(engine.snapshot())), "Baseline preparation must match already published cloud trials byte for byte");
    }

    @Test void ninetyThousandTradesAndUnackedOutboxRestoreWithinOneGiBHeap() throws Exception {
        String classpath = String.join(File.pathSeparator,
                Path.of(RemoteCapacityExperimentTest.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString(),
                Path.of(RemoteCapacityExperiment.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString(),
                Path.of(MatchingEngine.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        Path log = directory.resolve("extended-profile-1g-probe.log");
        Process child = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-Xmx1g", "-cp", classpath, ExtendedProfileProbe.class.getName()).redirectErrorStream(true).redirectOutput(log.toFile()).start();
        try {
            assertTrue(child.waitFor(120, TimeUnit.SECONDS), "1 GiB profile probe exceeded 120 seconds");
            String output = Files.readString(log, StandardCharsets.UTF_8);
            assertEquals(0, child.exitValue(), output);
            assertTrue(output.contains("EXTENDED_90K_1G_PASS"), output);
            System.out.print(output);
        } finally {
            if (child.isAlive()) { child.destroyForcibly(); child.waitFor(10, TimeUnit.SECONDS); }
        }
    }

    /** Executes outside measurement, in a separately bounded JVM matching the deployed member heap. */
    public static final class ExtendedProfileProbe {
        private static void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
        private static Execution apply(MatchingEngine engine, ReplicatedOutbox outbox, Command command) {
            require(outbox.hasCapacity(engine.maximumEventsFor(command)), "Outbox preflight exceeded profile capacity");
            Execution execution = engine.apply(command);
            require(execution.result().accepted(), "Business command rejected: " + execution.result());
            outbox.append(execution.events());
            return execution;
        }
        public static void main(String[] arguments) {
            long started = System.nanoTime();
            var profile = RemoteCapacityExperiment.Profile.EXTENDED_90K;
            MatchingEngine engine = ClusterCapacity.newEngine();
            ReplicatedOutbox outbox = new ReplicatedOutbox(profile.outboxCapacity);
            ClusterCapacity.validate(engine.limits(), outbox.capacity());
            for (Command command : RemoteCapacityExperiment.preparationCommands(profile, "capacity-fixed-v1")) apply(engine, outbox, command);
            require(engine.lastCommandSeq() == 167 && engine.lastEventSeq() == 267 && outbox.size() == 267, "Prepared state counters differ");
            String preparedHash = HexFormat.of().formatHex(ClusterStateSnapshot.digest(engine.snapshot()));
            int[] bought = new int[64];
            Command last = null;
            for (int index = 0; index < profile.maximumArrivals; index++) {
                RemoteCapacityExperiment.Sample sample = new RemoteCapacityExperiment.Sample(index, 64, "capacity-fixed-v1");
                Execution execution = apply(engine, outbox, sample.command);
                require(execution.result().tradeCount() == 1 && execution.result().remainingQuantity() == 0, "IOC did not fully trade one lot");
                require(execution.events().size() == 2, "IOC did not produce exactly acceptance and trade");
                bought[sample.worker]++;
                last = sample.command;
            }
            engine.checkInvariants();
            require(engine.lastCommandSeq() == 90_167 && engine.lastEventSeq() == 180_267 && engine.lastMarketSeq() == 180_201, "Final sequence counters differ");
            require(engine.retainedOrderCount() == 90_101 && engine.retainedOrderCount() < engine.limits().maxRetainedOrders(), "Retained order count/budget differs");
            require(outbox.size() == 180_267 && outbox.capacity() == 262_144 && outbox.exportedSeq() == 0, "Unacknowledged outbox differs");
            require(engine.order(1).orElseThrow().remainingQuantity() == 89_900, "Maker residual differs");
            require(engine.account(1_000_001).base().available() == 0 && engine.account(1_000_001).base().reserved() == 89_900
                    && engine.account(1_000_001).quote().available() == 901_000_000 && engine.account(1_000_001).quote().reserved() == 0, "Seller asset conservation differs");
            for (int worker = 0; worker < 64; worker++) {
                AccountView buyer = engine.account(1_000_100 + worker);
                require(buyer.base().available() == bought[worker] && buyer.base().reserved() == 0
                        && buyer.quote().available() == profile.buyerFunding - bought[worker] * 10_000L && buyer.quote().reserved() == 0, "Buyer asset conservation differs");
            }
            String expectedHash = engine.stateHash();
            byte[] bytes = ClusterStateSnapshot.encode(engine, outbox);
            require(bytes.length < SnapshotTransport.MAX_SNAPSHOT_BYTES, "Actual serialized checkpoint exceeds transport limit");
            var restored = ClusterStateSnapshot.decode(bytes);
            restored.engine().checkInvariants();
            require(restored.engine().stateHash().equals(expectedHash), "Restored core hash differs");
            require(Arrays.equals(engine.snapshot(), restored.engine().snapshot()), "Restored canonical core bytes differ");
            require(restored.outbox().capacity() == 262_144 && restored.outbox().size() == 180_267
                    && restored.outbox().lastEventSeq() == restored.engine().lastEventSeq() && restored.outbox().exportedSeq() == 0, "Restored outbox metadata differs");
            var first = restored.outbox().fetch(1, 16).events();
            var tail = restored.outbox().fetch(180_252, 16).events();
            require(first.size() == 16 && first.getFirst().eventSeq() == 1 && first.getLast().eventSeq() == 16, "Restored first outbox batch differs");
            require(tail.size() == 16 && tail.getFirst().eventSeq() == 180_252 && tail.getLast().eventSeq() == 180_267, "Restored final outbox batch differs");
            require(last != null, "Last measured command missing");
            Execution duplicate = restored.engine().apply(last);
            require(duplicate.replayed() && duplicate.events().isEmpty() && restored.engine().stateHash().equals(expectedHash), "Restored identical retry duplicated business state");
            require(restored.outbox().acknowledge(180_267) == 180_267 && restored.outbox().size() == 0, "Restored pending events could not be acknowledged contiguously");
            System.out.println("EXTENDED_90K_1G_PASS maxHeapBytes=" + Runtime.getRuntime().maxMemory()
                    + " measuredCommands=90000 measuredTrades=90000 retainedOrders=" + engine.retainedOrderCount()
                    + " pendingEvents=" + outbox.size() + " snapshotBytes=" + bytes.length
                    + " checkpointBudgetBytes=" + ClusterCapacity.snapshotBudget(engine.limits(), profile.outboxCapacity)
                    + " preparedSnapshotSha256=" + preparedHash + " stateHash=" + expectedHash
                    + " elapsedSeconds=" + (System.nanoTime() - started) / 1e9);
        }
    }
}
