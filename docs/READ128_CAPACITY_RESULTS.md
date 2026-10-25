# Fixed128-credit capacity exploration

Two finite points pass native/raw qualification. The next attempted point exposed a startup/catchup fault and is retained as unqualified; it does not establish a throughput ceiling.

|Offered/s|Orders|In-window accepted/s|Scheduled-arrival p99 ms|Sampled queue high-water|Qualification|
|---:|---:|---:|---:|---:|---|
|1000|20000|999.65|231.350510|4|qualified finite observation|
|2000|40000|1996.65|234.798035|67|qualified finite observation|
|4000|80000|3993.45|256.316291|1038|UNQUALIFIED: startup/catchup errors|

All planned orders in these three attempts confirmed unique ACCEPTED results, with zero rejected/notSent/observed or final UNKNOWN and valid arrival scheduling. Raw completeness is separate from a healthy-cluster performance qualification. Each row is a fresh20s lineage, not cumulative endurance or sustained capacity.

Same source `3acc84281089f0ed780b69249391f70301bba82e`, actual installed code `08f0ad10d34594ad21fab9621df6c1c263469c71236f32bba21d0b5711d930f6`, leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64, one physical client session and5s pre-load warm-up. Three JVM nodes share one CPU host over loopback UDP. No JFR. No new resources or chargeable instances were created. Prior32/128 ABAB and older capacity curves are different cohorts.

At1000/s and2000/s,96.89% and97.39% of the slowest1% latency occurs before business dispatch;95.19% and95.42% overlaps maintenance while queued. These same-row timestamp descriptions support continuing maintenance-path investigation, but do not isolate network,server or storage causality.

The4000/s attempt logged an ingress bind conflict on follower2 and catchup replay session clash on leader0 before scheduled arrivals. Complete original binary mark-file error records place those failures6.12–6.30s before the arrival origin, with catchup timeout3.87s into the arrival window. The original native controller rejected the logs and remains failed. Higher-load progression is false even though all80000 order identities/results reconcile. Startup readiness must check all followers rather than only process-ready markers and leader replies.

Every original compressed native TAR,CSV,raw frame/index/offer body and decoded result is retained. Files above32MiB in the4000 archive are losslessly partitioned with original paths/bytes/SHA/mode/owner and ordered offset/hash maps. Full byte-stream reconstruction and all315 private Git blobs were verified. No samples are dropped to fit Git.

[Complete curve and timestamp diagnosis](../evidence/2026-10-24/runpod-cpu/retention-read128-capacity-v3/curve-diagnosis-r1/README.md), [1000/s](../evidence/2026-10-24/runpod-cpu/retention-read128-capacity-v3/native-1000-r1/README.md), [2000/s](../evidence/2026-10-24/runpod-cpu/retention-read128-capacity-v3/native-2000-r1/README.md), [failed4000/s](../evidence/2026-10-24/runpod-cpu/retention-read128-capacity-v3/native-4000-r1/README.md). No hard-realtime,zero-latency or100M target is established.
