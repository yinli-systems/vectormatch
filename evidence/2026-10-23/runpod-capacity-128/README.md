# Fixed-node 64/128-client capacity audit

**Completed six-window cohort.** The controlled 64/128-client comparison demonstrates a client-window effect around 8,000 offered commands/s. The highest observed >=10-second stable window is one 10-second W128 run at 9,000/s. The unchanged 128-client path also tracks offered 10k and 12k rates in shorter windows, while 16k causes substantial queue loss, delay and leader-namespace UDP receive errors during 5.625 seconds. These are finite-window observations, not an unconstrained matching-engine or production capacity SLA. No round is omitted. A later 190k/state-limit/2 GiB-member experiment is a separate cohort and cannot be silently pooled with these measurements.

## Reproducible comparison boundary

The three member JVMs keep node revision `8b4bea3f37d623cd08f7c26ea4b5f6506fc3c5bd`, bundle SHA-256 `f6dbda4354c000edb3b3250ab4867ddd005c9875758055cb2280972102a45034`. Only the separately identified load-generator distribution uses revision `ed273d53dffe1e4aa5c95086f59fccc4a25cea4d`, bundle SHA-256 `2453411fdf27123d4aa7ad92b78f13003523932e3a933bef717b17a260a3a97c`. Both W64 and W128 controls use that same new load generator and the `extended-90k-128` profile. The older extended campaign is retained as prior evidence, not silently pooled into this controlled cohort.

Fixed settings: appointed leader 0; sync level 2; Aeron 1.53.3; MTU 1248; 1 GiB member heaps; 2 GiB load-generator heap; 128 server sessions; 262,144-event outbox; 64 queued requests per worker; 2-second initial execute timeout; 30-second post-window drain; 20 ms scheduler-lateness validity limit; SHARED driver/archive threading and default BackoffIdleStrategy; 131,072-byte send/receive socket buffers. The load generator shares member 2. Each fresh trial has 64 buyer accounts, 900,000,000 quote units per buyer, one 180,000-lot maker and 100 excluded warmup IOC commands. Measured commands are independent one-lot IOC buys, one accepted order and one trade event each.

The prepared core bytes have SHA-256 `bcd308591d3aef73744f7516977061afc170135ea773fd1bfcd182a57eaf7915` in all completed controls. Each worker owns an independent producer and sequential request identity. Workers 64–127 share buyer accounts through `worker % 64`; producer identities remain distinct. Final buyer checks aggregate by actual account ID, not worker index. Constructor parallelism is limited to eight; all connected workers keep their sessions alive and participate concurrently during measurement.

There are two explicit 12-second waits, after setup closes and after every worker closes before validation connects. These waits permit session reclamation under the default 10-second session timeout. They are outside arrival, completion-goodput and validation timing. Every run retains `session-reap-after-setup.json`, `session-reap-before-validation.json`, `validation-start.json` and `validation-timing.json`.

Source and transfer evidence: [node manifest](deployment-manifest.json), [load-generator manifest](loadgen-deployment-manifest.json), [load transfer receipt](loadgen-upload-receipt.json), [recorded configuration checks](configuration-verification.json), [registered controls](control-plan.json), [registered high-rate windows](high-rate-plan.json), and [adaptation rationale](ADAPTATION.md). Per-run `trial.json`, `load-process.json`, node process records, configuration-verification and fixed-leader checks identify the actual recorded commands. These records do not attest physical host isolation or permanent storage durability.

## Completed controls

| Raw run | Clients | Offered /s | Window s | Confirmed within window /s | Scheduled-to-confirmed p99 ms | Queue drops | Initial unknown / final unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|
| [z-control-8000-w64](runs/z-control-8000-w64/) | 64 | 8,000 | 11.25 | 7,839.022 | 373.620 | 0 | 0 / 0 |
| [z-control-8000-w128](runs/z-control-8000-w128/) | 128 | 8,000 | 11.25 | 7,993.956 | 24.149 | 0 | 0 / 0 |
| [z-control-9000-w128](runs/z-control-9000-w128/) | 128 | 9,000 | 10.00 | 8,992.400 | 22.755 | 0 | 0 / 0 |

All three controls have 90,000 raw arrival rows. Goodput above was independently recomputed by counting accepted rows with `confirmed_offset_ns <= arrivalWindowNs` and dividing by that window, exactly matching the published results. All three have valid generator timing, zero business rejects/server errors, no unresolved outcomes, canonical/asset/outbox verification, and unchanged observed leader/term. The W64 window fails the preregistered finite-window stability criteria because backlog/drain remain elevated; no failed or invalid point is hidden. The two W128 controls satisfy the criteria in their single observed windows. This cohort has one run per control/rate and no boundary repetitions. It establishes these observed windows; it does not establish repeatability or the long-window transition above 9k. The separately registered longer-window cohort addresses that next.

## Slot occupancy, recomputed from every request

A synchronous worker can execute one logical request at a time. Its FIFO is a waiting queue, not extra service concurrency. For each worker, sum the intersection of its `[execute_started_offset_ns, confirmed_offset_ns]` intervals with `[0, arrivalWindowNs]`. Divide that occupied duration by the window for worker utilization; summing across workers gives average occupied request slots. Unknown resolution, if present, must retain the entire interval rather than treating its first timeout as a completed request. These controls contain no initial unknowns, so initial API RTT and logical execution occupancy coincide.

| Run | Mean initial API execute ms | Initial API p99 ms | Mean occupied slots | Slot utilization | W / mean execute, requests/s |
|---|---:|---:|---:|---:|---:|
| W64 @ 8k | 8.090664 | 11.230764 | 63.444809 / 64 | 99.13% | 7,910.35 |
| W128 @ 8k | 8.024660 | 13.179622 | 64.173708 / 128 | 50.14% | 15,950.83 |
| W128 @ 9k | 7.892454 | 13.684734 | 70.998779 / 128 | 55.47% | 16,218.02 |

`W / mean execute` is an accounting-derived hypothetical window ceiling under the same observed mean RTT, perfect balance and no extra worker overhead. It is not an independent estimate of server capacity: RTT itself can grow with load, and workers share CPU/network resources with member 2. The occupancy sum is recomputed from every recorded interval; the once-per-second `backlog.csv` counters are separate non-atomic observations.

The 64-client run almost completely occupies every available synchronous slot. Doubling the slots preserves a similar mean API RTT and removes most scheduled queueing at the same offered load, while the 128-client pool is only half occupied. This directly supports a bounded client-window/FIFO explanation for the earlier roughly 8k limit. It does not establish that the matching core, storage, network or whole replicated path has reached its limit.

Worker balance cross-checks:

| Run | Per-worker mean API RTT ms, min–max | Per-worker slot utilization, min–max | Confirmations within window per worker, min–max |
|---|---:|---:|---:|
| W64 @ 8k | 7.9590–8.2166 | 98.76%–99.42% | 1,356–1,401 |
| W128 @ 8k | 7.9075–8.1595 | 49.41%–50.99% | 702–703 |
| W128 @ 9k | 7.7853–8.0272 | 54.71%–56.36% | 702–703 |

No single exceptionally slow worker explains the control result. The raw per-worker identities, execution intervals and outcomes remain in each run's `arrivals.csv`; `backlog.csv` records one-second queue observations and `result.json` records aggregate transport counters.

## High-rate windows and interpretation

The unchanged fixture allows at most 90,000 measured arrivals. Thus 10,000/s, 12,000/s and 16,000/s produce 9.0, 7.5 and 5.625-second windows. These are useful overload observations under exactly the same node/load profile, but **cannot satisfy the preregistered minimum 10-second stable-window criterion**. An analyzer's valid-but-nonstable classification for a short window must not itself be described as overload: inspect goodput deficit, queue loss, positive backlog growth, drain and conditional latency separately. All three registered high-rate observations have completed. Each retains 90,000 raw arrival rows and must remain separate from the >=10-second stable-window claim.

| Raw short-window run | Window s | Confirmed within window /s | Scheduled-to-confirmed p99 ms | Mean API execute ms | Average occupied slots / 128 | Drops / unknown / unresolved | Drain s |
|---|---:|---:|---:|---:|---:|---:|---:|
| [z-screen-10000-w128](runs/z-screen-10000-w128/) | 9.000 | 9,990.111 | 30.144 | 8.404431 | 83.995855 / 128 (65.62%) | 0 / 0 / 0 | 0.010593 |
| [z-screen-12000-w128](runs/z-screen-12000-w128/) | 7.500 | 11,984.667 | 40.047 | 8.535808 | 102.328420 / 128 (79.94%) | 0 / 0 / 0 | 0.009344 |
| [z-screen-16000-w128](runs/z-screen-16000-w128/) | 5.625 | 10,515.378 | 1,108.435 | 12.465692 | 127.882580 / 128 (99.91%) | 22,575 / 0 / 0 | 1.078317 |

All three have valid scheduling, fixed-leader evidence and successful state validation. The 10k and 12k points have no observed queue loss or substantial drain. Their short duration alone prevents the >=10-second stable-window label; neither currently demonstrates a material goodput deficit, queue loss or substantial drain. The per-worker occupied fractions are 64.61–66.57% at 10k and 78.84–80.69% at 12k, with 702–703 confirmations inside the window per worker. Occupancy therefore remains balanced rather than depending on a single blocked worker. The arithmetic `W / mean API execute` values are approximately 15,230/s and 14,996/s respectively; those are observed-window accounting figures, not promises of future throughput.

The 16k result is a positive overload observation for this deployed client+cluster path, despite its short duration: 67,425 commands were finally accepted and 22,575 were explicitly never sent because client queues were full (25.083% of offered load). Of the accepted commands, 59,149 confirmed inside the arrival window and 8,276 confirmed during drain. The all-offered accepted-command p99 is therefore **unknown/null**; 1,108.435 ms is conditional on the 67,425 accepted confirmations. Initial API execute p99 also grows from 14.278 ms at 12k to 56.999 ms at 16k, alongside the mean increase, so the higher scheduled delay is not merely a relabeling of unchanged transport latency.

The once-per-second queue depth rises to 4,341 at approximately 1 second and 8,153 near 2 seconds, close to the 128 × 64 = 8,192 waiting-queue bound. By that second sample, 4,807 requests have already been dropped. Near 5 seconds, the sampled queue still holds 8,127 requests and cumulative drops reach 18,767. Per-worker slot utilization is 99.836–99.984%, with 162–194 queue drops per worker. All worker windows are saturated; a single blocked worker does not explain the aggregate loss. These queue samples are non-atomic observations, separate from the interval-based occupancy recomputation.

The full six-point cohort accounts for 540,000 scheduled arrivals: 517,425 accepted commands and 22,575 explicit queue-full never-sent outcomes, zero initial unknowns/final unresolved outcomes, and zero business rejections/server errors. Every run has a successful canonical, invariant, balance and pending-outbox audit. Stability classification still follows the original minimum-window rule; a short valid window is never promoted to >=10-second stable capacity.


Retain all rounds. A meaningful short-window instability observation needs a working generator and fixed leader/term, correct final state, a material arrival-window goodput deficit or bounded-queue loss, and a consistent queue/drain signature. Repeat the boundary at least twice with the same configuration. Positive evidence of queue loss remains useful in a short window; the absence of loss does not establish a >=10-second stable rate. One-second backlog sampling also leaves very few second-half observations in a five-second test, so a fitted slope alone is weak evidence.

The default audit criteria are in [analysis/summary.json](analysis/summary.json): at least 10 seconds, >=95% arrival-window goodput, bounded second-half backlog growth, bounded drain, no drops/rejects/errors/unresolved outcomes, valid scheduling/configuration/state and fixed-leader evidence. No default p99 SLO is imposed. P99 is scheduled-to-confirmed and conditional on confirmed commands. Where any offered command is dropped or unresolved, an all-offered accepted-command p99 cannot be inferred from surviving samples.

### Resource observations for the controls

The following CPU values were independently recomputed from verified process user+system CPU-tick deltas divided by each collector's monotonic elapsed seconds. Only full one-second intervals whose wall-clock samples lie inside the approximate recorded arrival window are included; this is observational alignment, not synchronized one-way timing.

| Run | Load process mean CPU cores | Leader process mean CPU cores | Load threads observed | Load peak RSS GB | Leader private-interface transmit Mbps |
|---|---:|---:|---:|---:|---:|
| W64 @ 8k | 7.142 | 1.981 | 228–230 | 3.438 | 39.57 |
| W128 @ 8k | 9.833 | 2.475 | 420–421 | 6.605 | 40.79 |
| W128 @ 9k | 10.458 | 2.378 | 420–423 | 6.603 | 45.56 |
| W128 @ 10k, short | 9.699 | 2.399 | 420–422 | 6.600 | 50.56 |
| W128 @ 12k, short | 9.178 | 2.502 | 420–423 | 6.607 | 60.71 |
| W128 @ 16k, short | 8.616 | 2.482 | 420–424 | 6.565 | 54.31 |

The member-2 quota is 23.8 cores and the leader quota is 5.1 cores. Across the three control windows, all three cgroups have zero additional throttled periods/time; cumulative historical throttling is not a per-window result. Private-namespace UDP `InErrors`, `RcvbufErrors` and `SndbufErrors` also have zero measured-window increments. The 2 GiB load heap is not a 2 GiB process-RSS limit: many embedded media drivers, mappings, threads and native allocations add resident memory. At 16k the leader network namespace records **+1,302 UDP `InErrors` and +1,302 `RcvbufErrors`** inside the observed interior measurement interval; these are overlapping error counters, not 2,604 separate losses. Other member namespaces record zero corresponding increments, as do all nodes at 10k and 12k. The leader CnC interior-window counters also report +25,036 NAKs sent, +4,353 NAKs received and +310 retransmits sent; these transport-event counts must not be added to kernel packet errors or interpreted as unique lost commands. They support receive/repair-path pressure, while accepted business requests can still complete with no final unknowns. All six windows show zero additional cgroup throttle periods/time in the measured interior intervals.

The 16k CPU estimates use only four complete leader and five complete load-process sample intervals; they are coarse. The namespace receive error is a direct observation, but without socket-level drops, packet capture, GC/scheduling traces or isolated generator placement it does not uniquely identify a specific application socket or causal mechanism. No transport bandwidth ceiling or pure-engine CPU limit was established by these observations. Raw per-node records are `nodeN-telemetry.jsonl`; process identity checks and thread counts are retained with every sample.

CPU/quota, telemetry, transport counters and packet/error deltas can help bound explanations, but this experiment has no isolated load-generator machine, CPU profiling, packet trace, storage latency trace or synchronized one-way timestamps. Low aggregate CPU does not exclude a hot single thread; lack of quota throttling does not prove spare per-core execution capacity. Any later 190k/state-limit/heap experiment must be a separate cohort, with overlap controls rather than being merged into this one.


## Audit and interpretation summary

- Controlled concurrency result: W64 at 8k saturates its synchronous window; W128 at the same rate largely removes scheduled queueing while mean API RTT stays near 8 ms. This is evidence of the earlier client-window constraint.
- Highest eligible observed stable window in this cohort: W128 at 9k for 10 seconds, once. This is a demonstrated finite window, not a repeated sustained service promise.
- Short observations: 10k/9s and 12k/7.5s track arrivals without loss; 16k/5.625s exhibits explicit queue loss, near-full windows, worsened API RTT and leader-namespace receive-buffer errors. There is no tested >=10-second upper transition in this cohort.
- The 16k point constrains this fixed end-to-end path; it does not isolate the matching core from embedded clients, UDP, replication, archive sync, scheduling or shared-host effects.
- Reproduce the analysis using the repository's `scripts/analyze-capacity.py` against this cohort's `runs/`. Raw per-arrival timing, backlog, complete CnC observations, telemetry, exact configurations, session waits and canonical snapshots remain beside each linked run. Preserve invalid and failed rounds in any future extension.
