# Pipelined warm-up: node pinning selected (2026-10-28, run v8, stamp 20261028-231100)

One unattended [`scripts/pod-autopilot`](../../../scripts/pod-autopilot/README.md) run on RunPod CPU pod
`z01seweximrhz8` (EPYC 9655, 8 physical cores, data-center NVMe with fdatasync p50 57 µs), continuing
[`pod-pinning-r2`](../pod-pinning-r2/README.md), on `runtime-r6`. Three replicas and the load source share the
host over loopback; not a physical failure-domain result.

Both ABAB arms (`c2spinsrc3gw` vs `c2spinsrc3gwpin`) are busy spin with static GC workers,
`-XX:+SafepointTimeout`, `-XX:GuaranteedSafepointInterval=0`, a load generator that does not collect during a
window and runs unpinned on three CPUs, and, new here, **two seconds of pipelined warm-up at the window rate**
(16,000 orders at 8000/s) just before the measured window. B pins the three nodes (`roles: [0, 1, 2]`) with
their housekeeping on the fourth CPU. Warm-up orders are accepted, replayed by the reference and counted in
`window.json` (`preWindowCommands`), which the audit uses for the expected sequence numbers.

## ABAB at 8000/s (sync0) — candidate selected

| Case | Arm | p50 | p99 | p99.9 | max |
|---|---|---|---|---|---|
| ab-a1 | unpinned | 35.8 µs | 3.39 ms | 12.4 ms | 25.2 ms |
| ab-b1 | nodes pinned | 36.9 µs | **1.10 ms** | 8.15 ms | 15.1 ms |
| ab-a2 | unpinned | 37.5 µs | 2.91 ms | 11.6 ms | 18.2 ms |
| ab-b2 | nodes pinned | 36.4 µs | **0.48 ms** | 5.59 ms | 13.0 ms |
| confirm-b1 | nodes pinned | 35.2 µs | **0.30 ms** | 6.60 ms | 13.8 ms |

Ratios B/A: pair 1 p99 0.32, p99.9 0.66; pair 2 p99 0.16, p99.9 0.48. Every gate passed, final states agree,
governor reported no errors; the confirmation passed. This is the first pinning candidate the registered rule
selected. Warm-up alone also moved the unpinned baseline: earlier runs' unpinned 8000/s p99 was 8.5–11.6 ms.

## Ladders on the selected configuration (`c2spinsrc3gwpin`)

sync0, all originals accepted on every passing rung; "round trip" is offer to reply:

| Rate/s | p50 | p99 | p99.9 | Round-trip p50 / p99 |
|---|---|---|---|---|
| 1000 | 39 µs | 2.26 ms | 5.1 ms | 36 µs / 200 µs |
| 2000 | 34 µs | **0.50 ms** | 3.1 ms | 33 µs / **61 µs** |
| 5000 | 35 µs | **0.51 ms** | 6.7 ms | 33 µs / **69 µs** |
| 8000 | 38 µs | **0.93 ms** | 12.0 ms | 34 µs / 113 µs |
| 12000 | 37 µs | 6.08 ms | 12.1 ms | 35 µs / 5.84 ms |
| 20000 | warm-up refused twice (see below) | | | |

Durable (consensus and catalog sync2, recording data sync1, a force per commit):

| Rate/s | p50 | p99 | p99.9 | Round-trip p50 / p99 |
|---|---|---|---|---|
| 1000 | 71 µs | 1.57 ms | 7.1 ms | 69 µs / 193 µs |
| 2000 | failed: one ~206 ms stall 0.7 s in, 155 orders not sent | | | |
| 2000 repeat | 69 µs | 2.63 ms | 3.8 ms | 67 µs / 117 µs |

The production target (p99 ≤ 5 ms and p99.9 ≤ 20 ms) holds for sync0 at 1000–8000/s and for durable at
1000/s and the 2000/s repeat. By the ladder rule (the first failing rung stops escalation) the knees are
sync0 12,000/s and durable 1,000/s; the durable ladder above 2000/s was rerun as v9.

## Failures, and what they were

- **sync0 20,000/s:** the probe refused both runs because a pipelined warm-up order was not sent (the warm-up
  itself hit the cold-start stall and the source's 512-order bound overflowed). Fixed in 0bf7469: warm-up
  orders that never reached the cluster are skipped.
- **durable 2000/s:** a single ~206 ms stall with no GC overlap; every node's file force had p99 0.04 ms but a
  maximum of 53–73 ms in that window (shared-host storage). The source was not the cause (release lateness
  ≤ 6.2 ms). The repeat passed. `node*-g0/stdout.log` for that rung is kept.
- In durable mode the governor reports one overflow agent per node: a second, mostly idle thread named
  `archive-conduct` that it correctly keeps on the housekeeping CPU while the busy recorder has its own.

Round trips are same-host loopback and include matching and the reply; vendor figures (98 µs Aeron Cluster
Premium round trip on AWS) are cross-host and without a matching engine, so the comparison is not like-for-like.
