# Independent fault-domain soak and recovery — measured results

The 30-minute cross-VM experiment accepted and independently reconciled **180,000 of 180,000 scheduled IOC orders**, with no business rejection, not-sent request or initial/final unknown. It **failed the registered latency and generator-timing gates**. This is correctness and observability evidence, not a passing capacity or low-latency result.

Three Azure replicas occupied provider-reported fault domains 2, 0 and 1 in France Central; an independent generator ran in Switzerland North. Each VM had 2 vCPUs/8GiB RAM. Leader 1, sync level 2, the state profile, artifact and configuration stayed fixed throughout the arrival window. The [registered protocol](PHYSICAL_SOAK_PROTOCOL_20261027.md) and [evidence index](../evidence/2026-10-27/azure-physical-r1/) describe placement and scope. Managed fault-domain placement is verified; bare-metal host identity and physical-media failure are not.

## Sustained window and bottleneck observations

The scheduled window was 2026-10-26 21:25:11.250620704 UTC to 21:55:11.250620704 UTC, at 100 planned orders/s, with 128 logical workers on one multiplexed session. All 30 minute windows and every original intent/terminal checkpoint were verified against the arrival rows. Full canonical bytes, per-reply deterministic results, asset conservation and the fixed leader passed. Native JFR streams and buffered tails were reconciled, including 4,737 generator file-write events present only in the tail; no JFR data loss was recorded.

| Metric | Observed value |
| --- | ---: |
| Scheduled-to-confirmed p50 | 56.028 ms |
| Scheduled-to-confirmed p99 | 1,378.657 ms |
| Scheduled-to-confirmed p99.9 | 6,686.163 ms |
| Scheduling lateness over 20 ms | 69,323 originals |
| Scheduling lateness p99 | 1,322.141 ms |
| Client queue delay p99 | 134.405 ms |
| Initial execute RTT p99 | 106.255 ms |
| Maximum planned but not yet confirmed | 757 |
| Accepted within the arrival window | 179,997 / 180,000 |

Component percentiles are separate distributions and must not be added. All originals eventually accepted, so the scheduled-arrival percentiles include all planned orders. Nevertheless, the generator could not maintain the registered schedule: 99.998/s in-window goodput is **not a valid capacity estimate**.

Time-weighted JFR CPU observations over the arrival window estimate 1.977 of 2 vCPUs used by the generator (154 threads), versus 0.113 vCPU by the leader (27 threads). Other replicas averaged about 0.084 vCPU each. Inside-window UDP counters recorded zero receive-buffer, send-buffer and checksum errors; these counters do not prove an absence of network delay or loss.

Disk latency also matters. Generator evidence-file force p99 was 195.495 ms, maximum 1,244.746 ms. Replica force p99 was 10.607–12.264 ms; replica 2 had an 861.292 ms maximum. Arrival-window maximum GC pauses were 45.214 ms on the generator and 28.049–29.969 ms on replicas. These are JFR observations, not independently measured physical-media flush guarantees. The [full telemetry audit](../evidence/2026-10-27/azure-physical-r1/physical-soak-r2-AUDIT.json) also reports whole-process statistics; the [resource supplement](../evidence/2026-10-27/azure-physical-r1/physical-soak-r2-RESOURCES.json) restricts statistics to the arrival window.

The evidence supports investigating client polling, dispatch and evidence-writer stalls before claiming the server reached its throughput limit. An opt-in `notify` worker wait policy has correctness tests, but its proposed Azure ABAB was **not executed** before cleanup. No improvement is claimed. This is also separate from the requested 7k/8k V4 PAUSE/CONTINUE ABAB.

## Leader process failure

After closing sustained telemetry, the same business state was restarted. The recorded leader process was killed after 25 new confirmations during a 128-order fault probe. Leadership changed from 1 to 0. All 128 originals eventually accepted; one timed-out attempt was resolved using its unchanged identity, with zero unresolved outcomes. The final canonical state hash matched the expected state.

The controller-observed upper bound to confirmed progress on the new leader was **13.828 seconds**. This includes SSH control and observation delays and is not isolated election latency or exact production RTO. The killed replica was restarted, and all three replicas subsequently wrote the same canonical snapshot hash.

## Offline volume replacement: partial recovery qualification

All writers stopped before a provider snapshot of replica 2's managed data volume. A different managed-disk resource was created from that snapshot; the original was detached and retained. After explicit mounting, **all 67 volume files matched their pre-snapshot byte counts and SHA-256 hashes**. All three restarted replicas logged the expected canonical state hash and command sequence 180,295.

The first mount command wrongly assumed an fstab entry existed. The empty underlying mount directory failed manifest comparison before writers started. This failure is retained; the correction verified the replacement attachment and filesystem UUID, mounted it explicitly and repeated the full comparison.

The subsequent full canonical read **timed out at 120 seconds**, before cached-result replay or a fresh trade. Complete cold-recovery acceptance therefore **did not pass**. A fallback probe was refused by the original launch deadline and never ran. Neither physical disk failure, power loss nor network partition was injected.

The earlier post-soak canonical read transferred 38,772,257 bytes in approximately 348.684 seconds using serial 3KiB requests. A bounded pipelined read is a separate candidate optimization; it cannot retrospectively convert this failed restore validation into a pass.

## Evidence and resource closure

The failed initial non-fresh-state soak, formal soak, fault probes, mount correction and failed recovery read are retained. Eight complete role archives and one control/source archive were uploaded to private draft release 423510304, then checked by full authenticated download and member SHA-256 verification. Git contains small receipts and reports, not another copy of the large raw data.

All four temporary VMs were deallocated, then the complete owned resource group was deleted and its absence confirmed at approximately 22:21 UTC. This removed managed disks, snapshot, IPs and networks. The prepaid Runpod CPU was untouched. The student spending limit stayed enabled; the plan allowed at most $3 of credit, with no cash authorization or subscription upgrade. This is not a final billing reconciliation.

The next acceptance gates remain: controlled client-wait and V4 maintenance ABAB, a passing same-configuration sustained latency run, full cold-restore plus cached/fresh-trade validation, and separately scoped physical/network fault tests. This result is not a production-readiness certification.

A subsequent [new-VM backup restore and snapshot-read ABAB](SNAPSHOT_RECOVERY_RESULTS_20261027.md) passed full canonical, cached-result and fresh-trade checks using the opt-in bounded reader. It uses a separate client artifact and experiment; the original failed cold-read attempt is unchanged.
