# Cloud testing: Runpod campaign, USD 20 ceiling

On 2026-10-23, this project deployed three Runpod GPU Pods in the same supported Global Networking region. Native private IPv4 UDP passed the six-direction preflight, followed by an initial correctness-checked, three-member matching smoke. The actual resource choices, measured limits, storage profile and detailed evidence are recorded in [RUNPOD_LAB.md](RUNPOD_LAB.md).

## Confirmed measurements

| Experiment | Recorded result | Scope |
|---|---|---|
| Private UDP full mesh | 18,000 request/echo roundtrips; zero observed loss, duplicates or reordering | Six ordered pairs; 200 requests/s per active path; authenticated raw IPv4 UDP |
| UDP payload / path | DF probes at 96, 512 and 1248 payload bytes; private interface MTU 1300 | Largest tested IPv4 datagram, including UDP/IP headers, was 1276 bytes |
| Pooled UDP RTT | p50 0.653665 ms; p99 1.298711 ms; max 39.338844 ms | All 18,000 returned samples; client monotonic clock; no one-way measurement |
| Initial replicated matching | 900 measured commands, 300 trades, 1,200 executed lots; zero unknown timeouts | Single-inflight closed loop; two deposits and 90 warmup commands excluded |
| Initial matching performance | 95.149787 confirmed commands/s; execute RTT p50 9.148866 ms, p99 12.361379 ms, max 526.493987 ms | Automatic retries included; two accepted resends; load generator shares a member host |
| State correctness | Per-command reference result/sequence comparison, canonical snapshot bytes, invariants and same-key replay passed | Normal-business smoke; fault recovery and PostgreSQL projection require separate checks |

See the local recorded [UDP summary](../evidence/2026-10-23/runpod-network/summary.json) and [matching result](../evidence/2026-10-23/runpod-cluster/result.json). Their different scopes must remain visible when presenting the results. The matching throughput denominator includes reference matching, validation and sample recording. Its single-inflight closed-loop model does not establish arrival-rate capacity. Every measured tail sample is retained; the 900-sample nearest-rank p99.9 equals the maximum RTT.

## Deployment and isolation

The current topology supports explicitly configured, directly routed private IPv4 member addresses and a reachable client egress address. The remote launchers run one member per Pod without systemd, using Java 21 installDist bundles. This campaign uses Aeron MTU **1248**, sync level **2**, port base **19000** and an outbox capacity of **65536**. Refer to [the remote launcher guide](../deploy/REMOTE.md) for configuration, process ownership checks, logs, graceful shutdown and SSH tunnelling.

The Pod identities and kernel boot IDs are distinct. Provider self-information requests returned HTTP 403, so provider `machineId` values were unavailable. **Physical anti-affinity, independent power domains and dedicated bare-metal placement remain unverified.** Container-visible CPU affinity is also wider than the actual cgroup quota. Report the measured quota/memory bounds and shared scheduling conditions with every result; do not substitute the host-visible core count for allocated CPU capacity.

The cluster state currently resides on temporary container overlay disks. This is sufficient for the present Java-process stop/kill/restart tests while the same Pod and disk remain available. It provides no verified guarantee across Pod stop, rebuild, disk loss or host power loss. Sync level 2 requests Archive/catalog/consensus synchronization; storage and hardware semantics still need their own fault evidence. A small flush+fsync timing probe is not power-loss verification.

PostgreSQL has been started as an unprivileged OS user with loopback access. Its transactional exporter uses commit-before-ack; real projection cursor, event continuity and recovery evidence are still being checked. PostgreSQL process liveness and skipped database integration tests do not establish those results.

## Recovery issue under investigation

An externally injected leader termination exposed a client bootstrap problem: the original connection path stalled until its approximately 20-second timeout, while the official Aeron `ClusterTool` observed that another member had already been elected leader. A client-bootstrap patch is under test.

This is an application/client issue discovered by the cloud experiment. Leader election alone does not establish end-to-end service recovery. Keep the failure trace, patch revision, deployment checksums and subsequent results together. Recovery remains **pending** until a client confirms a command or an identical-key retry, sequences remain correct, and the canonical state agrees with the saved expected state. Full-process restart, restored pending outbox events and PostgreSQL catch-up also require their own recorded checks. Do not replace the failed observation with only the best successful rerun.

An independent fault timeline must measure from the actual external fault action to confirmed usable service. A later `verify` invocation measures its own connection and checks; its duration cannot supply the missing outage start time.

## Budget, archival and cleanup

The approved **USD 20 total** applies to this project's newly rented resources. The observed three-Pod compute plus temporary-disk quote totals **USD 1.551/hour**, rounded up to **USD 1.56/hour** for planning. Actual billed cost is pending: start times were staggered, and the experiment has not completed resource cleanup. No account-balance or unrelated-workload information is available. The budget is an operating limit for this campaign, not an account-wide automatic cutoff.

Preserve the agreed evidence, then terminate this project's newly created resources and record each resource's end time and any remaining storage charges. Stopping a Java benchmark does not stop provider billing. Do not terminate unrelated workloads or use other projects' volumes.

The user explicitly authorized local archival and private-repository pushes of this campaign's synthetic raw snapshots, CSV samples, and JSON evidence after the initial automated approval rejection. The baseline raw evidence has now been exported and pushed. SSH private keys and API credentials remain excluded. This archival approval is separate from the deployed UDP transport and the client recovery issue. Keep cleanup marked pending until the approved evidence is safely preserved and the new resources have actually been ended; reconcile estimated cost with provider billing afterward.

## Network and storage references

- [Runpod public port exposure](https://docs.runpod.io/pods/configuration/expose-ports) provides TCP/HTTP exposure and documents its UDP restriction. The private UDP results above were collected directly between private addresses.
- [Global Networking](https://docs.runpod.io/pods/networking) is documented for NVIDIA GPU Pods with a nominal 100 Mbps inter-Pod network. The current low-rate probes do not measure bandwidth saturation or generalize to CPU Pods and other deployments.
- [Storage options](https://docs.runpod.io/pods/storage/types) distinguish temporary container disks from storage that survives Pod lifecycle operations. Export state and evidence before ending temporary resources.

## Next measurement stages

After the client recovery issue is resolved and verified, retain the initial baseline and compare the patched version using the same workload and durability settings. Run controlled repeated trials with the synthetic gateway flow paused. Record offered arrivals, useful confirmed work, unknown outcomes, queue depth, CPU throttling, RSS, GC, synchronization latency and network use.

A later capacity campaign should separate the load generator from the members, use a fixed-arrival workload with bounded outstanding work, and validate balances, order state, event continuity and replay hashes at each offered rate. Claim a sustainable capacity only after repeated trials remain correct and stable. The current three-Pod campaign establishes the measured reachability and normal-business results above, with recovery and resource closure still tracked explicitly.
