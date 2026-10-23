# Controlled node UDP receive-buffer comparison

**The receive-buffer comparison is complete: actual node receive limits increase as intended and the selected follower LOG socket stops dropping, but 15k remains nonstable in all four windows.** The 128 KiB controls have 218/205 strictly interior matched LOG-socket drops; both 1 MiB rounds have zero. Goodput changes by +0.934% and −4.616% in the two pairs, and returned-command scheduled p99 improves in neither pair. The unchanged control itself varies substantially, so these observations do not prove a unique cause of a performance regression or a higher stable capacity.

Both network modes use the same new node artifact and the same shared-driver load generator. Earlier b6f-node results remain historical context, not replacement controls. The experiment supports retaining the 131,072-byte request as the control for a separate threading test, while preserving the demonstrated reduction in selected socket drops as a distinct result.

## Fixed identities and changed factor

The [registered plan](plan.json) changes only the node MediaDriver receive-buffer request, from 131,072 bytes (`receive128k`, A) to 1,048,576 bytes (`receive1m`, B). Driver/archive threading, send-buffer request, idle strategies, leader, durability setting, workload and client resources remain fixed. The plan was registered after all four formal driver-count outcomes; those outcomes and their hashes remain in the plan rather than being discarded.

| Component | Identity / fixed value |
|---|---|
| Node source for both A and B | `071029fb1f3c1718b15a8850eb531783677674fe` |
| Node bundle SHA-256 | `fac70db5c98d7d8e03de737e68552bdf606acfe540afbfcba7c8658884ebddd3` |
| Load source for both A and B | `bdfe09a2907d9b953309e9e870d6f61f28c5e054` |
| Load bundle SHA-256 | `0afb2570dbfdfe6c11b43a68f18135b9e21e4c0efd79a66a8e5996f0f6f4f6c4` |
| Attribution observer identity | `b51226cc3902e77e457836e2ea2545b71fe7b1722caa7da9ee0630f118aa5dee` |
| Actual-socket probe SHA-256 | `29eaef020c644e9f64384c0b1773a5b4ede25326552b2cf6c68bf61799ebaf50` |
| Prepared core SHA-256 | `2247db9c15b0043a0b28172c5bfa2d9e4f20b5748f6a16424d881e296102655f` |

The [node release](node-release.json), [node artifact manifest](node-deployment-manifest.json), per-run process arguments/startup logs and configuration verification establish the deployed identities. A source identifier alone is not proof of what executed. Each run uses leader 0, sync level 2, Aeron 1.53.3, MTU 1248, 2 GiB node/load heaps, SHARED driver/archive threading, existing Backoff idle defaults, 131,072-byte send-buffer request and 128 maximum sessions. No global sysctl or new Pod is part of this factor.

The load remains `shared` with one client MediaDriver, 128 independent Aeron clients/sessions/workers and one synchronous request per worker. Each worker has a 64-slot FIFO. Requests retain the same business identities, retries, 2-second initial execute timeout, 30-second drain and 20 ms scheduler-lateness validity limit. The client socket-buffer setting does not change in this node-only experiment. Setup and validation remain outside measurement, including the two 12-second session-reclamation waits.

Both modes use fresh state with `extended-190k-128` / `capacity-190k-v1`: 190,000 maximum arrivals, 64 identically funded buyers, one 380,000-lot maker, 100 excluded warmup commands, one one-lot trade per measured accepted IOC, 200,000 retained-order limit, 100,000 cached results, cache per producer 1,024, outbox 524,288 and full-checkpoint bound 512 MiB. The matching rules, account assignment, absolute arrival scheduler and leader/durability configuration remain unchanged. This remains the direct client + replicated matching path, excluding HTTP, PostgreSQL projection and subscriber fanout.

## Actual socket-buffer evidence

Each run retains `socket-buffer-before.json` and `socket-buffer-after.json`. The read-only probe filters ingress/log ports, verifies the explicit node PID/start time/command hash, joins stable file-descriptor/socket inodes before and after collection, and archives only owned selected socket fields. It reads actual Linux `ss` kernel-memory `rb`/`tb` limits rather than substituting requested values or results from a separate throwaway socket. Linux accounting commonly doubles requested buffer values; these limits are kernel accounting bytes, not exact payload capacity.

For the first 128 KiB control, all selected live ingress sockets and both follower log sockets show receive/send kernel limits of 262,144/262,144 bytes before and after the run, with matching node identities and socket inodes. A leader log receive socket is not invented when none exists in the filtered result. The node-0 `SS_CGROUP2_MOUNT_METADATA_WARNING` is preserved as a probe diagnostic; the explicit PID/inode joins and buffer reads pass. The first 1 MiB round independently attests 2,097,152-byte receive and unchanged 262,144-byte send kernel limits on all selected ingress/follower-log sockets before and after its run, with matching owned identities and socket inodes.

Pre/post probe times encompass preparation, load and validation. A log-socket counter changing from 0 to 218 across the first control's probes does not by itself establish a 12.667-second load-window drop count. Strict interior attribution deltas are needed to isolate measurement-window observations. Neither an empty sampled queue nor zero drops in the selected sockets proves an entirely loss-free network.

## Registered order and assessment

| Order | Trial | Node receive request bytes | Offered /s | Planned arrivals | Planned window s |
|---:|---|---:|---:|---:|---:|
| 1 | `n-r128k-15000-w128-r1` | 131,072 | 15,000 | 190,000 | 12.667 |
| 2 | `n-r1m-15000-w128-r1` | 1,048,576 | 15,000 | 190,000 | 12.667 |
| 3 | `n-r128k-15000-w128-r2` | 131,072 | 15,000 | 190,000 | 12.667 |
| 4 | `n-r1m-15000-w128-r2` | 1,048,576 | 15,000 | 190,000 | 12.667 |

Plans are not measured results. Preserve every dispatched round, including invalid scheduler timing, unknowns and unfavorable outcomes. The existing criteria remain: complete source/configuration/state/leader validation, at least ten seconds of arrivals, >=95% in-window accepted goodput, no client-not-sent/reject/error/unknown, bounded drain and bounded fitted second-half backlog growth. There is no implicit latency SLO. A finite passing window would not establish indefinite capacity.

For each complete trial, independently stream every arrival row and recompute accepted confirmations within the integer-nanosecond window, nearest-rank scheduled-to-confirmed p99, initial API RTT and per-worker execution-through-resolution occupancy. FIFO capacity is not extra in-flight capacity. Keep drain confirmations separate from arrival-window goodput. If any arrival is not accepted with a confirmed outcome, report returned-command p99 as conditional and all-offered accepted p99 as null. Unknown is not a business rejection. Identical identities must be resolved before advancing a producer.

## Completed observations

| Raw run | Requested / observed node receive bytes | Window accepted goodput /s | Scheduled p99 ms | Accepted / scheduled | FIFO not sent | Initial unknown / unresolved | Drain ms | Classification |
|---|---|---:|---:|---:|---:|---:|---:|---|
| [n-r128k-15000-w128-r1](receive128k/runs/n-r128k-15000-w128-r1/) | 131,072 / 262,144 | 14,215.816 | 623.427 conditional | 188,261 / 190,000 | 1,739 | 0 / 0 | 493.570 | Valid; admission, goodput, growth and drain fail |
| [n-r1m-15000-w128-r1](receive1m/runs/n-r1m-15000-w128-r1/) | 1,048,576 / 2,097,152 | 14,348.605 | 631.623 conditional | 188,926 / 190,000 | 1,074 | 0 / 0 | 465.073 | Valid; admission and drain fail |
| [n-r128k-15000-w128-r2](receive128k/runs/n-r128k-15000-w128-r2/) | 131,072 / 262,144 | 14,602.974 | 408.282 | 190,000 / 190,000 | 0 | 0 / 0 | 454.672 | Valid; growth and drain fail |
| [n-r1m-15000-w128-r2](receive1m/runs/n-r1m-15000-w128-r2/) | 1,048,576 / 2,097,152 | 13,928.921 | 619.682 conditional | 184,210 / 190,000 | 5,790 | 0 / 0 | 592.137 | Valid; admission, goodput and drain fail |

Every first-control CSV row is accounted for: 188,261 commands are finally accepted, 180,067 confirm in the 12.666666666-second arrival window and 1,739 are explicitly `CLIENT_QUEUE_FULL_NOT_SENT`. These counts independently reproduce 14,215.815790/s goodput and 623.427290 ms scheduled conditional p99. All-offered accepted p99 is null. Initial unknowns, unresolved outcomes, business rejections and server errors are zero. Scheduler timing and source/configuration/state/leader checks pass.

The first control fails four stability checks: admission loss, >=95% in-window goodput, drain (493.570 ms versus 126.667 ms allowed) and fitted second-half growth (2,857.125 commands versus 1,900 allowed). Peak sampled queue depth is 8,129 and peak outstanding 8,257. The result is valid evidence of a nonstable path, not a server-rejection count or an invalid generator run.

Mean initial API execute RTT is 8.933680 ms and API p99 14.200664 ms. Mean occupied slots are 127.929009/128 (99.9445%), with worker occupancy 99.900–99.984%, mean RTT 8.8754–8.9929 ms, 1,397–1,416 window confirmations and 5–22 FIFO drops. The first control therefore retains near-continuous occupation across workers. The other three completed observations below are also nonstable. No network-buffer capacity improvement is inferred from the control or earlier driver experiment.


The first 1 MiB round contains all 190,000 raw arrivals: 188,926 accepted commands, 181,749 confirmations inside the arrival window and 1,074 FIFO drops. Independent recomputation gives 14,348.605264/s goodput and 631.623298 ms scheduled conditional p99; all-offered accepted p99 is null. Initial unknowns, unresolved outcomes, business rejections and server errors are zero, and source/configuration/state/leader and scheduler checks pass. Admission and drain fail stability: 465.073 ms drain remains above 126.667 ms. Fitted second-half growth of 1,035.713 commands is within its separate 1,900-command bound. Peak sampled queue depth is 8,134 and peak outstanding 8,262.

The 1 MiB round's mean initial API RTT is 8.872137 ms, API p99 13.723362 ms and mean occupied slots 127.929116/128 (99.9446%). Worker occupancy spans 99.902–99.985%, mean RTT 8.7989–8.9356 ms, window confirmations 1,409–1,431 and FIFO drops 0–19. Load configuration objects differ from the first control only in `startedAt`, as expected for a node-only buffer factor; the changed requested node setting and actual live buffer values are retained in separate node/process/probe artifacts.

In this first pair, 1 MiB goodput is approximately 0.934% higher but scheduled conditional p99 is slightly worse, with both modes nonstable and all synchronous slots almost continuously occupied. The selected 1 MiB sockets have zero drop-counter increments over the whole before/after probe interval, while the control's follower log counter increases. That interval also includes validation, so it cannot substitute for interior measurement-window drop deltas or prove that network loss caused the throughput difference. The repeated control and final 1 MiB round below complete the registered comparison and retain this variation.


Independent [interior attribution](analysis/attribution-summary.json) now provides a measurement-window comparison, rather than relying on the broad pre/post interval. It matches node identity, file descriptor and socket inode across adjacent fully interior collections: the owned follower-1 LOG socket at port 23104 adds 218 drops in A1 and zero in B1. Other matched node/load socket-drop deltas are zero. The matching number 218 is independently derived here; equality with the later probe counter is not used as the method. Strict adjacent-pair coverage is approximately twelve versus eleven seconds, with selected raw/tool hashes verified.

| First network pair | A1: 128 KiB request | B1: 1 MiB request |
|---|---:|---:|
| Observed selected socket receive limit bytes | 262,144 | 2,097,152 |
| Observed selected socket send limit bytes | 262,144 | 262,144 |
| Follower-1 matched LOG socket interior drop increment | 218 | 0 |
| Leader top path-name TID CPU cores | 0.95673 | 0.96637 |
| Leader process CPU cores | 2.5450 | 2.5854 |
| Load process CPU cores | 4.1550 | 3.9775 |
| Enumerated load threads / owned UDP sockets | 293 / 129 | 293 / 129 |
| Median load RSS MiB | 540.48 | 539.53 |
| Leader CnC NAKs sent / retransmits | 104 / 4 | 241 / 0 |

The larger receive buffer coincides with zero matched socket drops in this pair, while NAKs remain and the path is nonstable. Socket drops and CnC counters measure different scopes and must not be added as lost commands or treated as equivalent. Leader hot-thread occupation remains near one core, and low receive-error counts do not establish a unique server limit. Archive counter 107 write-path wall-time ratios are approximately 0.3883/0.4113 on node 0, 0.9884/0.9894 on node 1 and 0.9790/0.9774 on node 2; these include the observed path's wall time and are not isolated disk/fsync latency. Recorder counter 106 rates are approximately 2.73–2.76 MB/s. These observations accompany the retained correctness, goodput, queue and drain results; they do not substitute for those outcomes or demonstrate a storage bottleneck.


The repeated 128 KiB control A2 accepts all 190,000 scheduled arrivals, with zero FIFO drops, rejections, errors, initial unknowns or unresolved outcomes. Exactly 184,971 confirmations land inside the window, independently reproducing 14,602.973685/s; the remaining 5,029 confirm during 454.672 ms drain. Scheduled p99 and all-offered accepted p99 are both 408.281502 ms. This no-loss window is still nonstable: drain exceeds 126.667 ms and fitted second-half backlog growth is 2,914.995 commands versus 1,900. Peak sampled queue depth is 4,989 and peak outstanding 5,117. Source/configuration/state/leader and scheduler validation passes, while before/after actual selected socket limits remain 262,144/262,144 bytes.

A2 initial API RTT averages 8.750910 ms, API p99 13.366380 ms and occupied slots average 127.799920/128 (99.8437%). Worker occupancy is 99.637–99.984%, mean RTT 8.6911–8.8348 ms and window confirmations 1,426–1,456. Load configuration differs from A1 only in `startedAt`. The unchanged control itself gains approximately 2.72% goodput and reduces scheduled p99 by approximately 34.5% between repetitions, exceeding the first pair's small 0.934% goodput difference. Small buffer-associated throughput changes must therefore not be over-attributed to the setting.

Strict A2 attribution covers approximately twelve seconds on nodes 0/2 and eleven on node 1, with no selected identity/read/truncation/socket gaps. Its owned follower-1 LOG socket adds 205 measurement-window drops, rather than the later post-probe absolute counter 330. Zero client-not-sent and complete accepted business outcomes therefore do not imply zero UDP receive drops. Leader process/hot-TID CPU is approximately 2.61418/0.96010 cores; load CPU is 3.89918 cores with 293 enumerated threads, 129 owned UDP sockets and 544.69 MiB median RSS. Leader CnC counters add 563 NAKs sent and three retransmits (65,280 bytes); node 1 sends two NAKs. Archive write-path wall-time ratios remain high on followers, but those ratios are not isolated storage latency. The final 1 MiB repetition below completes the comparison.


The final 1 MiB round B2 contains all 190,000 raw arrivals: 184,210 accepted commands, 176,433 confirmations inside the window and 5,790 explicit FIFO drops. Independent recomputation gives 13,928.921053/s goodput and 619.681569 ms scheduled conditional p99; all-offered accepted p99 is null. No initial unknown, unresolved outcome, business rejection or server error occurs. Source/configuration/state/leader and scheduler checks pass, while admission, >=95% goodput and drain fail. Drain is 592.137 ms versus 126.667 ms allowed. Peak sampled queue depth reaches 8,177 and outstanding 8,305. Fitted second-half growth is zero after the queues saturate and admissions drop; that flat trend cannot establish stability.

B2 mean initial API RTT is 9.179369 ms, API p99 15.412789 ms and occupied slots average 127.930283/128 (99.9455%). Worker occupancy spans 99.903–99.989%, mean API RTT 9.1129–9.2981 ms, window confirmations 1,360–1,389 and FIFO drops 36–63. Its load configuration differs from B1 only in `startedAt`. All selected actual socket receive/send limits remain 2,097,152/262,144 bytes before and after, and matched interior socket-drop deltas are zero. A/B node-configuration objects differ only in the requested receive-buffer fields; source, send buffer and remaining fixed settings match.

B2 strict attribution covers twelve seconds/twelve adjacent pairs per host, with no selected identity/read/truncation/socket gaps. Load CPU is 3.96417 cores, with 293 enumerated threads, 129 owned UDP sockets and 528.72/595.99 MiB median/peak RSS. Leader total/hot-TID CPU is 2.51667/0.96005 cores, consensus CPU 0.74338 and service CPU 0.14835. Leader CnC counters add 758 NAKs sent and one retransmit (4,608 bytes); node-2 counters add one NAK sent, eight received and one 64-byte retransmit. Thus zero matched socket drops does not imply zero transport recovery. Archive write-path wall-time ratios remain 0.39001/0.98914/0.97135 across nodes 0/1/2, with recorder rates approximately 2.687–2.689 MB/s. Node-2 observer cost is 0.04774 CPU core and 62.60 ms maximum collection wall time. The attribution receipt verifies all 62 raw-input hashes and tool identities.

## Reconciliation and interpretation

Independent streaming of all four CSV files accounts for 760,000 scheduled arrivals, 751,397 final accepted executions and 8,603 explicit client-FIFO not-sent arrivals. Accepted results split into 723,220 confirmations inside the arrival windows and 28,177 during drain. Every per-run goodput and nearest-rank scheduled p99 reproduces its result artifact within floating-point rounding. Prepared state, node source and load source match across all rounds; fixed leader/term, configuration, canonical snapshot and asset/order/event checks pass. Correctness replay uses the same `MatchingEngine` implementation in actual command-sequence order, not an independent matching algorithm.

All four windows remain nonstable. The larger node receive buffer repeatedly eliminates observed drops on the selected follower LOG socket, but does not produce a passing 15k window or a lower returned-command p99 in either paired comparison. Goodput changes direction between pairs, and unchanged controls already vary by more than the first pair's difference. Two pairs do not establish a causal performance regression. They support a narrower result: the selected receive-overflow symptom is reduced, while client + replicated-path saturation remains. All four windows occupy almost all 128 synchronous slots, and the leader hot TID remains near one core; those observations do not uniquely isolate a bottleneck.

The next independent threading comparison can therefore use the original 131,072-byte receive request as its explicit control, avoiding an unproven combined throughput/latency optimization. This does not erase the 1 MiB socket-drop result or rule out a useful interaction in another separately registered configuration. No matching rule, durability setting, rejection count or validation criterion is weakened to make a round pass.

The total project budget remains USD 20 with no new resources. Trial budget receipts are launch-time/rate estimates rather than reconciled billing. The separate 100-million cumulative-unique-command, commands-per-second and simultaneous-connection goals remain unmet; these fresh finite-window trials cannot be pooled into a globally unique 100-million-command run.
