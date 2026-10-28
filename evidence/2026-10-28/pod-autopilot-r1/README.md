# Pod autopilot r1 (2026-10-28)

One unattended run of [`scripts/pod-autopilot`](../../../scripts/pod-autopilot/README.md) on RunPod CPU pod
`z01seweximrhz8` (EU-SE-1): AMD EPYC 9655, 8 complete physical cores in the container cpuset, docker overlay
root on data-center NVMe. Three cluster replicas and the load source share that host over loopback, so this is
not a physical failure-domain result. Runtime: `runtime-r5` (reply back-pressure queue, sync0-capable diagnostic
node, busy-spin option), Temurin 21.0.13+9, Aeron 1.53.3.

Root-filesystem force latency, measured separately with `fsync_floor.py` (3,000 × 4 KiB appends):
fdatasync p50 57 µs, p99 79 µs, p99.9 151 µs; fsync p50 55 µs, p99 64 µs.

`autopilot-20261028-142756/SUMMARY.md` is the generated summary; every number below comes from it or from the
per-stage `*-AUDIT.json`, `*-SWEEP_ROW.json` and `*-LADDER_ROW.json` files. Latency is measured from each
order's planned arrival time; "offer→reply" is closest to a client round trip. Each run is bounded to 180,000
originals, and raw per-order samples, recordings and telemetry stayed on the pod.

## Results

**sync0 sweep** (exploratory, Aeron's default durability: majority replication without a per-write force):

| Configuration | 1000/s p50 / p99 | 8000/s p50 / p99 / p99.9 |
|---|---|---|
| 1 core per node, park 100 µs | 797 µs / 1.90 ms | 294 µs / 15.8 ms / 26.5 ms |
| 2 cores, park 100 µs | 780 µs / 1.57 ms | 312 µs / 5.87 ms / 12.1 ms |
| 2 cores, park 1 µs | 460 µs / 0.82 ms | 307 µs / 5.35 ms / 16.6 ms |
| 2 cores, busy spin (nodes and client driver) | **36 µs** / 2.53 ms | **35 µs** / 9.33 ms / 20.4 ms |

At 20000/s every configuration failed the gates because the source's 512-order bound overflowed (orders not
sent); busy spin still had a 32 µs offer→reply median there.

**Pick and ABAB** (sync0, 8000/s): the fixed rule (lowest gate-passing p99 at 8000/s) chose two cores with
1 µs park. Against the one-core 100 µs baseline it passed both pairs: p99 ratios 0.43 and 0.38, p99.9 ratios
0.67 and 0.62, final states equal. Busy spin was not picked because of its p99.

**Ladders** on the selected configuration (first failing rung stops escalation and is repeated once):

| Rate/s | sync0 p50 / p99 / p99.9 | Durable p50 / p99 / p99.9 |
|---|---|---|
| 1000 | 456 µs / 0.85 ms / 5.3 ms | 607 µs / 6.18 ms / 12.6 ms |
| 2000 | 410 µs / 1.18 ms / 8.4 ms | 479 µs / 2.71 ms / 9.3 ms |
| 3000 | — | 435 µs / 3.14 ms / 11.7 ms |
| 5000 | 345 µs / 3.90 ms / 12.2 ms | 392 µs / 5.41 ms / 12.9 ms |
| 8000 | 294 µs / 5.26 ms / 13.6 ms | 351 µs / 5.52 ms / 12.6 ms |
| 12000 | failed twice: 43 and 149 orders not sent | 311 µs / 10.9 ms / 22.2 ms (all accepted) |

Durable = consensus and catalog sync2, recording data sync1, initialized segments. Every listed durable rung
accepted all originals and passed the registered 25 ms gates; 12,000/s was the highest rate tested, so its knee
is at least that. The production target (p99 ≤ 5 ms and p99.9 ≤ 20 ms) is met by sync0 through 5000/s and by the
durable configuration at 2000 and 3000/s; the durable 1000/s rung missed it (p99 6.18 ms).

## Limits

- Exploratory sweep cases are single runs; only the 8000/s sync0 pick was confirmed by ABAB. The durable ladder
  reuses that pick and was not separately ABAB-tested under durable settings.
- sync0 vs sync2 at 12000/s differ by a few dozen unsent orders on single runs; that is run-to-run noise near
  the source bound, not evidence that durability is faster.
- Vendor comparisons (Aeron Cluster Premium 98 µs round trip on AWS, Aeron transport 57 µs on Google Cloud) are
  vendor-reported, cross-host and without a matching engine; their durability setting is assumed, not verified.
- Busy spin gives a tens-of-microseconds median but a worse p99, consistent with spinning agents being
  descheduled by other JVM threads on the same cores; that cause has not been measured yet.
