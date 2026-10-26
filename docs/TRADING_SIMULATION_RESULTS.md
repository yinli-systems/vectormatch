# Synthetic trading and bounded low-load latency results

On2026-10-26 the existing user-provided CPU Pod executed real matching-engine
commands with synthetic accounts/funds. No external trading account, exchange or
real money was involved. No new cloud resource or paid upgrade was created.

## Trading correctness

Both the original and experimental cache artifacts completed100 cycles on the
in-process core and a three-replica Aeron cluster. Each qualification has1600
attempts:1000 fresh accepted business commands,100 cached retries,400 expected
business rejections and100 identity conflicts. It executes400 unique trades,
transferring1500 base lots, with no unresolved outcome.

The [scenario contract](TRADING_SIMULATION.md) checks FIFO makers, partial fills,
maker-price improvement, IOC expiry, self-trade prevention, residual release,
foreign/terminal cancellation, insufficient funds, overflow and retry semantics.
Balances are checked against independent arithmetic expectations; complete
canonical state is compared to replay and snapshot restore. CLUSTER event files
are explicitly reference-derived; this is not a distributed market-feed test.

## Core cache candidate: not promoted

The candidate replaces only the global cached-result TreeMap with an
insertion-ordered LinkedHashMap, rebuilding global command order after restore.
The complete source diff and both JARs are retained. Each fresh arm schedules
320000 attempts at20000/s, including expected rejections and cached retries.
This is **not20000 fresh orders/s** and is not replicated throughput.

| Arm | Core service P99 | Original-arrival P99 | Original-arrival P99.9 | Completed in16s window |
|---|---:|---:|---:|---:|
| A1 original |1.240µs|1.328µs|1.880153ms|320000|
| B1 candidate |1.010µs|1.070µs|1.258730ms|320000|
| A2 original |1.580µs|1.707µs|1.902178ms|320000|
| B2 candidate |2.210µs|2.342µs|3.415156ms|320000|

All1280000 original attempts, replies and events were independently recounted.
Both artifacts produce identical command semantics, event bytes and canonical
snapshot bytes. Each arm has80000 unique trades and no unresolved outcome.
The first registered pair passes; the second fails. **The default core remains
the original TreeMap implementation.** No successful optimization is claimed for
this candidate. Peak core execution still has approximately15–17ms outliers.

The first auditor mistakenly compared raw JSON file hashes for original intents:
Java Map.of object-key iteration order varies across JVMs. The corrected auditor
retains raw hashes and additionally compares every complete parsed intent in a
canonical representation. It changes neither orders nor latency measurements.
The original auditor, failure observation and corrected auditor are archived.

## Replicated polling: both finite latency pairs pass

The next experiment uses the **original core** and unchanged baseline JARs.
Only the existing explicit node data-path maximum park differs:1000000ns vs
100000ns. All arms use sync2,2GiB G1 JVMs,SHARED drivers,MTU1248,128KiB receive
buffers,16384-event outbox,appointed leader0 and three replicas on the same CPU
container over loopback UDP. An independent client JVM has one outstanding RPC.
Replica JFR/GC and process metrics are enabled equally in both configurations.

| Arm | Maximum park | Attempts | RPC P50 | RPC P99 | RPC P99.9 | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| A1 |1ms|8000|7.935170ms|11.106324ms|16.384664ms|20.604746ms|
| B1 |100µs|8000|4.744826ms|6.870942ms|15.320077ms|27.177631ms|
| A2 |1ms|8000|8.459904ms|17.421460ms|23.828438ms|32.227834ms|
| B2 |100µs|8000|4.755406ms|7.936619ms|12.168091ms|23.733939ms|

P99 improves38.1% and54.4%; P99.9 also improves in both pairs, satisfying the
registered finite latency-direction gates. Every arm has5000 fresh accepted
business commands,500 cached retries,2500 expected rejections/conflicts,2000
unique trades,7500 traded lots and no unresolved outcome. Full intent semantics,
reply semantics,reference-derived events and canonical snapshots match across arms.

Sampled whole-process CPU deltas (three replicas plus client) are58.71/59.08s for
A1/B1 and61.57/61.71s for A2/B2. They include startup/verification/JFR work and
omit unsampled edges; they are not pure matching CPU costs. Faster completion
means greater CPU occupancy during the shorter run, even though total observed
CPU work per8000 attempts is similar. Maximum metric gaps are below1.003s.

All12 JFR captures close healthily. Native dumps and streams are reconciled with
multiplicity, including buffered tails; no observed DataLoss is accepted.
Whole-replica-life FileForce P99 ranges4.13–4.81ms in A1,4.01–4.74ms in B1,
10.31–11.17ms in A2 and4.45–5.61ms in B2. Shared-host/storage variation therefore
confounds attribution of the entire second-pair improvement to the idle policy.
These force statistics include startup/verification/shutdown and are not physical
disk durability or per-request causal measurements.

The controller appoints leader0 and raw callbacks record only node0 becoming
LEADER. This deployed harness did not record the actual leader with every reply,
so the independent auditor conservatively leaves `actualFixedLeaderProven=false`.
The next source version records per-reply observed leaders and the measurement
time window; those additions are not retroactively attributed to this artifact.

This is a useful candidate for sustained open-loop qualification, not a default
production promotion. It does not establish saturation throughput,30–60 minute
latency,physical-host isolation,continuous100M orders or a hard realtime/HFT SLA.
In particular B1's maximum latency worsens despite lower P99/P99.9.

## Validation and reproduction

Final retained code passes59 core and11 benchmark tests locally, all without
failure or skip; the raw auditor has5 passing regression tests. Candidate full
cluster regression executes485 tests:483 pass;2 are refused by the existing
fresh-root disk-admission guard before their native workloads start. Those
failures remain archived. This is not an all-green full Linux/PostgreSQL CI run.
The original and candidate both pass actual Linux three-replica business
qualification; the failed candidate remains an archived experiment only.

Exact deployed baseline source is `cf79179e064f668f6f57288ab11ec5883dc4ca68`.
The baseline library inventory, candidate patch/JAR, controllers, original intents,
samples,events,snapshots,Aeron state,JFR,metrics and failed attempts are in the
private raw archive:74472080 bytes,SHA-256
`909e3ef50bbecf4781d237745619d882bc0a3905fe5f3824720a528fe09de95a`,
private draft release423510304,asset679262900. All450 original members and a full
authenticated download were verified. Large raw files stay outside Git history.
Thin proofs are in
[`evidence/2026-10-26/trading-sim-r1`](../evidence/2026-10-26/trading-sim-r1/).
Use the archived controllers/JARs for exact-artifact reproduction; current source
includes the extra leader/time-window reporting described above.

`scripts/audit-trading-simulation.py` independently checks the core A/B population;
`scripts/audit-trading-polling.py` checks all four replicated arms, deployment
parameters,exits,raw percentiles,CPU intervals and original JFR tails. The latter
binds historical JFR paths to the recorded launch configuration and validates
archived JAR hashes, so the extracted evidence may live at another local path.
No benchmark child is left running after this campaign; the authorized CPU Pod
itself remains available.
