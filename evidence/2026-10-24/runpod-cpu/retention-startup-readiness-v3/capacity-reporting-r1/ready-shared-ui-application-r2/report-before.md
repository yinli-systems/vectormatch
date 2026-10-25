# All-member-ready maintained read128 capacity

These are finite20s observations on one unchanged artifact with both all-member startup gates. A passing exploration gate is not sustained capacity or a throughput ceiling.

|Offered/s|Arrivals|In-window accepted/s|All-arrival accepted p99 ms|Conditional accepted p99 ms|Sampled queue high-water|Not sent|Observed/final unknown|Exploration gate|
|---:|---:|---:|---:|---:|---:|---:|---:|---|
|1000|20000|999.75|200.818441|200.818441|11|0|0/0|passed|
|2000|40000|1996.65|228.817372|228.817372|67|0|0/0|passed|
|4000|80000|3993.45|241.596422|241.596422|1039|0|0/0|passed|

Source `e5ac8f7ccb872c2f98c2857aec51ce189b905376`,actual installed fingerprint `1a9ee9586e83c32d6ddab3cf89e927b6ecbb2639b30dab506f8b43c2c774f494`. Same CPU container33ace3d92505,leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64 and one physical client session. Three JVMs share one CPU host over loopback UDP;128 logical workers are not128 physical connections. No JFR. No new resources.

The original three PIDs/CnC files pass two read-only readiness gates: before setup and after setup/5s warm-up. Each requires2s of sampled common commit position,closed elections,term0,expected roles,fresh heartbeat and zero mandatory shared driver/Archive,consensus and service errors. All actual counter rows and ownership bindings were independently recomputed. Sampling is non-atomic and does not prove continuous or hard-realtime health.

The earlier3acc8428 curve remains separate,including its invalid4000/s startup/catchup attempt. The initial023b8e17 readiness artifact also remains failed: its nine-counter assumption rejected the actual shared Archive/driver error-counter wiring before any order. The shared-counter correction passes73 local tests; explicit classpath order reconciles all8 Linux class origins with actual tests. [Implementation and failures](ALL_MEMBER_READINESS_V3.md). These startup changes define a new cohort; differences from older p99 observations are not a paired performance improvement claim.

Raw completeness,measurement validity and stability are distinct. All-arrival accepted p99 is null on any loss/rejection/unknown; conditional p99 includes only accepted orders. The predeclared progression gate requires at least99% in-window confirmations,all original orders accepted,zero unknown/rejected/notSent,valid scheduler and defined p99<=1s. The first nonpassing point stops load increases for diagnosis/repeat. A20s observation cannot establish a sustained SLA.

Every complete original native TAR,CSV,physical request/reply/index/offer body,decoded result,configuration,source/JAR input and process stop is retained in private evidence. Every archive member and raw identity/result binding was checked. Large original files are losslessly partitioned into32MiB Git parts with original path/size/SHA/mode/owner and ordered part maps. Candidate reference/checkpoint logs are not an independent algorithm oracle or binary snapshot/cold-restart proof.

[1000/s complete evidence](../evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/native-1000-r1/README.md), private commit `7b83814fca1b767c769950b081eb869ea3d784e1`.

[2000/s complete evidence](../evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/native-2000-r1/README.md), private commit `cb6f5f9cd3138e89fc52009e10e826650d4364e0`.

[4000/s complete evidence](../evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/native-4000-r1/README.md), private commit `74cf989ece5892522a4f2f1fd58ba06720d05df1`.

No zero latency,hard realtime,100M orders/s,100M physical connections or100M continuous lineage is established.
