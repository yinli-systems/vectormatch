# Cloud testing: Runpod campaign, USD 20 ceiling

On 2026-10-23, this project deployed three Runpod GPU Pods in the same supported Global Networking region. Native private IPv4 UDP, normal matching, two repaired-client leader-failure trials and repeated all-JVM cold restart passed their recorded checks. A second 900-command matching run, restored outbox projection, HTTP business smoke, three WebSocket state frames and SQL ledger continuity were then verified. The actual resource choices, measured limits, storage profile and detailed evidence are recorded in [RUNPOD_LAB.md](RUNPOD_LAB.md). Offline backups are complete. The user chose to retain all three Pods for another six hours; services are UP on the original state, synthetic flow is paused, and Pod billing continues.

## Confirmed measurements

| Experiment | Recorded result | Scope |
|---|---|---|
| Private UDP full mesh | 18,000 request/echo roundtrips; zero observed loss, duplicates or reordering | Six ordered pairs; 200 requests/s per active path; authenticated raw IPv4 UDP |
| UDP payload / path | DF probes at 96, 512 and 1248 payload bytes; private interface MTU 1300 | Largest tested IPv4 datagram, including UDP/IP headers, was 1276 bytes |
| Pooled UDP RTT | p50 0.653665 ms; p99 1.298711 ms; max 39.338844 ms | All 18,000 returned samples; client monotonic clock; no one-way measurement |
| Initial replicated matching | 900 measured commands, 300 trades, 1,200 executed lots; zero unknown timeouts | Single-inflight closed loop; two deposits and 90 warmup commands excluded |
| Initial matching performance | 95.149787 confirmed commands/s; execute RTT p50 9.148866 ms, p99 12.361379 ms, max 526.493987 ms | Automatic retries included; two accepted resends; load generator shares a member host |
| Matching after repeated cold restart | 900 measured commands, 300 trades; 96.849023 confirmed commands/s; RTT p50 9.124065 ms, p99 12.295407 ms, max 524.124121 ms | Separate single-inflight run, 9.292814470 seconds; two accepted resends and zero unknown timeouts |
| State correctness | Per-command reference result/sequence comparison, canonical snapshot bytes, invariants and same-key replay passed | The two separate 900-command runs retain their own results and samples |
| Recovery | Two post-patch leader SIGKILLs, rejoin/catch-up, snapshot and repeated all-JVM cold restart passed | Same running Pods and temporary disks; preserved failed attempts remain in the timeline |
| PostgreSQL restored outbox | 2,896 cumulative events, 722 cumulative trades, observed lag 0 | Restored pending outbox plus subsequent business; single local database |
| HTTP / WS workbench | Place/retry/conflict/cancel and canonical mirror checks passed; three full-state WS snapshots received | HTTP test adds two commands and zero trades; cumulative observed DB cursor 3300, trades 819, lag 0 |
| SQL ledger continuity | Event sequences 1..3300, nonzero market sequences 1..3286, 819 TRADE rows agree with durable cursor/counters | Full ledger in one read-only repeatable-read JDBC transaction; an earlier observation than retained-service readiness |

See the recorded [UDP summary](../evidence/2026-10-23/runpod-network/summary.json), [initial matching result](../evidence/2026-10-23/runpod-cluster/runs/cloud-3nodes-01/result.json) and [post-cold-restart result](../evidence/2026-10-23/runpod-cluster/runs/cloud-after-cold-final/result.json). Their different scopes must remain visible when presenting the results. Both matching throughput denominators include reference matching, validation and sample recording. Their single-inflight closed-loop model does not establish arrival-rate capacity. Every measured tail sample is retained; each 900-sample nearest-rank p99.9 equals that run's maximum RTT. The later result does not replace the initial 526.493987 ms tail or establish that the patch improved performance.

## Deployment and isolation

The current topology supports explicitly configured, directly routed private IPv4 member addresses and a reachable client egress address. The remote launchers run one member per Pod without systemd, using Java 21 installDist bundles. This campaign uses Aeron MTU **1248**, sync level **2**, port base **19000** and an outbox capacity of **65536**. Refer to [the remote launcher guide](../deploy/REMOTE.md) for configuration, process ownership checks, logs, graceful shutdown and SSH tunnelling.

Version provenance distinguishes the **immutable Java release `2597bc3b849d8e042c8bbe67f0a5142580871a5b`** from the **Python launcher revision `e1972ed1842b8d333163d8313ccfea7fd0f96dcd`** used for the repaired cold restart. The original matching baseline used Java revision `924ecdd`. Updating the Python supervisor did not replace the pinned Java artifacts. Member and client launches for the repaired deployment select the release explicitly:

```sh
export VECTOR_DIST_ROOT=/opt/vectormatch/releases/2597bc3b849d8e042c8bbe67f0a5142580871a5b/dist
```

The Pod identities and kernel boot IDs are distinct. Provider self-information requests returned HTTP 403, so provider `machineId` values were unavailable. **Physical anti-affinity, independent power domains and dedicated bare-metal placement remain unverified.** Container-visible CPU affinity is also wider than the actual cgroup quota. Report the measured quota/memory bounds and shared scheduling conditions with every result; do not substitute the host-visible core count for allocated CPU capacity.

The cluster state currently resides on temporary container overlay disks. This is sufficient for the present Java-process stop/kill/restart tests while the same Pod and disk remain available. It provides no verified guarantee across Pod stop, rebuild, disk loss or host power loss. Sync level 2 requests Archive/catalog/consensus synchronization; storage and hardware semantics still need their own fault evidence. A small flush+fsync timing probe is not power-loss verification.

PostgreSQL 18.6 runs as an unprivileged OS user on loopback with recorded `fsync=on` and `synchronous_commit=on`. The gateway and this single PostgreSQL instance share a cluster member's resources and failure domain; there is no PostgreSQL replication or HA evidence.

The [outbox-to-PostgreSQL record](../evidence/2026-10-23/runpod-workbench/outbox-to-postgres-summary.json) confirms that restored pending events and subsequent post-cold business reached durable cursor/eventsStored **2896**, tradesStored **722**, marketSeq **2888**, with observed lag **0** before the gateway's new business. Export follows the commit-before-ack contract. These are cumulative lineage totals, including warmup activity.

The initial HTTP probe encountered ConnectionReset and left an [empty trace](../evidence/2026-10-23/runpod-workbench/http-smoke/trace.json). Its [failure record](../evidence/2026-10-23/runpod-workbench/http-smoke/failure.json) identifies the gateway-readiness stage and zero business commands sent. After [gateway readiness](../evidence/2026-10-23/runpod-workbench/gateway-readiness.json), the [successful repeat](../evidence/2026-10-23/runpod-workbench/http-smoke-ready/summary.json) checked place, identical-key retry, conflicting payload rejection, cancel, restored balances and canonical replicated mirror state. It adds **two business commands and zero trades**; its observed cursor/eventsStored **3300** and tradesStored **819** are cumulative database totals. The [WebSocket probe](../evidence/2026-10-23/runpod-workbench/websocket.json) then received three full-state snapshots through the local SSH tunnel, each with health UP and the same observed cursor 3300 / lag 0.

The actual SQL audit in [PgAudit.java](../evidence/2026-10-23/runpod-workbench/PgAudit.java) used one read-only repeatable-read JDBC transaction to examine the full ledger. Its [postgres-ledger.json result](../evidence/2026-10-23/runpod-workbench/postgres-ledger.json) confirms contiguous **eventSeq 1..3300**, contiguous nonzero **marketSeq 1..3286**, and **819 TRADE rows**, agreeing with the durable cursor and counters in that transaction. This is database-internal sequence/count evidence; it does not independently prove every payload's semantics or equality to source events.

The PostgreSQL cursor shown by the gateway is a cached background observation. Lag is the last observed source high-water mark minus the durable cursor, not an atomic source/database snapshot or a live measurement of an unseen source position. The HTTP/WS checks are functional evidence; they do not establish per-event feed delivery, WebSocket latency, database host failover or Pod-stop persistence.

## Recovery results and preserved failures

An externally injected leader termination exposed a client bootstrap problem: the original connection path stalled until its approximately 20-second timeout, while the official Aeron `ClusterTool` observed that another member had already been elected leader. Java release `2597bc3` repaired the bootstrap path, and a fresh client verified the unchanged canonical state and same-key replay while the original leader was still stopped.

Two subsequent leader SIGKILL trials passed canonical state/replay verification, confirmed new business writes and trades, and rejoined the stopped members. A later all-JVM graceful stop succeeded, but the first cold start hit the launcher's immediate `/proc` identity check. Launcher revision `e1972ed` added a maximum two-second identity-establishment window while preserving exact start ticks, argv hashing and pidfd signal ownership. All 18 supervisor tests passed on each Pod. After the repair, restored state was checked and another complete all-JVM stop/start trial passed. These observations do not establish every underlying cause of the original identity sample failure.

The [complete fault timeline](../evidence/2026-10-23/runpod-cluster/fault-timeline.json) retains the original client failure, first launcher failure, upgrades, successful repetitions and new writes. The [after-cold records](../evidence/2026-10-23/runpod-cluster/after-cold-restart/) show all three restored the same checkpoint: **commandSeq 1182, exported watermark 0, pending outbox 1574**, with hash:

```text
296778015e702417f40a705afbdf4598926ec2f3ee239fb52d3b8e871a656fae
```

Client canonical bytes and retry checks passed, and the official member list then showed all three at **term 6 / logPosition 909632**. The subsequent 900-command run ends at command/event/market sequences **2174 / 2896 / 2888**, with its own expected snapshot and result; that later business state is distinct from the restored checkpoint.

The two successful fault rounds recorded **28.451178 seconds** and **31.386420 seconds** of orchestration-inclusive elapsed time. They include SSH setup, signal dispatch, client JVM startup, connection and snapshot/replay checks. They are not first-new-write recovery latency or a failover SLA. A later `verify` invocation measures its own connection and checks; its duration cannot supply a missing outage start time.

## Offline backups, retained services and budget

The approved **USD 20 total** applies to this project's newly rented resources. The observed three-Pod compute plus temporary-disk quote totals **USD 1.551/hour**, rounded up to **USD 1.56/hour** for planning. At the resource-status observation, estimated accrued project cost was approximately **USD 1.17**, or **USD 1.35** using the conservative planning method. Those estimates use approximate staggered creation times and rates, not a reconciled provider bill. No account-balance or unrelated-workload information is available. The USD 20 budget is not a provider-enforced automatic cap or stop rule.

Before archival, all three members wrote checkpoint **commands=2440, exported=3300, pending=0**, with hash `0425728d6119c011db1d45d0607c5370a3a156969ba740ba6044a23183b26abd`; see [final-before-archive](../evidence/2026-10-23/runpod-cluster/final-before-archive/). The gateway, projector, all member JVMs and PostgreSQL were gracefully stopped. The [offline-backup summary](../evidence/2026-10-23/runpod-cleanup/offline-backups-summary.json) and three archive manifests record local paths, sizes, SHA-256 values, allowed archive members and deployment provenance. Archive creation, export and local validation passed, and the manifests/summary have been pushed. Restoration from these archive copies has not been rehearsed.

The user then explicitly chose to keep all three Pods running. The Stop dialog was cancelled: **no Pod Stop, disk clearing or Pod restart occurred**. Cluster, PostgreSQL, projector and gateway services resumed on the original unchanged filesystems, preserving the offline archives as their earlier snapshot in time. The [retained-platform readiness](../evidence/2026-10-23/runpod-cleanup/retained-platform-readiness.json) records health UP, recoveredCommands **2440**, mirror command/event sequences **2454 / 3327**, and an observed database cursor **3327**, marketSeq **3313**, tradesStored **825**, lag **0**, with synthetic flow disabled. This later 3327/825 observation does not replace the earlier 3300/819 SQL audit, and service resumption was not a restore from the backups.

The user selected **another six hours** of retention. A one-time reminder was created and verified with automation ID `vectormatch`, at **2026-10-23 18:23:59.656 UTC**. It is due at approximately **2026-10-24 00:24 UTC / 04:24 Asia/Dubai**. The reminder only notifies: it does not automatically Stop Pods, clear temporary disks or enforce the budget. All three Pods continue billing at approximately USD 1.56/hour; projected cumulative project cost at that reminder is roughly **USD 10.5–11**, subject to actual runtime/rates and billing reconciliation. Final resource termination and actual bill settlement have not occurred.

The user explicitly authorized local archival and private-repository pushes of this campaign's synthetic raw snapshots, CSV samples and JSON evidence after the initial automated approval rejection. Failed observations remain alongside subsequent recovery and workbench artifacts. SSH private keys and API credentials remain excluded. The final resource state is retained-running at the user's request, with completed backups and a reminder; it is not a zero-cost or stopped deployment.

## Network and storage references

- [Runpod public port exposure](https://docs.runpod.io/pods/configuration/expose-ports) provides TCP/HTTP exposure and documents its UDP restriction. The private UDP results above were collected directly between private addresses.
- [Global Networking](https://docs.runpod.io/pods/networking) is documented for NVIDIA GPU Pods with a nominal 100 Mbps inter-Pod network. The current low-rate probes do not measure bandwidth saturation or generalize to CPU Pods and other deployments.
- [Storage options](https://docs.runpod.io/pods/storage/types) distinguish temporary container disks from storage that survives Pod lifecycle operations. Export state and evidence before ending temporary resources.

## Next measurement stages

Retain both matching runs and all failure/recovery traces. Further controlled trials should pause the synthetic gateway flow and record offered arrivals, useful confirmed work, unknown outcomes, queue depth, CPU throttling, RSS, GC, synchronization latency and network use. Add per-request attempt/resend timing and leader/session events before attributing the observed tails to storage, packet loss or GC.

A later capacity campaign should separate the load generator from the members, use a fixed-arrival workload with bounded outstanding work, and validate balances, order state, event continuity and replay hashes at each offered rate. Claim a sustainable capacity only after repeated trials remain correct and stable. The current three-Pod campaign establishes the finite reachability, normal-business, Java-process recovery, workbench and backup-creation results above. The user-requested retained-running period and continuing billing remain explicit.
