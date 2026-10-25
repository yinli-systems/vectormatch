# Immutable handoff retest:one common qualified sampler

Both paired finite observations meet the registered criterion of lower all-arrival p99 and maintenance wall time. This is a finite descriptive comparison,not statistical significance,sustained capacity or a production SLA. All offer-to-reply and phase tradeoffs remain visible below.

Each arm contains80,000 fresh one-unit IOC orders at4,000 scheduled arrivals/s for20s,against one pre-funded seeded sell order at10 ticks. Every arm reconciles80,000 distinct accepted orders and80,000 trade events,with zero notSent,rejection,observed UNKNOWN or final UNKNOWN. This workload exercises one price,maker and fill per order;multi-level sweeps,cancel/replace,external venues and funded trading require separate evidence.

The [prospective retest registration](VERIFIED_ARCHIVE_HANDOFF_EXIT_WAIT_V3.md) fixes leader0,sync2,ROTATING_CONTINUE,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64,one physical session/three JVMs on one CPU host,JDK/boot/affinity/cgroups,readiness around setup/5s warm-up,no JFR,and the same project-only cache preconditioning. All four use the same CI8-qualified proc-directory/stat/cmdline/stat sampler with bounded PF_EXITING wait for terminal proof. C uses sourceaed9430d/codef3a5745c;D uses source23f9c070/code79e5a932. All227 CI8 application classes equal qualified CI6 classes;actual benchmark JAR identities remain unchanged.

The [initial comparison](VERIFIED_ARCHIVE_HANDOFF_INITIAL_RESULTS_V3.md) remains separate and incomplete:C1/D1 valid,C2 invalid,D2 unexecuted. Its failure is never renamed or added as a valid retest observation. The first common-sampler retest also remains incomplete:C1 valid,D1 invalid,C2/D2 unexecuted. Both invalid observations remain visible. The proven-exit sampler changes control-plane observation;all three campaigns stay separate.

| Arm | Accepted / trade events | In-window goodput/s | All-arrival p50 ms | All-arrival p99 ms | After-positive-offer p99 ms | Clearing comparable intervals | Maintenance wall s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C1 | 80,000 / 80,000 | 3993.45 | 7.027770 | 236.456120 | 11.879762 | 23/23 | 5.687831711 |
| D1 | 80,000 / 80,000 | 3993.45 | 7.247166 | 222.490080 | 13.218056 | 23/23 | 5.305104728 |
| C2 | 80,000 / 80,000 | 3993.45 | 7.153841 | 229.942534 | 10.591247 | 23/23 | 5.690259952 |
| D2 | 80,000 / 80,000 | 3993.45 | 7.262411 | 211.041407 | 10.749765 | 23/23 | 5.008048526 |

## Paired observations

C1→D1:all-arrival p99 changes-5.91%;maintenance wall-6.73%;after-positive-offer p99+11.27%.

C2→D2:all-arrival p99 changes-8.22%;maintenance wall-11.99%;after-positive-offer p99+1.50%.

In-window goodput counts confirmations inside the20s arrival window;all80,000 originals reconcile after drain. Comparable full-cut recovery intervals exclude setup and post-arrival drain. Two short observations per artifact do not establish a sustained throughput ceiling. After-positive-offer latency includes client polling,loopback transport,replication and service;it is not isolated network RTT.

## Complete phase accounting

Durations below are seconds summed over each arm. Source-RPC intervals are merged by monotonic union,not summed across concurrent calls. Writer subphases are components of elapsed and must not be added to elapsed again. Copy/queue precede elapsed. Remaining coordinator/observation/encoding costs stay in an explicit residual;no phase is labelled pure hardware or CPU latency.

| Duration,s | C1 | D1 | C2 | D2 |
| --- | ---: | ---: | ---: | ---: |
| Maintenance wall | 5.687831711 | 5.305104728 | 5.690259952 | 5.008048526 |
| Source-RPC interval union | 2.446090439 | 2.432989129 | 2.411767635 | 2.530529824 |
| Coordinator archive verification | 0.876431618 | 0.922098527 | 0.851942048 | 0.897250705 |
| Archive writer elapsed | 1.862358464 | 1.269335868 | 1.902959118 | 1.046661293 |
| Archive repeated prevalidation,inside elapsed | 0.985543639 | 0.000022100 | 1.006202157 | 0.000017298 |
| Archive full readback,inside elapsed | 0.695900841 | 1.056075247 | 0.718501256 | 0.853953852 |
| Event writer elapsed | 0.433923996 | 0.616545975 | 0.461353836 | 0.475390075 |
| All payload/receipt forces,inside writer elapsed | 0.229840905 | 0.242779556 | 0.229360177 | 0.228178440 |
| All handoff copy/queue,outside elapsed | 0.006848404 | 0.003091748 | 0.005394635 | 0.002719933 |
| Remaining coordinator/uninstrumented residual | 0.062178790 | 0.061043481 | 0.056842680 | 0.055496696 |

Every original cycle and all corresponding payloads/receipts are audited. C archive receipts retain the legacy handoff fields;D archive cycles explicitly identify the immutable verified handoff,with zero second handoff copy. Event persistence remains unchanged. Exported write/force/readback values match their receipts exactly;all seven serial writer phases fit within elapsed. Every byte length and payload hash agrees. Complete canonical forced readback,payload/receipt forces and ticket completion still precede either destructive ACK. Directory-entry/independent-storage crash durability is not established by file force/readback alone.

## Original evidence and practical limits

- [C1 complete native/raw archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/exitwait-arm-c1-native-r1/README.md),privately closed at`bd882feae5a760494a7b2ab4b24de9c3b8b07257`.
- [D1 complete native/raw archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/exitwait-arm-d1-native-r1/README.md),privately closed at`cd98e3d68dc1e4726764094f34c99ff071d4f46f`.
- [C2 complete native/raw archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/exitwait-arm-c2-native-r1/README.md),privately closed at`4e7ae31644531906ffcb5965cf497271e9f10205`.
- [D2 complete native/raw archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/exitwait-arm-d2-native-r1/README.md),privately closed at`88f7af849208c10f835998a7aff87df3c25cbbf8`.

The [complete reporting package](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/exitwait-reporting-r1/README.md) retains all analysis sources/results,trade/event checks,per-arrival decomposition,recovery intervals,schema/receipt checks,private proofs,previous/derived index and publication receipts. Each native asset preserves every original closed native TAR,CSV,wire/frame/offer,configuration,identity,source,readiness and lifecycle body. Complete authenticated downloads and member SHA/size/mode/owner/directory verification precede every next case. Candidate-codec checks are not an independent matching oracle or binary cold recovery.

All58 previous runs/26 cohorts remain unchanged;the index appends4 observations in2 common-sampler artifact cohorts,64 runs/28 cohorts. No stable marker or earlier capacity curve is inferred from this fixed-rate retest. HTTP verification is not browser rendering. Separate fresh lineages are not continuous endurance. No5ms p99 SLA,independent physical-host isolation,production certification,HFT endorsement,external/funded trading readiness or100M target is established. Those [production acceptance gates](PRODUCTION_ACCEPTANCE.md) remain separate.
