# Three fault domains, independent generator and recovery

This campaign is separate from the anchored in-process V4 endurance run and the finite V4 PAUSE/CONTINUE capacity comparisons. The completed observations, failed gates and resource closure are in [the results report](PHYSICAL_SOAK_RESULTS_20261027.md). Its predeclared workload is 100 scheduled IOC orders/s for 1,800 seconds, with 128 logical clients, one multiplexed Aeron client session, fixed observed leader, sync level 2 and the unchanged `capacity-190k-v1` state profile. No setting changes during the arrival window. Every original intent, reply/unknown outcome and terminal checkpoint is retained.

## Placement and measurement

Three Azure managed VMs in France Central have observed fault-domain assignments 2, 0 and 1 in one aligned availability set. The fourth VM generates load from Switzerland North over privately peered networks. Each VM has 2 vCPUs and 8GiB RAM. Replica 0/1 and the generator use D2s_v4; replica 2 uses D2ds_v4. The latter's local temporary disk is not used. Each replica stores state on its own 32GiB StandardSSD_LRS managed data disk with host caching `None`. All guests run the same pinned Ubuntu image and installed Java 21.0.12.1 build.

The provider inventory and instance-view responses must accompany the evidence. Distinct IP addresses alone do not attest physical placement. The placement audit checks all three distinct provider fault domains, the common availability set and the separate generator region. It does not claim bare-metal host identities or independent providers.

Scheduled-arrival p50/p99/p99.9 include client queueing, transport, replicated execution and confirmation. Per-minute windows, backlog, all rejected/not-sent/unknown originals, process CPU/IO/pressure, GC and native JFR FileForce events are retained. Native buffered JFR tails are reconciled with streamed events without discarding multiplicity. The existing 25ms p99 and 100ms p99.9 gates are unchanged. Crossing them is a failed latency gate, even if all business results remain correct. Cross-region network RTT is included; there is no one-way latency claim.

## Separate fault phases on the same business state

1. Complete the arrival window and full canonical replay. Gracefully close the measured process generation and its telemetry before fault injection.
2. Restart the same persisted state. Continue with 128 fresh capacity-fixture orders using `FaultWindowProbe`, with 100ms planned spacing. Force each original intent and every reply/unknown attempt to the evidence tape. After at least ten confirmed trades, kill only the recorded leader child. Retry a timed-out request with its exact original identity; unresolved outcomes stop later identities. Require the complete expected post-fault state hash.
3. Restart the failed replica and require all three replicas to snapshot the same canonical core state. Stop all owned writers. Hash every file on replica 2's data volume, unmount it, create a provider snapshot, create a **different managed disk resource** from that snapshot, detach the original and attach the replacement. Keep the original disk until final cleanup. Before starting any writer, require every restored file to match the offline manifest.
4. Restart all replicas. Verify full canonical bytes, an original cached result without duplicate execution, and a fresh settled trade. The full-byte recovery client runs on replica 0 over the replica-region network; it is outside the sustained performance window and shares that VM's CPU.

This is a process-crash test plus a **planned offline volume replacement/backup restore**. It does not inject a physical disk/media failure, power loss or network partition. A successful replacement cannot be relabelled as those missing tests. Controller-observed recovery bounds include SSH signalling/observation, provisioning, startup and verification overhead; they are not isolated election latency or exact production RTO.

## Retention and cleanup

Only uniquely owned lab resources are in scope. The prepaid Runpod CPU is untouched. The plan permits no new cash charge or subscription upgrade; the student spending limit remains on. Planned credit usage is capped at $3 with a two-hour compute estimate plus storage/network reserve.

Stopped evidence is streamed into per-role archives, checked against complete member SHA-256 manifests, uploaded to the existing private draft release and checked again by full authenticated download. The control/source/provider records are archived separately, excluding authentication caches, keys and parameter input. Only after those proofs close does the controller delete the entire tagged resource group, including disks, snapshots, public IPs and networks, and check that it no longer exists. A local deadline guard stops compute at 22:20 UTC if evidence is still open; independent provider shutdown is configured for 22:30 UTC. Preserved disks must still be collected and deleted if the guard takes that fallback.
