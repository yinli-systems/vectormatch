# Fixed continuous long-cut preset

`RetentionCapacityAeronPilotV3 <fresh-directory> idle-window8-long-cuts [fixed-port-base]`
selects exactly33,792 orders at500/s (67.584 scheduled seconds), cap4/chunk6144/Fetch16/read-window8.
The existing explicit idle property `vm.retention.maxParkNs=100000|1000000` remains required.
The original default, archive-chunks, read-windows and idle-window8 entry points retain6,400 orders.
There is no arbitrary arrival/rate/duration CLI.

Funding, seed quantity, Plan, scheduler configuration, registration and final order checks all use the same immutable workload preset.
One lineage, scheduler/ledger, owner/session, reference service, archive/event chain and cumulative ACK budget persist across the whole exposure.
There are11 full3,072-command cuts followed by a3-command partial. The first full cut contains3setup commands;
cuts2–11 are ten homogeneous3,072-load-order cuts. Setup and the final partial are excluded from equivalent-cut drift comparison.
The source requires all12cycles to complete; incomplete/unknown/notSent outcomes retain the existing evidence/failure behavior.

The finite profile,90s task/2s admission permit/90s drain, four-offer ceiling, journal, read slots,
1MiB metadata documents,256samples,2,048 owned paths, writer, raw and allocated-growth limits are unchanged.
Prospective actual-code Plan bounds must be observed from the new frozen distribution before a native run.
The old6,400-order Python controller/auditor is not compatible with this preset: it pins3cycles/six phases
and rejects more than8read phases. A separate preregistered long-run revision must bind12cycles/24phases and33,792 rows.

This entry point is a functional test source, not a performance or endurance claim. A fresh raw audit must verify continuous command/event prefixes,
all planned arrivals, scheduler timing, ACK/force/readback evidence and exact current JARs. Compare backlog/oldest unfinished age at equivalent full-cut boundaries,
cycle wall time (not summed overlapping RPC intervals), all-arrival p99, goodput, rejects, unknown and final drain.
No stability or capacity promotion follows merely from completing the in-process unit fixture or building the distribution.
