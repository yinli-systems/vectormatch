# Pod B autopilot summary (20261028-223943 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-223943",
  "a": "c2spinsrc3g",
  "b": "c2spinsrc3gpin",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.2608435157418253,
      "p999Ratio": 0.5530941297535228,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": true
    },
    {
      "a": "ab-a2",
      "b": "ab-b2",
      "p99Ratio": 0.3313112822114672,
      "p999Ratio": 1.7275836000367724,
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
| ab-a1 | 9875.856 | 1761 | 0.2697 | 0.0 | 0.0886 | 0.6417 | 681 orders over 174.781 ms |
| ab-b1 | 2576.053 | 1761 | 0.2368 | 0.0 | 0.0528 | 0.7104 | 190 orders over 28.3 ms |
| ab-a2 | 11249.798 | 1761 | 0.2425 | 0.0 | 0.0426 | 0.7149 | 626 orders over 132.021 ms |
| ab-b2 | 3727.185 | 1761 | 0.2334 | 0.0 | 0.0011 | 0.7655 | 466 orders over 65.083 ms |

## Sync0 capacity ladder (Aeron default durability) — config c2spinsrc3g

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 34.407 | 3683.405 | 8684.973 | 33.08 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 35.152 | 2844.982 | 7432.517 | 33.411 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 35.719 | 5897.613 | 12422.899 | 33.921 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 35.765 | 9025.32 | 17288.29 | 32.309 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 36.124 | 11977.479 | 15944.58 | 34.432 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | 33.821 | {'ACCEPTED': 178534, 'NOT_SENT': 1466} | FAIL | no |
| r20000-repeat | 20000 | None | None | None | 34.393 | {'ACCEPTED': 177385, 'NOT_SENT': 2615} | FAIL | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
