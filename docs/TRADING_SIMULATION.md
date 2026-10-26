# Deterministic synthetic trading and cache-index experiment

`io.vectormatch.bench.TradingSimulation CORE|CLUSTER NEW_OUTPUT cycles rate portBase`
runs the actual matching engine with synthetic accounts and funds. It does not
send orders to an external venue or use real money. The CLUSTER mode requires a
fresh isolated cluster and rate0 (one outstanding RPC); it never creates or stops
cluster members. CORE rate>0 schedules every attempt against its original time,
without skipping late arrivals. Neither mode alone establishes saturation capacity.

Each16-attempt cycle includes two same-price makers, partial fills, a FIFO sweep,
maker-price improvement, foreign cancellation rejection, residual cancellation,
a resting bid, self-trade prevention, an IOC with no liquidity, insufficient funds,
an exact cached retry, a conflicting retry, terminal cancellation and notional
overflow. Eight orders are accepted, four unique trades transfer15 base lots.
The three trading accounts settle to analytically specified balances; all reserves
are released. Every cycle adds14 business sequence positions and16 public events.
The retry returns its old trade count without emitting new trades.

The harness preserves original identities before execution, every completed reply,
all per-attempt timings, canonical state and events. In CORE, events come from the
actual execution; CLUSTER event JSON is explicitly reference-derived, not evidence
of distributed market-feed delivery. Cluster replies and final canonical state
are compared to replay, then final balances to independent arithmetic expectations.
Unknown transport failures stop with the original trace and a partial outcome
file. They are never silently reclassified as rejection.

CORE uses a separate1000-cycle warm-up, fresh measured state, a1024-result
per-producer cache and4096-result global bound. It measures execute service time
separately from original-arrival latency; retaining events/replies adds observer
cost to dispatch and total elapsed time. No file I/O occurs inside the CORE loop.
All verification and CSV serialization follow timing. CLUSTER validates replies
between requests, so its elapsed throughput includes this cost, whereas RPC
percentiles measure execute calls. It cannot establish open-loop capacity.

## Registered candidate comparison, 2026-10-26

Use only the existing user-authorized CPU Pod, no new resources or charges.
Baseline is the current TreeMap global cached-result index. Candidate changes only
that index to insertion-ordered LinkedHashMap, with explicit sorted reconstruction
after snapshot restore because producer serialization is not command order.
The snapshot format, result semantics, per-producer cache and business limits stay
the same. Both artifacts, candidate source diff and SHA-256 must be preserved.

First qualify the unmodified baseline with100-cycle CORE and100-cycle CLUSTER
simulations. Run candidate core/regression tests, including adversarial restore
and eviction chronology. Then execute A1/B1/A2/B2 on the same host, Java21,
2GiB heap, G1 GC,20000 cycles (320000 attempts),20000 scheduled attempts/s.
No simultaneous benchmark processes. Keep the full trace and failed experiments.

Promotion requires identical complete outcome/canonical hashes, all independent
settlement checks, and in **both** pairs: service P99 improves by at least5%,
scheduled P99 and P99.9 do not worsen, and in-window completed attempts do not
decrease. A service-only improvement is a lead, not an end-to-end optimization.
The bounded result cannot be promoted to replicated throughput or an SLA.
Host load, cgroup CPU throttling, child CPU/I/O and GC must be retained.

Build with `./gradlew :bench:installDist`; invoke Java21 with
`--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED` for CLUSTER and classpath
`bench/build/install/bench/lib/*`. Use a new output directory for every run.
