# Pod B autopilot summary (20261028-220810 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-220810",
  "a": "c2spinsrc3",
  "b": "c2spinsrc3pin",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.32352704391361725,
      "p999Ratio": 1.1080272784652936,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": false
    },
    {
      "a": "ab-a2",
      "b": "ab-b2",
      "p99Ratio": 0.2964393873995579,
      "p999Ratio": 1.2735054970066424,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": false
    }
  ],
  "finalStateEqual": true,
  "candidateSelected": false,
  "rule": "First six originals in order. Every A/B source/completion/correctness gate and exact joins must pass, states must agree. Both B latency gates must pass: p99<=25ms,p999<=100ms,every-minute-p99<=25ms. EACH pair B/A p99<=0.90,p999<=1.00. Only then run confirm-b1 (a third 22s B window at 8000/s). No default promotion."
}
```

Tail attribution (slow = at or above p99; GC = a pause overlapping the order):

| case | p99 µs | slow orders | leader GC | source GC | follower GC only | no GC | largest stall |
|---|---|---|---|---|---|---|---|
| ab-a1 | 9427.759 | 1761 | 0.2487 | 0.0 | 0.0125 | 0.7388 | 672 orders over 102.983 ms |
| ab-b1 | 3050.135 | 1761 | 0.2868 | 0.0 | 0.0 | 0.7132 | 279 orders over 41.699 ms |
| ab-a2 | 9904.335 | 1761 | 0.0579 | 0.0 | 0.0136 | 0.9284 | 741 orders over 110.267 ms |
| ab-b2 | 2936.035 | 1761 | 0.2504 | 0.0 | 0.0 | 0.7496 | 310 orders over 41.636 ms |

## Sync0 capacity ladder (Aeron default durability) — config c2spinsrc3

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 35.954 | 3262.465 | 12255.129 | 33.381 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 34.199 | 3511.694 | 9622.61 | 32.58 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 33.359 | 7991.109 | 16949.233 | 31.868 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 34.512 | 9590.738 | 19915.606 | 31.217 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 31.841 | 14317.153 | 20265.072 | 30.887 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | 32.529 | {'ACCEPTED': 179819, 'NOT_SENT': 181} | FAIL | no |
| r20000-repeat | 20000 | None | None | None | 33.181 | {'ACCEPTED': 177228, 'NOT_SENT': 2772} | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spinsrc3

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 64.365 | 3038.22 | 10964.944 | 63.135 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 62.247 | 3910.229 | 13907.673 | 60.752 | {'ACCEPTED': 120000} | pass | yes |
| r3000 | 3000 | 60.285 | 5644.887 | 12534.654 | 59.2 | {'ACCEPTED': 180000} | pass | no |
| r5000 | 5000 | 60.101 | 7121.552 | 17644.201 | 59.039 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 64.918 | 8497.031 | 16896.952 | 61.824 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 64.627 | 13267.04 | 28175.948 | 63.166 | {'ACCEPTED': 180000} | pass | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
