# Controlled bottleneck and optimization campaign

Registered on 2026-10-24 Dubai time (2026-10-23 UTC), after the completed [capacity campaign](CAPACITY_RESULTS.md). This is an experiment protocol, not a claim that any new optimization or hundred-million-scale target has passed.

## Targets and current limits

The user requested all three: at least 100,000,000 accepted new commands in total, 100,000,000 accepted commands/second, and 100,000,000 simultaneous connections. They require independent evidence. Retries do not count as new commands; isolated trial totals do not prove uninterrupted operation; transport packets are not matched orders; projected shard multiplication is not a measured aggregate; application sessions are not interchangeable with TCP connections.

The present three-Pod configuration has 128 synchronous cluster sessions and a 200,000 retained-order bound. Its repeatedly stable tested arrival rate was 13,000/s in finite windows. Terminal orders are not compacted. The current fixture cannot continuously accept one hundred million new orders. A long-run design needs explicit retention, outbox export, bounded idempotency history and restart/replay semantics, followed by actual accepted-command and audit counts. The two larger instantaneous targets cannot be honestly verified on the current resources within the USD20 total budget. This campaign first measures and improves the real deployment, retaining the larger targets as unverified requirements.

## Causal comparisons

Keep the node artifact `b6f6c5cd165110e330d409e2ff51ee4574a3720b` immutable, private UDP/MTU1248, sync2, leader0, 2 GiB heaps, capacity-190k-v1, outbox524288, session limit128, W128/Q64, timeouts and the prepared logical state SHA `2247db9c15b0043a0b28172c5bfa2d9e4f20b5748f6a16424d881e296102655f`. Setup, session cleanup and validation remain outside the measured window.

The first change only replaces 128 embedded client MediaDrivers with one shared MediaDriver. Keep 128 independent Aeron clients, 128 ClusterClient instances, 128 worker owners, one synchronous in-flight request per worker, independent ephemeral egress sockets, original Backoff strategy, producer identities and retry behavior. Sharing Aeron, pipelining, changing queue scheduling, changing socket buffers and changing server threading are separate factors.

Build one immutable new load artifact with both isolated and shared modes. Record source/bundle SHA, actual JVM property, runtime mode/driver counts and node identity. Compare A and B with the same new load artifact rather than selecting a favorable result against an older baseline. The pre-registered primary sequence is A15k-r1, B15k-r1, A15k-r2, B15k-r2, each with 190,000 offered arrivals. Preserve all failures, including invalid generator/collector observations. A and B retain separate configuration fingerprints and curves. Use a small correctness smoke first. If B passes repeated 15k windows, screen B at16k and19k, repeating its boundary before a capacity claim. If B fails or regresses, retain it and choose the next factor from the completed diagnostic evidence.

Compare confirmed goodput inside the arrival window, scheduled-to-confirmed p99, initial API RTT, client queue delay, all-offered acceptance, queue-full/not-sent, rejects, initial/final unknowns, drain, backlog growth, slot occupancy, CPU/RSS/thread count, socket drops/queues, UDP/Aeron repair counters and recording/commit/service positions. Correctness after drain is separate from stability under load. Keep the original minimum10s and drain/backlog/scheduler rules; do not invent a p99 SLA after seeing results.

## Attribution without changing the workload

Use identical bounded read-only observers in every new control/treatment. Existing 1Hz process/cgroup/network and CnC collectors remain unchanged. An additional collector samples only verified project PIDs: per-thread CPU/start identity, limited top-thread wait/scheduling data and UDP sockets joined by owned file-descriptor inode. Preserve missing/error observations and collector wall/CPU cost. Namespace UDP counters overlap and are not unique business losses. Kernel buffer limits do not establish actual per-socket SO_RCVBUF capacity. Do not run JVM attach, thread-dump, packet capture or profiler pauses inside a capacity window.

The archive recording wall-time includes write/force/scheduling, so it is not device utilization or proof of the unique cause. If needed, a separately labelled sync0 diagnostic may isolate durability cost; it cannot be presented as a same-semantics sync2 optimization. A receive-buffer experiment must verify its actual effective buffer and kernel clamp. Client exchange idle, client driver idle, node driver idle, Archive threading and asynchronous pending-window size must each be compared separately.

## Evidence, budget and restoration

Reuse the three existing Pods, with no new purchase or global kernel change. Before each trial estimate cumulative project spend, reserve USD2 for recovery plus the next bounded trial, and refuse new load if the USD20 ceiling would be exceeded. Quotes/launch-time estimates are not a reconciled bill or provider-enforced cap. Preserve the user's existing retention reminder and do not stop/delete Pods. Pause the original application only for isolated measurements; preserve its original lineage and restore HTTP/SQL/WS readiness at the end.

Raw evidence and code continue to the existing private repository. Native PostgreSQL/application archives are not newly exported: the prior automatic rejection remains respected; use same-Pod offline copies and metadata if another backup is needed. Synthetic capacity arrivals/results, protocol counters and the explicit project telemetry are within the user's archival authorization.

References: [pinned Aeron client ownership](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-client/src/main/java/io/aeron/Aeron.java), [client concurrency model](https://github.com/aeron-io/aeron/wiki/Client-Concurrency-Model), [Aeron performance factors](https://aeron.io/docs/aeron-cluster/performance-limits/).

## Registered receive-buffer follow-up

After all four formal client-driver trials completed, neither shared run met the registered stability rule at 15k/s. The resource reduction was reproducible; the owned follower log receive socket still accumulated drops. A separate [network plan](../evidence/2026-10-23/runpod-optimization/network/plan.json) was frozen before new load, referencing the four completed result digests.

The receive-buffer sequence is 128 KiB request → 1 MiB → 128 KiB → 1 MiB, all at 15k/s, 190k arrivals,128 workers. Both configurations use node source `071029fb1f3c1718b15a8850eb531783677674fe` and bundle `fac70db5c98d7d8e03de737e68552bdf606acfe540afbfcba7c8658884ebddd3`, with the same prior `bdfe09a` load artifact in shared mode. Only ClusterNodeMain entries differ from the prior bdfe distribution; core/dependencies match. This comparison does not substitute the previous b6f node runs as controls.

The node's explicit eighth positional argument requests the receive buffer for its MediaDriver UDP sockets. Every other source setting remains fixed, including send buffer128KiB, SHARED node/archive drivers, existing Backoff, sync2, leader0,MTU1248,2GiB heaps, the prepared-state digest and capacity profile. The two values have separate fixed-configuration identities.

Outside each arrival window, identical read-only probes verify PID/startTicks/command identity and stable owned socket FD/inode joins, using only the known ingress/log local ports in filtered ss output. Archive only owned local socket kernel rb/tb, queue/drop and safe diagnostics; no packet contents or peer list. Linux commonly doubles buffer accounting, so report the actual rb/tb values rather than calling the request the effective value. Require both pre/post observations and an actual treatment increase, and preserve missing/failing attestations. The same source-digested probe runs in every group. A known exact cgroup-mount metadata warning is recorded by diagnostic code; any other stderr or nonzero ss status fails the attestation.

The initial strict probe correctly rejected node0's cgroup warning and its receipt remains in tool-validation; node1/2 attestations passed. The narrowly corrected probe is separately identified and validated before this matrix. No earlier raw receipt is overwritten. This observer correction occurs before the network trials and is not a measured optimization.

Keep all original correctness, scheduler,>=10s stability,goodput,drain,backlog and unknown rules. Network loss reduction alone is not a throughput/latency win. Preserve A/B/A/B outcomes and choose any later threading factor only from the completed evidence. Original application recovery and the project USD20 total guard remain mandatory.
