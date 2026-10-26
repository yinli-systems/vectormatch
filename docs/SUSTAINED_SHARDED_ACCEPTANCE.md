# Sustained, sharded and failure-domain acceptance

This is an implementation/experiment contract, not completed production evidence.
The user authorizes a new aggregate cloud-spend cap of USD20. The existing prepaid
CPU is separate; previous temporary GPU Pods remain stopped. Resource creation
requires a concrete qualified topology, live quote, bounded lifetime and shutdown
plan. No 6/12/24-node result is claimed before those nodes actually run.

## First sustained baseline

Two separate 30-minute fresh lineages, on the unchanged existing CPU container,
use the same Java21, three local replica JVMs, loopback UDP, fixed leader0, sync2,
2GiB heap per process, `capacity-190k-v1`, 524288-event outbox, shared/multiplexed
client with128 logical workers,64 queue slots each,2s RPC deadline/30s drain and
20ms scheduler gate. Each schedules100 one-lot IOC buys/s:180000 per repetition.
This is deliberately a low-rate uptime/telemetry baseline, not a sustained4000/s
or independent-physical-node proof. It is not a continuous100M lineage. The old
capacity entry point still rejects arrival windows above300s and retains its
state bounds; the separate soak entry point accepts30..60minutes within those
same limits. It does not fix the journal lifetime/retention boundary.

Per-original intents and terminal checkpoints are written throughout the run;
final original33-column CSV and complete canonical replay remain authoritative.
Minute windows retain exact nearest-rank P50/P99/P99.9. Any not-sent/rejected/error/
unknown makes the all-offered accepted quantiles undefined. Unfinished intervals
must not be presented as complete. Raw-ledger force duration is separately sampled;
its observer overhead is part of this instrumented cohort and does not transfer
to older short-test latency numbers. A killed client can leave unobserved outcomes
between checkpoints: reconcile original identities and durable state; do not infer
rejection or erase them. The full bounded sample fixture remains in memory; this
is not the future constant-memory100M harness.

All JVMs stream an explicit JFR event allowlist for owned-path FileForce/FileWrite,
GC and CPU, plus whole-life GC/safepoint logs and per-PID CPU/RSS/IO/pressure samples.
No environment/system-property recording is enabled. Reconcile the original
bounded final JFR tail with streamed events to cover buffered events; DataLoss,
stream failure, missing closure or incomplete coverage invalidate the corresponding
telemetry claim. Stop the NIO writer gracefully: interrupting a thread inside
FileChannel IO closes that channel. Natural client exit finalizes recording before
JVM/JFR shutdown; owned server stop first dumps its live recording. Node process
identity is pinned by boot/PID/startTicks/argv and only managed children are stopped.

Before each long trial: native short qualification, exact JAR/overlay/agent/JDK
hashes, actual loaded-class origins, capacity headroom, disk admission and no
competing Java workload are required. Complete original raw/snapshots/logs are
privately archived with full authenticated download/member-hash verification
before any task-owned originals are retired to make room for the second run.
Failed qualifications remain separate evidence. Cold restore must compare bytes,
retry an original identity and accept a fresh order; a startup log is insufficient.

## Multi-market funds and scale

Each market gets an independent book and a three-replica group. Orders, replies,
producer sequences and order IDs are scoped by market and group. A common client
clock drives the aggregate workload; aggregate throughput/latency is recomputed
from original cross-market request tapes, never multiplied from one shard.
The intended stages are2/4/8 groups:6/12/24 replica machines, plus explicitly
counted independent generator/control resources. Virtual workers or same-host
JVMs are not machine counts.

Shared-asset risk uses conserved escrow credits: reserve at the parent ledger
before sending a grant; destinations apply an identity once; acknowledge only
a committed destination result; timeout never refunds or reissues spendable
credit. Snapshots must retain pending grants, complete payload binding and retry
results. Test duplicate/conflicting grants, lost ACK, sender/destination restarts,
wrong-market/asset/group receipts and overflow, and verify total assets across
central available funds plus all books/reservations. Static prefunding is a
separate narrower capability from dynamic cross-shard transfers/portfolio risk.

## Real fault domains and RTO

A distinct Pod/boot ID alone is not physical placement evidence. Accept provider
spread/partition placement metadata or independently verifiable host inventory.
Hetzner Spread guarantees distinct host servers within a placement group, but not
independent storage pools or site isolation; [official documentation](https://docs.hetzner.com/cloud/placement-groups/faq/).
AWS rack-spread groups place instances on distinct hardware and allow at most7
per AZ; multiple spread groups do not guarantee separation between groups;
[official documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/placement-strategies.html).
Therefore24-node topology must not silently claim global spread from a single
unsupported placement choice. Storage and network failure domains need their
own evidence. Provider access/placement is a prerequisite, not a fabricated test.

Fault trials preserve a continuous lineage and distinguish JVM kill, full-instance
loss, network partition, detached/lost persistent volume and restore into empty
replacement storage. Unknowns keep their original identities. RTO starts at the
observed fault-control boundary and ends at the first confirmed fresh post-fault
order, including reconnect/reconciliation as measured. Cached replay alone does
not stop the RTO clock. Quorum-loss availability must stop, never accept divergent
orders. Archive the entire fault timeline and all failed/unobserved commands.

## Public reproducibility and research

Prepare a clean source-only export with pinned toolchain/dependencies, generated
synthetic fixtures, one-command local qualification/soak, independent auditors,
configuration fingerprints and complete failure semantics. Keep existing private
history, credentials, deployment addresses and raw archives out of the export.
Public source publication requires reviewing this concrete export; the current
private repository is not made public. An external engineer's actual clean run
is stronger evidence than an unexecuted README. Only after repeated controlled
results should a paper make claims about replication/persistence and tail latency.
