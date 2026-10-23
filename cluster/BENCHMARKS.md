# Replicated matching benchmark smoke

```sh
./gradlew :cluster:replicatedBenchmark
```

This task starts three new local JVM processes on loopback ports `27001..27205`, with a separate Archive and Cluster state directory for every member. Archive data, Archive catalog, and ConsensusModule metadata synchronization are all explicitly configured to level 2. It cleans up the processes it owns and retains evidence under `cluster/build/replicated-benchmark/run-<timestamp>/`.

The workload uses one client and **one outstanding request at a time**. It is a **closed-loop smoke benchmark**, not an open-loop capacity test. All cluster processes, the load generator, reference checker, and Gradle run on the same host. No multi-machine, power-loss, or production capacity claim follows from this measurement.

After funding two accounts, it warms up with 300 effective commands. The measured trace contains 1,002 accepted commands: 334 cycles of a resting sell order, an incoming buy that actually trades four base lots, and a successful cancellation of the remaining sell quantity. Every cycle creates exactly one trade. There are no deliberately invalid orders or cheap failed cancellations in the measured workload.

For every command, the harness checks the exact result and all command/event/market sequences against a local deterministic reference engine. After measurement it checks core invariants, downloads the canonical core snapshot in digest-verified chunks, checks its invariants, and compares its state hash against both the reference and the live Cluster service. Pending outbox sequence metadata is also checked.

`result.json` discloses:

- Confirmed accepted logical commands per second. The denominator is the complete measured closed-loop trace, including reference validation and in-memory sample recording.
- Client call RTT, including encoding, transport, replication/commit, business processing, response decoding, and any internal resend. Local reference processing occurs outside each RTT interval.
- Exact nearest-rank p50, p95, p99, p99.9, min and max over all 1,002 samples.
- Transport-accepted attempts and accepted resends, unsuccessful transport offers, request timeouts/unknowns, unresolved commands, actual trades and executed quantity.
- JVM/OS/architecture, processor count, state sequences, hash, and synchronization configuration.

`samples.csv` retains every measured RTT, command type, trade count, and returned replay flag. Node logs retain launch and Cluster diagnostics. The task fails on an unresolved timeout, rejection, state discrepancy, invariant failure, unexpected trade count, or inconsistent snapshot. A failed task is not a successful benchmark result.

The small sample size and short duration make this a functional performance baseline. It is unsuitable for estimating extreme tails, saturation capacity, sustained production throughput, or behavior under independently scheduled arrivals. It intentionally does not subtract pauses or hide resend delay. An open-loop multi-client benchmark, repeated steady-state runs, independent hosts, load curves, and production idle-strategy/CPU/storage tuning remain separate work.

The initial development implementation uses shared driver/archive threads, backoff idle strategies, small terms, a low-volume single-inflight client, and safe file synchronization. Preserve these settings when reproducing its baseline; compare alternative settings as separately disclosed experiments.

## Paired concurrency experiment

```sh
./gradlew :cluster:replicatedConcurrencyComparison
```

This runs the same new harness first with one client and then with four clients. Each configuration has 300 warmup commands and 1,008 measured effective commands, sync level 2 on all three members, fresh isolated state, and unchanged node idle/heartbeat defaults. Each client owns its `ClusterClient`, producer, buyer account and seller account on one thread. Each has one business request outstanding: this remains a **multi-client closed-loop** experiment.

Reference validation occurs after the measured interval in both configurations. The harness sorts all confirmed funding, warmup and measured commands by the server's original result command sequence, replays them through an independent engine instance, checks every result, and compares the live state and downloaded snapshot hashes. Every measured cycle has one real trade and a successful residual cancellation. Clients share one market, so their buyers can fill another client's maker; large maker quantities preserve valid cancellation while the reference validates the actual interleaving.

Each run records aggregate and per-client throughput/RTT, all resends and unknowns, replayed replies, invariant checks and raw `trace.csv`. It samples Aeron's official Archive total recording write-byte/write-time counters for every member before and after the measured trace. These counters include recorder force time under sync level 2. Their deltas provide measured storage-work context; the exposed counters do **not** count force calls or reveal exact commands per batch. The lifetime maximum write-time counter is explicitly labelled as lifetime rather than measured-only.

The top-level `comparison.json` reports the observed concurrency throughput ratio and storage-time-per-command change. Those observations cannot isolate batching from scheduling, transport or storage effects. One short run per configuration on a shared host does not establish statistical significance or production capacity. The original single-client benchmark remains unchanged as an earlier baseline, and is not substituted for the fair paired one-client control.

## Later protocol extension

The additive `POSITION` operation and `ClusterClient.position(Duration)` were introduced **after** the archived runs `replicated-benchmark/run-1792771468145` and `replicated-concurrency/run-1792772681750`. Those saved results were not rerun or relabelled after this extension. `position()` returns only command/event/market counters with an empty state hash; it does not serialize or hash the core. Full `state()` behavior remains unchanged. An idle mirror can poll these counters and download a snapshot only when they change. The original measured benchmark traffic did not include the new position operation.

Startup directory handling was subsequently hardened to `dirDeleteOnStart(false)` for both clients and nodes. [Aeron 1.53.3 checks the existing driver's heartbeat before deleting/recreating its directory](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-driver/src/main/java/io/aeron/driver/MediaDriver.java#L479). An active driver causes `ActiveDriverException`; a confirmed stale directory is recreated. Graceful shutdown marks the heartbeat inactive; after a hard crash, liveness detection can require the configured driver timeout. This uses Aeron's existing mechanism and does not claim an atomic lock for simultaneous first-ever startup. The change postdates the archived timings and those results have not been relabelled or rerun.
