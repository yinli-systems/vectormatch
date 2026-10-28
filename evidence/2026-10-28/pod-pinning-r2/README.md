# Pinning without starving safepoints (2026-10-28, runs v5–v7)

Three unattended [`scripts/pod-autopilot`](../../../scripts/pod-autopilot/README.md) runs on RunPod CPU pod
`z01seweximrhz8` (EPYC 9655, 8 physical cores, data-center NVMe with fdatasync p50 57 µs), continuing
[`pod-quiet-source-r1`](../pod-quiet-source-r1/README.md). Three replicas and the load source share the host
over loopback; not a physical failure-domain result. Every arm is busy spin with measurement hygiene (static
GC workers, `-XX:+SafepointTimeout` at 20 ms, a load generator that does not collect during a window). Each
run is an ABAB at 8000/s (sync0), then a sync0 and a durable ladder on the baseline because no candidate was
selected. Kept here: summaries, selections, per-case audits, ladder rows, thread-pinning summaries, tail
attributions, and the pinned arms' `stdout.log` files with the SafepointTimeout output.

**v7 is still running** (`20261028-223943`): its ABAB and sync0 ladder are complete; its durable ladder had
finished 1000/s and 2000/s when this was recorded.

## ABAB at 8000/s

| Run | A vs B | Pair 1 p99 / p99.9 ratio | Pair 2 p99 / p99.9 ratio | Selected | Why not |
|---|---|---|---|---|---|
| v5 `213534` | `c2spinsrc` vs `c2spinsrcpin5` (all JVMs pinned, compilers at normal priority) | 0.79 / 1.90 | pinned arm lost orders | no | SafepointTimeout named the JFR telemetry thread and the source's compilers; the source's time-to-safepoint reached 30 ms (61 orders released >20 ms late), because four JVMs shared one housekeeping CPU |
| v6 `220810` | `c2spinsrc3` vs `c2spinsrc3pin` (nodes pinned, source unpinned on three CPUs) | **0.32** / 1.11 | **0.30** / 1.27 | no | p99.9 rose: at p99.9 the pinned tail overlaps no GC; it is the once-a-second Cleanup safepoint waiting 21 ms on the shared housekeeping CPU, plus warm-up in the first half second |
| v7 `223943` | `c2spinsrc3g` vs `c2spinsrc3gpin` (as v6, plus `-XX:GuaranteedSafepointInterval=0` in both arms) | **0.26 / 0.55** ✅ | 0.33 / 1.73 | no | pair 2's whole p99.9 tail was one 57 ms stall 0.24 s into the window, overlapping no GC (first full-rate use of the pipelined path) |

Pinned arms, 8000/s, p50 / p99 / p99.9: v6 35.3 µs / 3.05 ms / 17.5 ms and 36.5 µs / 2.94 ms / 20.8 ms; v7
36.3 µs / **2.58 ms / 10.6 ms** and 36.5 µs / 3.73 ms / 34.7 ms. Every v6 and v7 arm accepted every original
and passed every gate except v7 pair 2's ratio. Unpinned arms in the same runs: p99 8.8–11.2 ms.

The next run (v8, commit 50a5caf) adds a two-second pipelined warm-up at the window rate to both arms.

## Ladders on the unpinned baselines

All originals accepted on every passing rung. p50 / p99 / p99.9:

| Rate/s | v5 sync0 | v6 sync0 | v7 sync0 (no periodic safepoints) |
|---|---|---|---|
| 1000 | 35 µs / 2.63 ms / 7.6 ms | 36 µs / 3.26 ms / 12.3 ms | 34 µs / 3.68 ms / 8.7 ms |
| 2000 | 34 µs / 2.59 ms / 9.2 ms | 34 µs / 3.51 ms / 9.6 ms | 35 µs / 2.84 ms / 7.4 ms |
| 5000 | 32 µs / 7.25 ms / 14.4 ms | 33 µs / 7.99 ms / 16.9 ms | 36 µs / 5.90 ms / 12.4 ms |
| 8000 | 37 µs / 7.98 ms / 14.5 ms | 35 µs / 9.59 ms / 19.9 ms | 36 µs / 9.03 ms / 17.3 ms |
| 12000 | 33 µs / 11.32 ms / 20.9 ms | 32 µs / 14.32 ms / 20.3 ms | 36 µs / 11.98 ms / 15.9 ms |
| 20000 | 33 µs / 15.76 ms / 21.1 ms | failed twice (181, 2,772 not sent) | failed twice (1,466, 2,615 not sent) |
| 30000 | failed twice (5,625, 5,506 not sent) | — | — |

Durable (consensus and catalog sync2, recording data sync1, a force per commit):

| Rate/s | v5 | v6 | v7 (partial) |
|---|---|---|---|
| 1000 | 69 µs / 7.18 ms / 10.6 ms | 64 µs / 3.04 ms / 11.0 ms | 74 µs / 3.12 ms / 7.1 ms |
| 2000 | 65 µs / 4.53 ms / 10.0 ms | 62 µs / 3.91 ms / 13.9 ms | 63 µs / 3.87 ms / 11.6 ms |
| 3000 | 62 µs / 4.56 ms / 12.0 ms | 60 µs / 5.64 ms / 12.5 ms | running |
| 5000 | 63 µs / 5.38 ms / 14.1 ms | 60 µs / 7.12 ms / 17.6 ms | |
| 8000 | 65 µs / 10.95 ms / 16.4 ms | 65 µs / 8.50 ms / 16.9 ms | |
| 12000 | 58 µs / 11.57 ms / 18.9 ms | 65 µs / 13.27 ms / 28.2 ms | |

Knees by the ladder rule: sync0 20,000/s (v5) and 12,000/s (v6, v7); durable at least 12,000/s in v5 and v6
(every rung passed). The production target (p99 ≤ 5 ms and p99.9 ≤ 20 ms) holds for sync0 at 1000–2000/s in
every run, and for durable at 2000–3000/s (v5), 1000–2000/s (v6) and 1000–2000/s so far (v7).

Single runs per rung; the same configuration varies between runs (durable 1000/s p99 3.0–7.2 ms), so
single-rung differences of a millisecond or two are not meaningful.
