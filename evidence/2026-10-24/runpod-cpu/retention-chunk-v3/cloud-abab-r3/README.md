# CPU chunk-size ABAB: four closed finite cohorts

Both ordered pairs show lower scheduled-arrival p99 and higher fixed-window goodput with6144-byte chunks. All four remain finite overload observations at500 offered orders/s; this does not establish stable capacity or authorize a performance promotion.

| Cohort | Chunk | Accepted within12.8s | Window goodput/s | All-arrival p99(s) | Raw last-reply drain(s) | Maintenance(s) | RPCs | Sampled queue high water |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 | 3072 | 3069 | 239.765625 | 7.368829634 | 7.012967443 | 13.978515761 | 1785 | 2989 |
| B1 | 6144 | 6141 | 479.765625 | 4.888360956 | 4.408074524 | 10.321075933 | 1298 | 2486 |
| A2 | 3072 | 3069 | 239.765625 | 8.670942044 | 8.296721338 | 15.337593311 | 1785 | 3331 |
| B2 | 6144 | 6141 | 479.765625 | 4.858316070 | 4.410985820 | 10.266799161 | 1298 | 2024 |

Each cohort has6400 distinctly accepted synthetic load orders, zero notSent/rejected/initial or final UNKNOWN, valid scheduler timing and three maintenance cycles. P99 is nearest rank over **all6400 planned arrivals**, from the scheduled arrival to complete reply, independently recalculated from each CSV and matched to the full decoded raw audit. No percentile is pooled across cohorts.

| Paired treatment versus control | P99 reduction | Fixed-window goodput ratio | Maintenance-duration reduction |
|---|---:|---:|---:|
| B1 versusA1 | 33.66% | 2.000978 | 26.16% |
| B2 versusA2 | 43.97% | 2.000978 | 33.06% |

The actual maintenance inventory is1785/1298/1785/1298 logical RPCs:975/488 chunk reads,801 event reads and nine serial Prepare/ACK barriers per cohort. Exact descriptor/offset/hash assembly, immutable writer bytes, event continuity and ACK targets pass for every prefix. The chunk read count falls by487; event fetch count stays fixed. Caller RPC timing includes scheduling, transport, recorded/quorum commit, service, reply and evidence writes; these totals do not identify pure fsync cost.

All four use source `e3c4885a8854c3edfbfdea4848633efc75951894`, actual code fingerprint `68943a1eb48e2da1d4ef99d10b2717b112b5e698e6c87db2fa9c8b25ae5dbd14`, profile `732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68`, frozen release SHA `5d8bd210f5f7e78cb421a1dc80f3367ecee07e90bcba9a54c6c0a88db05a92c7`, business batch4, W128/Q64, pending128, leader0/term0, sync2, ports42000, MTU1248, event page16 and one common finite admission envelope. The selected chunk and fresh lineage/time origins are the intended differences. Actual JAR/class-source, process, native archive and unchanged protected original57-file/989-file PG checks pass in each round.

Actual receiver Image lifecycle/geometry and association counters are reconciled with complete raw reply totals. The raw tape has no Image-ID field: per-callback actual Header/Image validation is source enforced and independently checked at the aggregate level. No ingress-default receiver geometry or independent packet-to-Image reconstruction is claimed.

Each round preserves the full closed JOB and strict staged source allowlist, complete outer/nested file SHA/bytes/mode/uid/gid/empty-directory closure, raw tapes, CSVs, telemetry and actual artifacts. Round2 includes the approved prior-collection gate and its before.priorRound binding; it did not run until root independently approved round1. Per-round local completion receipts, native/raw audit reports and full inventories remain in `round-1` and `round-2`. `comparison.json` includes every exact comparison input SHA plus all130 raw-audit input bindings (65 per round), paired ratios, full RPC kind metrics, queues, three drain definitions and explicit limitations. The builder and execution receipt are retained in `comparison-build-r1`.

Only two ordered repetitions were observed, with no randomization or confidence interval. Both6144 cohorts still complete only6141 of6400 replies inside12.8s and require additional drain. Four fresh lineages are four separate finite observations; they do not prove cumulative endurance,100M orders/s,100M connections,100M retained orders, zero latency, independent-host durability or a sustained500/s SLA. No legacy cohort is mixed into this comparison.
