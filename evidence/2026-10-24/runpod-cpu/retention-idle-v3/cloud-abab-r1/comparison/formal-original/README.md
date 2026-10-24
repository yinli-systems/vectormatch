# Actual finite idle ABAB derivation

All four CPU arms have independent closed process, complete collection, full outer/native/raw and root review receipts. The frozen comparison script was executed once formally after all four independent root reviews existed. All197 inputs were rehashed unchanged before publication. This does not change the original gates or earlier diagnostic failure.

| Arm | Requested max park | All-arrival p99(ms) | Three-cycle maintenance wall(s) | Window goodput(/s) | Scheduled→dispatch p99(ms) | Offer-return→reply p99(ms) |
|---|---:|---:|---:|---:|---:|---:|
| A1 | 1ms | 899.508607 | 1.988772353 | 479.765625 | 889.311362 | 13.126106 |
| B1 | 100µs | 562.917877 | 1.292279377 | 479.765625 | 556.902664 | 11.233968 |
| A2 | 1ms | 916.236996 | 1.985234229 | 479.765625 | 902.049842 | 13.561791 |
| B2 | 100µs | 558.369463 | 1.286542112 | 479.765625 | 551.609439 | 14.842196 |

Both paired observations have lower all-arrival p99 (37.42% and39.06%) and shorter complete maintenance wall time (35.02% and35.19%). This is a descriptive finite comparison, not statistical significance or sustained500/s capacity. Each arm has6400 distinct accepted orders, zero notSent/unknown/rejection/scheduler>20ms lateness and zero warning pairs. The source's finite outstanding-at-window-end classification is retained. Requested tuples/22factory creations are observed; actual sleep duration is not measured.

The separate same-arrival tail explainer selects exactly the slowest64/6400 arrivals per arm. Scheduled→dispatch accounts for98.9600%,98.9605%,98.8595%,98.8487% of those cohorts' summed latency. Of64 scheduled timestamps,58/59/61/59 fall within actual maintenance cycles. This is direct component accounting and temporal association, not subtraction of unrelated percentiles. External FIFO waiting, maintenance dispatch pause and dispatch scheduling are not separately identified. The offer-to-reply p99 does not improve in the second pair.

## Coarse process CPU tradeoff

| Role | A1 mean cores | B1 mean cores | A2 mean cores | B2 mean cores |
|---|---:|---:|---:|---:|
| node0 | 0.6400 | 0.7010 | 0.6902 | 0.7161 |
| node1 | 0.4789 | 0.5240 | 0.4590 | 0.5598 |
| node2 | 0.4633 | 0.5526 | 0.4468 | 0.5550 |
| parent | 0.6871 | 0.6576 | 0.6123 | 0.7281 |

Every node has higher mean occupied cores in both paired observations. Parent direction differs by pair. These are per-process cumulative CPU tick deltas divided by each role's covered adjacent interior intervals, not uniform full-window CPU totals or thread attribution. Actual arrival exposure coverage durations are11.483677630,11.526580916,11.547511530,12.540077290s, each within12.8s. All individual intervals and gaps remain in comparison.json. The separately reported parent entire observed spans include setup/drain/close and must not be substituted for arrival exposure CPU. No quota normalization, pure fsync or unique CPU causal claim is made.

Physical business-frame counts are5820/5941/5810/5951. Full batch-size distributions and physical offer counters are retained; configured cap4 does not imply every frame contains4commands. Maintenance wall time is from the three complete cycle receipts; overlapping per-RPC elapsed sums are explicitly separate.

Inputs remain in their original collections. comparison.csv and cpu-coverage.csv are direct tabular projections of comparison.json; tail-component-analysis.json is independently reproducible with explain_tail.py. registration.json/receipt.json preserve the exact formal command and interpreter; tail-registration.json/tail-receipt.json preserve the separate tail derivation. PREPARATION_FROZEN.json in the parent directory describes the earlier source freeze (when no formal run had yet occurred), and remains unchanged.
