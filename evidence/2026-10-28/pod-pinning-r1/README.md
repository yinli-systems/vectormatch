# Busy spin and thread pinning (2026-10-28)

Three unattended [`scripts/pod-autopilot`](../../../scripts/pod-autopilot/README.md) runs on RunPod CPU pod
`z01seweximrhz8` (EPYC 9655, 8 physical cores in the cpuset, data-center NVMe with fdatasync p50 57 µs).
Three replicas and the load source share the host over loopback, so nothing here is a physical
failure-domain result. Each run is an ABAB at 8000/s followed by a sync0 and a durable ladder on the
configuration the ABAB selected (or on its baseline). Every case is audited from raw frames; summaries,
selections, per-case audits, ladder rows, thread-pinning summaries and tail attributions are kept here, raw
samples and recordings stayed on the pod.

| Stamp | ABAB (A vs B) | Governor | Outcome |
|---|---|---|---|
| `20261028-164618` | `c2spin` vs `c2spinpin` | v1 | Stopped after `ab-b1`: the source's arrival thread landed on the shared housekeeping CPU (the launcher's primordial thread was counted as an agent), 321 orders not sent. See `ABANDONED.json`. |
| `20261028-165634` | `c2spin` vs `c2spinpin` | v2 | Pinned arm still lost orders (329 not sent): time-to-safepoint 28–39 ms and 70 ms young-GC copying with every non-agent thread on one CPU. The controller then crashed on the failed candidate (fixed in cd281c8); ladders ran on `c2spin`. |
| `20261028-203625` | `c2spinst` vs `c2spinstpin` | v3 | Not selected: both baselines failed the source-timing gate (load-generator GC up to 24 ms) and one pinned arm lost orders. Pair 1 p99 ratio 0.80, p99.9 ratio 1.47. Ladders ran on `c2spinst`. |

## Ladders (busy spin, unpinned)

sync0 (Aeron default durability), all originals accepted on every passing rung:

| Rate/s | `c2spin` p50 / p99 / p99.9 | `c2spinst` p50 / p99 / p99.9 |
|---|---|---|
| 1000 | 36 µs / 2.15 ms / 6.3 ms | 40 µs / 3.12 ms / 14.1 ms |
| 2000 | 36 µs / 3.26 ms / 11.1 ms | 34 µs / 3.95 ms / 14.5 ms |
| 5000 | 31 µs / 6.69 ms / 14.1 ms | 36 µs / 11.17 ms / 19.7 ms |
| 8000 | 34 µs / 8.66 ms / 17.7 ms | 36 µs / 8.58 ms / 19.5 ms |
| 12000 | 34 µs / 13.50 ms / 24.5 ms | 35 µs / 13.08 ms / 28.0 ms |
| 20000 | failed twice (847 and 609 not sent) | failed twice (456 and 1,024 not sent) |

Durable (consensus and catalog sync2, recording data sync1, every commit forced):

| Rate/s | `c2spin` p50 / p99 / p99.9 | `c2spinst` p50 / p99 / p99.9 |
|---|---|---|
| 1000 | 68 µs / 3.26 ms / 9.7 ms | 67 µs / 3.54 ms / 9.6 ms |
| 2000 | 65 µs / 3.42 ms / 13.4 ms | 64 µs / 3.68 ms / 12.7 ms |
| 3000 | 62 µs / 3.65 ms / 11.3 ms | failed the gates twice; all accepted, p99 8.9 and 7.1 ms |
| 5000 | 63 µs / 6.76 ms / 16.9 ms | — |
| 8000 | failed once (p99 12.3 ms), repeat passed (p99 8.4 ms) | — |

Knees by the ladder rule (first failing rung stops escalation): sync0 12,000/s for both; durable 5,000/s
(`c2spin`) and 2,000/s (`c2spinst`). The production target (p99 ≤ 5 ms and p99.9 ≤ 20 ms) is met by sync0
at 1000–2000/s and by durable at 1000–3000/s (`c2spin`) and 1000–2000/s (`c2spinst`).

## What these runs established

- Busy spin holds the median at 31–40 µs (sync0) and 60–69 µs (durable, with a force per commit) at every
  rate tested; the tail, not the median, is what limits the production target.
- `tail_attribution.py` on the v3 ABAB: 41–55% of orders at or above p99 overlap a leader or source GC pause;
  the source (which keeps every command and reply for verification) paused up to 24 ms.
- Pinning failures traced to the shared housekeeping CPU: starved VM Thread and GC workers (v2), then a
  reniced JIT compiler thread holding safepoints (found in the next run with `-XX:+SafepointTimeout`).

Single runs per rung; sync0 knees at 12,000/s and 20,000/s failures sit at the source's 512-order bound.
The ladders differ in more than one setting from earlier runs (static GC threads in `c2spinst`), so the two
columns are not an ABAB comparison.
