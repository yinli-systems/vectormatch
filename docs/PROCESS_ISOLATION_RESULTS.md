# Isolated arrival source and collector results

The matched collector intervention improves100K/s finite tails in both pairs: G1 p99=15.061/30.129ms versus Generational ZGC=0.299/1.984ms, with all500000 originals accepted per arm and no decrease in accepted in-window goodput. These are five-second same-host TCP results, not replicated or durable capacity.

Source isolation alone fixes the source clock in both100K pairs (maximum lateness25.042→3.007ms and40.853→8.051ms), but it does not establish an overall capacity improvement: the first isolated G1 arm misses5568 arrivals and correctly rejects816 dependent commands. With the source no longer paused alongside the business, stalls become real outstanding demand rather than hidden lateness. Every failure remains in the result set.

| Phase | Rate/s | Arm | Accepted | Not sent | Rejected | Full-stream p99 ms | Max source late ms | Finite gate |
|---|---:|---|---:|---:|---:|---:|---:|---|
| placement | 100000 | a1 | 500000 | 0 | 0 | 10.876 | 25.042 | fail |
| placement | 100000 | b1 | 493616 | 5568 | 816 | undefined | 3.007 | fail |
| placement | 100000 | a2 | 500000 | 0 | 0 | 22.755 | 40.853 | fail |
| placement | 100000 | b2 | 500000 | 0 | 0 | 20.417 | 8.051 | pass |
| placement | 250000 | a1 | 1241869 | 7445 | 686 | undefined | 72.343 | fail |
| placement | 250000 | b1 | 1237241 | 11981 | 778 | undefined | 9.006 | fail |
| placement | 250000 | a2 | 1225990 | 22156 | 1854 | undefined | 102.694 | fail |
| placement | 250000 | b2 | 1232128 | 16732 | 1140 | undefined | 4.007 | fail |
| collector | 100000 | a1 | 500000 | 0 | 0 | 15.061 | 3.446 | pass |
| collector | 100000 | b1 | 500000 | 0 | 0 | 0.299 | 2.361 | pass |
| collector | 100000 | a2 | 500000 | 0 | 0 | 30.129 | 3.096 | pass |
| collector | 100000 | b2 | 500000 | 0 | 0 | 1.984 | 6.649 | pass |
| collector | 250000 | a1 | 1231746 | 17532 | 722 | undefined | 3.066 | fail |
| collector | 250000 | b1 | 1236918 | 12607 | 475 | undefined | 1.133 | fail |
| collector | 250000 | a2 | 1221038 | 27314 | 1648 | undefined | 6.020 | fail |
| collector | 250000 | b2 | 1239150 | 10358 | 492 | undefined | 6.007 | fail |

All16 performance arms independently replayed the full executed order stream, fills, balances and final book.14M planned originals produced13,859,696 accepted,131,693 not sent,8,611 business rejections and0 unknown. Rejections after omitted GTC orders include valid rejection of subsequent cancel attempts; replay checks the actual received stream instead of treating every rejection as engine corruption. The finite gate requires every planned command accepted, valid20ms source timing and99% replies before the five-second deadline; it contains no latency SLA.

## What still limits250K/s

Both isolated ZGC arms still fail:12,607/10,358 not sent. The source clock is valid; peak written-awaiting-reply reaches8192 while source-queued peaks only884/499. There are no zero-byte client writes in these two arms. This localizes the credit pressure downstream of the source, but alone does not distinguish kernel queueing from business work.

The original worker rows provide the next clue: both maximum service durations occur at the exact same corpus index1,089,073, when accepted retained orders reach786,433. Their durations are82.901/74.010ms. Other long calls repeatedly coincide with49,153,98,305,196,609 and393,217 retained orders. Those are the default0.75-load-factor HashMap growth boundaries. The business client-order index is a default-sized HashMap; these native results support a resize hypothesis. This is an inference from source and exact original events, not an invented profiler stack. [OpenJDK21 HashMap implementation](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/HashMap.java) describes the threshold-triggered resize.

The8192-credit budget spans32.768ms at250K/s, shorter than either maximum call. Increasing that window would conceal the stall behind more queueing; the follow-up instead tests an explicit startup index-sizing hint with the same credit bound, business semantics, collector, CPU set and workload. No result is claimed for that follow-up here. ZGC pause receipts must not be confused with concurrent-cycle elapsed time; full GC/safepoint logs are retained.

## Reproduce and audit

The [frozen protocol](PROCESS_ISOLATION_PROTOCOL.md) and [thin closed evidence](../evidence/2026-10-27/process-isolation-r1/) bind original sources, actual JVM identities, configuration, raw members and private draft asset receipts. All20 native groups (qualification,3functional,16performance) closed. The16 performance archives contain2,706,274,084 raw bytes and774,181,741 compressed bytes; each complete authenticated download matched its pre-upload SHA-256. Raw archives remain private and do not add large Git blobs.

Run `python3 scripts/summarize-process-isolation.py evidence/2026-10-27/process-isolation-r1 --output /tmp/isolation-summary.json` to rebuild the paired conclusions and check every thin result against its original archive member hash. The [resize diagnoses](../evidence/2026-10-27/process-isolation-r1/analysis/) record verified archive/member hashes and all original worker calls above1ms in the two ZGC250K arms. Full original audits use `scripts/audit-process-isolation.py` after extracting a raw private attachment.
