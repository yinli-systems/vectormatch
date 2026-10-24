package io.vectormatch.bench.jmh;

import org.openjdk.jmh.annotations.*;
import java.util.concurrent.TimeUnit;

/** Intentional bounded cached retries, separate from all fresh matching/placement scores. */
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Fork(value = 3, jvmArgs = {"-Xms2g", "-Xmx2g"})
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 10, time = 1, timeUnit = TimeUnit.SECONDS)
@Threads(1)
@State(Scope.Thread)
public class DedupCacheBenchmark {
    private CoreJmhFixture fixture;

    @Setup(Level.Trial) public void prepare() { fixture = CoreJmhFixture.cachedReplay(); }

    @Benchmark @OperationsPerInvocation(CoreJmhFixture.BATCH_SIZE)
    public long replayBatch() { return fixture.executeReplayBatch(); }

    @TearDown(Level.Iteration) public void verify() { fixture.verifyReplay(); }
}
