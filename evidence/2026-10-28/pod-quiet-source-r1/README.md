# Quiet load generator and safepoint diagnostics (2026-10-28, stamp 20261028-210356)

One unattended [`scripts/pod-autopilot`](../../../scripts/pod-autopilot/README.md) run on RunPod CPU pod
`z01seweximrhz8` (EPYC 9655, 8 physical cores, data-center NVMe with fdatasync p50 57 µs). Three replicas
and the load source share the host over loopback; not a physical failure-domain result.

Both ABAB arms use busy spin with measurement hygiene (`c2spinsrc`): static GC workers,
`-XX:+SafepointTimeout -XX:SafepointTimeoutDelay=20` in every JVM, and for the load generator only a fixed
pre-touched 8 GiB heap with a 6 GiB young generation, so its own bookkeeping does not collect during a
window. Node JVMs are unchanged. B adds thread pinning with governor v3 (`c2spinsrcpin`, compiler threads at
nice 19).

## ABAB at 8000/s (sync0)

| Case | Arm | p50 | p99 | p99.9 | Gates |
|---|---|---|---|---|---|
| ab-a1 | unpinned | 37.8 µs | 8.45 ms | 19.2 ms | all pass |
| ab-b1 | pinned | 36.1 µs | **2.71 ms** | 18.9 ms | all pass |
| ab-a2 | unpinned | 35.0 µs | 11.6 ms | 20.0 ms | all pass |
| ab-b2 | pinned | — | — | — | 36 orders not sent |

Pair 1 met the selection ratios (p99 0.32, p99.9 0.98), but the candidate was not selected: ab-b2 lost
orders, so final states differ and no pair can pass. The SafepointTimeout output in
`sync0-abab-20261028-210356/experiments/ab-b2/node*-g0/stdout.log` names the cause: in each node,
`C2 CompilerThread0` (in node 0 compiling `ConsensusModuleAgent::consensusWork`) did not reach the safepoint;
the leader's slowest safepoint waited 156 ms. A compiler thread inside the VM must acknowledge safepoints,
and at nice 19 on the shared housekeeping CPU it barely ran. Commit 8e7dc92 makes renicing opt-in; the
next run (`c2spinsrcpin5`) leaves compilers at normal priority.

Tail attribution (`*-TAIL_ATTRIBUTION.json`): the source's GC overlaps **no** slow order in any case (it was
up to 24 ms before this fix). In the unpinned baselines 75–76% of orders at or above p99 overlap no GC at all,
which is the preemption that pinning removes; the leader's GC overlaps 19–22%.

## Ladders on the unpinned baseline (`c2spinsrc`)

All originals accepted on every passing rung.

| Rate/s | sync0 p50 / p99 / p99.9 | Durable p50 / p99 / p99.9 |
|---|---|---|
| 1000 | 33 µs / 3.01 ms / 9.0 ms | 64 µs / 3.90 ms / 8.9 ms |
| 2000 | 33 µs / 3.48 ms / 9.0 ms | 62 µs / 5.22 ms / 13.7 ms |
| 3000 | — | 67 µs / 3.73 ms / 13.3 ms |
| 5000 | 32 µs / 5.97 ms / 14.5 ms | 63 µs / 7.38 ms / 18.8 ms |
| 8000 | 36 µs / 8.75 ms / 15.9 ms | 65 µs / 12.15 ms / 17.7 ms |
| 12000 | 36 µs / 12.18 ms / 19.5 ms | 59 µs / 11.72 ms / 22.3 ms |
| 20000 | failed twice (462 and 208 not sent) | not reached (ladder ends at 12000) |

Durable = consensus and catalog sync2, recording data sync1, a force per commit. Knees: sync0 12,000/s;
durable at least 12,000/s (every rung passed; the previous run's durable knee was 2,000/s, limited by the
load generator's GC). The production target (p99 ≤ 5 ms and p99.9 ≤ 20 ms) is met by sync0 at 1000–2000/s
and by durable at 1000 and 3000/s; durable 2000/s missed it by 0.22 ms of p99.

Single runs per rung. The quiet source changes the measurement apparatus, so these ladders are not directly
comparable with earlier ones that used the default 1–2 GiB source heap.
