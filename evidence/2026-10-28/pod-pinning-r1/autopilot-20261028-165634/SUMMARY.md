# Pod B autopilot summary (20261028-165634 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 capacity ladder (Aeron default durability) — config c2spin

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 35.976 | 2147.493 | 6332.231 | 32.229 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 35.984 | 3264.729 | 11052.863 | 34.062 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 31.368 | 6689.29 | 14121.239 | 30.245 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 34.02 | 8657.785 | 17745.893 | 31.037 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 34.223 | 13497.252 | 24528.541 | 32.749 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | 32.459 | {'ACCEPTED': 179153, 'NOT_SENT': 847} | FAIL | no |
| r20000-repeat | 20000 | None | None | None | 32.369 | {'ACCEPTED': 179391, 'NOT_SENT': 609} | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spin

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 67.636 | 3261.653 | 9719.502 | 65.369 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 64.996 | 3416.862 | 13357.508 | 63.256 | {'ACCEPTED': 120000} | pass | yes |
| r3000 | 3000 | 61.505 | 3645.405 | 11308.436 | 60.341 | {'ACCEPTED': 180000} | pass | yes |
| r5000 | 5000 | 62.6 | 6758.555 | 16912.568 | 60.862 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 65.71 | 12331.742 | 22682.823 | 62.214 | {'ACCEPTED': 176000} | FAIL | no |
| r8000-repeat | 8000 | 60.547 | 8356.616 | 14019.201 | 57.437 | {'ACCEPTED': 176000} | pass | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
