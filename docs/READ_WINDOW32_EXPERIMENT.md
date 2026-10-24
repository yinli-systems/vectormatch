# Read-only maintenance credit experiment: 8 vs 32

Status: **predeclared experiment plan, retained verbatim below**. Four exploratory, single-host, RAM-backed native ABAB runs were subsequently completed on 2026-10-24; see [measured results and limitations](READ_WINDOW32_RAMDISK_ABAB_2026-10-24.md). **Disk-backed qualification remains outstanding.** All numeric values and gates in the sections below are original settings or pass criteria, not claimed measurements.

## Why this factor

The measured page-16/page-32, 33,792-order ABAB experiment found page32 read-phase spans of 3.329670381 and 3.084928706 seconds (60.43% and 59.03% of their maintenance-wall totals). Those spans include transport, execution, scheduling, and evidence work; increasing credits may help, but cannot be assumed to shrink them. Existing page32, read8, rate500/s is the control.

Change one factor only: read-only maintenance bank credit limit **8** versus **32**, with both arms using *the same* 32-credit wire-copy, immutable-original failure, raw-trace, allocated-growth and disk admission envelope. Page32, chunk6144, business cap4, workload, owner poll and server/driver idle settings remain fixed. The 1/8 old experiments and default page16 remain unchanged.

## Safety contract and validation

- This is an **opt-in, single-process read-bank width**, not a new Aeron node, additional business client, partition or multi-host capacity claim. Three native JVMs continue to run on one host.
- Both candidate arms call `Config.readWindow32(arrivals,500,selectedWidth)` and `RetentionCapacityPlanV3.commonReadWindow32Plan(...)` and must receive identical `Plan.observation()` values except `requestedReadWindow`. Their common `maxReadOnlyInFlight=32`, `eventFetchCount=32`.
- Any plan exceeding the original 2 GiB raw-trace or 2.5 GiB allocated-growth limits remains rejected; no cap is widened. The original four-physical-offer limit, immutable request bytes, permit deadlines, journal budget, and ACK fences remain in force.
- Every read phase reserves all original wires and flushes request evidence **before arming any offer**. A credit remains owned through completion until reply/timing evidence is flushed and consumed. Wrong semantic events, missing replies, failed sinks and UNKNOWN retain all original wire identities and **fence both ACKs**.
- Tests include 32 simultaneous retained reads; reversed and duplicated replies; exact canonical archive/event exports; 32-original semantic failure, no event receipt and no ACK; equal finite envelopes; invalid and legacy combinations.

## Build and invoke

Java 21, the repo's Gradle wrapper, a fresh writable root and the same native runtime prerequisites as the existing `event-fetch-page-long-cuts` campaign are required.

```bash
./gradlew :cluster:test :cluster:installDist

# Run sequentially, on the SAME host and SAME built distribution.
# Supply a fresh non-existing directory for EACH arm. Never reuse a root.
java --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED \
     --add-opens=java.base/java.util.zip=ALL-UNNAMED \
     -Dvectormatch.retention.idleMaxParkNs=100000 \
     -Dvectormatch.retention.ownerPollMaxParkNs=1000000 \
     -cp 'cluster/build/install/cluster/lib/*' \
     io.vectormatch.cluster.RetentionCapacityAeronPilotV3 \
     /path/to/fresh/A1 read-window32-long-cuts 8 42000

# After A1 is fully closed and preserved, repeat with:
# /path/to/fresh/B1 read-window32-long-cuts 32 42000
# /path/to/fresh/A2 read-window32-long-cuts 8 42000
# /path/to/fresh/B2 read-window32-long-cuts 32 42000
```

The CLI rejects other windows, ports, absent/mismatched idle settings, incompatible page sizes, and invalid workload modes **before starting a node**. Only the explicit `read-window32-long-cuts` selection activates a 32-credit bank. Even the 8-credit control reserves the larger common envelope.

## Evidence gate before any claim

1. Pin one exact source commit, distribution/JAR fingerprints, machine, ports, OS/JVM settings, real effective owner and server/driver configuration and controller implementation across all A1/B1/A2/B2 arms.
2. Require four fresh completed `completion.json` receipts, intact original request/reply tapes, raw-failure evidence, final leader0/term0/sync2, all three matching checkpoint logs, complete archive/event receipt hashes, 12 maintenance cycles and full canonical replay reconciliation.
3. Require exactly 33,792 uniquely accepted orders in each 67.584s / 500-per-second workload; zero final or observed UNKNOWN, rejected, not-sent, unresolved warnings, lost original identities or ACK before verified receipt.
4. Compare each paired **nearest-rank all-arrival p50/p95/p99**, maintenance wall duration, read-phase spans, read offered-overlap high water, per-RPC counts, physical-offer attempts and native RSS. Verify that increased concurrency actually reaches 32 during long event phases.
5. Report both A1→B1 and A2→B2 effects separately with the raw inputs, checksums and uncertainty. No statistical-significance, stable-throughput, zero-latency, one-lineage endurance, independent-host capacity or 100M-order claim follows from four shared-host trials.

A failed pair is a failed candidate, not evidence to discard. Maintain all traces and the existing page32/read8 result as the benchmark to beat.
