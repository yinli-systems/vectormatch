# Pod B autopilot summary (20261028-210356 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-210356",
  "a": "c2spinsrc",
  "b": "c2spinsrcpin",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.32081069896629,
      "p999Ratio": 0.9836202559716907,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": true,
      "passes": false
    },
    {
      "a": "ab-a2",
      "b": "ab-b2",
      "p99Ratio": null,
      "p999Ratio": null,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
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

| case | p99 µs | slow orders | leader GC | source GC | follower GC only | no GC | largest stall |
|---|---|---|---|---|---|---|---|
| ab-a1 | 8452.854 | 1761 | 0.2237 | 0.0 | 0.0239 | 0.7524 | 369 orders over 119.13 ms |
| ab-b1 | 2711.766 | 1761 | 0.2493 | 0.0 | 0.0034 | 0.7473 | 253 orders over 34.214 ms |
| ab-a2 | 11575.662 | 1761 | 0.1885 | 0.0 | 0.0471 | 0.7643 | 912 orders over 161.076 ms |
| ab-b2 | 5212.869 | 1760 | 0.1801 | 0.0 | 0.0131 | 0.8068 | 546 orders over 77.949 ms |

## Sync0 capacity ladder (Aeron default durability) — config c2spinsrc

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 33.349 | 3013.907 | 8987.32 | 32.259 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 33.398 | 3477.461 | 8984.458 | 32.269 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 32.218 | 5968.259 | 14527.986 | 31.157 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 36.151 | 8746.906 | 15933.068 | 33.04 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 35.886 | 12184.511 | 19509.631 | 34.021 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | None | None | None | 32.69 | {'ACCEPTED': 179538, 'NOT_SENT': 462} | FAIL | no |
| r20000-repeat | 20000 | None | None | None | 32.93 | {'ACCEPTED': 179792, 'NOT_SENT': 208} | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spinsrc

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 63.709 | 3895.391 | 8856.344 | 62.635 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 61.665 | 5217.211 | 13687.298 | 60.292 | {'ACCEPTED': 120000} | pass | no |
| r3000 | 3000 | 66.9 | 3730.874 | 13347.435 | 65.079 | {'ACCEPTED': 180000} | pass | yes |
| r5000 | 5000 | 63.085 | 7377.433 | 18845.671 | 61.994 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 65.432 | 12152.897 | 17748.251 | 61.984 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 59.401 | 11718.59 | 22344.539 | 58.389 | {'ACCEPTED': 180000} | pass | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
