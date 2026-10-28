# Pod B autopilot summary (20261028-203625 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-203625",
  "a": "c2spinst",
  "b": "c2spinstpin",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.7954740780523211,
      "p999Ratio": 1.4685048742784892,
      "baselineLatencyGate": false,
      "baselineNonLatencyGates": false,
      "candidateGate": false,
      "passes": false
    },
    {
      "a": "ab-a2",
      "b": "ab-b2",
      "p99Ratio": null,
      "p999Ratio": null,
      "baselineLatencyGate": false,
      "baselineNonLatencyGates": false,
      "candidateGate": false,
      "passes": false
    }
  ],
  "finalStateEqual": false,
  "candidateSelected": false,
  "rule": "First six originals in order. Every A/B source/completion/correctness gate and exact joins must pass, states must agree. Both B latency gates must pass: p99<=25ms,p999<=100ms,every-minute-p99<=25ms. EACH pair B/A p99<=0.90,p999<=1.00. Only then run confirm-b1 (a third 22s B window at 8000/s). No default promotion."
}
```

Tail attribution (slow = at or above p99; GC = a pause overlapping the order):

| case | p99 µs | slow orders | leader/source GC | follower GC only | no GC | largest stall |
|---|---|---|---|---|---|---|
| ab-a1 | 12035.824 | 1761 | 0.4145 | 0.1488 | 0.4367 | 409 orders over 82.092 ms |
| ab-b1 | 9574.186 | 1761 | 0.5457 | 0.0 | 0.4543 | 405 orders over 60.158 ms |
| ab-a2 | 11183.775 | 1761 | 0.4446 | 0.0256 | 0.5298 | 354 orders over 69.952 ms |
| ab-b2 | 7594.616 | 1760 | 0.4455 | 0.0 | 0.5545 | 560 orders over 84.371 ms |

## Sync0 capacity ladder (Aeron default durability) — config c2spinst

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 40.424 | 3115.865 | 14083.093 | 37.907 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 33.574 | 3952.801 | 14457.162 | 31.958 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 35.522 | 11169.189 | 19693.153 | 33.671 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 36.188 | 8580.8 | 19527.109 | 32.459 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 35.21 | 13076.999 | 27957.864 | 33.551 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | 31.688 | {'ACCEPTED': 179544, 'NOT_SENT': 456} | FAIL | no |
| r20000-repeat | 20000 | None | None | None | 32.018 | {'ACCEPTED': 178976, 'NOT_SENT': 1024} | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spinst

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 67.277 | 3544.227 | 9604.238 | 65.93 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 63.995 | 3684.352 | 12690.358 | 62.655 | {'ACCEPTED': 120000} | pass | yes |
| r3000 | 3000 | 65.999 | 8875.424 | 24359.685 | 64.157 | {'ACCEPTED': 180000} | FAIL | no |
| r3000-repeat | 3000 | 69.347 | 7141.383 | 15442.04 | 67.452 | {'ACCEPTED': 180000} | FAIL | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
