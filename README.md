# VectorMatch

**Deterministic execution. Recoverable state. Measured performance.**

A private engineering project exploring a limit-order matching engine, replicated execution, and real-time market data. Every capacity claim must link to its workload, hardware, durability settings, and raw results.

## Delivery principles

- Price-time priority, integer accounting, explicit reservation and settlement.
- A deterministic state machine owns balances, orders, deduplication, and events.
- A timeout is an unknown outcome, not permission to place a second order.
- Local execution, replicated execution, and market delivery are measured separately.
- Performance improvements must pass the same correctness checks as the baseline.

## Implementation status

Executable deterministic matching, a local journaled workbench, a three-process Aeron Cluster backend, replicated bounded outbox, and transactional PostgreSQL event export. The React console shows actual order books, commands, replica checks, cached projection observations, and recorded benchmark evidence. See [the implementation contract](docs/IMPLEMENTATION.md).

Verified locally: leader termination and replacement, snapshot/cold restart with unacknowledged events, outbox backpressure, idempotent retries, PostgreSQL commit-before-ack recovery, and HTTP-to-quorum-to-database execution. All three cluster processes currently share one host. Independent-machine deployment, high connection-count fanout, sharding and production authentication remain future work.

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

The repository also includes a bounded [HTTP arrival-rate generator](bench/HTTP_LOAD.md), [replicated concurrency experiment](cluster/BENCHMARKS.md), and [USD 20 cloud-testing plan](docs/CLOUD_TESTING.md). Initial shared-host results are evidence for further investigation, not production latency or throughput guarantees.

