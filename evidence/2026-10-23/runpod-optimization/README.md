# Controlled client MediaDriver comparison

**The registered driver-count comparison is complete: sharing the load MediaDriver reduces resource use, while 15k offered commands/s remains nonstable in both modes.** The two formal A/B pairs deliver 14,176.579/14,336.211 and 14,192.132/14,552.921 accepted confirmations/s respectively: shared goodput is 1.126% and 2.542% higher, but neither shared window passes the unchanged stability criteria. Scheduled p99 is lower in both shared rounds, yet dropped arrivals in three of the four formal windows prevent an all-offered latency guarantee. All favorable and unfavorable results remain visible.

This campaign changes one load-generator factor: 128 independent client MediaDrivers (`isolated`, A) versus one shared client MediaDriver (`shared`, B). Both modes keep 128 independent Aeron clients, 128 cluster sessions, 128 worker threads and at most one synchronous request per worker. The original capacity evidence remains historical context; this comparison uses the same new load artifact and observers in both modes. It does not establish a new maximum stable rate or attainment of any 100-million-scale target.

## Frozen identities and controls

The [frozen identity receipt](frozen-load-and-observer.json) records:

| Component | Fixed identity |
|---|---|
| Three matching nodes | `b6f6c5cd165110e330d409e2ff51ee4574a3720b` |
| Node bundle SHA-256 | `0c17626c6aed8061a71915e4dd784887ed9221f7fb3ba56d7fbf1f96985c062d` |
| Both load-generator modes | `bdfe09a2907d9b953309e9e870d6f61f28c5e054` |
| Load bundle SHA-256 | `0afb2570dbfdfe6c11b43a68f18135b9e21e4c0efd79a66a8e5996f0f6f4f6c4` |
| Read-only attribution observer identity | `b51226cc3902e77e457836e2ea2545b71fe7b1722caa7da9ee0630f118aa5dee` |
| Prepared core SHA-256 | `2247db9c15b0043a0b28172c5bfa2d9e4f20b5748f6a16424d881e296102655f` |

The [isolated campaign](isolated/campaign.json) and [shared campaign](shared/campaign.json) fix leader 0, sync level 2, Aeron 1.53.3, MTU 1248, 2 GiB node and load heaps, 128 allowed sessions, 64 FIFO slots per worker, 2-second initial execute timeout, 30-second post-window drain and a 20 ms scheduler-lateness validity limit. Each member starts fresh independent test state. The load generator shares member 2; gateway, PostgreSQL projection and subscriber fanout are excluded.

Both modes use the same `extended-190k-128` workload and explicit `capacity-190k-v1` node state profile: 64 funded buyer accounts, 380,000 maker lots, 1,900,000,000 quote units per buyer, 100 excluded warmup IOC buys, maximum 190,000 measured arrivals, 200,000 retained orders, 100,000 cached results, per-producer cache 1,024, outbox 524,288 and full-checkpoint bound 512 MiB. Every measured accepted command is a one-lot IOC buy producing one trade. The absolute arrival scheduler, round-robin worker/producer assignment, account sharing, queue limits, request identities, leader handling, retries and unknown resolution remain unchanged. Constructor concurrency remains eight and both 12-second session-reclamation waits remain outside measurement.

The strict opt-in property is `vectormatch.capacity.client.driver=isolated|shared`; omission selects isolated. Shared mode requires egress port 0 so clients retain independently resolved response endpoints. Setup and validation clients still use their original independent drivers. The load owner closes the shared driver only after workers terminate; client closure and failed client connection do not close the borrowed driver. Each successful trial records `clientDriverMode`, its actual connected-load `clientDriverCount` and `clientAeronMode=one-independent-Aeron-per-client` in configuration and result artifacts. A planned mode alone is not evidence that it ran.

## Validation and observer scope

The [isolated source-build receipt](tool-validation/java-tests.json) records 109 tests with zero failures or skips from committed `bdfe09a` source. These include real three-node borrowed-driver ownership/failure, independent Aeron/session/response-endpoint checks and existing bootstrap/identity/capacity regressions. A successful local build is not itself a cloud capacity measurement.

The initial attribution-tool deployment failed before measurement because its controller flattened the required `scripts/tests` hierarchy. The [failure receipt](tool-validation/attribution-initial-deploy-failure.json) retains the exact missing path, failed source and correction; it reports zero capacity arrivals sent. Corrected content-identified deployment receipts for [node 0](tool-validation/attribution-node0.json), [node 1](tool-validation/attribution-node1.json) and [node 2](tool-validation/attribution-node2.json) each pass 14 Linux tests and a three-second read-only live smoke. The failed packaging attempt is not a benchmark result and is not hidden.

The same new observer runs in both A and B. It records verified PID/start-time identities, per-thread CPU and available scheduling data, plus UDP socket queues/drops joined to owned file-descriptor inodes. Missing/restricted/zero scheduling statistics cannot prove no waiting. Socket and process samples are asynchronous; namespace UDP errors cannot identify a particular socket without the ownership evidence. Kernel accounting bytes are not packet counts. Collector elapsed/CPU costs must accompany comparisons because observing more threads/sockets can itself cost more work. No packet capture, attach, kernel setting or live socket-buffer change is part of this factor.

The [socket-buffer capability probe](socket-buffer-capability.json) used fresh short-lived sockets, sent zero packets and changed no cluster setting. Linux returned 262,144 bytes for a 131,072-byte receive-buffer request and 2,097,152 for 1,048,576 on those probe sockets. Those observations are not effective-buffer attestations for later Aeron sockets and are not a second optimization applied to this campaign.

## Registered order and assessment

The [registered plan](plan.json), frozen before the first load, dispatches a short shared-driver smoke and then alternating A/B/A/B at 15k offered commands/s:

| Order | Trial | Mode | Offered /s | Planned arrivals | Planned window s | Purpose |
|---:|---|---|---:|---:|---:|---|
| 1 | `o-smoke-shared-8000-w128` | B, shared | 8,000 | 20,000 | 2.500 | Wiring/correctness smoke; cannot meet >=10s stability rule |
| 2 | `o-isolated-15000-w128-r1` | A, isolated | 15,000 | 190,000 | 12.667 | Control 1 |
| 3 | `o-shared-15000-w128-r1` | B, shared | 15,000 | 190,000 | 12.667 | Shared-driver 1 |
| 4 | `o-isolated-15000-w128-r2` | A, isolated | 15,000 | 190,000 | 12.667 | Control 2 |
| 5 | `o-shared-15000-w128-r2` | B, shared | 15,000 | 190,000 | 12.667 | Shared-driver 2 |

Planning entries are not measured results. Any adaptive extension must be registered after the preceding complete evidence, with its configuration boundary retained. Historical b6f-load trials are not substituted for the new A controls. The same >=10-second minimum window, state/configuration/leader validity, >=95% in-window accepted goodput, no admission loss/reject/error/unknown, bounded backlog growth and drain criteria remain in force. There is no implied latency SLO; p99 is reported separately.

For each completed run, independently stream every arrival CSV row. Recompute accepted confirmations inside the integer-nanosecond arrival window, conditional scheduled-to-confirmed p99, API RTT and worker execution-through-resolution occupancy. Waiting FIFO capacity is not extra in-flight capacity. Keep never-sent, initial unknown, resolved and unresolved outcomes distinct. All-offered accepted p99 is null if any offered command is dropped, rejected, errored or unresolved. Confirmations during drain cannot inflate in-window goodput. Compare every paired round and retain variation rather than selecting a best result.

## Completed observations

The first exported smoke is valid, with passing canonical-state, configuration and fixed-leader/term checks; it is correctly classified `INSUFFICIENT_WINDOW` for stability because the arrival window is only 2.5 seconds. It is not an A/B capacity result. All four complete 15k windows are valid but nonstable. Shared goodput is slightly higher in each paired observation, but both shared rounds fail drain/backlog criteria, and the first shared round drops arrivals. The registered A/B/A/B repetitions are all retained.

| Raw trial | Mode / actual load drivers | Offered /s | Arrivals | Window s | In-window accepted goodput /s | Scheduled p99 ms | Client not sent | Initial unknown / unresolved | Drain ms | Scope |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| [o-smoke-shared-8000-w128](shared/runs/o-smoke-shared-8000-w128/) | shared / 1 | 8,000 | 20,000 | 2.500 | 7,978.800 | 17.224 | 0 | 0 / 0 | 7.874 | Valid smoke; insufficient stability window |
| [o-isolated-15000-w128-r1](isolated/runs/o-isolated-15000-w128-r1/) | isolated / 128 | 15,000 | 190,000 | 12.667 | 14,176.579 | 664.706 conditional | 2,200 | 0 / 0 | 635.988 | Valid; admission, goodput and drain criteria fail |
| [o-shared-15000-w128-r1](shared/runs/o-shared-15000-w128-r1/) | shared / 1 | 15,000 | 190,000 | 12.667 | 14,336.211 | 575.981 conditional | 451 | 0 / 0 | 585.641 | Valid; admission, backlog growth and drain criteria fail |
| [o-isolated-15000-w128-r2](isolated/runs/o-isolated-15000-w128-r2/) | isolated / 128 | 15,000 | 190,000 | 12.667 | 14,192.132 | 623.971 conditional | 1,986 | 0 / 0 | 623.372 | Valid; admission, goodput, backlog growth and drain criteria fail |
| [o-shared-15000-w128-r2](shared/runs/o-shared-15000-w128-r2/) | shared / 1 | 15,000 | 190,000 | 12.667 | 14,552.921 | 440.259 | 0 | 0 / 0 | 450.614 | Valid; backlog growth and drain criteria fail |

Every one of the smoke's 20,000 raw CSV rows is accepted; 19,947 confirm in the arrival window and 53 during drain. Independently recomputed goodput and nearest-rank scheduled p99 match the result. Mean initial API RTT is 7.127287 ms, API p99 16.525303 ms and mean execution occupancy 56.938052/128 slots (44.4829%). Per-worker occupancy is 43.087–45.901%, mean API RTT 6.9205–7.3559 ms and window confirmations 155–156. Configuration and result both record `shared`, one load driver and independent per-client Aeron. Cloud CSVs do not expose individual Aeron client IDs; independent Aeron/session/response-endpoint separation is covered by local regression tests, not claimed as a cloud wire-identity capture.

Only one or two complete interior telemetry intervals are available in this short window, so they provide diagnostics rather than a capacity comparison. The verified load process has 294–300 sampled threads and a 394,403,840-byte RSS peak within the window; all three namespace UDP error counters remain unchanged. Node-2 attribution collection costs 51.681–77.773 ms wall time and 51.680–70.422 ms CPU per sampled collection in this window. Those costs and the smoke's smaller 20k sample allocation prevent comparison of its resource peaks directly against a 190k control. The short smoke is not substituted for a full-window 15k shared comparison.


The first new isolated 15k control contains 190,000 raw arrivals: 187,800 finally accepted, 179,570 confirmed inside the window and 2,200 explicitly never sent because a worker FIFO is full. Those counts reproduce 14,176.578948/s goodput. Initial unknowns, unresolved outcomes, business rejections and server errors are zero; scheduler timing, canonical state, configuration and leader/term checks pass. Scheduled p99 is 664.705655 ms conditional on accepted confirmations; all-offered accepted p99 is null. The registered stability rule fails no-admission-loss, >=95% goodput and bounded drain; 635.988 ms drain is outside the 126.667 ms limit. Peak sampled queue depth is 7,892 and peak outstanding 8,020. The fitted second-half growth remains within its separate bound, which does not override the other failures.

Initial API RTT for this A control averages 9.040423 ms, with 15.275189 ms API p99. Average occupied slots are 127.930809/128 (99.9459%); every worker is between 99.906% and 99.982%, mean worker API RTT spans 8.8192–9.1733 ms, in-window confirmations 1,383–1,439 and FIFO drops 0–36. This is near-continuous occupation across workers, not a slow single worker. Configuration and result record `isolated` and 128 actual connected-load drivers. The same-new-artifact paired rounds establish whether changing driver count improves this deployment; the historical cohort does not replace these controls. The [attribution audit](analysis/attribution-summary.json) uses 13 complete interior collections and twelve adjacent pairs for this A round, with no selected thread/FD/table gap, error or truncation. Load CPU averages 9.11586 cores; 128 kernel-truncated `/opt/vectormatc` TIDs combine approximately 6.74167 cores and 128 `capacity-worker` TIDs 1.91834 cores. A truncated thread name alone does not prove a Java driver-role mapping. Verified node-2 process telemetry samples 420–424 load threads and a 6,755,016,704-byte load RSS peak. Strict interior collections show median file-backed RSS of 6,025.86 MiB, so most observed residency is file-backed; the 2 GiB heap is not an RSS limit. The attribution audit observes 256 owned UDP sockets. A matched owned follower-1 LOG socket at port 23104 adds 186 drops; matched node-0/node-2/load socket-drop counters do not increase. One-second queue samples cannot establish burst maxima. Observer collection CPU averages 0.05028/0.01557/0.07925 cores on nodes 0/1/2, with maximum collection wall costs 59.20/17.04/96.82 ms. These observational details accompany, rather than replace, the paired outcomes.


The first full-window shared round contains 190,000 raw arrivals: 189,549 finally accepted, 181,592 confirmed inside the window and 451 explicit FIFO drops. Goodput independently recomputes to 14,336.210527/s and scheduled conditional p99 to 575.981291 ms; all-offered accepted p99 is null. Unknowns, unresolved outcomes, business rejections and server errors are zero, while source/configuration/state/leader checks and scheduler timing pass. Its 585.641 ms drain exceeds the 126.667 ms bound. Fitted second-half outstanding growth is 2,519.295 commands, above 1,900, with peak sampled queue depth 7,750 and peak outstanding 7,878. The separate >=95% goodput criterion passes, but admission loss, growth and drain fail; B is still nonstable.

B1 mean initial API RTT is 8.923473 ms and API p99 15.450210 ms. Occupied slots average 127.928171/128 (99.9439%), and all workers span 99.901–99.987% occupancy, 8.8617–9.0390 ms mean RTT, 1,400–1,429 window confirmations and 0–21 FIFO drops. Configuration/result record one shared load driver. Comparing the complete A1/B1 configuration objects finds exactly three differing fields: `startedAt`, `clientDriverMode` and `clientDriverCount`; prepared state and all other values match. In this first pair, B goodput is approximately 1.126% higher and conditional scheduled p99 13.35% lower, while both configurations remain nonstable. This single pair does not establish repeatability or a higher stable arrival rate. The second pair below repeats the same modes and source, and remains nonstable in both cases.


The first formal pair nevertheless shows a substantial resource reduction under the same 190k workload. The [attribution summary](analysis/attribution-summary.json) restricts deltas to complete verified interior collections; A has twelve seconds of adjacent-pair coverage and B has twelve seconds on nodes 0/1 and eleven on node 2/load. Selected identity, thread, descriptor and socket reads have no reported gaps/errors/truncation.

| First 15k pair: load resource | A1 isolated | B1 shared |
|---|---:|---:|
| Mean process CPU cores | 9.11586 | 4.35545 |
| Enumerated load threads in attribution audit | 420 | 293 |
| Owned UDP sockets | 256 | 129 |
| Median resident memory MiB | 6,366.34 | 520.66 |
| Peak resident memory MiB | 6,442.09 | 597.84 |
| Path-name thread group: TIDs / combined CPU cores | 128 / 6.74167 | 1 / 0.87454 |
| Worker thread group: TIDs / combined CPU cores | 128 / 1.91834 | 128 / 3.02636 |
| Node-2 observer mean collection CPU cores | 0.07925 | 0.04703 |
| Node-2 observer maximum collection wall ms | 96.82 | 52.30 |

The approximately 52.22% lower load CPU and much lower file-backed residency are observed resource improvements in this first pair, not an achieved higher stable arrival rate. The kernel-truncated path-name thread group changes from 128 TIDs to one, consistent with the configured driver factor; a truncated name alone does not uniquely identify an internal Java object. Worker count remains 128, and its combined CPU increases while total load CPU decreases. Observer work is also lower when fewer threads/sockets are scanned and is reported rather than assumed free.

Server pressure remains: leader CPU is 2.54333 versus 2.53250 cores, and its top path-name TID occupies approximately 0.9633 versus 0.9575 core. Consensus CPU is approximately 0.740 versus 0.742 core, while service CPU is 0.1425 versus 0.1525. The owned follower-1 LOG socket adds 186 versus 126 drops; other matched owned socket-drop counters do not increase. These observations identify useful next hypotheses, but do not uniquely prove a server driver, core or storage limit. The repeated pair below tests whether this resource pattern recurs; near-full occupation of a thread alone does not establish that it is the unique bottleneck.


The repeated isolated control A2 also fails stability while retaining valid source/state/configuration/leader and scheduler evidence. Its 190,000 raw arrivals contain 188,014 accepted commands and 1,986 FIFO drops. Exactly 179,767 confirm in the window, independently reproducing 14,192.131580/s; scheduled conditional p99 is 623.971256 ms, all-offered accepted p99 null and drain 623.372 ms. Unknowns, unresolved outcomes, rejections and server errors remain zero. This round fails admission, >=95% goodput, drain and fitted backlog growth (3,584.433 commands versus 1,900), with peak sampled queue depth 8,043 and outstanding 8,171. Its configuration differs from A1 only in `startedAt`.

A2 initial API RTT averages 9.024808 ms, API p99 14.220094 ms and occupied slots 127.893343/128 (99.9167%). Per-worker occupancy is 99.567–99.986%, mean API RTT 8.9075–9.1027 ms, window confirmations 1,393–1,421 and FIFO drops 0–26. Both isolated control rounds therefore remain near continuously occupied under the unchanged 128-slot synchronous window. The second shared round completes the registered A/B/A/B comparison below. A2 attribution over approximately eleven strict interior seconds reproduces the isolated resource pattern: load CPU 8.82819 cores, 420 enumerated threads, 256 owned UDP sockets, median/peak RSS 6,343.13/6,419.93 MiB, and 128 path-name TIDs combining 6.58089 cores. Its matched follower-1 LOG socket adds 148 drops; a later absolute socket counter must not replace this measurement-window delta. Node-2 observer collection averages 0.07869 CPU core with 90.19 ms maximum wall time, and selected reads report no gaps/errors/truncation.


The final shared round B2 accepts all 190,000 scheduled commands, with no FIFO drop, rejection, error, initial unknown or unresolved outcome. Exactly 184,337 confirm inside the window (14,552.921053/s) and 5,663 during 450.614 ms drain. Scheduled p99 is 440.259014 ms; because every offered command is accepted with a confirmed result, this round's all-offered accepted p99 is also defined at that value. B2 remains nonstable: drain exceeds 126.667 ms and fitted second-half backlog growth is 1,960.997 commands versus the 1,900 limit. Sampled peak queue depth is 5,382 and peak outstanding 5,510. Passing no-loss and >=95% goodput checks does not override failed drain and growth.

B2 mean initial API RTT is 8.767121 ms, API p99 15.387919 ms and occupied slots average 127.929579/128 (99.9450%). Workers span 99.903–99.980% occupancy, 8.7118–8.8304 ms mean RTT and 1,426–1,451 window confirmations. B1/B2 configuration objects differ only in `startedAt`; A2/B2 differ only in time, driver mode and count. In pair 2, B goodput is 2.542% higher and returned-command scheduled p99 29.44% lower than A, but A's missing arrivals mean this is not a paired all-offered p99 guarantee. Every formal window keeps almost all 128 synchronous slots occupied, so this experiment has not removed the path's finite-window saturation.

## Reconciliation and conclusion

Independent streaming of all five CSV files reconciles 780,000 scheduled arrivals to 775,363 final accepted executions and 4,637 explicit client-FIFO not-sent arrivals. Accepted results split into 745,213 confirmations inside arrival windows and 30,150 during drain. Per-run goodput and nearest-rank p99 reproduce the result artifacts, with floating-point rounding only. All five windows pass source/configuration/state/leader validity; the short smoke has insufficient duration and all four formal 15k windows fail the registered stability rule. No failed round is removed, and the no-drop B2 window is not relabeled stable.

The observed benefit is lower load-generator resource use with modest finite-window goodput changes; a higher stable arrival rate is unproven. This remains a fixed 128-in-flight client + replicated matching path on shared hardware, excluding HTTP, projection and fanout. Correctness replay uses the same `MatchingEngine` in actual command-sequence order and is supplemented by asset/order/event checks; it is not an independent matching algorithm. Future socket-buffer, driver-threading, shared-Aeron or pipeline changes require separately identified controls and must not be pooled into this driver-count comparison.

## Unmet scale targets

The three goals in the registered plan are separate and remain unverified: 100,000,000 cumulative unique accepted commands, 100,000,000 unique accepted commands per second, and 100,000,000 simultaneous connections. The experiment currently configures 128 sessions. A finite-window throughput or sum of executions across fresh isolated trials does not satisfy any of those goals. Business identities are intentionally repeated across fresh trial lineages for preparation/comparison; those totals cannot be presented as one globally deduplicated 100-million-command run.

The total project cloud budget remains USD 20, with no new resources planned and a reserved recovery allowance. Launch-time/rate estimates in trial receipts are not a reconciled provider invoice. No capacity or target attainment is inferred from available budget or a planned run.
