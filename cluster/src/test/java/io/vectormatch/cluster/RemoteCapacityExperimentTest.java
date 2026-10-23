package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
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
}
