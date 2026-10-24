# Independent raw CPU pilot audit

Local raw verification passed for frozen source `4102446b333573efde2b33a0eb53a8177575bad5`, release SHA `f56126dab203c80b42f950fa7037fb0b58e52103bf4f6fb86e7f578b0bd4dfa4`. This audit used no SSH, cloud API, benchmark launch, business source change or Git operation. `result.json` records the bytes and SHA of every input read. Parent evidence verification independently closes the full original archive; this audit focuses on the bounded extracted raw arrival, request/reply, maintenance, log and telemetry inputs.

| Independently derived metric | Batch cap 1 | Batch cap 4 |
|---|---:|---:|
| Scheduled/released identities | 6,400 / 6,400 | 6,400 / 6,400 |
| Fixed arrival window | 12.8 s | 12.8 s |
| Intended arrival rate | 500/s | 500/s |
| Distinct accepted orders eventually confirmed | 6,400 | 6,400 |
| Accepted replies within fixed window | 3,069 | 3,069 |
| Fixed-window goodput | 239.765625/s | 239.765625/s |
| All-arrival p99, scheduled arrival to reply completion | 7.536495815 s | 7.399907680 s |
| Last reply drain beyond fixed window | 7.175610967 s | 7.023707470 s |
| Final maintenance end beyond fixed window | 7.792911955 s | 7.642407882 s |
| Total source drain, reported and ordering checked | 7.793246221 s | 7.642723548 s |
| Initial observed UNKNOWN / final UNKNOWN / notSent / business rejection | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Maximum scheduler lateness | 2.791957 ms | 2.629148 ms |
| Sampled external backlog high water | 2,994 | 2,986 |
| Physical business batch frames | 6,400 | 3,974 |
| All physical request/reply frames | 8,185 / 8,185 | 5,759 / 5,759 |
| Physical offer attempts / negative returns | 8,227 / 42 | 5,793 / 34 |

Both arms are **valid finite overload observations**. A 239.765625/s reply rate inside this particular window is not a stable throughput ceiling. The source generated all arrivals on the original schedule while maintenance blocked business dispatch. Each exact logical identity and SHA matches its nested physical request and full accepted batch result; order IDs cover exactly 2..6401 and command sequence exactly 4..6403, without duplicates. Full reply completion, not matching-core or network-only time, defines latency. P99 is nearest rank over all 6,400 planned arrivals and remains defined here because all eventually confirm distinct accepted orders, with no notSent or UNKNOWN. The exact terminal source timestamp is not separately logged; total source drain is therefore labelled as reported, checked against the independently observed last reply and final maintenance boundaries.

Cap 4 actual business frame sizes were 3,106 singles, 67 pairs, 44 triples and 757 groups of four. This confirms actual aggregation, but one cap-1 arm followed by one cap-4 arm on fresh distinct lineages cannot establish an ABAB improvement or justify promotion.

## Maintenance RPC closure

Every arm has 1,785 complete logical RPC rows and matching length-framed request/reply bytes. The independent decoder verifies request operation, correlation, full bounded framing, scope, reply tag/error, exact physical-wire SHA equality, monotonic serial timing, and `end - start == elapsed`. RPC totals/counts/maxima match the recorded summary. Three cycle receipts close the RPC inventory and their time bounds. These are caller RPC times, including transport, server work, scheduling and evidence writes; **they are not pure fsync latency**.

| RPC kind | Count per arm | Cap 1 total / p99 | Cap 4 total / p99 |
|---|---:|---:|---:|
| PrepareArchive | 3 | 0.049655683 s / 25.808525 ms | 0.051365073 s / 27.967781 ms |
| ArchiveChunk | 975 | 7.444719347 s / 10.650708 ms | 7.417251994 s / 10.662809 ms |
| FetchEvents | 801 | 6.114617604 s / 9.757668 ms | 6.077533661 s / 9.628040 ms |
| ArchiveCommit | 3 | 0.078932779 s / 33.810364 ms | 0.085337187 s / 40.627416 ms |
| EventAck | 3 | 0.031376903 s / 13.194530 ms | 0.027781704 s / 10.722698 ms |

All three maintenance cycles span 14.159243918 s / 14.024982171 s in cap 1 / cap 4. The first cycle spans Java offsets 6.143719624..12.980703946 s / 6.142703725..12.887918235 s and contains the release of **3,328 new arrivals in each arm**. This directly supports the maintenance queueing lead: arrivals continue and the first cycle extends past the exposure window. It does not isolate which underlying server, transport or storage wait dominates each RPC.

Approximate UTC labels for first maintenance are 06:02:57.093..06:03:03.930 for cap 1 and 06:03:20.467..06:03:27.213 for cap 4, on 2026-10-24. These come from the Java origin Instant and Java offsets and are only coarse labels. Java `nanoTime` and Python monotonic origin alignment was not validated.

## Owned CPU, RSS, I/O and node logs

The telemetry file closes at 47 ordered samples and 128,804 bytes, below its 512-row / 8 MiB bounds. All seven process identities match exact PID, Linux startTicks and argv SHA; successful process counters are complete and nondecreasing, using explicit 100 ticks/s and 4096-byte pages. Every node has 22 available process samples and 12 available samples in its coarse UTC exposure interval. No registered node metric failure occurs inside those coarse exposure intervals.

The 80 unavailable records are all explicitly `Registered exact process no longer alive`: 24 for each cap-1 node, 2 for each cap-4 node, and 2 for the parent. These are retained after the old arm or parent exited and are not interpreted as zero CPU, zero memory or lost data. Telemetry is sampled, not continuous; successful values do not prove no missing subsecond peaks.

| Role | Observed-span average CPU cores | Sampled maximum VmRSS |
|---|---:|---:|
| Cap 1 node 0 | 0.4913 | 427,450,368 B |
| Cap 1 node 1 | 0.3704 | 388,485,120 B |
| Cap 1 node 2 | 0.3810 | 363,761,664 B |
| Cap 4 node 0 | 0.5124 | 382,746,624 B |
| Cap 4 node 1 | 0.3701 | 355,807,232 B |
| Cap 4 node 2 | 0.3706 | 384,151,552 B |

Observed spans include setup/startup, load, maintenance and parts of shutdown; they are not exact load-window CPU averages. `result.json` also records CPU deltas between the first/last available samples strictly inside each coarse UTC exposure window, RSS values, kernel `read_bytes/write_bytes/syscr/syscw` deltas and each observation span. Parent JVM measurements cover both arms and setup/reference/reconciliation work. Kernel I/O counts do not identify individual force calls, independent physical media or provider durability.

All six node logs are bounded (1,055 bytes for each leader, 1,028 for each follower), with exact source/profile/lineage/PID startup, `sync=2`, MTU 1248, prepared cache enabled and matching final combined checkpoint hash. No `Exception` or `ERROR` marker appears. Raw load transport observations retain leader 0 and term 0 without a new-leader callback. This closes observed evidence, not unobserved subsecond state or crash recovery.

The first local audit attempt reached completion of both raw arrival/wire/RPC checks, then failed because local Python rejected a Java Instant with nine fractional digits. Its full source and failure receipt are retained. The corrected parser strictly validates UTC syntax and truncates to microseconds only for coarse labels. No benchmark was rerun or raw input changed. Final source/result/log hashes are in `FINAL.json`.

No maximum stable throughput, sustained latency SLA, independent-host network/storage, crash durability, 100M cumulative orders, 100M/s or 100M connections is proven by this pilot.
