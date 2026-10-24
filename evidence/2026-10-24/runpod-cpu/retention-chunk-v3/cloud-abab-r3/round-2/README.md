# CPU chunk comparison: round2 independently closed

Round2 completed at2026-10-24T06:34:00.638432Z after root approved round1 collection. One explicitly authorized read-only collector and first native/raw/finalizer invocations passed. No benchmark was rerun by the collector, and no next cloud run or Git operation was performed.

| Result | Chunk3072(A2) | Chunk6144(B2) |
|---|---:|---:|
| All-arrival p99(s) | 8.670942044 | 4.85831607 |
| Window goodput/s | 239.765625 | 479.765625 |
| Raw last-reply drain(s) | 8.296721338 | 4.41098582 |
| Raw final-maintenance boundary drain(s) | 8.952906767 | 4.864886463 |
| Reported total source drain(s) | 8.953145844 | 4.86519524 |
| Maintenance-cycle sum(s) | 15.337593311 | 10.266799161 |
| Logical maintenance RPCs | 1785 | 1298 |
| Sampled queue high water | 3331 | 2024 |

Each arm schedules6400 arrivals at500/s over12.8s, confirms6400 distinct accepted load orders, and has notSent/rejection/initial/final UNKNOWN0 with valid scheduler timing and three maintenance cycles. Replies inside the window are3069/6141; **both remain finite overload**. Scheduled-arrival nearest-rank p99 covers every planned order and includes queue/maintenance wait. Last-reply/final-maintenance drains are independently raw-derived; total source drain is reported and ordering checked because no separate terminal raw event exists.

Complete outer closure:210files/31directories,2,512,557,963 logical bytes; `full-closed-round.tar.gz`32,299,943B SHA `3fb1cd9a6120cb2642273a19ab9810138fc4dada9ed413da9fa540acc7081b29`. The strict23-file source allowlist includes the actual approved round1 gate; PREP is never recursively archived.

Nested archive:159files/27directories,2,487,409,021 logical bytes;19,949,610B SHA `61e784558d4fb0a97afb34c2dbcea18839232d8a1b973f83523d5c2c85c5807c`. Every file has full SHA/bytes/mode/uid/gid verification and every empty directory closes against its inventory and outer rows. Sparse segments were streamed, not fully extracted. Canonical native inventory SHA is `53af747f3eb24105296e8f9160d5e9441e45addf338436805bcc01a4504e13ed`.

Actual four JARs/ZIP entries/type sources, six raw node stop reports plus normal parent exit/reap/final-absence basis, all fixed runtime arguments and both common plans pass. The exact approved round1 gate SHA `ce6b09f985646ef584e986187a85a2727443c71cc31b4b9248354c80e7745121` is bound to source bytes and before.priorRound. Original57-file three-node native state and989-file PG baseline remain unchanged according to full wrapper before/after checks, reconciled locally; this collector does not claim a second live rehash.

Raw audit independently decodes65 SHA-bound files, all6400 logical identities per arm, all physical/nested batch replies, exact requested-chunk/event CSV fields, descriptor-derived chunk counts, complete archive/writer/event bytes, ACK targets and timing. Actual logical inventories are1785/1298 with975/488 chunks,801 event fetches and nine barriers; safe prefix byte-size variation is allowed and verified. All45 bounded telemetry samples and explicit unavailable/exited records remain retained.

Actual receiver geometry/ever-seen lifecycle and per-Image counts reconcile to decoded raw reply totals. Per-callback Header/Image matching is source enforced; raw replies have no Image ID, so independent per-packet Image mapping is not claimed. Java/Python clock alignment is unvalidated and telemetry UTC phase labels are coarse. RPC timing is not pure fsync/network latency; all replicas share one CPU host.

The all-four comparison is in `../README.md` and `../comparison.json`, including two paired ratios,44 direct input SHA bindings and130 raw-audit input bindings. Cohorts remain separate fresh lineages: no pooled percentile, cumulative endurance, legacy comparison or stable-capacity promotion. The successful executed auditor source is in each audit directory and collection/collector-source; its unchanged source-only preparation and prior local failures remain in round1/local-preparation. No actual round2 audit or collection failed, so no failed benchmark/sample was discarded.
