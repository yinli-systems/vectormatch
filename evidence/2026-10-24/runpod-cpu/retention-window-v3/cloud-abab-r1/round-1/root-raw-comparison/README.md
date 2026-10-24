# Round 1 raw latency, maintenance and batch comparison

This local analysis recomputes both 6,400-row arrival CSVs and binds every row exactly once to its decoded original business request and accepted reply. It reuses the byte decoder and phase validator from the frozen preparation, whose source hashes match its manifest. The performance arithmetic, full-cycle endpoint subtraction and batch distributions are calculated by `analyze.py`, independently of runtime summary fields; summary values are only cross-checks. All 30 input files were rehashed unchanged after analysis. Native closure, original application state and PostgreSQL protection remain the separate strict collection audit's scope.

| Raw metric | Read window 1 | Read window 8 |
|---|---:|---:|
| All-arrival p99, nearest rank | 5.032984288 s | 0.774253656 s |
| Arrival-to-dispatch p99 | 5.024933563 s | 0.765671544 s |
| Successful-offer-return to reply-completion p99 | 16.732224 ms | 11.183988 ms |
| Accepted inside the 12.8s arrival window | 6,141 | 6,141 |
| Arrival-window goodput | 479.765625/s | 479.765625/s |
| Last-known-reply drain after arrival window | 4.525984569 s | 0.277586063 s |
| Total recorded maintenance-cycle wall duration | 10.615118901 s | 1.756311306 s |
| Wire-observed positive-offer awaiting first callback high-water | 1 | 8 |

All 6,400 planned identities in each arm have distinct accepted order IDs and command sequence numbers, one positive physical admission per frame, no notSent, no observed/final UNKNOWN, no replay and no rejection. The p99 reduction is 84.6164%. The recorded cycle wall total falls 83.4546%. Most of the observed delay is waiting before dispatch, consistent with shorter maintenance pauses reducing the business queue. The timestamp components' percentiles cannot be added. Neither metric is a kernel deadline or pure fsync measurement.

| Cycle | Window 1 recorded wall | Window 8 recorded wall | Logical RPCs, both |
|---|---:|---:|---:|
| 1 | 5.139549107 s | 0.880114120 s | 621 |
| 2 | 5.001950143 s | 0.754864930 s | 621 |
| 3 | 0.473619651 s | 0.121332256 s | 56 |

These wall times subtract the recorded coordinator cycle-start/end monotonic endpoints. The analysis checks their non-overlap, contiguous complete RPC ranges, first PrepareArchive, final EventAck and absence of every business physical offer across each full cycle. They include the complete coordinator cycle work, evidence and writer barriers. They are not the sums of overlapping per-RPC elapsed times. The six read-phase spans are lower bounds from earliest reservation through last coordinator reply end, not exact retained-slot/consume intervals. The raw positive-offer-to-first-callback intervals independently exhibit read overlap of eight in the treatment arm through the frozen phase validator.

| Decoded business batch size | Window 1 frames | Window 8 frames |
|---|---:|---:|
| 1 | 3,490 | 5,690 |
| 2 | 31 | 6 |
| 3 | 48 | 10 |
| 4 | 676 | 167 |
| Total business frames | 4,245 | 5,873 |
| Total orders across all frames | 6,400 | 6,400 |
| Maintenance frames | 1,298 | 1,298 |
| Total positive physical admissions | 5,543 | 7,171 |

The additional 1,628 physical admissions are exactly 1,628 additional business frames. There are no extra positive admissions or extra callbacks. The cap stays four; the treatment arm sends more partially filled batches. Shorter queueing plausibly reduces batch filling, but that mechanism was not varied as a separate factor. The maintenance inventory is identical: 488 ArchiveChunk, 801 FetchEvents and nine serialized control RPCs per arm.

This is one finite fixed-order pair (1 then 8), with the preregistered second round also 1 then 8, yielding ABAB. Preserve that order. It is not counterbalanced against systematic within-pair order or host-time drift. Both arrival-window goodputs are equal; no increase in stable500/s capacity is established. A 774ms p99 is not absolute realtime. A finite tail and trailing maintenance cycle alone cannot determine persistent queue growth. Sampled backlog is retained in the JSON but its1Hz samples can miss subsecond maintenance pauses and are not continuous maxima. Await the complete second round and root review before a combined ABAB conclusion.

The JSON contains all exact input hashes, per-arrival latency quantiles, cycle endpoints and batch totals. No SSH, workload, Java, Git or source mutation was performed for this analysis.
