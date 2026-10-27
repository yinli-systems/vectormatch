# V4 asynchronous maintenance at 7,000 and 8,000 planned orders/s

All eight finite overload runs passed raw-order, financial, physical-order replay, snapshot and three-node cold-restore checks. **All eight failed their finite capacity gates.** CONTINUE increased in-window goodput in both pairs at each rate, but did not eliminate queue saturation or missing planned orders. No stable 7k/8k capacity, global accepted-arrival p99 or default performance promotion is established.

[Prospective protocol](OVERLOAD_CONTROLS_V4.md) · [All exact measurements, source bindings, phase analysis and private raw references](../evidence/2026-10-27/overload-r2/comparison/COMPARISON.json).

## Same-environment ABAB

Each rate ran PAUSE A1, CONTINUE B1, PAUSE A2, CONTINUE B2 in that order. All eight use source `a9f21f1fc408bd70f09a231c55d33ad3a5093926`, bundle SHA-256 `199941e7fd69fd661017963ffe1987c053c455c3193be162dccc6aaf9e8e9b98`, the same host/boot, leader 0, sync 2, three 256MiB replicas, 768MiB client heap, 127 active producers, queue 64 per producer, batch 4, cut 1536, read window/page 32 and archive chunk 6144. The source passed 27 targeted Linux tests before native execution. Those tests are not a fresh full-project CI run.

The 20-second open-loop arrival clock never pauses for maintenance. Each arm has fresh state, followed by drain, independent raw audit and actual three-node cold restore. Compilation, replay, compression and upload run outside arrivals. Complete raw private assets were authenticated-downloaded and all manifested original members verified before the next native point. These are three UDP JVMs on one CPU host, not independent physical nodes.

| Planned/s | Arm / policy | Accepted / planned | In-window goodput/s | Not sent | Accepted-only p99 ms | Post-first-offer p99 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 7,000 | A1 / PAUSE | 114,055 / 140,000 | 5,299.05 | 25,945 | 1668.845581 | 15.721348 |
| 7,000 | B1 / CONTINUE | 124,396 / 140,000 | 5,831.95 | 15,604 | 1445.487166 | 14.000969 |
| 7,000 | A2 / PAUSE | 112,416 / 140,000 | 5,222.25 | 27,584 | 1664.956830 | 14.150057 |
| 7,000 | B2 / CONTINUE | 122,178 / 140,000 | 5,700.75 | 17,822 | 1509.874963 | 15.221064 |
| 8,000 | A1 / PAUSE | 112,654 / 160,000 | 5,227.15 | 47,346 | 1650.296908 | 14.294265 |
| 8,000 | B1 / CONTINUE | 120,529 / 160,000 | 5,624.75 | 39,471 | 1547.680020 | 15.462112 |
| 8,000 | A2 / PAUSE | 111,037 / 160,000 | 5,145.45 | 48,963 | 1661.442260 | 14.623642 |
| 8,000 | B2 / CONTINUE | 122,116 / 160,000 | 5,700.75 | 37,884 | 1486.568493 | 14.849818 |

All-arrival accepted p99 is **undefined in every arm** because some planned orders were never sent. The two displayed p99 columns are conditional distributions and exclude missing planned acceptances; they cannot replace global request latency. Accepted counts include confirmations after the arrival window; goodput counts only confirmations inside it. Server rejection and observed/final UNKNOWN are zero in all eight arms. Every scheduler passes its registered timing gate.

| Rate/s | Pair | CONTINUE goodput change | Not-sent reduction | Post-first-offer p99 change |
| --- | --- | ---: | ---: | ---: |
| 7,000 | 1 | +10.057% | 39.857% | -1.720379 ms |
| 7,000 | 2 | +9.163% | 35.390% | +1.071007 ms |
| 8,000 | 1 | +7.606% | 16.633% | +1.167847 ms |
| 8,000 | 2 | +10.792% | 22.627% | +0.226176 ms |

Three of four candidate post-first-offer p99 measurements worsen. None of the four pairs can pass the registered global-latency criterion. Two repeats do not establish statistical significance. Do not average these percentiles into a combined p99.

## Recorded waiting and maintenance phases

The trace analyser verifies each complete original archive SHA, member SHA, frame sequence, phase continuity and exact clipping to the arrival interval. The following times are coordinator-state exposure, not CPU utilization, device service time or a causal allocation of each request's latency.

| Point | Phase permits new business (s) | Archive + event reads (s) | Verification + file wait (s) |
| --- | ---: | ---: | ---: |
| 7000-a1 | 8.199649 | 6.158003 | 2.296343 |
| 7000-b1 | 8.587694 | 6.458484 | 3.419372 |
| 7000-a2 | 8.261105 | 6.014591 | 2.357638 |
| 7000-b2 | 8.738031 | 6.397450 | 3.181692 |
| 8000-a1 | 8.146440 | 6.076864 | 2.452653 |
| 8000-b1 | 8.868117 | 6.229780 | 2.991403 |
| 8000-a2 | 8.168480 | 6.032947 | 2.470294 |
| 8000-b2 | 8.745526 | 6.436838 | 3.323535 |

PAUSE allows new business only in IDLE; CONTINUE also allows it in VERIFY_WAIT and FILE_WAIT. A permitted phase may still encounter exact-cut, pending-command or retention-credit limits. Read banks remain exclusive and preserve the original command/event bounds and pre-ACK safety fence. No force/readback or destructive acknowledgement check was removed.

Sampled queued requests reach 8,091–8,128 against the 8,128 total active queue bound. Accepted-only planned-to-first-offer p99 is 1.437–1.660 seconds, whereas post-first-offer p99 is 14.001–15.721 milliseconds. These are separate distributions: subtracting their percentiles would not produce a per-request attribution. The source scheduler p99 is 58.947–163.082 microseconds. Mean CPU over fully interior sample intervals is 1.156–1.320 cores for the parent, 0.830–0.958 for the leader, and 0.588–0.668 for each follower. These means do not rule out busy individual threads or force/wakeup stalls.

The evidence prioritizes bounded dispatch during immutable historical reads and safe reduction of maintenance/control round trips. Enlarging queues alone could conceal overload while increasing wait; adding cores alone is not justified by these observations. Earlier bounded-read/direct-export experiments had mixed post-offer tails and remain separate failed promotion tests. A new candidate needs its own same-artifact control and all original correctness fences.

## Completion and remaining scope

This campaign retains 1,200,000 planned arrivals, including every not-sent outcome. The original failed 120k ledger-admission attempt is preserved separately and is not a ninth performance point. The corrected A1 was not rerun after local archive admission and timestamp-parser failures; only collection/analysis resumed on its unchanged original bytes. All eight native groups closed before final offline phase analysis.

The [completed 100M lineage](ANCHORED_CONTINUITY_RESULTS_V4.md) is in-process with 22 explicit cold-continuation boundaries. The [managed-VM replacement recovery](SNAPSHOT_RECOVERY_RESULTS_20261027.md) proves a different recovery path. Neither supplies the still-missing uninterrupted 30–60 minute replicated V4 experiment at high rate. That requires integrating the anchored journal into the replicated adapter and bounded streaming arrival/evidence rotation, followed by fresh correctness and endurance qualification. This overload report supplies no millisecond SLA, hard-realtime guarantee, physical media failure certification, HFT endorsement or external funded-trading result.
