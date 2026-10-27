# VectorMatch

**Deterministic execution. Recoverable state. Measured performance.**

A private engineering project exploring a limit-order matching engine, replicated execution, and real-time market data. Every capacity claim must link to its workload, hardware, durability settings, and raw results.

[Source-only review checkout](docs/REVIEW_AND_REPRODUCE.md) · [Forced Linux correctness results](docs/PRODUCTION_CORRECTNESS_RESULTS.md) · [Writer timing results](docs/WRITER_TIMING_RESULTS_V3.md) · [Production acceptance gates](docs/PRODUCTION_ACCEPTANCE.md)

## Latest completed evidence · 27 October

- **Recording preallocation rejected by both ABAB pairs:** p99 rises from 10.86 → 22.57 ms and 11.83 → 53.76 ms at 100/s, with identical sync2/configuration and all 24,000 comparison originals correctly confirmed. Exact request attribution shows durable-replication waiting dominates; the option remains disabled and no candidate endurance run follows. [Full negative result, concrete slow request and original evidence](docs/RECORDING_PREALLOCATION_RESULTS.md).
- **Slow requests joined to exact log blocks and commit gates:** all 6,000 traced comparison originals have additive phase timings on an attested kernel clock. Durability/replication waiting accounts for 86.7%/67.3% of the slowest-original latency; file-force calls and associated recording waits dominate the stalled sample. Observer controls have mixed directions, so no negligible-overhead or performance-win claim follows. [Exact phase evidence and limits](docs/REPLICATED_STAGE_TRACE_RESULTS.md).

- **Communication-buffer placement ABAB closed:** moving only Aeron driver files to tmpfs produces p99 55.10/17.39 ms against overlay controls 37.85/43.67 ms, each at 100/s for 60 seconds. All 24,000 comparison orders confirm and final states agree, but paired directions differ, so the candidate is not promoted. Durable archives stay on the original storage with sync2. [Every arm, actual mapped devices and closure](docs/REPLICATED_BUFFER_LAYOUT_RESULTS.md).

- **Replicated path diagnosis and a second 30-minute window:** the empty service already has 74.9/75.1 ms p99; reducing replica park from 1 ms to 100 µs has inconsistent paired results. The selected baseline confirms all 180,000 originals at 100/s, with 202.1 ms p99 and failed latency/source-timing gates. Long file-force stalls remain when matching callbacks are short. This uses a different source fixture from the earlier endurance run and is not a performance improvement claim. [All controls, 30 minute windows and raw receipts](docs/REPLICATED_PATH_PROBE_RESULTS.md).

- **250K/s finite bottleneck fixed in repeated ABAB:** opt-in startup client-index sizing removes the ~80ms resize stall. Both five-second candidates accept all 1.25M mixed commands with zero not-sent/rejected/unknown; full-stream p99 is 2.372/0.386ms. Both lazy-sizing controls miss more than 11k originals. At 100K/s, p99 directions disagree, so no universal/default performance win is claimed. [All arms, exact stall location and raw receipts](docs/CLIENT_INDEX_SIZING_RESULTS.md).

- **Three-replica continuous endurance:** one 30-minute, 100/s same-host UDP run confirms all 180,000 originals and passes canonical replay plus cold-backup continuation. Full-stream p99 is 33.72ms; 107 source releases exceed 20ms, so the latency/timing acceptance gate fails. This is separate from high-rate core/TCP capacity. [Complete windows, telemetry and recovery](docs/REPLICATED_SUSTAINED_R3_RESULTS.md).

- **Independent arrival clock + collector ABAB:** at 100k/s, the same-host TCP path accepts every original in both collector pairs; business Generational ZGC reduces full-stream p99 from 15.06/30.13ms to 0.30/1.98ms. At 250k/s, missing arrivals remain and global accepted p99 is undefined. Exact worker originals identify client-index expansion as the next tested hypothesis. These five-second results exclude journal/replication. [All 16 arms and failure accounting](docs/PROCESS_ISOLATION_RESULTS.md).

- **Mixed-flow same-host comparison:** all 16 five-second VectorMatch/exchange-core arms complete independent financial replay. VectorMatch passes both finite gates at 50k/s (global API-result p99 1.24–2.07ms), one at 100k/s, and neither at 250k/s. The explicit exchange-core Java 21 compatibility cohort passes its eight finite gates. Native callback settlement positions differ; no sustained, replicated or equivalent-settlement ranking follows. [Complete counts, tails, curves and reproduction](docs/COMMON_ENGINE_COMPARISON_RESULTS.md).
- **100,000,000 accepted orders in one business lineage:** 99,999,999 settled synthetic trades, exact cash/inventory reconciliation, complete raw replay and verified private archives. State continues across 22 explicit cold restarts; this is an in-process continuity result, not uninterrupted replicated uptime. [Counters, timings and boundaries](docs/ANCHORED_CONTINUITY_RESULTS_V4.md).
- **Full 7k/8k PAUSE/CONTINUE ABAB:** all eight raw/replay/three-node cold-restore checks pass; all eight capacity gates fail. Asynchronous maintenance improves window goodput by 7.6–10.8%, but 260,619 of 1,200,000 planned arrivals are not sent. Global accepted-arrival p99 is undefined. [Complete overload results](docs/OVERLOAD_RESULTS_V4.md).
- **Independent managed-VM recovery:** three replicas use distinct provider fault domains. Full state is recovered onto replacement VMs/disks; an original retry and a fresh trade reconcile exactly. The 30-minute cross-region load run fails scheduler validity, and no physical media/power-loss claim is made. [Long-run result](docs/PHYSICAL_SOAK_RESULTS_20261027.md) · [Replacement recovery and snapshot-transfer ABAB](docs/SNAPSHOT_RECOVERY_RESULTS_20261027.md).

Uninterrupted high-rate replicated V4 endurance and the production latency target remain open. The earlier replicated overload source is available as a verified 1.80MB [source-only bundle](docs/REVIEW_AND_REPRODUCE.md), independently compiled to that candidate's class bodies; the new common-flow comparison records its own source and artifact hashes. Complete raw experiments remain private attachments rather than new bulk Git blobs.

## Delivery principles

- Price-time priority, integer accounting, explicit reservation and settlement.
- A deterministic state machine owns balances, orders, deduplication, and events.
- A timeout is an unknown outcome, not permission to place a second order.
- Local execution, replicated execution, and market delivery are measured separately.
- Performance improvements must pass the same correctness checks as the baseline.

## Implementation status

Executable deterministic matching, a local journaled workbench, a three-process Aeron Cluster backend, replicated bounded outbox, and transactional PostgreSQL event export. The React console shows actual order books, commands, replica checks, cached projection observations, and recorded benchmark evidence. See [the implementation contract](docs/IMPLEMENTATION.md).

The bounded [asynchronous maintenance V4](docs/ASYNC_MAINTENANCE_V4.md) is available as an opt-in coordinator. It admits business during independent file work,retains bounded command/event/byte credits,and records original control identity before destructive ACK. Its [actual Linux UDP results](docs/ASYNC_MAINTENANCE_V4_RESULTS.md) establish finite correctness. The [registered capacity comparison](docs/ASYNC_CAPACITY_RESULTS_V4.md) now includes two PAUSE/CONTINUE pairs at 500 arrivals/s.

The old-artifact 1,000/s CONTINUE measurement remains excluded for its 1,535-command first cut. The [exact-cut correction](docs/CAPACITY_CUT_GATE_CORRECTION_V4.md) now has a successful full Linux regression:442 Java and197 Python tests,including11 PostgreSQL integration tests,zero failure/error/skip. CI17's procfs-reader regression and CI18's disk refusals remain archived. The [fresh exact-cut capacity campaign](docs/EXACT_CUT_CAPACITY_RESULTS_V4.md) uses its own qualified artifact and cohorts;earlier latency results do not transfer.

<!-- exact-cut-v4-status:start -->

Completed coarse curve: all four finite gates pass through **4,000/s**, and all four fail at **6,000/s**. The interval between them and long-run capacity remain unmeasured. [Curve, raw references and failure semantics](docs/EXACT_CUT_CAPACITY_RESULTS_V4.md).

Latest exact-cut comparison:6000 scheduled arrivals/s,artifact `65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69`,source `0c8303b2`.

C1:113280/120000 accepted,p99 undefined,goodput 5299.05/s; D1:120000/120000 accepted,p99 796.814ms,goodput 5779.9/s; C2:113105/120000 accepted,p99 undefined,goodput 5281.2/s; D2:120000/120000 accepted,p99 690.515ms,goodput 5803.5/s.

All four finite gates passed:False. Both preregistered pair directions passed:False. Both candidates meet10ms p99:False. These are two pairs of20-second fresh lineages on one physical host;no long-run SLA or default performance promotion. [Exact values and complete private raw references](docs/EXACT_CUT_CAPACITY_RESULTS_V4.md).

<!-- exact-cut-v4-status:end -->

The [V4 owner-poll A/B/A/B](docs/OWNER_POLL_RESULTS_V4.md) lowers global p99 in both100us candidates but worsens post-offer p99 in both. All four finite gates pass;the full optimization criterion fails and defaults are unchanged.

<!-- v4-latency-factors:start -->

Latest [single-factor read-bank comparison](docs/INTERBANK_DISPATCH_RESULTS_V4.md),artifact `dcfeeb81`: C1: 60.758ms global p99 / 12.599ms post-offer / 3993.45/s; C2: 67.470ms global p99 / 12.423ms post-offer / 3993.45/s; D1: 42.061ms global p99 / 13.100ms post-offer / 3993.9/s; D2: 47.816ms global p99 / 13.367ms post-offer / 3994.95/s. Both registered pair directions pass: False. Both candidates meet10ms global p99: False. Two20-second pairs;no default promotion or sustained SLA.

<!-- v4-latency-factors:end -->

The earlier read-bank and agent-idle experiments use [CI21-qualified source and actual artifact dcfeeb81](evidence/2026-10-26/runpod-cpu/v4-latency-r1/linux-admission-r1/README.md). The500/s native qualification confirms10000 unique trades,32 audited bounded read-yield turns and all three cold restores. Both subsequent factor comparisons retain post-offer regressions and fail the full registered optimization criterion;defaults are unchanged.

## Verified evidence

The [new synthetic trading simulation](docs/TRADING_SIMULATION_RESULTS.md) checks
FIFO/partial fills,settlement,reservations,cancellation,rejections and retries on
the real core and three-replica path. A1280000-attempt core cache comparison fails
its paired promotion gate;the default is retained. A separate instrumented
replicated polling comparison improves RPC P99 from11.11/17.42ms to6.87/7.94ms
in two8000-attempt pairs,with identical business state and no unknowns. This is
same-host,single-inflight,finite evidence;not a capacity or sustained SLA claim.

The [two new30-minute baselines](docs/SUSTAINED_BASELINE_RESULTS.md) each confirm
180000/180000 synthetic orders at100/s on the same CPU container and unchanged
replica/client artifacts. P99 is24.892/11.130ms; both registered combined gates
fail because37/3 scheduler delays exceed20ms. Full CSV/checkpoint/JFR audits and
empty-directory backup restore with a cached retry and fresh trade are archived.
The restore controller lost its final stdout line, so no recovery RTO is claimed.
These are separate bounded lineages, not sustained high-rate or physical-host proof.
The [new multi-market escrow core](docs/MARKET_ESCROW_PROTOCOL.md) has15 local
functional tests; it is not connected to distributed market groups yet.

The [native private-UDP cross-Pod round](docs/PRIVATE_CROSS_NODE_RESULTS.md) uses
three real replica Pods and an independent fourth-Pod generator. It retains 490,000
planned synthetic requests and actual leader-fault/cold-recovery continuation.
4,000/s passes both finite 100ms-p99 gates; 8,000/s has inconsistent tails. The
single-factor idle comparison does not pass its paired promotion criterion. All
new instances are stopped; estimated incremental cost is $2.062 of the $3 cap.

The [CPU Pod UDP/storage diagnosis](docs/CPU_UDP_PATH_RESULTS.md) adds bounded
per-packet server receipts and independently attributes 29 incomplete UDP round
trips to 17 missing server receipts and 12 missing client replies. The preceding
policy comparison fails its zero-loss gate; its packet rates are not trading
throughput. Eleven targeted tests pass on Linux; original data is privately archived.

| Path | Actual evidence | Limit |
| --- | --- | --- |
| Linux correctness |556 Java tests and209 Python tests;zero failure/error/skip;11 real PostgreSQL tests included |Source `97db58e2`;CI28 on the existing one-job CPU runner;hosted billing still blocked |
| V4 replicated execution |1003 commands,1000 unique trades,2003 events;three exact archive cuts;128 extra confirmations during a held original file |Three JVMs sharing one CPU host;functional fixture |
| Earlier V4 snapshot/cold restore |All three snapshots and all three restarted services match the complete state hash |Earlier same-host V4 fixture; no new orders/client continuation in that fixture |
| Original-artifact V4 paired capacity at500/s |Four 20-second arms each confirm all 10,000 trades; p99 PAUSE 286.78/175.01 ms vs CONTINUE 65.65/59.93 ms |Both registered direction checks pass; 10 ms target remains unmet; separate fresh lineages |
| Previous V3 maintained capacity |6000/s and7000/s accept all planned arrivals;p99208.34/317.32ms in finite20s observations |7500/s loses74531/150000 arrivals;global accepted-arrival p99 is undefined;escalation stops |

The earlier V4 held-file fixture has no measured throughput or p99. The original finite comparison uses one qualified artifact (`2ea38974`), fixed leader/configuration, 127 active load producers and a 1536-command cut. Both pairs improve global p99 without worse post-offer p99 or lower in-window goodput; this is a bounded observation, with no default performance promotion or long-run latency guarantee. The [V3 capacity curve](docs/VERIFIED_HANDOFF_CAPACITY_RESULTS_V3.md), [negative immutable-batch encoding comparison](docs/BATCH_WIRE_VALIDATION_RESULTS_V3.md), [writer timing/handoff comparisons](docs/VERIFIED_ARCHIVE_HANDOFF_EXIT_WAIT_RESULTS_V3.md) and [client JFR diagnostic](docs/CLIENT_JFR_DIAGNOSTIC_RESULTS_V3.md) remain separate. Full raw attachments are retained in the same private repository with SHA-256, member inventories and authenticated download verification. The console contains 135 runs and 50 capacity cohorts;all79 runs and34 cohorts present before the exact-cut campaign retain their original records. New exact-cut curves have separate configuration fingerprints.

This remains a trading-systems research prototype. The [production acceptance gates](docs/PRODUCTION_ACCEPTANCE.md) still require uninterrupted replicated endurance, sustained latency/capacity, broader fault injection, production authentication/risk controls and external venue/account qualification. The completed in-process 100M lineage and managed-VM recovery above close narrower, explicitly separate evidence scopes. No hard realtime, millisecond SLA, HFT endorsement or funded external trading readiness is claimed. [Continuous endurance](docs/CONTINUOUS_ENDURANCE_PLAN.md) requires persistent journal anchors and producer/frontier recovery, not repeated reset fixtures.

[Original application CPU recovery](docs/CPU_RESTORATION_PLAN.md) is separate from these fresh retention experiments. Its archived4609-command/6214-event state and PG ledger passed full offline reconciliation;the original application's current-container cold restart and HTTP/WS recovery remain pending. The [passive startup mode](docs/PASSIVE_GATEWAY_RESTORATION.md) disables bootstrap/flow for that recovery.

## Toolchain

Java 21, Gradle, Aeron, Netty, React and TypeScript. The bootstrap pins Temurin 21.0.13+9, Node 24.22.1 and Gradle 8.14.3 and verifies vendor SHA-256 files. Portable development tools live under `.tools/` and are never committed.

```bash
python3 scripts/bootstrap.py
source scripts/env.sh
./gradlew check
cd web && npm ci && npm run build && cd ..
bash scripts/run-workbench.sh
```

Open <http://127.0.0.1:8000>. The workbench binds only to loopback. It starts a synthetic market flow using the real engine, and labels its execution mode `LOCAL_JOURNALED`. Its WebSocket feed sends complete snapshots at 5 Hz; it does not claim reliable individual-event delivery.

The console supports order placement and cancellation, actual browser command RTT samples, server service time, flow controls, and replay verification. Its Evidence section reads the repository's recorded results; it does not turn live demo activity into a capacity claim.

## Replicated workbench and database

```sh
python3 scripts/bootstrap-postgres.py
export VM_CLUSTER_ID='local-cluster-generation-1'
bash scripts/run-replicated.sh
```

Open <http://127.0.0.1:8001>. This runs the gateway and projector in the foreground and preserves the cluster and PostgreSQL processes/data after exit. The default cluster profile requests Archive/catalog/consensus sync level 2. Use a stable, unique lineage ID for each cluster/database pair; never reuse an ID after resetting either side. A second stack launcher is refused before creating Aeron driver directories. Read [deployment and durability](deploy/README.md), [projection recovery](projector/README.md), and [checkpoint capacity](cluster/CAPACITY.md) before changing an existing runtime.

The gateway's order/account reads are a checked in-memory mirror of the replicated core. PostgreSQL currently stores an event ledger, counters, cursor and sanitized market view; it is not a complete order-query service. Its observer performs database I/O on a separate thread, and reports cached/stale/unavailable status explicitly.

The gateway polls core sequence positions once per second and refreshes its mirror when another client changes the core. A transport/session failure enters `BACKEND_RECOVERY_REQUIRED`: restart the gateway to reconnect and reload a snapshot, then reconcile an unknown request using its original producer ID, sequence and payload. Core leader failover does not imply uninterrupted gateway availability in this first release.

```sh
python3 scripts/verify-replicated-workbench.py
export VM_TEST_PG_URL='jdbc:postgresql://127.0.0.1:55432/postgres?user=vectormatch'
./gradlew check :cluster:failoverSmoke
```

The functional verification pauses synthetic flow and leaves it paused. Test JDBC settings must be provided for the real PostgreSQL suite; otherwise those tests are reported as skipped.

## First performance baseline

```bash
./gradlew :bench:installDist
bench/build/install/bench/bin/bench 20000 3 reports/local/core-20k
```

This measures a fixed-rate **in-process memory-only** path, including scheduling delay in its main latency histogram. It excludes network, persistence, and replication. Raw baseline artifacts are in `evidence/`; see [measurement boundaries](docs/BENCHMARKS.md).

The repository also includes a bounded [HTTP arrival-rate generator](bench/HTTP_LOAD.md), [replicated concurrency experiment](cluster/BENCHMARKS.md), and [USD 20 cloud campaign](docs/CLOUD_TESTING.md). Recorded smoke results are evidence for further investigation, not production latency or throughput guarantees.


[Instrumented counter diagnosis](docs/V4_COUNTER_DIAGNOSTIC_RESULTS.md) records durable-write timing, zero observed retransmit increments and actual batch sizes on artifact `dcfeeb81`. It remains separate from uninstrumented comparisons; the next coalescing experiment has no performance result yet.

Latest [bounded coalescing comparison](docs/BATCH_COALESCING_RESULTS_V4.md) uses CI22-qualified artifact `fb1068dd`. Both finite pair criteria pass: False;both candidates meet10ms globalp99: False. Full raw,parameter binding and cold recovery are retained. Defaults remain unchanged.

Latest [owned-node JFR diagnostic](docs/V4_OWNED_JFR_RESULTS.md) accepted all80000 planned orders at4000/s,with3993.45/s in-window goodput,67.905817ms all-arrival p99 and12.692245ms post-positive-offer p99. Instrumented archive-conductor force calls account for15.96–16.34s per node inside the20s window. This prioritizes a storage-path experiment;it is not an optimization promotion or physical persistence certificate. All prior curves remain separate.

The [standalone file-materialization A/B/A/B](docs/V4_FORCE_MATERIALIZATION_RESULTS.md) lowers force p99 by11.8–21.2% in all six matched writer comparisons. All36000 samples are retained. This screens a candidate for native testing;no trading-capacity or latency improvement is claimed.

Latest [native first-segment preparation comparison](docs/V4_SEGMENT_PREPARATION_RESULTS.md) uses exact CI24-qualified artifact `a33240fa`. Both registered finite pair criteria pass: False;both candidates meet10ms globalp99: False. Complete order/recovery evidence remains private and reproducible;default mode remains unchanged.

Latest [sealed historical-read route comparison](docs/V4_SEALED_READ_EXPORT_RESULTS.md) uses the exact CI27-qualified artifact `0a6b1c8b`. Both registered paired criteria pass: False. These are separate20-second synthetic workloads;default path and sustained production targets remain separate. Complete original frames and order/recovery evidence remain private and reproducible.

Latest [sealed bounded-dispatch comparison](docs/V4_SEALED_BOUNDED_DISPATCH_RESULTS.md) uses exact CI28-qualified artifact `a21a720d`. Both registered pair criteria pass: False. These are separate20-second synthetic workloads;default CLOSED and sustained production gates remain separate.
