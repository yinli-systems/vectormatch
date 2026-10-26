package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

class CapacityWorkerWaitPolicyTest {
    @TempDir Path directory;
    @Test void defaultIsUnchangedAndIndependentOwnerIsRequired() {
        assertEquals(CapacityWorkerWaitPolicy.POLL, CapacityWorkerWaitPolicy.select(null, "direct"));
        assertEquals(CapacityWorkerWaitPolicy.NOTIFY, CapacityWorkerWaitPolicy.select("notify", "multiplexed"));
        assertThrows(IllegalArgumentException.class, () -> CapacityWorkerWaitPolicy.select("notify", "direct"));
        assertThrows(IllegalArgumentException.class, () -> CapacityWorkerWaitPolicy.select("typo", "multiplexed"));
    }
    @Test void waitingQueuePreservesFifoAndIsInterruptible() throws Exception {
        var queue = new ArrayBlockingQueue<Integer>(2);
        queue.add(1); queue.add(2);
        assertEquals(1, CapacityWorkerWaitPolicy.NOTIFY.poll(queue));
        assertEquals(2, CapacityWorkerWaitPolicy.NOTIFY.poll(queue));
        var started = new CountDownLatch(1);
        var interrupted = new CompletableFuture<Boolean>();
        var thread = new Thread(() -> { started.countDown(); try {
            while (true) CapacityWorkerWaitPolicy.NOTIFY.poll(queue);
        } catch (InterruptedException expected) { interrupted.complete(true); } });
        thread.start();
        try { assertTrue(started.await(1, TimeUnit.SECONDS)); thread.interrupt(); assertTrue(interrupted.get(1, TimeUnit.SECONDS)); }
        finally { thread.interrupt(); thread.join(1000); }
        assertFalse(thread.isAlive());
    }
    private RemoteCapacityExperiment.LoadResult run(boolean unresolved) throws Exception {
        String previous = System.getProperty(CapacityWorkerWaitPolicy.PROPERTY);
        System.setProperty(CapacityWorkerWaitPolicy.PROPERTY, "notify");
        try {
            var samples = new RemoteCapacityExperiment.Sample[8];
            for (int i = 0; i < samples.length; i++) samples[i] = new RemoteCapacityExperiment.Sample(i, 1, "fixture");
            var seen = new ArrayList<Command>();
            var options = new RemoteCapacityExperiment.Options(directory, 19000, 100, 8, 1, 16, 10, 200, 0, 1000);
            var result = RemoteCapacityExperiment.runLoad(options, samples, new RemoteCapacityExperiment.TransportFactory() {
                public String transportMode() { return "multiplexed"; }
                public RemoteCapacityExperiment.Transport open(int worker) { return new RemoteCapacityExperiment.Transport() {
                    public CommandCodec.Reply execute(Command command, Duration timeout) {
                        seen.add(command);
                        if (unresolved || seen.size() == 1) throw new IllegalStateException("synthetic unknown");
                        long seq = command.requestSeq();
                        return new CommandCodec.Reply(1, new Result(ResultCode.ACCEPTED, "", seq, seq, 0, 1), seq == 1,
                                seq, seq * 2, seq * 2, "", "");
                    }
                    public int leader() { return 0; }
                    public void idle() {}
                    public ClusterClient.TransportCounters counters() { return new ClusterClient.TransportCounters(0, 0, 0, 0); }
                    public void close() {}
                }; }
            });
            assertEquals(CapacityWorkerWaitPolicy.NOTIFY, result.workerWaitPolicy);
            assertEquals("notify", RemoteCapacityExperiment.summarize(result).get("clientWorkerWaitPolicy"));
            assertEquals(seen.get(0), seen.get(1), "unknown retries preserve the exact original command");
            if (unresolved) assertTrue(seen.stream().allMatch(c -> c.equals(seen.getFirst())));
            return result;
        } finally {
            if (previous == null) System.clearProperty(CapacityWorkerWaitPolicy.PROPERTY); else System.setProperty(CapacityWorkerWaitPolicy.PROPERTY, previous);
        }
    }
    @Test void resolvedUnknownRetainsOriginalTimeoutAndAllOriginals() throws Exception {
        var result = run(false);
        assertEquals(8, result.completed.get()); assertEquals(0, result.dropped.get());
        assertEquals(1, result.initialUnknown.get()); assertEquals(0, result.unresolved.get());
        assertEquals(2, result.samples[0].attempts);
        assertTrue(Arrays.stream(result.samples).allMatch(s -> s.outcome.equals("CONFIRMED_ACCEPTED")));
    }
    @Test void unresolvedOriginalPreventsIssuingHigherSequences() throws Exception {
        var result = run(true);
        assertEquals(1, result.unresolved.get()); assertEquals(7, result.dropped.get());
        assertTrue(Arrays.stream(result.samples).skip(1).allMatch(s -> s.outcome.equals("WORKER_BLOCKED_UNKNOWN_NOT_SENT") && s.started == 0));
    }
}
