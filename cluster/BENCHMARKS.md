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

The small sample size and short duration make this a functional performance baseline. It is unsuitable for estimating extreme tails, saturation capacity, sustained production throughput, or behavior under independently scheduled arrivals. It intentionally does not subtract pauses or hide resend delay. The later remote open-loop campaign below records separate evidence; these historical smoke measurements have not been relabelled.

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

## Remote open-loop capacity campaign

The [protocol](../docs/CAPACITY_CAMPAIGN.md) and [results](../docs/CAPACITY_RESULTS.md) retain fixed-configuration cohorts, all scheduled arrivals, client admission losses and unknown outcomes. Each trial uses fresh state and a fixed leader. Node and load-generator revisions, release hashes, actual launch arguments and the prepared-state hash are recorded separately.

Build `:cluster:installDist` from the pinned revision and launch the three members as described in [REMOTE.md](../deploy/REMOTE.md#isolated-fixed-leader-capacity-tests). On the load host, export the same `VECTOR_CLUSTER_HOSTS` and `VECTOR_AERON_MTU_LENGTH`, and set `VECTOR_CLIENT_EGRESS_HOST` to that host's reachable private address. The long-window cohort requires the explicit `capacity-190k-v1` node profile, outbox 524288, 2 GiB node heaps, session limit 128 and appointed leader 0 on all members. Then use a new evidence directory:

```sh
java --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED \
  --add-opens=java.base/java.util.zip=ALL-UNNAMED -Xmx2g \
  -cp '/opt/vectormatch/releases/PINNED_REVISION/dist/cluster/lib/*' \
  io.vectormatch.cluster.RemoteCapacityExperiment \
  /opt/vectormatch/evidence/UNIQUE_TRIAL 23000 13000 190000 128 64 2000 30000 0 20 extended-190k-128
```

The arguments after the evidence directory are port base, target arrivals/s, arrival count, workers, queue capacity per worker, request timeout ms, maximum drain ms, expected leader ID, scheduler lateness limit ms and load fixture. This example offers 190,000 commands over 14.615 seconds; it is not a long-duration soak test. Keep client egress port allocation ephemeral when starting many drivers. Setup, session cleanup and final reference replay occur outside the measurement window.

The Java harness writes arrivals/backlog CSV, canonical snapshots, configuration and result JSON. The campaign additionally collects official pre/post membership, read-only CnC counters, 1 Hz process/cgroup/network telemetry and process identity receipts. Export all of them before analysis; a Java result alone is insufficient for the independent fixed-leader/configuration checks. Recompute an archived cohort without cloud access:

```sh
python3 -B scripts/verify-capacity-config.py evidence/2026-10-23/runpod-capacity-long
python3 -B scripts/analyze-capacity.py \
  --runs-dir evidence/2026-10-23/runpod-capacity-long/runs \
  --output-dir /tmp/vectormatch-capacity-recomputed --plot
```

`--plot` uses Matplotlib if already installed. Stable-window classification requires at least ten seconds and the declared loss, backlog, drain, scheduler and correctness checks; it has no invented p99 SLA. Terminal orders remain retained, so these fresh-state finite windows do not establish indefinite write capacity. Keep older node/heap/seed cohorts separate.
