# Recorded evidence

These are short **development-machine observations**, not production capacity guarantees. The console reads `index.json`; it does not synthesize benchmark numbers. Different timing boundaries are shown explicitly, and absent metrics are null.

| Experiment | Useful confirmed work | Observation | Boundary |
|---|---:|---|---|
| Core fixed-arrival smoke | 60,000 commands / 15,000 trades | 20,000.331 commands/s; scheduled p99 203 µs | Memory-only, shallow book, 3 seconds |
| HTTP lifecycle | 250 places + 250 cancels / 0 trades | 98.315 accepted commands/s; place scheduled p99 234.367 ms | Loopback + forced local journal; 50 new orders/s |
| Paired replicated, 1 client | 1,008 commands / 336 trades | 52.732 confirmed commands/s; RTT p99 32.954 ms | Three local processes, sync 2, one in flight |
| Paired replicated, 4 clients | 1,008 commands / 336 trades | 118.395 confirmed commands/s; RTT p99 233.313 ms | Same harness, one in flight per client |
| Current leader-kill / cold restart | 57 final core commands | Hash, pending outbox, retry and backpressure checks passed | Three processes on one host; observed recovery 11.342 seconds |
| HTTP → quorum → PostgreSQL | Place/cancel, stable retry, conflict | Core snapshot agrees; database cursor reaches confirmed event | Functional verification, not a benchmark |

The paired experiment performs reference validation after timing and replays the actual global command order. Both configurations had zero unknown outcomes. One trial per configuration and a fixed run order do not establish statistical significance. Higher throughput came with worse tail latency. Official Archive recording-write counters are preserved; exact force-call counts were not collected, so no commands-per-force or causal batching claim is made.

Raw results, per-command traces and histograms are stored in `2026-10-23/`. The early replicated single-client result is retained separately; its elapsed throughput includes reference validation and must not be used as the paired control. The older fault-smoke result is also retained; the console points to the later conservative-capacity run.

## Source and verification limits

These exploratory runs were collected during development. Exact source manifests were not captured at each original invocation. The repository commit containing these artifacts also includes subsequent gateway correctness fixes and deployment tooling. Do not describe an older run as a measurement of every later change. Repeat a campaign from a clean recorded commit on isolated Linux hardware before publishing a release comparison.

`validation/` records the final local test summaries and source-file digests of the reviewed candidate. Java checks include actual PostgreSQL integration when the reported JDBC test suite has zero skipped tests. The generated core property test runs 150 randomized traces against an independent reference model; it counts as one property test in JUnit's suite totals.

No cloud results are included: the existing configured Runpod SSH endpoint was unreachable. The USD 20 cloud campaign is planned in [CLOUD_TESTING.md](../docs/CLOUD_TESTING.md).
