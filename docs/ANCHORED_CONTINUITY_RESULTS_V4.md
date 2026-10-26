# 100M accepted orders on one anchored business lineage

The in-process campaign completed **100,000,000 accepted orders and 99,999,999 settled one-lot trades**. Two funding commands occur only at genesis. Every original command, execution, event, archive receipt, maintenance roll and checkpoint passed full native replay; an independent cash/inventory formula holds at every cut. All 23 raw packs are retained in the private draft release with full authenticated download verification. The final chain audit joins the exact parent-pack hash, snapshot and business sequence across all continuations.

**This is a closed-loop, in-process continuity result.** There are 22 explicit cold-continuation boundaries, with the original state restored instead of reset. It is not uninterrupted process uptime, Aeron replication, an open-loop capacity result or an end-to-end latency SLA. The requested uninterrupted replicated 30–60 minute high-rate experiment remains incomplete.

## Exact completed counters

| Quantity | Verified value |
| --- | ---: |
| Accepted orders | 100,000,000 |
| Actual settled trades | 99,999,999 |
| Funding commands | 2, at genesis only |
| Business command sequence | 100,000,002 |
| Event sequence | 200,000,001 |
| Forced/read-back maintenance cuts | 65,122 |
| Raw packs / cold continuation boundaries | 23 / 22 |
| Complete raw-pack bytes | 11,429,487,346 |

The same lineage crosses 1M in segment 0003, 10M in segment 0005 and 100M in segment 0023. The final seller has 999,999,990 quote units and no remaining base inventory; the buyer has 99,999,999 base units and no remaining quote. There are no resting orders. The price is 10 integer ticks; these are synthetic internal trades, with no external venue or funded account.

The final canonical snapshot SHA-256 is `f178d7f0a74082c2d4b47deb4a4a825ed8a470e18ded8fef281428c4233bf038`; final raw-pack SHA-256 is `a5cc1a20ea66824fd266a6453081da4405c9125cb73efe017756a4f36fc68087`.

## All original order-execution samples

The lossless frequency union contains exactly 100,000,000 order samples, excluding the two funding commands. Percentiles are recomputed from that union, never averaged across segments.

| Service-call statistic | Value |
| --- | ---: |
| p50 | 4.580 µs |
| p99 | 6.500 µs |
| p99.9 | 12.110 µs |
| Maximum | 6.415076 ms |

These timings measure the in-process business call only. External maintenance, archive verification, source pauses, network and restart gaps are outside the samples. They must not replace trading request latency. Per-segment execution/maintenance/evidence/hash elapsed sums to 2,918.001 seconds; this is a sum of separated native intervals, **not** a continuous 48.6-minute service window or sustainable offered throughput. Recorded raw-pack `FileChannel.force` calls sum to 354.100 seconds; this excludes the separate final-snapshot force and does not prove physical power-loss persistence.

## Evidence and preserved interruption

[Final chain audit](../evidence/2026-10-27/anchored-continuity-r1/CHAIN_THROUGH_100M.json), [complete counters and segment metrics](../evidence/2026-10-27/anchored-continuity-r1/CONTINUITY_RESULTS_100M.json), and [private raw asset/member indexes](../evidence/2026-10-27/anchored-continuity-r1/) bind the result. The chain auditor checks exact genesis, parent pack, snapshot transition, command sequence and cumulative count. It relies explicitly on recorded full native replay and private full-download receipts; it does not claim to repeat full business replay from thin indexes.

At 65M, the local archive controller refused insufficient local free disk. A second archive-only continuation was also refused. Both failures remain in `final-control`; the third controller continued from the already completed native boundary. No business segment was replaced or its state reset to hide the interruption. Large original packs live in private release assets rather than new Git blobs; metadata, lossless sample tables and reconstructible references remain in Git.

The [protocol](ANCHORED_CONTINUITY_PROTOCOL_V4.md) gives the exact bounded frames, funding and source-identity rules, force/readback-before-ACK fences, journal anchors, recovery and reproduction commands. The [7k/8k replicated controls](OVERLOAD_CONTROLS_V4.md) and [managed-VM recovery experiment](SNAPSHOT_RECOVERY_RESULTS_20261027.md) remain separate workloads and evidence claims.
