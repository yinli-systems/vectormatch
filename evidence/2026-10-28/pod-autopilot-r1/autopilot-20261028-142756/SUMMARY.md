# Pod B autopilot summary (20261028-142756 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 configuration sweep (exploratory)

| case | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | gates |
|---|---|---|---|---|---|
| c1p100-r1000 | 797.354 | 1902.942 | 9055.436 | 746.971 | pass |
| c1p100-r20000 | None | None | None | 168.766 | FAIL |
| c1p100-r8000 | 294.049 | 15848.403 | 26516.068 | 269.889 | pass |
| c2p1-r1000 | 459.818 | 824.65 | 5480.491 | 426.897 | pass |
| c2p1-r20000 | None | None | None | 222.176 | FAIL |
| c2p1-r8000 | 306.734 | 5347.047 | 16623.422 | 271.541 | pass |
| c2p100-r1000 | 779.506 | 1573.386 | 6101.749 | 733.641 | pass |
| c2p100-r20000 | None | None | None | 222.116 | FAIL |
| c2p100-r8000 | 311.724 | 5869.028 | 12057.723 | 275.407 | pass |
| c2spin-r1000 | 36.384 | 2533.58 | 11513.542 | 34.302 | pass |
| c2spin-r20000 | None | None | None | 32.329 | FAIL |
| c2spin-r8000 | 35.482 | 9333.391 | 20438.772 | 31.998 | pass |

Pick rule: lowest p99 at 8000/s among gate-passing configurations, else at 1000/s, else baseline → **c2p1**

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-142756",
  "a": "c1p100",
  "b": "c2p1",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.4260085684659904,
      "p999Ratio": 0.673152290519653,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": true
    },
    {
      "a": "ab-a2",
      "b": "ab-b2",
      "p99Ratio": 0.38180705572002605,
      "p999Ratio": 0.6194926677761577,
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

## Sync0 capacity ladder (Aeron default durability) — config c2p1

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 456.144 | 852.399 | 5338.115 | 429.951 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 410.385 | 1175.892 | 8431.067 | 398.183 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 345.007 | 3900.836 | 12231.5 | 322.429 | {'ACCEPTED': 180000} | pass | yes |
| r8000 | 8000 | 294.396 | 5257.741 | 13644.511 | 270.43 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | None | None | None | 222.097 | {'ACCEPTED': 179957, 'NOT_SENT': 43} | FAIL | no |
| r12000-repeat | 12000 | None | None | None | 221.716 | {'ACCEPTED': 179851, 'NOT_SENT': 149} | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2p1

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 607.023 | 6184.334 | 12609.837 | 586.389 | {'ACCEPTED': 60000} | pass | no |
| r2000 | 2000 | 478.778 | 2713.767 | 9268.31 | 438.274 | {'ACCEPTED': 120000} | pass | yes |
| r3000 | 3000 | 434.563 | 3138.106 | 11670.456 | 407.398 | {'ACCEPTED': 180000} | pass | yes |
| r5000 | 5000 | 391.827 | 5408.998 | 12885.198 | 357.743 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 350.615 | 5523.966 | 12638.785 | 323.441 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 310.704 | 10911.839 | 22193.861 | 274.627 | {'ACCEPTED': 180000} | pass | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and STATE.json.
