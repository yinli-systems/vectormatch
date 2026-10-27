# Three-replica thirty-minute endurance, R3

**Correctness and backup continuation pass; the registered sustained latency/timing gate fails.** One uninterrupted1800-second arrival window processed180000 synthetic orders at100planned/s on the existing CPU. All180000 confirmations arrived before the window deadline, with0initial unknown,0unresolved unknown,0not-sent and0business rejection. The source released107 originals more than20ms late. Full-stream scheduled-to-confirmed p50/p99/p99.9 are8.995/33.722/71.917ms.12of30minute windows exceed25ms p99. These measurements do not qualify a fixed-arrival latency SLA.

This is one host with three separate UDP Aeron JVM replicas and a separate generator process, each on a disjoint four-CPU affinity set. Leader0 remained fixed; all use G1,1–2GiB heap and the frozen archive file-sync level2. The workload is the existing bounded single-lot IOC fixture, not the mixed GTC/IOC/cancel TCP workload. It does not establish100K/s or250K/s replicated capacity, independent physical fault domains, hardware power-loss durability or production readiness. The state/outbox profile is finite: the final outbox contains360267pending events; no continuous archival-retention throughput is claimed.

## Qualification and precommitted selection

|30-second100/s qualification|Replica collector|All-original p99 ms|Confirmed inside window|Source timing|
|---|---|---:|---:|---|
|A1|G1|12.391|3000|pass|
|B1|Generational ZGC|11.278|3000|pass|
|A2|G1|32.963|3000|fail|
|B2|Generational ZGC|12.834|2999|pass|

ZGC lowers p99 in both short pairs, but B2 has one fewer confirmation before the exact window deadline. The preregistered no-goodput-regression condition therefore does not promote it; the long run retains G1. This strict finite decision is not evidence that G1 is intrinsically faster. A2 remains a failed timing/latency qualification even though its financial replay passes. See the [frozen protocol](REPLICATED_SUSTAINED_R3_PROTOCOL.md) and [selection receipt](../evidence/2026-10-27/replicated-sustained-r3/preparation/SELECTION.json).

## What the original rows and telemetry show

|Boundary|p50 ms|p99 ms|p99.9 ms|Maximum ms|
|---|---:|---:|---:|---:|
|Source scheduling lateness|0.028|0.070|10.158|124.111|
|Intent-recording plus worker wait|0.079|0.185|9.708|134.167|
|Initial execute round trip|8.892|32.470|67.804|148.601|
|Scheduled arrival to final confirmation|8.995|33.722|71.917|157.979|

These are separate marginal percentiles, not additive components of a selected request. Source `enqueued` is recorded before the synchronous intent writer, so the next column includes writer/lock time and cannot be labelled pure worker-queue latency. The exact source-clock planned-but-not-confirmed peak is16, and it drains to0. This is not a kernel or server queue-depth estimate.

The pre-intent record delay reaches134.050ms; recorded checkpoint force time reaches134.310ms.130of3378accepted originals above25ms have direct same-clock overlap with a recorded checkpoint-force interval. That supports removing recorder blocking as a distinct follow-up, but it does not explain all3378slow requests. The execute round-trip p99 is32.470ms.

|Role|Mean process CPU cores in enclosing sample interval|Observed file-force p99 ms|Observed file-force max ms|Observed GC pause max ms|
|---|---:|---:|---:|---:|
|Replica 0|0.171|13.515|133.586|39.572|
|Replica 1|0.109|13.773|141.689|67.330|
|Replica 2|0.116|14.213|131.377|55.886|
|Generator|0.903|13.438|122.223|27.996|

CPU is computed from each owned process's user+system ticks using SC_CLK_TCK observed on the same boot; no assumed two-vCPU multiplier is applied. File-force/GC figures above are streamed JFR events whose UTC start falls in the approximate arrival window. The full audit separately reconciles the complete streamed recording with each buffered final JFR tail and verifies coverage. Low average CPU usage is consistent with waiting, but these observations are not a randomized proof of one exclusive bottleneck. File-force durations are syscall-level observations, not a physical-media durability certificate.

## State and recovery

Every original intent and terminal checkpoint matches its final CSV row. Final core bytes equal a replay in actual command-sequence order; account conservation, retained-order count, event/outbox continuity and fixed leader all pass. That replay uses the same MatchingEngine implementation and is not an independent matching algorithm. The separate mixed-flow TCP experiments use independent Java and Python models.

The final canonical state has180101retained orders,100000cached results and195producers. Snapshot reading and final validation take117.907seconds after the arrival window and are reported separately; no part of this cost is removed from a request that actually occurred inside the window.

After all four original JVMs stop and the complete private archive is authenticated-download verified,22backed-up members are extracted into a fresh directory on the same host/disk. Restored canonical bytes match the original SHA-256 `ed08597c9d5e16fbf6b099402fa382a62dbcf948541c954eb1004fa610a6cfc4`. Retrying original result sequence180167 returns the cached result without changing the state. A fresh synthetic order executes once at sequence180168; its exact result and post-trade snapshot match the reference. This is a successful backup/continuation check, not an independent disk-fault experiment or a qualified physical-fault RTO.

## Evidence

The [closed result, source rows, telemetry, archive hashes and recovery receipts](../evidence/2026-10-27/replicated-sustained-r3/) retain all failures. The1800-second archive has88members and92,117,668compressed bytes; its SHA-256 is`61fdd8a3fc6a60349cbb6d550e5b935872625b19ee7276430546389937a25eeb`, private asset681025488. Runtime binaries have a separate verified private asset680945826. The archive indexes include every original uncompressed member hash.

Use `scripts/audit-sustained-soak.py` on an extracted original with the recorded JDK's`jfr` tool. Supplemental `scripts/diagnose-sustained-window.py` uses the original archive plus the recorded post-closure host-units receipt; it changes no original file. Its same-clock checkpoint-overlap analysis and CPU method are separate from the registered acceptance test. All measurement and restore JVMs were closed before the next sizing campaign; the existing prepaid CPU remains available.
