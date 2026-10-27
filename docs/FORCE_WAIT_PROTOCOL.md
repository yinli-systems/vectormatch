# Force CPU and blocking-state attribution

The [preallocation ABAB](RECORDING_PREALLOCATION_RESULTS.md) failed in both pairs. Continue on the same prepaid CPU, preserving sync2 and every original outcome. No host-wide tracing settings, sysctls, storage mounts or cloud resources are changed.

## Observability boundary, checked before implementation

The existing Linux 6.8 container has `perf_event_paranoid=4`, no accessible tracefs, `sched_schedstats=0` and `task_delayacct=0`. An own-process software perf counter returns EPERM; reading the test thread's kernel stack returns EACCES. The disabled runqueue/block-delay counters must **not** be interpreted as zero delay. `/proc/self/task/<tid>/stat` and `wchan`, `CLOCK_THREAD_CPUTIME_ID` and `getrusage(RUSAGE_THREAD)` are available.

The initial Python observation qualification uses only a fresh synthetic log and its own writer thread. Of 485 samples, 476 observe D state; XFS `xlog_wait_on_iclog` is the most frequent wait location. This is a capability check, not a trading benchmark; Python/GIL effects prevent treating its timings as application performance.

## Bounded opt-in probe

The same pinned Aeron 1.53.3 diagnostic overlay brackets each RecordingWriter `force` with thread CPU/resource snapshots. Preserve the original Java `FileChannel.force(forceMetadata)` call. Native monotonic timestamps enclose the counter reads and retain their complete overhead interval. Exact stage-force start/end, recording ID, publication session and log positions join each native row back to original requests.

If the wider counter interval consumes `C` CPU nanoseconds, the actual force call consumes **at most** `min(C, forceWall)` CPU time. Therefore `max(0, forceWall-C)` is a lower bound on its off-CPU time. The enclosing counter interval also supplies an upper bound. Keep both bounds and all envelope slack. Voluntary/involuntary context switches are counts, not durations.

A native observer samples **only its own registered recording thread** every nominal 500 µs. It reads task state before and after `wchan`, retaining sample begin/end and active-force sequence before/after. Only samples strictly inside a single exact force interval qualify. Transition samples remain explicit; R means running **or** runnable and does not distinguish CPU execution from runqueue delay. D-state wait-location counts indicate observed blocking paths, not exact storage-wait durations. Report exact runnable-wait and device-wait durations as unavailable.

Native tapes are bounded to 250,000 force rows and 2,000,000 state samples per recording thread; overflow/read errors invalidate attribution. Evidence is written only after the measured workload closes. The sampler uses no Java heap allocation per sample and performs no filesystem evidence writes during arrivals. It still has CPU/procfs costs, so observer controls are mandatory. The native qualification retains all 128 calls, samples, compiled library, source and hashes.

## Frozen observer ABAB

Use functional OFF/ON arms of 2 seconds at 10/s, then **OFF A1 / ON B1 / OFF A2 / ON B2**, each **60 seconds at 100/s**. Keep ordinary exact-stage tracing ON in every arm; disable the failed recording preallocation option. Same artifact, leader 0, G1, 1–2 GiB heap, four fixed disjoint CPU sets, 1 ms park, shared media drivers, overlay storage and archive/catalog/consensus **sync2**. Same-host synthetic IOC workload; no physical failure-domain claim.

Freeze the candidate hashes and actual launch matrix first. Require all original replies, exact canonical state equivalence, native/stage joins, zero recorder overflow, valid source timing and owned-process closure. Preserve all failed gates and opposite observer-effect directions. Do not describe instrumentation as an optimization or assume its overhead is negligible. This phase selects a bottleneck hypothesis; it does not select a production default or an endurance candidate.

Only after closing all originals should a separate optimization be frozen and tested with its own same-config ABAB. Require both paired p99 ratios ≤0.90, both p99.9 ratios ≤1.00, correct complete outcomes and the registered absolute/source gates before a 30–60 minute candidate run. Preserve sync2 and the same confirmation semantics. No promotion based on an averaged win or on changing durable acknowledgments.

## Interpretation sources

Linux documents [schedstat](https://www.kernel.org/doc/html/latest/scheduler/sched-stats.html) and [task delay accounting](https://docs.kernel.org/accounting/delay-accounting.html) as separate CPU-runqueue and resource-wait measures; those measures are disabled here. [`getrusage`](https://man7.org/linux/man-pages/man2/getrusage.2.html) supplies thread resource and context-switch counts. In the upstream [Linux 6.8 XFS log implementation](https://github.com/torvalds/linux/blob/v6.8/fs/xfs/xfs_log.c), `xlog_wait_on_iclog` waits for log synchronization completion. Observing it provides a kernel-level blocking location, but does not separate physical-device service time, filesystem ordering, other writers or wakeup scheduling.
