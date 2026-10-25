# Immutable handoff: initial comparison remains incomplete

The registered C1/D1/C2/D2 campaign stops after C2 fails its process-identity observation gate. C1 and D1 are valid finite observations;C2 remains invalid and D2 never executes. The candidate removes repeated archive prevalidation,but this campaign does not establish a repeatable performance gain.

Each executed arm uses80,000 fresh one-unit IOC orders at4,000 scheduled arrivals/s for20s,against one pre-funded seeded sell order at10 ticks. Original order outcomes agree with80,000 distinct trade events in each arm. This is a real path through the synthetic matching engine,with one price/maker/fill per order;it is not a multi-level,cancel/replace,external-venue or funded-trading workload.

Leader0,sync2,ROTATING_CONTINUE,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64,one physical session and three JVMs on one CPU host remain fixed. All use the original process sampler,the same pinned JDK/boot/affinity/cgroups,two2s readiness observations around setup/5s warm-up,and the same project-only cache preconditioning. No JFR. C uses timing sourceaed9430d/codef3a5745c;D uses CI6-qualified source23f9c070/code79e5a932. Full payload/receipt force and canonical readback precede either destructive ACK.

| Arm | Native control | Accepted orders / trade events | In-window goodput/s | Qualified all-arrival p99 ms | Diagnostic p99 ms | After-positive-offer p99 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| C1 | Valid finite observation | 80,000 / 80,000 | 3993.45 | 229.613096 | 229.613096 | 11.069032 |
| D1 | Valid finite observation | 80,000 / 80,000 | 3993.45 | 222.965821 | 222.965821 | 17.014943 |
| C2 | INVALID process identity | 80,000 / 80,000 | 3993.45 | — | 240.568357 | — |

All three arms reconcile every planned original outcome,with zero notSent,rejection,observed UNKNOWN or final UNKNOWN. C1/D1 each clear recorded waiting in23/23 comparable offered-cut intervals. All outcomes and invalid status remain visible;the C2 diagnostic quantile cannot substitute for a qualified performance observation.

## What the first pair establishes

Scheduled-to-confirmation p99 changes by-2.89%;maintenance wall changes5.561833365→5.333869314s over27 cycles. Repeated archive prevalidation changes0.990036012→0.000017659s;the immutable handoff flag and zero handoff-copy duration are present in every D1 archive cycle. Complete forced canonical readback and receipt metrics still verify.

Other measured phases become slower:archive readback0.666567529→1.077229423s;event prevalidation0.134192534→0.227562981s;event readback0.144072792→0.239359550s. After-positive-offer p99 increases11.069032→17.014943ms. The phase distributions show persistent differences beyond the first cycle. These observations do not isolate CPU scheduling,JIT,GC,NUMA,network or storage as the cause. Removed work is not a prediction of end-to-end savings. One pair,especially with this tradeoff,is insufficient to claim an extreme or repeatable optimization.

## Why C2 stays invalid

The original controller records`Incomplete process identity`during execution,without the PID/read phase. All four owned JVMs subsequently stop cleanly,and independent raw-byte checks verify all80,000 orders/trades,zero unknown and matching three-node snapshot logs. Nevertheless,the original nativeControlPassed and performanceQualified values remain false. No waiver,rerun of that lineage or valid reclassification is applied.

An independent controlled exit interleaving reproduces the exact old sampler exception. The [identity observation fix](PROCESS_IDENTITY_OBSERVATION.md) binds reads to one proc directory descriptor,rechecks birth/exit state and still refuses malformed live identities. The exact historical C2 trigger remains unproved. A common qualified sampler and new exclusive lineages are required for a fresh full comparison;D2 of this incomplete campaign remains unexecuted.

## Complete private evidence

- [C1 complete original archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/arm-c1-native-r1/README.md):asset675524354,213,635,640 bytes,SHA-256`8e8bd315a48a8107839bec7e9b59e369fcf4b3aa093de6bec6db5010761a33ff`,full authenticated download/member verification at`3c4b668d09b31e0f2ba95674cf84dc8bfb826555`.
- [D1 complete original archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/arm-d1-native-r1/README.md):asset675543971,214,284,009 bytes,SHA-256`d682022d92d627df25979aeed2af86164ca9bf8244bbcafa383327841b87c1c8`,full authenticated download/member verification at`0d1206ed8119369a17ef6c8c18afcb96d6ae9f47`.
- [C2 complete original archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/arm-c2-invalid-native-r1/README.md):asset675570512,213,030,129 bytes,SHA-256`79869cb040b6db1cd99e4d672667fb48d74b9dfe8d97b757be23e1bfb6add2fd`,full authenticated download/member verification at`17a7d5dd6db4afecd71ef866d0e8ac0492017507`.

The [reporting package](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/incomplete-reporting-r1/README.md) preserves every analysis/audit source and result,invalid-control review,trade counting,private closure proofs,prepared-but-unexecuted four-arm report source,original/derived UI index and publication receipts. Native assets retain every original closed native TAR,CSV,wire/frame/offer,configuration,identity,source and readiness/lifecycle record. Member SHA/size/mode/owner/directory inventories are complete. Candidate-codec checks are not an independent matching oracle or binary cold recovery.

The index retains all55 earlier runs and22 cohorts unchanged,and appends these3 observations in2 original-sampler artifact cohorts:58 runs/24 cohorts. C2 is visibly invalid;no stable marker is inferred. An HTTP data check is not a rendered-browser review. Separate reset lineages cannot be added into continuous1M/10M/100M endurance. No sustained capacity,millisecond SLA,physical-host isolation,production certification,HFT endorsement or funded-trading readiness is established.
