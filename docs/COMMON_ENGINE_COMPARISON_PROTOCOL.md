# Common-subset same-host comparison

This registers an initial finite comparison, not a reproduction of exchange-core's published benchmark or a replacement for replicated sustained testing. The [previous 100M lineage](ANCHORED_CONTINUITY_RESULTS_V4.md) and [7k/8k overload results](OVERLOAD_RESULTS_V4.md) retain their original boundaries.

## Sources and comparability

The [exchange-core README](https://github.com/exchange-core/exchange-core#readme), reviewed at upstream commit `2f8548749839e9095c8dc597e4b61521d259fa5d`, reports a single-symbol mix dominated by move commands (82%). It excludes network, IPC and journaling. VectorMatch has no native amend operation. Cancel/new is not substituted for amend. This comparison uses the common GTC/IOC/cancel subset with normal integer spot accounting and zero fees. It does not reproduce the upstream mix, hardware, JDK or published latency numbers.

Nasdaq's [14µs statement](https://www.nasdaq.com/products/fintech/eqlipse/trading-technology/exchange-matching) concerns its fastest production door-to-door implementation; it supplies neither a same-workload p99 comparison nor a benchmark run here. The [2011 LMAX report](https://martinfowler.com/articles/lmax.html) describes in-memory business processing. [Aeron's performance limits](https://aeron.io/docs/aeron-cluster/performance-limits/) distinguish sequential business execution from network and resource constraints. These sources motivate separate measurement boundaries, not a numeric ranking.

The released `exchange.core2:exchange-core:0.5.3` JAR is used without modifying its engine classes. Its stock Chronicle dependency fails initialization on Java 21 (`FileChannelImpl.unmap0` absent). That original failure and a subsequent unavailable commercial-BOM artifact resolution failure are retained. The measured candidate explicitly uses the public **Chronicle BOM 2.25ea60** compatibility cohort. [Chronicle's version-support documentation](https://github.com/OpenHFT/OpenHFT/blob/ea/docs/Version-Support.adoc) identifies x.25 as the first Java 21 line. This historical dependency cohort is an isolated benchmark dependency, not a production dependency recommendation. Exact resolved JAR hashes are part of the experiment manifest. A qualified result must name this dependency change, never call it the unmodified stock benchmark environment.

## Frozen workload and boundary

`CommonFlow` starts with 16 funded synthetic accounts and 1,024 resting orders, 64 bid and 64 ask price levels. A seeded, state-aware generator produces valid resting GTC additions, IOC sweeps, partial fills, FIFO fills and cancellations. It replenishes a depleted book and limits planned live orders; actual operation ratios and minimum/maximum live orders are reported. No native amend, self-trade, margin, multi-market, persistence or network is included. Command index and order IDs are frozen before timing. The exact complete `commands.csv` SHA must match across four arms at each rate.

The absolute source plan has an independent thread and never waits for a response. Both adapters share an 8,192-total-outstanding credit bound, covering source queue plus submitted requests. A credit refusal records the original as NOT_SENT and continues the original plan. The publisher uses the engine's normal API; exchange-core can also backpressure that publisher internally. VectorMatch has one business writer and its native hot result cache/terminal-order retention; exchange-core uses its native Disruptor risk/matching pipeline, direct order book, one risk shard and one matching shard. Both use the same CPU affinity/heap/JDK and isolated classpath. Their internal thread counts and history/duplicate semantics are different and are disclosed rather than disabled to improve a score.

Scheduled-to-copied-result latency includes source scheduling, common queue, adapter conversion/copy and engine processing. Publisher-to-result is separate. Neither is pure matching-function time or wire-to-wire latency. Engine callback data is copied before mutable native objects can be recycled. Workload construction, separate 10k-command warmup, funding, seed-book setup, full replay and file serialization occur outside the measured arrival window. Warmup uses a separate state and is not included in measured business counts.

Timing clarification verified against the [released 0.5.3 sources](https://repo.maven.apache.org/maven2/exchange/core2/exchange-core/0.5.3/exchange-core-0.5.3-sources.jar) while the frozen campaign ran: exchange-core's result handler and risk-release stage both depend on matching; its result callback does **not** wait for risk release. VectorMatch's synchronous `execute` returns after its account changes. These are native API-result boundaries with unequal settlement timing, not equivalent final-settlement acknowledgements. Full final balances are checked after the run, which does not move the earlier timestamps. No candidate, arrival plan, acceptance gate or original preregistration bytes were changed by this clarification. This further prevents interpreting a timing ratio as an engine or settlement-performance ranking.

## Order and acceptance

First run the six targeted Java tests on actual Linux classes, three Python auditor tests, then 1,000/s for one second in each engine as functional native qualification. These points are not comparative performance evidence.

Then run each of 10,000, 50,000, 100,000 and 250,000 planned commands/s for **five seconds**, in VECTOR A1, EXCHANGE B1, VECTOR A2, EXCHANGE B2 order. Seed 73439, 8,192 credits, `-Xms1g -Xmx3g`, G1 defaults, Java 21.0.13+9 and `ActiveProcessorCount=8` stay fixed. Select and record eight allowed logical CPUs before native work; do not change affinity between arms. No unrelated native benchmark, build, replay or compression overlaps arrivals. A five-second result is explicitly finite; it cannot establish a 30–60 minute SLA or steady-state capacity.

Report all planned, replied, accepted, business-rejected, not-sent and unknown counts; in-window accepted goodput; scheduled-to-result p50/p99/p99.9; publisher-to-result; source lateness; sampled queue/outstanding; process CPU, GC totals/log and post-window drain. All-arrival accepted percentiles are undefined if any planned acceptance is missing. The finite gate requires every planned command accepted, zero unknown/not-sent/rejection, at least 99% in-window confirmations, and no source release over 20ms late. A scheduling-invalid point remains a failed measurement; favorable conditional percentiles cannot rescue it. This follows the planned-arrival principle explained by [wrk2](https://github.com/giltene/wrk2), without applying a second synthetic histogram correction to already planned timestamps.

Full independent Java flat-list replay and Python price-level/FIFO replay must agree with every actual received original, fill and final available/reserved balance. For overloaded points, replay the exact executed subset; do not pretend unsent commands executed. Preserve every row and fail on an unmatched reply, duplicate, unresolved original, missing trade, changed clock or state mismatch. Correctness failure stops the campaign; finite overload or timing failure is retained and may continue the preregistered diagnostic rates. A global winner is not predeclared and cannot follow from these short runs alone.

## Reproduce and retain

```sh
./gradlew :bench:comparisonTest :bench:comparisonInstallDist
# JAVA21_FLAGS are the explicit --add-opens/--add-exports in bench/build.gradle.kts.
java $JAVA21_FLAGS -Xms1g -Xmx3g -XX:ActiveProcessorCount=8 \
  -cp 'bench/build/install/common-comparison/lib/*' \
  io.vectormatch.bench.comparison.CommonComparison VECTOR 10000 5 73439 NEW_OUTPUT
python3 scripts/audit-common-comparison.py NEW_OUTPUT --output NEW_AUDIT.json
```

The controller records complete argv, CPU/boot identity and all JAR hashes. New output paths are mandatory; no failed native point is overwritten or silently rerun. Full commands, outcomes, trades, balances, GC, telemetry, sources and audit results remain in private raw attachments with hashes and complete authenticated download/member verification. Only thin indexes/results belong in Git. The existing prepaid CPU is used; no new cloud node is required.

The replicated anchored adapter, uninterrupted high-rate streaming source/evidence rotation and sustained in-flight fault campaign remain separate implementation gates. Success here would qualify only the declared common-subset API workload.
