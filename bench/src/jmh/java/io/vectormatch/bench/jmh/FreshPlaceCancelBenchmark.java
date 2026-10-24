package io.vectormatch.bench.jmh;

import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

/** Fresh accepted place/cancel commands; unrelated matching sweep parameters are absent. */
@BenchmarkMode(Mode.SingleShotTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Fork(value = 3, jvmArgs = {"-Xms2g", "-Xmx2g"})
@Warmup(iterations = 5, batchSize = 1)
@Measurement(iterations = 10, batchSize = 1)
@Threads(1)
@State(Scope.Thread)
public class FreshPlaceCancelBenchmark {
    @Param({"1", "100", "10000"}) public int initialPriceLevels;
    @Param({"PLACE", "CANCEL"}) public CoreJmhFixture.Action action;
    private CoreJmhFixture fixture;

    @Setup(Level.Iteration) public void prepare() {
        fixture = CoreJmhFixture.lifecycle(initialPriceLevels, action);
    }

    @Benchmark @OperationsPerInvocation(CoreJmhFixture.BATCH_SIZE)
    public long lifecycleBatch() { return fixture.executeFreshBatch(); }

    @TearDown(Level.Iteration) public void verify() { fixture.verifyFresh(); }
}
