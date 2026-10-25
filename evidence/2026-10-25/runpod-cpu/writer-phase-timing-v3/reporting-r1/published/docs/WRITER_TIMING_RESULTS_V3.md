# Writer phase timing: A1/B1/A2/B2

All four registered observations accept every planned arrival,with zero notSent,rejection,observed UNKNOWN or final UNKNOWN. This closes an instrumentation comparison,not a performance optimization or the production latency target.

Each observation is a fresh80,000-order lineage at4,000 scheduled IOC arrivals/s for20s. All four use leader0,sync2,ROTATING_CONTINUE,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64,one physical session and three JVMs on the same CPU host. JDK/container/boot/affinity/cgroups are pinned;two original-PID2s readiness gates bracket setup/5s warm-up;no JFR. The same registered project-only read-only cache preconditioning precedes each arm. The initial A1 memory-headroom refusal and every preflight/cache receipt are retained. See the [prospective registration](WRITER_TIMING_ABAB_V3.md).

## Observed finite behavior

| Arm | Artifact | Accepted | In-window goodput/s | All-arrival p50 ms | All-arrival p99 ms | After-positive-offer p99 ms | Clearing offered-cut intervals |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A1 | 2b8d7594 | 80,000 | 3993.45 | 7.609782 | 245.282081 | 11.618506 | 23/23 |
| B1 | f3a5745c | 80,000 | 3993.45 | 7.100721 | 229.152637 | 13.190047 | 23/23 |
| A2 | 2b8d7594 | 80,000 | 3993.45 | 7.488041 | 249.916563 | 12.005511 | 23/23 |
| B2 | f3a5745c | 80,000 | 3993.45 | 7.468863 | 239.408311 | 11.327567 | 23/23 |

A1/A2 use original source566dd2fa/code2b8d7594. B1/B2 use timing sourceaed9430d/codef3a5745c,qualified by the full forced Linux CI run. The41 core classes are identical;the timing change preserves all canonical validation,force/readback,receipt completion and ACK fences. The small p99 differences do not establish causation or statistical significance. These are two observations per artifact on shared hardware,without randomized ordering or long-duration replication.

In-window goodput counts confirmations during the20s arrival window;all80,000 distinct accepts reconcile after drain. Comparable recovery intervals exclude setup and post-arrival drain. Clearing recorded waiting is a finite observation,not proof of an unbounded steady-state workload. Successful-offer-to-reply includes client polling,loopback transport,replication and service;it is not network RTT.

## Where maintenance time goes

Each arm completes27 maintenance cycles. Every original cycle and all54 payloads/receipts are checked. Every B cycle has timing schema1;every A cycle retains the legacy schema. Exported write/force/readback values exactly match their corresponding payload receipts,with payload byte length/SHA-256 verified. All seven serial writer phases fit within writer elapsed;copy and queue precede that interval.

The following durations are summed over one arm's27 cycles,in seconds. RPC intervals are merged by monotonic interval union,not summed across concurrent calls. They include queueing,service and evidence consumption. Writer elapsed includes prevalidation,hashing,write,force,full readback and receipt write/force;the subphases below are components of elapsed and must not be added to elapsed a second time.

| Measured duration,seconds | B1 | B2 |
| --- | ---: | ---: |
| Maintenance wall | 5.322435258 | 5.768132160 |
| Source-RPC interval union | 2.339057468 | 2.383283274 |
| Coordinator archive verification | 0.798911151 | 0.918744077 |
| Archive writer elapsed | 1.679516482 | 1.923077659 |
| Archive writer repeated prevalidation,inside elapsed | 0.829553798 | 0.998578782 |
| Archive full readback,inside elapsed | 0.648313222 | 0.713898274 |
| Event writer elapsed | 0.437141482 | 0.469671933 |
| All payload and receipt forces,inside writer elapsed | 0.263643708 | 0.264631620 |
| All handoff copy and queue,outside writer elapsed | 0.006828973 | 0.007085716 |
| Remaining coordinator/uninstrumented residual | 0.060979702 | 0.066269501 |

B1:duplicate archive prevalidation accounts for15.59% of maintenance wall;all measured payload/receipt forces account for4.95%. The slowest1% requests spend96.70% of their summed latency before dispatch.

B2:duplicate archive prevalidation accounts for17.31% of maintenance wall;all measured payload/receipt forces account for4.59%. The slowest1% requests spend97.15% of their summed latency before dispatch.

The measured next candidate is an [immutable verified archive handoff](VERIFIED_ARCHIVE_HANDOFF_V3.md),which avoids one repeated pre-write parse while keeping complete canonical validation of the forced readback. It needs separate artifact qualification and controlled trials. None of this report's arms executes that candidate. The results do not justify attributing the bottleneck to physical disk,CPU alone or a cross-host network.

## Complete evidence and limits

- [A1 complete native/raw evidence](../evidence/2026-10-25/runpod-cpu/writer-phase-timing-v3/arm-a1-native-r1/README.md),privately closed at`c32b583ea8e6979694af0a633b1534f8a6005728`.
- [B1 complete native/raw evidence](../evidence/2026-10-25/runpod-cpu/writer-phase-timing-v3/arm-b1-native-r1/README.md),privately closed at`517bfe12cc914c58b76233b209f94c4a10932b59`.
- [A2 complete native/raw evidence](../evidence/2026-10-25/runpod-cpu/writer-phase-timing-v3/arm-a2-native-r1/README.md),privately closed at`19f0fe2d65f8c6913918eeba6576b72745fb5252`.
- [B2 complete native/raw evidence](../evidence/2026-10-25/runpod-cpu/writer-phase-timing-v3/arm-b2-native-r1/README.md),privately closed at`2548bf9773a965769336836a139c457264738553`.

The [complete reporting package](../evidence/2026-10-25/runpod-cpu/writer-phase-timing-v3/reporting-r1/README.md) retains the comparison/audit sources,per-arrival decomposition,recovery intervals,phase/receipt checks,private closure proofs,and previous/derived UI index. The four native packages retain every original closed native TAR,CSV,wire/frame/offer,identity,readiness and lifecycle record as lossless compressed scope parts,with full member SHA/size/mode/owner verification. Candidate-codec/reference checks are not an independent matching oracle or binary cold restore.

All51 prior runs and20 cohorts remain unchanged. The index appends four observations in two separate artifact/setup cohorts,55 runs/22 cohorts. No stable marker or prior capacity curve is inferred from this diagnostic. HTTP verification is not a rendered-browser check.

The four fresh lineages cannot be added into continuous endurance. No100M target,independent physical-host fault isolation,millisecond SLA,production certification or HFT endorsement is established. Current all-arrival p99 remains hundreds of milliseconds. The [production acceptance gates](PRODUCTION_ACCEPTANCE.md) remain explicit.
