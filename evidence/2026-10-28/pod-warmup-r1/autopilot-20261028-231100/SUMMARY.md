# Pod B autopilot summary (20261028-231100 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-231100",
  "a": "c2spinsrc3gw",
  "b": "c2spinsrc3gwpin",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.3237388400990241,
      "p999Ratio": 0.6554729580033198,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": true
    },
    {
      "a": "ab-a2",
      "b": "ab-b2",
      "p99Ratio": 0.16397356166875202,
      "p999Ratio": 0.48349386071375466,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": true
    }
  ],
  "finalStateEqual": true,
  "candidateSelected": true,
  "rule": "First six originals in order. Every A/B source/completion/correctness gate and exact joins must pass, states must agree. Both B latency gates must pass: p99<=25ms,p999<=100ms,every-minute-p99<=25ms. EACH pair B/A p99<=0.90,p999<=1.00. Only then run confirm-b1 (a third 22s B window at 8000/s). No default promotion."
}
```

Tail attribution (slow = at or above p99; GC = a pause overlapping the order):

| case | p99 µs | slow orders | leader GC | source GC | follower GC only | no GC | largest stall |
|---|---|---|---|---|---|---|---|
| ab-a1 | 3389.479 | 1761 | 0.2794 | 0.0 | 0.0642 | 0.6564 | 292 orders over 90.025 ms |
| ab-b1 | 1097.306 | 1761 | 0.2743 | 0.0 | 0.0006 | 0.7252 | 131 orders over 17.461 ms |
| ab-a2 | 2908.353 | 1761 | 0.2731 | 0.0 | 0.0239 | 0.703 | 190 orders over 29.901 ms |
| ab-b2 | 476.893 | 1761 | 0.2198 | 0.0 | 0.0341 | 0.7462 | 120 orders over 15.357 ms |

## Sync0 capacity ladder (Aeron default durability) — config c2spinsrc3gwpin

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 38.544 | 2260.172 | 5066.11 | 36.486 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 33.811 | 500.909 | 3075.609 | 32.649 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 34.834 | 511.08 | 6724.342 | 32.88 | {'ACCEPTED': 180000} | pass | yes |
| r8000 | 8000 | 37.645 | 927.533 | 12036.026 | 33.981 | {'ACCEPTED': 176000} | pass | yes |
| r12000 | 12000 | 36.58 | 6083.721 | 12052.046 | 34.623 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | None | None | FAIL | no |
| r20000-repeat | 20000 | None | None | None | None | None | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spinsrc3gwpin

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 70.753 | 1570.943 | 7062.028 | 68.704 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 69.015 | 1351.578 | 147020.677 | None | {'ACCEPTED': 119845, 'NOT_SENT': 155} | FAIL | no |
| r2000-repeat | 2000 | 69.31 | 2633.918 | 3807.428 | 67.031 | {'ACCEPTED': 120000} | pass | yes |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
