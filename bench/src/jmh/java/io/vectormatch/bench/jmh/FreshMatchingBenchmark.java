package io.vectormatch.bench.jmh;

import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

/** Score is a normalized finite-batch mean, never an individual-command latency distribution. */
@BenchmarkMode(Mode.SingleShotTime)
@OutputTimeUnit(TimeUnit.MICROSECONDS)
@Fork(value = 3, jvmArgs = {"-Xms2g", "-Xmx2g"})
@Warmup(iterations = 5, batchSize = 1)
@Measurement(iterations = 10, batchSize = 1)
@Threads(1)
@State(Scope.Thread)
public class FreshMatchingBenchmark {
    @Param({"1", "100", "10000"}) public int initialPriceLevels;
    @Param({"1", "10", "100"}) public int tradesPerCommand;
    private CoreJmhFixture fixture;

    @Setup(Level.Iteration) public void prepare() {
        fixture = CoreJmhFixture.matching(initialPriceLevels, tradesPerCommand);
    }

    @Benchmark @OperationsPerInvocation(CoreJmhFixture.BATCH_SIZE)
    public long matchBatch() { return fixture.executeFreshBatch(); }

    @TearDown(Level.Iteration) public void verify() { fixture.verifyFresh(); }
}
