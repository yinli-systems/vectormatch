# VectorMatch

**Deterministic execution. Recoverable state. Measured performance.**

A private engineering project exploring a limit-order matching engine, replicated execution, and real-time market data. Every capacity claim must link to its workload, hardware, durability settings, and raw results.

[Source-only review checkout](docs/REVIEW_AND_REPRODUCE.md) · [Forced Linux correctness results](docs/PRODUCTION_CORRECTNESS_RESULTS.md) · [Writer timing results](docs/WRITER_TIMING_RESULTS_V3.md) · [Production acceptance gates](docs/PRODUCTION_ACCEPTANCE.md)

## Delivery principles

- Price-time priority, integer accounting, explicit reservation and settlement.
- A deterministic state machine owns balances, orders, deduplication, and events.
- A timeout is an unknown outcome, not permission to place a second order.
- Local execution, replicated execution, and market delivery are measured separately.
- Performance improvements must pass the same correctness checks as the baseline.

## Implementation status

Executable deterministic matching, a local journaled workbench, a three-process Aeron Cluster backend, replicated bounded outbox, and transactional PostgreSQL event export. The React console shows actual order books, commands, replica checks, cached projection observations, and recorded benchmark evidence. See [the implementation contract](docs/IMPLEMENTATION.md).

The bounded [asynchronous maintenance V4](docs/ASYNC_MAINTENANCE_V4.md) is available as an opt-in coordinator. It admits business during independent file work,retains bounded command/event/byte credits,and records original control identity before destructive ACK. Its [actual Linux UDP results](docs/ASYNC_MAINTENANCE_V4_RESULTS.md) establish finite correctness. The [registered capacity comparison](docs/ASYNC_CAPACITY_RESULTS_V4.md) now includes two PAUSE/CONTINUE pairs at 500 arrivals/s.

The old-artifact 1,000/s CONTINUE measurement is excluded after the independent checker exposed a 1,535-command first cut instead of 1,536. The [exact-cut correction](docs/CAPACITY_CUT_GATE_CORRECTION_V4.md) has passed 74 local source tests and 14 actual CPU checker tests; full Linux application regression and fresh comparisons remain pending. Earlier 500/s latency results do not qualify the new artifact.

## Verified evidence

| Path | Actual evidence | Limit |
| --- | --- | --- |
| Linux correctness |435 Java tests and 197 Python tests; zero failure/error/skip; 11 real PostgreSQL tests included |Source `6716f74a`; existing one-job CPU runner; hosted billing still blocked |
| V4 replicated execution |1003 commands,1000 unique trades,2003 events;three exact archive cuts;128 extra confirmations during a held original file |Three JVMs sharing one CPU host;functional fixture |
| Snapshot/cold restore |All three snapshots and all three restarted services match the complete state hash |No new orders/client continuation after cold restore |
| V4 paired capacity at 500/s |Four 20-second arms each confirm all 10,000 trades; p99 PAUSE 286.78/175.01 ms vs CONTINUE 65.65/59.93 ms |Both registered direction checks pass; 10 ms target remains unmet; separate fresh lineages |
| Previous V3 maintained capacity |6000/s and7000/s accept all planned arrivals;p99208.34/317.32ms in finite20s observations |7500/s loses74531/150000 arrivals;global accepted-arrival p99 is undefined;escalation stops |

The earlier V4 held-file fixture has no measured throughput or p99. The new finite comparison uses one qualified artifact (`2ea38974`), fixed leader/configuration, 127 active load producers and a 1536-command cut. Both pairs improve global p99 without worse post-offer p99 or lower in-window goodput; this is a bounded observation, with no default performance promotion or long-run latency guarantee. The [V3 capacity curve](docs/VERIFIED_HANDOFF_CAPACITY_RESULTS_V3.md), [negative immutable-batch encoding comparison](docs/BATCH_WIRE_VALIDATION_RESULTS_V3.md), [writer timing/handoff comparisons](docs/VERIFIED_ARCHIVE_HANDOFF_EXIT_WAIT_RESULTS_V3.md) and [client JFR diagnostic](docs/CLIENT_JFR_DIAGNOSTIC_RESULTS_V3.md) remain separate. Full raw attachments are retained in the same private repository with SHA-256, member inventories and authenticated download verification. The console contains 79 runs and 34 capacity cohorts; the earlier 77 runs and all 34 cohorts remain unchanged. The added 1,000/s entries distinguish the unpaired control from the disqualified measurement.

This remains a trading-systems research prototype. The [production acceptance gates](docs/PRODUCTION_ACCEPTANCE.md) still require sustained latency/capacity evidence,continuous100M lineage,physical-node fault isolation,production authentication/risk controls and external venue/account qualification. No hard realtime,millisecond SLA,HFT endorsement or funded external trading readiness is claimed. [Continuous endurance](docs/CONTINUOUS_ENDURANCE_PLAN.md) requires persistent journal anchors and producer/frontier recovery,not repeated reset fixtures.

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

