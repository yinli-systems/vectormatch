# Core JMH measurement contract

These benchmarks execute the existing `MatchingEngine` in memory. They include
command dispatch, matching/result/event creation, storing each of 64 replies and
a returned sequence checksum. They exclude networks, journals, replication,
gateway queues, PostgreSQL, market delivery and client scheduling. They provide
neither end-to-end latency nor production capacity or real-time guarantees.
The historical `CoreBenchmark` and HTTP generator retain their original behavior.

## Reproducible defaults

The dedicated `jmh` source set uses published OpenJDK **JMH 1.37**, its annotation
processor, and the core project. It does not inherit the HTTP application's
Jackson/HdrHistogram dependencies. Defaults are:

| Setting | Fresh matching / lifecycle | Cached retries |
| --- | --- | --- |
| JDK | Repository Java **21** toolchain | Same |
| Forks / worker threads | **3 / 1** | **3 / 1** |
| Fork heap | **`-Xms2g -Xmx2g`** | Same |
| Mode | **SingleShotTime** | **Throughput** |
| Warmup | **5 iterations**, one 64-command batch each | **5 × 1 second** |
| Measurement | **10 iterations**, one 64-command batch each | **10 × 1 second** |
| Operations per invocation | **64** | **64** |
| State lifecycle | Recreate outside timing before every iteration | Prepare/cache once per trial |
| Score unit | Microseconds per command **within a batch mean** | Cached replies/second |

Five SingleShot warmup iterations are only 320 measured-path commands per fork.
This is an explicit finite warmup policy, **not evidence that all JIT/GC behavior
has reached steady state**. Evaluate warmup sensitivity separately before drawing
comparative conclusions. Fixture construction also exercises the core, but its
different operations cannot stand in for measured-path warmup.

Use the same exact JDK distribution and configuration in comparisons, and retain
`java -version`, commit, machine/CPU and cgroup limits, command, full console log,
distribution file hashes and result JSON. JMH JSON records its version, JVM/JDK,
JVM arguments, forks, threads, parameters and warmup/measurement settings. Direct
CPU runs must explicitly select the intended JDK 21 binary; a plain `java` on a
different PATH does not inherit Gradle's toolchain choice. Any overrides belong
to a separately disclosed configuration. CPU-host and historical GPU-Pod
observations remain separate cohorts.

## Workload and state lifecycle

`FreshMatchingBenchmark.matchBatch` varies **initial** ask price levels
`1 / 100 / 10000` and **resting orders traded per incoming command** `1 / 10 / 100`.
Each resting maker has quantity one. The fixture creates
`max(initialPriceLevels, 64 × tradesPerCommand)` makers, distributes them over
the declared prices, and then executes 64 distinct, fully funded IOC buys.
Each buy must match exactly the declared number of makers. That number is a
trade/order count; it is **not** necessarily the number of price levels crossed.

`FreshPlaceCancelBenchmark.lifecycleBatch` independently varies initial levels
and action `PLACE / CANCEL`. Places append real one-lot SELL GTC orders to
existing ask prices. Cancels target 64 distinct, owned, open maker orders spread
through the fixture; none is an invented or already cancelled ID. Both actions
must be accepted and produce zero trades. These cases do not include an unused
matching-sweep parameter.

Every fresh case starts with a new engine and prebuilt command/reply arrays in
`@Setup(Level.Iteration)`. Each producer's measured identities use distinct
sequences 1..64 in that engine. Setup funding/maker producers are separate.
SingleShot uses exactly one benchmark invocation per iteration (`batchSize=1`).
An explicit fixture guard refuses a second invocation on the same engine, so
an accidental batch-size override cannot silently measure cached repeats.

The initial book **changes during the 64-command batch**: matching consumes
makers, placements add them, cancellations remove them. This is not a steady
book-depth workload. The maximum fixture retains only 10064 orders against an
explicit 20000-order bound; there is no unbounded state growth or state-cap
rejection masquerading as throughput. Accounts/producers/result retention are
also explicitly bounded. The fixture has no exporter or state compactor.

Outside timing, teardown checks all 64 accepted fresh replies, contiguous new
business command sequences, exact trade counts, retained-order headroom, exact
buyer/seller balances, global base/quote conservation and core invariants.
The fixture unit tests cover every depth/sweep/action combination and prevent
reusing fresh state as a cache benchmark. This uses the existing implementation
and explicit expected outcomes, not an independent matching algorithm.

`DedupCacheBenchmark.replayBatch` is deliberately different. Setup executes and
validates 64 accepted placements once; timing repeatedly submits those original
identities and payloads. Teardown checks accepted replay flags, no new events,
unchanged command sequence and byte-identical canonical state. Its bounded cache
score must never be presented as fresh order-entry or trade throughput.

## Interpret statistics and allocation correctly

With the default fresh configuration, each measured iteration contributes one
64-command duration. `@OperationsPerInvocation(64)` normalizes that duration by
64. For one parameter combination, 3 forks × 10 measurement iterations therefore
yield **30 batch-mean observations**, not 1920 independent per-order timings.
Any percentiles in SingleShot output describe those normalized batch observations;
they are **not order p99/p99.9**. The reported error interval also does not make
these samples a sustained capacity guarantee. Tail latency for independently
scheduled requests comes from a separately scoped open-loop experiment.

Fixture setup/teardown are outside the benchmark timer, but can affect caches,
JIT, heap pressure and GC during measurement. If `-prof gc` is enabled,
`gc.alloc.rate.norm` includes fixture setup and verification allocations over
the iteration. Label it **allocation including the fixture per normalized
operation**, not pure `MatchingEngine.execute` B/op. Neither subtract setup
allocation estimates nor infer exact per-command GC pauses from these counters.

Iteration setup is deliberate: OpenJDK cautions about invocation-level timing
overhead for short benchmark calls. One SingleShot invocation per iteration
preserves fresh state without adding invocation-level timing around a potentially
sub-millisecond 64-command batch.

## Build a standalone CPU distribution

From the pinned source checkout, with the repository's JDK/Gradle configured:

```sh
./gradlew :bench:test :bench:jmhInstallDist
```

The output is `bench/build/install/core-jmh/lib/`: the benchmark JAR, core JAR,
JMH core and its complete transitive runtime dependencies. `jmhJar` verifies
nonempty generated `META-INF/BenchmarkList`, `META-INF/CompilerHints`, and
`jmh_generated` class entries. An ordinary classpath is sufficient; no fat JAR,
remote Gradle or custom runner is required. Copy the complete distribution,
preserving file hashes, to the authorized CPU host.

First list discovery results (this runs no benchmark):

```sh
/path/to/pinned-jdk21/bin/java -cp '/path/to/core-jmh/lib/*' org.openjdk.jmh.Main -l
```

One-case packaging/correctness smoke, **not a publishable benchmark**:

```sh
/path/to/pinned-jdk21/bin/java -cp '/path/to/core-jmh/lib/*' org.openjdk.jmh.Main \
  'io.vectormatch.bench.jmh.FreshMatchingBenchmark.matchBatch' \
  -p initialPriceLevels=100 -p tradesPerCommand=10 \
  -f 1 -wi 1 -i 1 -bs 1 -wbs 1 \
  -foe true -rf json -rff /new-evidence-directory/jmh-smoke.json
```

An explicitly authorized full run uses the annotation defaults:

```sh
/path/to/pinned-jdk21/bin/java -cp '/path/to/core-jmh/lib/*' org.openjdk.jmh.Main \
  'io.vectormatch.bench.jmh.*' \
  -foe true -rf json -rff /new-evidence-directory/core-jmh.json
```

That selects nine matching combinations, six place/cancel combinations and one
cached-retry case. Adding `-prof gc` produces the broader allocation scope above.
Choose a new output directory and never overwrite evidence; direct JMH CLI does
not enforce the repository's archival policy. `./gradlew :bench:jmh --args='…'`
is a convenience wrapper that selects JDK 21, requires fail-on-error and JSON, supplies a unique
default result path and refuses an existing `-rff` target. Without a filter it
runs the full matrix, so it is not a build-only task.

Acceptance requires actual fixture test results, the packaged resource checks,
three discovered benchmark methods, and one real forked smoke producing the
requested parameter/JDK/fork settings and no fixture failures. A source review,
unit-test pass or `-l` output alone does not establish performance. The default
matrix and warmup sensitivity runs require separate authorization and evidence.

## Primary implementation references

- [OpenJDK JMH 1.37 source and build](https://github.com/openjdk/jmh/tree/1.37).
- [Official annotation processor and core dependency](https://github.com/openjdk/jmh/blob/1.37/jmh-generator-annprocess/pom.xml).
- [Annotation processor class-output resources](https://github.com/openjdk/jmh/blob/1.37/jmh-generator-annprocess/src/main/java/org/openjdk/jmh/generators/annotations/APGeneratorDestinaton.java).
- [Gradle Java source sets and annotation processor configurations](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_source_sets).
- [JMH SingleShot mode caveats](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/annotations/Mode.java).
- [SingleShot operations normalization](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/results/SingleShotResult.java).
- [Fixture timing level cautions](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/annotations/Level.java#L46).
- [Profiler execution boundaries](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/runner/BenchmarkHandler.java#L307)
  and [GC allocation profiler](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/profile/GCProfiler.java#L92).
- [Standard JMH CLI main](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/Main.java)
  and [fork classpath construction](https://github.com/openjdk/jmh/blob/1.37/jmh-core/src/main/java/org/openjdk/jmh/runner/Runner.java#L731).
