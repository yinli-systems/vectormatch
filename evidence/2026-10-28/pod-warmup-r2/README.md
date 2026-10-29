# Pinned and warmed-up ladders (2026-10-28, run v9, stamp 20261028-233837)

Ladders only (`autopilot.py ladders:c2spinsrc3gwpin`) on the configuration selected by
[`pod-warmup-r1`](../pod-warmup-r1/README.md): busy spin, nodes pinned, two seconds of pipelined warm-up at each
window rate, on `runtime-r7` (warm-up skips orders that never reached the cluster). Same pod, same host
caveats as the earlier runs: three replicas and the load source share one host over loopback.

## sync0 (Aeron default durability)

| Rate/s | p50 | p99 | p99.9 | Round trip p99 | Result |
|---|---|---|---|---|---|
| 1000 | 37 µs | 0.36 ms | 2.4 ms | 56 µs | pass, all accepted |
| 2000 | 35 µs | 0.77 ms | 2.8 ms | 56 µs | pass |
| 5000 | 37 µs | 1.92 ms | 7.7 ms | 103 µs | pass |
| 8000 | 39 µs | 0.58 ms | 8.5 ms | 98 µs | pass |
| 12000 | 34 µs | 8.56 ms | 12.7 ms | 5.9 ms | pass |
| 20000 | 35 µs | 5.39 ms (repeat 5.53 ms) | 23.4 ms (repeat 13.3 ms) | — | first fail: 98 not sent; repeat pass, all accepted |

Knee by the ladder rule: 20,000/s (the repeat passed). Warm-up at 20,000/s accepted 15,546 and 14,189 of 16,000
orders; the rest were never offered (the source's bounded queue overflowed during the cold start) and were
skipped as the fix intends.

## Durable (consensus and catalog sync2, recording data sync1, a force per commit)

| Rate/s | p50 | p99 | p99.9 | Round trip p99 | Result |
|---|---|---|---|---|---|
| 1000 | 73 µs | 2.17 ms | 7.7 ms | 2.0 ms | pass |
| 2000 | 67 µs | 0.47 ms | 4.6 ms | 135 µs | pass |
| 3000 | 65 µs | 1.65 ms | 8.4 ms | 0.91 ms | pass |
| 5000 | 65 µs | 2.76 ms | 9.4 ms | 1.07 ms | pass |
| 8000 | 68 µs | 3.44 ms | 13.6 ms | 3.26 ms | pass |
| 12000 | 69 µs | 6.03 ms | 15.5 ms | 5.86 ms | pass (all accepted); p99 above the 5 ms target |

Knee by the ladder rule: 12,000/s. Within the production target (p99 <= 5 ms, p99.9 <= 20 ms) durable holds to
8000/s.

## Reading the numbers

- The median stays 33-73 µs at every rate, sync0 and durable alike.
- The 1000/s durable p99 (2.17 ms) is above the 2000/s p99 (0.47 ms) from the same configuration; single rungs
  vary by a few milliseconds, so the ladder is evidence of the shape, not of any one point.
- The round trip is measured from the offer to the reply; the full latency adds the source's own queueing and
  is inflated by source-side stalls the warm-up cannot remove (see v8 `pod-warmup-r1`).
- Single runs per rung; no repeats beyond the 20,000/s sync0 rung.
