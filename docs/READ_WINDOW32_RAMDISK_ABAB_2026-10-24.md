# Read-window 8 vs 32: exploratory native ABAB results (2026-10-24)

**Status:** Four sequential, complete native runs passed the correctness/evidence gates on a single RunPod host with **`/dev/shm` (tmpfs)** as their fresh workload root. This is evidence that the candidate executes correctly and shows a repeatable *same-host, RAM-backed P99 reduction*, **not evidence of disk durability, disk-backed throughput, distributed capacity, or statistically significant improvement**. See [READ_WINDOW32_EXPERIMENT.md](READ_WINDOW32_EXPERIMENT.md) for the predeclared method and gates.

## Provenance

- Candidate source commit executed: `c07b48bda21b93bbd37e3277e71a06b33274afc5` on `codex/retention-read-window32` (the documentation commit containing this report is later).
- Runtime: Temurin OpenJDK **21.0.13+9**, Linux **6.8.0-147-generic x86_64**, **32** visible logical processors.
- Native topology: three separate Aeron cluster JVMs plus one owning client on **one host**, same prebuilt distribution and UDP base port **42000**, strictly sequential fresh roots A1/B1/A2/B2.
- Fixed factors: 33,792 scheduled arrivals at 500/s (67.584 s), 12 maintenance cycles, 6,144-byte archive chunks, event fetch count 32, business in-flight cap 4, owner max requested park 1 ms, retention/driver max requested park 100 μs; both arms reserve the common 32-credit tracing and growth envelope.
- Deliberate sole treatment factor: **read-only maintenance bank credit 8 or 32**. Both treatments actually reached their selected hard capacity and offered-awaiting-reply high-water mark.
- Built JAR SHA-256:
  - `cluster-0.1.0-SNAPSHOT.jar`: `e63a1ee9f4f3d6ca96dd83ad89bbc19a4ef3c4ed948cd655d76e43bd1bad2192`
  - `core-0.1.0-SNAPSHOT.jar`: `e70c588bc3fe3926c274b57d41caa252d0afc0a6c80b1b4aca0a8c3a2105779f`
- Filesystem: **RAM-backed tmpfs** under `/dev/shm/vectormatch-read32-r1/{A1,B1,A2,B2}`; the archive was subsequently copied to network-mounted persistent `/workspace`. Force-and-readback is checked by the program, but tmpfs **cannot establish physical power-loss durability**.

## Results

Latencies are all-arrival, confirmed unique **ACCEPTED** order completion minus each arrival's *scheduled* offset (includes scheduling, admission, transport and maintenance queuing); nearest-rank `ceil(p*N)` from each full `arrivals.csv`. All computed P99s exactly match the program's `allArrivalP99Ns`.

| Arm | Credit | P50 (ms) | P95 (ms) | P99 (ms) | 12-cycle maintenance wall (s) | Read offered/awaiting high-water |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A1 | 8 | 1.298576 | 2.193796 | 185.559458 | 2.709698 | 8 |
| B1 | 32 | 1.328268 | 2.150042 | 135.922402 | 2.195716 | 32 |
| A2 | 8 | 1.348859 | 2.200012 | 192.815877 | 2.809563 | 8 |
| B2 | 32 | 1.338463 | 2.168104 | 144.952906 | 2.290248 | 32 |

- Matched-pair A1→B1: P99 **−26.7499%**, maintenance wall **−18.9682%**.
- Matched-pair A2→B2: P99 **−24.8231%**, maintenance wall **−18.4838%**.
- Descriptive two-run means: P99 **189.187668 → 140.437654 ms (−25.7681%)**; maintenance wall **2.759631 → 2.242982 s (−18.7217%)**. These are **two pairs, not confidence intervals**.
- P50 remains approximately 1.3 ms, and P95 approximately 2.2 ms. The observed gain is predominantly a **P99 tail improvement**, not a 25% improvement of the typical request.
- In *every* arm: **33,792/33,792** planned arrivals confirmed as unique accepted orders, **0** not-sent, **0** final-unknown, **0** arrivals over 20 ms late from the scheduler, `schedulerTimingValid=true`, 12 completed maintenance cycles, **499.955611** confirmed accepted orders/s within the 67.584 s arrival window, `completion.passed=true`, `allOwnedStopped=true`, `physical-reference-reconciliation.passed=true`.
- Exactly **4,738 logical maintenance RPCs** per run: **2,589 ArchiveChunk + 2,113 FetchEvents + 12 each PrepareArchive, ArchiveCommit and EventAck**, with no logical maintenance failures. The same RPC mix was executed for both read-window widths.
- End positions match across runs: leader member 0, businessSeq 33,795, eventSeq/exportedEventSeq 67,587, marketSeq 67,585. Combined hashes vary because independently generated run lineages differ; do **not** compare full run hashes for equality.
- Allocated growth reached **451,461,120 / 452,136,960 / 451,321,856 / 451,854,336 bytes** for A1/B1/A2/B2, all below the unchanged **754,102,673-byte** growth guard.

## Native command

With the pinned Java and built distribution, sequentially run a new root per arm:

```bash
/opt/vectormatch-cpu/tools/jdk/bin/java \
  --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED \
  --add-opens=java.base/java.util.zip=ALL-UNNAMED \
  -Dvectormatch.retention.idleMaxParkNs=100000 \
  -Dvectormatch.retention.ownerPollMaxParkNs=1000000 \
  -cp 'cluster/build/install/cluster/lib/*' \
  io.vectormatch.cluster.RetentionCapacityAeronPilotV3 \
  /dev/shm/vectormatch-read32-r1/A1 read-window32-long-cuts 8 42000
```

Repeat after full teardown for `B1:32`, `A2:8`, `B2:32`, replacing only the fresh run root and window selector.

The quantiles above are reproducible from `load/arrivals.csv` by selecting rows with `status=APPLIED` and `result_code=ACCEPTED`, subtracting column 6 (`scheduled_offset_ns`) from column 12 (`reply_completion_offset_ns`), numeric sorting, and selecting the nearest-rank positions. The maintenance wall duration is the sum of `cycleEndedMonotonicNs - cycleStartedMonotonicNs` for the 12 `load/maintenance/cycle-*.verified.txt` files.

## Preserved evidence and verification

- Persistent RunPod archive: `/workspace/vectormatch-read32-native-r1/read32-shm-abab-r1.tar.zst` (**~66 MiB** compressed; includes all four roots, native node logs, original offer/request/reply tapes, `arrivals.csv`, writer data, physical reference reconciliation, snapshot and ACK evidence, completion receipts).
- Archive SHA-256: `ab40402d2914569bed5f8568723ed4345d8bb5441eb45eabee6cc38a3bb8debe`. Executed **`zstd -t` successfully** after saving to persistent storage.
- Prior failed /workspace attempts preserved separately at `/workspace/vectormatch-read32-native-r1/A1` and `A1-r2`: one exposed mismatched Agrona classpath ordering and the other stopped at the **unmodified allocated-growth/free-space guard**. We fixed child JVM classpath source-order selection on the candidate branch (prefer the matching `DirectBuffer` before shaded Aeron classes), rebuilt, and did not silently bypass guard thresholds.
- Targeted retention tests for plan, bank and 32-read maintenance passed (**29** tests, zero skipped) and the candidate distribution built. The **full cluster test suite is not claimed green**: older integration tests exhibited node-start timeout behavior, and an existing `RetentionAeronAdapterV3Test` assertion still expects FetchEvents count 17 to fail though the current common envelope is 32. These need independent baseline/test maintenance before claiming a green suite.

## Limits and next acceptance gate

1. **Disk qualification still required.** These runs executed journal/files under tmpfs, where `force()` and readback do not demonstrate real nonvolatile flush, device tail latency or power-loss durability. They are not comparable to earlier disk-backed page-size experiments.
2. **Host isolation** is absent: four consecutive single-host runs share CPU, caches and system state. Only two paired repeats, no randomization, no CIs, no overnight endurance, no multi-host network.
3. **Correctness oracle limitation:** the physical reference is the **same candidate adapter** replayed in actual positive-offer order, not an independent matching algorithm. Native receipts/snapshots still add meaningful reconciliation checks, but this cannot independently prove economic correctness.
4. **Performance attribution** remains provisional until thread/GC/CPU/RSS traces and per-read-phase spans are analyzed. The unchanged 4,738 logical RPC count and attained read concurrency support the credit-window hypothesis but do not prove causality by themselves.
5. Next: move to an isolated **local ext4/XFS physical disk** with verified budget (`maxAllocatedGrowth + minFreeRuntime` plus safe headroom), retain the exact guard/fences and client settings, run multiple randomized 8/32 pairs plus sensitivity to rates and archive workloads; validate baseline/full test suite, independent correctness reference, and failure-injection/recovery before any production or distributed claim.
