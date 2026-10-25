# Immutable-batch encoding:fixed6000/s C1/D1/C2/D2

The four observations do not meet the registered descriptive criterion of full acceptance and lower scheduled-to-confirmed AND offer-return-to-completion p99 in both pairs. The candidate is not promoted on this comparison. Two observations per artifact are not statistical significance,a sustained capacity ceiling or a millisecond SLA. All other phase/recovery tradeoffs remain visible.

[Prospective registration](BATCH_WIRE_VALIDATION_COMPARISON_V3.md) fixes6000 scheduled arrivals/s for20s,120,000 fresh one-unit IOC buys against one pre-funded seeded maker at10 ticks per arm. Baseline C is source23f9c070/artifact79e5a932. Candidate D is sourceb5ce776e/artifact337dcfcd. Both retain immutable verified archive handoff;only RetentionWireV3.class changes. D removes one redundant reconstruction of an already validated immutable BusinessBatch;constructor/UTF-8/nested encoding and complete canonical decode checks remain. No trusted-wire bypass,shared mutable cache or wire version change.

All four use the same prepaid CPU host/container/boot,JDK,cgroups,affinity,leader0,sync2,ROTATING_CONTINUE,W128/Q64,one physical session,three256MiB-heap JVMs,read128/page32/batch4/chunk6144,owner1ms and driver100us. Both2s original-PID readiness gates around setup/5s read-only warm-up,the same project-only advisory cache preconditioning,and all seven qualified control/lifecycle source bodies remain. No JFR or GC logging is added;GC and exact allocation costs are unavailable in this uninstrumented comparison. The original failed7500 capacity point and parent-only JFR diagnostic remain separate;8000 remains unexecuted and no higher load is authorized.

| Arm | Planned | Accepted/trades | NOT_SENT | In-window goodput/s | Global accepted-arrival p99,ms | Accepted-only p99,ms | After-offer p99,ms | Clearing comparable intervals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C1 | 120000 | 120000 | 0 | 5990.25 | 305.786289 | 305.786289 | 27.358936 | 33/36 |
| D1 | 120000 | 120000 | 0 | 5990.25 | 205.089068 | 205.089068 | 13.198048 | 36/36 |
| C2 | 120000 | 120000 | 0 | 5990.25 | 220.220761 | 220.220761 | 12.602945 | 36/36 |
| D2 | 120000 | 120000 | 0 | 5990.25 | 235.339934 | 235.339934 | 15.693471 | 36/36 |

Server rejection,observed UNKNOWN and final UNKNOWN are zero in all four observations;every accepted original is linked to exactly one unique trade and complete original outcomes reconcile. Global accepted-arrival p99 is undefined on any NOT_SENT;conditional successful results are never substituted for missing outcomes. Goodput counts confirmations inside the20s arrival window;after-offer latency includes client polling,raw evidence work,loopback transport,replication and service,not pure network RTT.

## Both paired differences

C1→D1:global accepted-arrival p99 -32.93%;after-offer p99 -51.76%;maintenance wall +1.80%;in-window goodput +0.00/s.

C2→D2:global accepted-arrival p99 +6.87%;after-offer p99 +24.52%;maintenance wall -1.20%;in-window goodput +0.00/s.

The primary criterion was fixed before C1. Neither a single faster pair nor a different successful-only metric is enough. Shared-host variation,JIT/startup,unrecorded GC,storage and scheduling are not uniquely isolated. These short observations cannot establish production tail latency,causal phase attribution or long-term stability. Separate reset lineages do not constitute continuous endurance.

| Phase,total seconds | C1 | D1 | C2 | D2 |
| --- | ---: | ---: | ---: | ---: |
| Maintenance wall | 6.897625818 | 7.021984402 | 7.351790206 | 7.263480183 |
| Source-RPC interval union | 3.389622579 | 3.183944552 | 3.474721144 | 3.457886381 |
| Coordinator canonical archive verification | 1.056124347 | 1.248348269 | 1.285216526 | 1.141028165 |
| Archive writer elapsed | 1.605636733 | 1.699345547 | 1.687729842 | 1.715698770 |
| Archive full readback,inside writer elapsed | 1.290260869 | 1.379984876 | 1.364300605 | 1.396989107 |
| Event writer elapsed | 0.783354020 | 0.810014724 | 0.830643997 | 0.868164317 |
| All payload/receipt forces,inside writer elapsed | 0.397783664 | 0.379668845 | 0.415822307 | 0.398486799 |

Concurrent RPC intervals are merged by monotonic union. Writer subphases are components of elapsed and must not be added again. Payload/receipt force(true),complete canonical readback and both durable tickets remain before either destructive ACK. This does not establish physical-host loss durability. Comparable clearing intervals exclude setup/source-exhausted drain and reconstruct recorded waiting,not exact physical queue occupancy. All original raw/native/source/readiness/lifecycle records remain available.

## Reproduction and limits

- [C1 full original native/raw archive](../evidence/2026-10-25/runpod-cpu/batch-wire-validation-v3/arm-c1-native-r1/README.md),private commit`2f7b1b852e89303454d273730393b266b081743c`,asset`675922700`,SHA-256`3e08a492c5f29959f7e4d06d67691560428e56191e647307887532f4e2dd110a`.
- [D1 full original native/raw archive](../evidence/2026-10-25/runpod-cpu/batch-wire-validation-v3/arm-d1-native-r1/README.md),private commit`4cb2bbaae3a704dbaaba93f4d7aa8b3235e93b20`,asset`675940827`,SHA-256`4a0967b4f2fc42d78681a97c31ca2a013fa5ce27a558531f624f34c077438ef0`.
- [C2 full original native/raw archive](../evidence/2026-10-25/runpod-cpu/batch-wire-validation-v3/arm-c2-native-r1/README.md),private commit`81a1424bcd71fd7020d4e86315907ee4dfb417ad`,asset`675958113`,SHA-256`52f7c92c49f77bc07c5921bf9972ddfd14f1e3f6e3cc86437b96062860575a7c`.
- [D2 full original native/raw archive](../evidence/2026-10-25/runpod-cpu/batch-wire-validation-v3/arm-d2-native-r1/README.md),private commit`89bc55faca0742cca50501ef4283dd841dc784b3`,asset`675974388`,SHA-256`52f3cfcf25dae309966a0f8ca52c426080643035d92ff5db71c88e108c8937b4`.

[Complete qualification](../evidence/2026-10-25/runpod-cpu/batch-wire-validation-v3/qualification-r1/README.md) preserves actual forced Linux CI9:394 Java tests including11 real PostgreSQL integrations,197 Python tests,failover/snapshot/restart and web checks,all zero failure/error/skip. All227 JAR classes match actual compiled bodies;only the intended class differs from C. All454 actual CI9/benchmark JDK file bodies match.39 forced local tests and10,839 byte-identical differential rows cover valid/mutated/truncated/oversized/invalid-constructor cases. This is finite compatibility evidence,not an independent matching algorithm. Hosted account billing remains unresolved;the green run uses the existing one-job CPU runner.

[Complete comparison derivation](../evidence/2026-10-25/runpod-cpu/batch-wire-validation-v3/comparison-reporting-r1/README.md) retains every analysis source/result,phase/recovery/trade audit,all private proofs,local-space guards and sparse-checkout receipts,original/derived index and HTTP checks. Every native asset is authenticated-downloaded in full and every member verified before the next arm. Space safeguards remain unchanged. Historical checkout copies omitted after exact Git-blob verification remain fully recoverable from the same private Git commit;original raw evidence/Git objects are not deleted.

All68 previous runs/30 cohorts remain unchanged;four observations in two artifact cohorts make72/32. No stable marker or inferred capacity curve is added. HTTP checks are not browser rendering. No independent physical-node isolation,5ms p99 SLA,production certification,HFT endorsement,100M continuity or external/funded-trading readiness is established. The separate asynchronous V4 branch remains undeployed and excluded.
