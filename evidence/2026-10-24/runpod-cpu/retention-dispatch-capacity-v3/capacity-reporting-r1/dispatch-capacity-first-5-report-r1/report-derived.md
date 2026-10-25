# Rotating dispatch: fine maintained CPU capacity curve

Each point below uses one fresh20s lineage of scheduled synthetic IOC orders,one physical session and128 logical producers. All requests,outcomes and raw/native bytes are retained. The source and Linux JAR fingerprint are common to every point. This is a finite exploration;passing points do not establish sustained capacity or a realtime SLA.

|Scheduled /s|Accepted /planned|Confirmed inside20s /s|Window confirmation %|Global accepted p99 ms|Conditional accepted p99 ms|notSent /rejected /UNKNOWN|Finite gate|
|---|---:|---:|---:|---:|---:|---:|---|
|4000|80000/80000|3993.45|99.8363|227.856161|227.856161|0/0/0,0|met|
|6000|120000/120000|5990.25|99.8375|227.026307|227.026307|0/0/0,0|met|
|7000|140000/140000|6934.45|99.0636|230.204995|230.204995|0/0/0,0|met|
|7500|150000/150000|7493.20|99.9093|294.012995|294.012995|0/0/0,0|met|
|8000|160000/160000|7833.45|97.9181|380.731226|380.731226|0/0/0,0|not met|

UNKNOWN lists observed and final counts separately. The finite gate requires all original arrivals accepted,zero notSent/rejection/UNKNOWN,valid native/scheduler/readiness proof,at least99% confirmed within the source window and global accepted p99 at most1s. It controls load progression;it is not a definition of long-term stability. Null global accepted percentiles are never replaced with successful-only conditional samples.

## Maintenance recovery and queue observations

|Scheduled /s|Equivalent offered intervals|Intervals reaching zero recorded waiting|Sampled aggregate queue high|Per-worker queue high|After positive offer p99 ms|Complete maintenance wall s|Reply drain s|
|---|---:|---:|---:|---:|---:|---:|---:|
|4000|23|23|1038|10|11.030881|5.547070|0.179645|
|6000|36|36|528|13|11.404168|8.095313|0.205086|
|7000|43|43|1438|18|11.486357|9.296854|0.082762|
|7500|46|24|1749|21|11.574506|9.925635|0.009498|
|8000|49|0|2745|29|11.794495|10.186573|0.378157|

Recorded waiting is reconstructed from every arrival/dispatch timestamp. It is not exact physical queue occupancy:arrival and dispatch timestamps observe points around queue insertion/removal. Only adjacent setup-free full3072-command maintenance cuts whose end boundaries remain inside the offered window are compared;post-arrival drain is excluded. Zero recorded waiting between cuts supports finite recovery and must not be relabelled an indefinite guarantee. One-second aggregate sampling can alias the maintenance cycle,so a lower sampled high-water does not prove a lower instantaneous global maximum. After-offer latency combines client polling,loopback UDP,replication and service;it is not isolated physical-network RTT. Complete maintenance wall includes the final drain-side maintenance cycle.

All points fix leader0,sync2,ROTATING_CONTINUE,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64 and one physical session. Both original-PID all-member2s readiness gates bracket setup/5s warm-up. No JFR is attached. Three JVMs share one existing32-logical-thread/64GB CPU container over loopback UDP. Source566dd2fa8b185caa54f3c1061fcdf0009bc3cfd0,actual four-JAR fingerprint2b8d7594e03f8eeeef7aaf8e07db12c3bb585ba4ba67970d065c7174420fbf68.79 tests across17 suites qualify this artifact;the first failed lower-level planner attempt is retained.

## Full original private evidence

- [4000/s complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-4000-r1/README.md),private verified commit `11604952725e63c604ce2d19e4cd1f5056e0869d`.
- [6000/s complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-6000-r1/README.md),private verified commit `6ff16ef623e02eb1129dd9c21405ca433ae04ccf`.
- [7000/s complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-7000-r1/README.md),private verified commit `9cacd3a08ec659efad3cf04e64170c51dc0bcd2b`.
- [7500/s complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-7500-r1/README.md),private verified commit `e99dbb75c875110b949e7418c6650ffcb218486f`.
- [8000/s complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-8000-r1/README.md),private verified commit `f54e4a84be114864a9a9d4480ea9ce21fabe7c22`.

Every native point includes the complete compressed original scope TAR,original member SHA/size/mode/owner/directory inventory,lossless part map,raw identity/result audit,readiness rows and closed process records. Raw CSV inputs are rehashed against the original scope inventories before curve aggregation. No raw row is sampled or omitted. Compressed packaging changes archival representation;it changes no application,durability or benchmark setting. Candidate-codec and candidate-matching reference checks are not an independent algorithm oracle. Matching snapshot log messages are not a binary cold-recovery proof.

[Qualification and progression contract](DISPATCH_CAPACITY_V3.md),[prior same-artifact fairness ABAB](DISPATCH_FAIRNESS_RESULTS.md),and[previous all-member-ready curve](READY_READ128_CAPACITY_RESULTS.md) remain separate. These are different artifacts/cohorts;their results are not combined into a new executed throughput result. Repeated trials,longer continuous exposure,an exact instability region and all100M targets remain unproved. [Continuous endurance design](CONTINUOUS_ENDURANCE_PLAN.md) describes the journal,streaming source and segmented retention work still required.
