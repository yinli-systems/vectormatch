# Pod B autopilot summary (20261028-213534 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Sync0 ABAB confirmation at 8000/s

```
{
  "root": "/opt/vectormatch-b/experiments/sync0-abab-20261028-213534",
  "a": "c2spinsrc",
  "b": "c2spinsrcpin5",
  "pairs": [
    {
      "a": "ab-a1",
      "b": "ab-b1",
      "p99Ratio": 0.7915098494777659,
      "p999Ratio": 1.8964658977229647,
      "baselineLatencyGate": true,
      "baselineNonLatencyGates": true,
      "candidateGate": false,
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
| ab-a1 | 8981.796 | 1761 | 0.2243 | 0.0 | 0.0386 | 0.7371 | 813 orders over 122.101 ms |
| ab-b1 | 7109.18 | 1761 | 0.1164 | 0.0 | 0.0 | 0.8836 | 437 orders over 61.615 ms |
| ab-a2 | 8843.038 | 1761 | 0.2129 | 0.0 | 0.1056 | 0.6814 | 814 orders over 117.003 ms |
| ab-b2 | 8076.281 | 1760 | 0.0835 | 0.0 | 0.0 | 0.9165 | 263 orders over 40.935 ms |

## Sync0 capacity ladder (Aeron default durability) — config c2spinsrc

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 35.264 | 2632.393 | 7617.89 | 31.718 | {'ACCEPTED': 60000} | pass | yes |
| r2000 | 2000 | 33.644 | 2587.501 | 9225.07 | 32.129 | {'ACCEPTED': 120000} | pass | yes |
| r5000 | 5000 | 31.937 | 7253.163 | 14362.144 | 30.826 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 37.021 | 7983.737 | 14548.3 | 32.94 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 32.795 | 11316.977 | 20864.176 | 31.809 | {'ACCEPTED': 180000} | pass | no |
| r20000 | 20000 | 32.665 | 15759.397 | 21056.551 | 31.698 | {'ACCEPTED': 180000} | pass | no |
| r30000 | 30000 | None | None | None | 34.162 | {'ACCEPTED': 174375, 'NOT_SENT': 5625} | FAIL | no |
| r30000-repeat | 30000 | None | None | None | 34.762 | {'ACCEPTED': 174494, 'NOT_SENT': 5506} | FAIL | no |

## Durable capacity ladder (sync2 consensus/catalog, sync1 recording data) — config c2spinsrc

| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |
|---|---|---|---|---|---|---|---|---|
| r1000 | 1000 | 68.943 | 7178.915 | 10640.746 | 67.722 | {'ACCEPTED': 60000} | pass | no |
| r2000 | 2000 | 65.153 | 4527.347 | 9971.182 | 63.667 | {'ACCEPTED': 120000} | pass | yes |
| r3000 | 3000 | 61.558 | 4557.375 | 12036.42 | 60.542 | {'ACCEPTED': 180000} | pass | yes |
| r5000 | 5000 | 62.651 | 5380.439 | 14090.965 | 61.303 | {'ACCEPTED': 180000} | pass | no |
| r8000 | 8000 | 65.472 | 10950.069 | 16407.053 | 62.085 | {'ACCEPTED': 176000} | pass | no |
| r12000 | 12000 | 57.64 | 11567.098 | 18873.728 | 56.686 | {'ACCEPTED': 180000} | pass | no |

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
