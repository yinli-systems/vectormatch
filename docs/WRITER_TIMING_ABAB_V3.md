# Writer timing: registered control comparison

The new timing artifact is frozen from the actual forced Linux CI build on source `aed9430d133d86bfe9fc6abe47ede623ef3309b2`,code fingerprint `f3a5745cb67f6d46aae28ef68dede0a5b7a767a795dab3bd07c3b5d4143464ca`. Its226 core/cluster class files match the actual tested compiled classes. Local/Linux metadata,all nine loaded origins,the six legacy plans and five fine-rate/both-policy plans agree. The full454-file benchmark JDK image is identical to the JDK image used by CI.

Compared with source566dd2fa/code2b8d7594,the41 core classes are byte-identical. Only the two main source files `RetentionDurableWriterV3` and `RetentionBatchMaintenanceV3` change. Their compiled differences comprise those two classes,writer Job/Persisted/Ticket and the added PhaseTimings record. Ticket method disassembly/signatures are identical;its binary debug metadata changes. Wire,matching,capacity-plan,owner and all other compiled classes remain byte-identical. No verification,force/readback,ACK ordering or resource limit is weakened. This is instrumentation,not a throughput optimization.

## Fixed experiment

Register A1/B1/A2/B2 at4000 scheduled arrivals/s for20s per arm,80000 fresh IOC arrivals per lineage:

- A1 and A2:unchanged qualified source566dd2fa/code2b8d7594.
- B1 and B2:CI-qualified timing sourceaed9430d/codef3a5745c.
- All arms:leader0,sync2,ROTATING_CONTINUE,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64,one physical session. Existing CPU container/boot/affinity/cgroups,pinned identical JDK,two original-PID2s readiness gates around setup/5s warm-up,no JFR. No higher rate is registered in this comparison.

Use fresh exclusive namespaces. Preserve the original lifecycle,exact process identities/pidfd shutdown,strict native warnings/error policy,known-outcome reconciliation,raw frame/offer/arrival evidence and unchanged disk/memory bounds. Close and privately verify each complete native/raw arm before the next. Unknown,invalid scheduling,native faults or incomplete evidence stop for investigation;known missing/rejected outcomes remain visible and successful global percentiles are unavailable when any planned arrival is missing.

Before any arm executes,the first preflight refuses to start because the unchanged8GiB fresh-headroom guard sees60.25GB charged memory,including59.72GB file cache and about5.7MB anonymous memory;no Java/SQL workload is active. The cgroup reclaim interface is read-only. Register the same preconditioning for all four arms:with the container idle,apply `POSIX_FADV_DONTNEED` through read-only/no-follow descriptors to this project's closed regular files >=4MiB under `/opt/vectormatch-cpu` only. Preserve every file,verify inode/size/mode/owner/mtime/ctime unchanged,and record per-file hints plus cgroup memory before/after. No global cache flush,limit change or cache operation during measured load is allowed. The original8GiB guard must still pass. Retain the initial failed preflight and all preconditioning receipts. This is setup for the registered comparison,not an application memory optimization;earlier curves keep their own setup context.

Report each arm's scheduled/confirmed rates,all-arrival p99 where defined,conditional accepted p99,backlog/rejection/unknown,drain and every offered-cut recovery interval. Audit that every B cycle exports the new timing schema and every A cycle retains the legacy receipt. Check payload receipt Write/Force/Readback values against the corresponding exported cycle fields,and ensure measured serial writer phases do not exceed writer elapsed time. Copy/queue are outside that elapsed interval;unmeasured residual remains explicit.

This measures the timing change's finite behavior and locates maintenance cost. Two observations per artifact do not establish statistical significance,sustained capacity,hard real time,millisecond trading latency or100M. No optimization is selected merely because an exploratory number is lower. Later changes require their own qualified control comparison.
