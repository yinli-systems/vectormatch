# Pod B autopilot summary (20261028-233837 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 capacity ladder (Aeron default durability) — config c2spinsrc3gwpin

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 36.891 | 358.866 | 2367.165 | 34.923 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 34.769 | 770.383 | 2775.913 | 33.451 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 36.948 | 1922.302 | 7722.245 | 34.963 | {'ACCEPTED': 180000} | pass | yes |
| r8000 | 8000 | 38.544 | 579.012 | 8450.725 | 34.202 | {'ACCEPTED': 176000} | pass | yes |
| r12000 | 12000 | 33.679 | 8558.546 | 12670.035 | 32.7 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | 35.003 | {'ACCEPTED': 179902, 'NOT_SENT': 98} | FAIL | no |
| r20000-repeat | 20000 | 35.685 | 5533.955 | 13271.056 | 34.713 | {'ACCEPTED': 180000} | pass | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spinsrc3gwpin

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 72.815 | 2167.756 | 7672.676 | 68.574 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 67.089 | 466.071 | 4599.862 | 65.94 | {'ACCEPTED': 120000} | pass | yes |
| r3000 | 3000 | 65.202 | 1653.618 | 8426.836 | 64.077 | {'ACCEPTED': 180000} | pass | yes |
| r5000 | 5000 | 64.829 | 2755.831 | 9413.935 | 63.386 | {'ACCEPTED': 180000} | pass | yes |
| r8000 | 8000 | 67.874 | 3435.762 | 13575.232 | 63.856 | {'ACCEPTED': 176000} | pass | yes |
| r12000 | 12000 | 69.152 | 6031.421 | 15454.804 | 67.393 | {'ACCEPTED': 180000} | pass | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
