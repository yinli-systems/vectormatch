# Asynchronous maintenance V4: correctness qualification

The opt-in coordinator has passed full Linux correctness checks and a real three-JVM UDP functional experiment on the existing prepaid CPU. This closes the functional gate before a separately registered capacity comparison. No throughput or p99 is measured by this fixture.

| Verified item | Result |
| --- | --- |
| Fresh Linux CI |422 Java and197 Python tests;zero failure/error/skip |
| Real PostgreSQL integration |11 tests,included in Java total |
| Actual CI source |`b6a53eeb812877cfb6cabdf01cfeb4548de30502` |
| Actual application fingerprint |`c6fc2e180e266f5d9defb7c1e2e7c80bf3692d5d75b9fe6a87949b5b2edd5001` |
| Native Linux business/trades |1003 commands;1000 unique one-unit trades;1001 accepted Places |
| Complete events |2003 events;2001 market events |
| Exact archive cuts |512,640,1003 |
| Extra business during first file wait |128 commands,independently counted from positive physical offers |
| Original physical tapes |476 attempts;473 positive offers;473 replies |
| Logical maintenance RPCs |150 |
| Read credits/generations |32 maximum retained;seven generations;all credits consumed |
| ACK fences |Both forced/full-readback prefix receipts and each original control intent precede destructive offer calls |
| Node snapshots and cold restore |All three snapshot hashes match;all three stopped/restarted services restore the same hash |
| Ownership closure |Six node lifetimes across two generations and parent observed;all strictly absent afterward |

Final combined-state SHA-256:`580280f2467a12337ee1afe50da2585eac0a65f22ecfe813d478a508b231841c`. The same-adapter reference replays every positive original physical offer in its actual order and matches every received reply. A separate Python parser independently audits the raw trace,event prefixes,original deadlines,credit consumption and before-ACK receipt chronology. It counts1000 unique one-unit trades with notional10000. Neither is an independent matching algorithm. The actual six node logs contain exactly the expected readiness/service/leader/snapshot lines,with no warnings or error markers.

All245 application JAR class bodies equal actual CI compiled bodies;`MatchingEngine.class` is unchanged from the prior baseline. All454 files of the actual CI JDK and CPU runtime JDK are byte-identical. Twelve loaded Linux class origins/profile bounds/phases were verified before native admission. All five Java test tasks executed without result cache in a fresh Gradle home. The general CI failover smoke passed,but measured11498.907ms from leader kill to the next confirmed command including client handling;this is not an election-only latency or production SLA. Hosted GitHub billing remains unresolved;the successful run uses the existing one-job CPU runner.

## Preserved failures and their corrections

An earlier full Linux run was refused by unchanged disk-admission guards in two old pilots at1.57/1.48GB usable space. The twelve new coordinator tests passed,but the run overall failed and later Python/failover/web checks did not execute. Only fully byte-verified reconstructible completed runner distribution caches were retired;original app state,worktrees,compiled tests,logs and native evidence were preserved. The subsequent complete Linux run passed.

The first V4 Linux UDP controller then refused an incorrect four-JAR child-classpath contract before any business wire/logical tape was created. Actual qualified class origins deduplicate to three JARs. The failed scope remains failed. Its three children were individually matched to original Java-owned birth/command/argument SHA using the same JDK before pidfd cleanup;all three process directories disappeared. The corrected controller derives argv from actual class origins. Nine local and nine actual system-Python contract tests passed before its fresh second attempt. Cleanup now registers exact direct children before stopping them,and allows the Java program's own finally before considering a parent signal. Complete first-failure/recovery originals remain separately archived.

## Reproduce and scope

`./gradlew :cluster:asyncMaintenanceSmokeV4 -PasyncV4Root=<new-state-directory>` launches three local JVM nodes and refuses existing state. It uses leader0,sync2,the finite batch profile,32 read credits,page32,chunk6144 and an intentional held-original-file correctness gate. Full original sources,commands,wire tapes,observations,receipts,node logs,hot state,snapshots,ownership/cleanup records,independent audit and derivation are preserved in [the complete native/report archive](../evidence/2026-10-25/runpod-cpu/async-maintenance-v4/linux-udp-functional-r2/README.md). The native original collection contains116 files and1226936644 logical bytes;every member,size,SHA,mode,owner and directory was verified. [Pre-execution Linux qualification](../evidence/2026-10-25/runpod-cpu/async-maintenance-v4/linux-udp-admission-r1/README.md) and [corrected admission plus first failure](../evidence/2026-10-25/runpod-cpu/async-maintenance-v4/linux-udp-admission-r2/README.md) remain available.

This proves finite same-host correctness and dispatch progress during held file work. It does not establish a capacity gain,p99 SLA,independent physical-host/storage durability,client continuation or new orders after cold restore,100M continuity,HFT endorsement,production certification or funded external trading. The earlier V3/encoder capacity curves remain separate. The original failed encoder candidate is not promoted by this work. The evidence console adds one functional run without performance metrics;all72 prior runs and all32 capacity cohorts remain unchanged.
