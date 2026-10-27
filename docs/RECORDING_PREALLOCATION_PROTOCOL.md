# Recording preallocation: fixed-config ABAB

This experiment follows the closed [per-request attribution campaign](REPLICATED_STAGE_TRACE_RESULTS.md). In its two traced arms, durability/quorum gating accounted for 86.67% and 67.28% of the summed latency of the slowest 1% of requests. This identifies a software wait boundary, not the sole physical cause. The experiment tests whether moving recording allocation to startup reduces file-force stalls. It does not weaken durability or change defaults.

## Frozen intervention and measurement

Use the existing prepaid CPU host and pinned boot, Java 21 and Aeron 1.53.3. Three replica JVMs and a separate source JVM occupy the same four disjoint CPU sets as the previous campaign. Fixed leader 0, G1, 1–2 GiB heap, 1 ms park, shared media drivers, overlay filesystem, and archive/catalog/consensus file-sync level **2** remain unchanged. This is one physical host, not three fault domains.

All arms load identical application/native/shadow JARs, with full request tracing enabled and a shared attested native CLOCK_MONOTONIC clock. The sole arm switch is `vectormatch.stage.preallocate=false` (A) versus `true` (B). B calls Linux `fallocate(FALLOC_FL_KEEP_SIZE)` on an existing 128 MiB recording immediately after Aeron sets its logical length, before arrivals. No file bytes, logical size, sync calls, acknowledgment policy or storage device change. Unsupported allocation fails; there is no zero-writing emulation or fallback.

Run A/B functional checks (2 s × 10/s), then **A1, B1, A2, B2**, each **60 s × 100/s**, on fresh equivalent synthetic states. Preserve every original, including failures, source late releases, not-sent, rejects and unknowns. Freeze hashes and the complete launch matrix before starting. Record allocated blocks and logical lengths before the source starts; require all B recordings physically allocated according to `st_blocks`, and retain startup duration and space cost. The source, warmup, arrival plan, trace capacity and all other flags are identical within each pair.

## Pre-registered selection

Both pairs must satisfy all of the following before selecting B for a **30-minute × 100/s** run:

- Every original has its correct final accepted result, no not-sent/rejected/unknown, and exact equivalent final state across all four arms.
- Both arms pass the existing source-validity and finite-window gates (source maximum lateness ≤20 ms, ≥99% original confirmations within the window, end backlog zero, p99 ≤25 ms).
- In **each** pair, B/A p99 ≤0.90 and B/A p99.9 ≤1.00. No averaging opposite directions into a win.
- All stage joins are complete, all tapes have zero overflow, native file allocation and actual patched class origins verify, and no owned process remains after closure.

If either pair fails, preserve the negative result and do not run an additional candidate endurance test or promote a default. The earlier 30-minute baseline remains archived separately. If both pass, run the registered 180,000-original candidate test with the same configuration and complete metrics, stages, correctness, archive verification and closure. Passing a finite run alone does not establish a production SLA. This workload fits one segment, so rollover behavior is outside this claim.

## Qualification and reproducibility

The native qualification checks an existing 128 MiB file with head/tail sentinels: before/after SHA-256 and logical length remain equal while allocated space rises from 8 KiB to 128 MiB. Preserve the first failed fixture (one-byte tail offset error) and corrected fixture, not only the successful result. The initial Java test fixture also exposed macOS's `/var` symlink; the corrected test resolves its temporary root without relaxing the implementation's symlink rejection. Keep both test records.

Build with `scripts/build-replicated-stage-patch.py --preallocation` and the frozen classpath. The patch manifest verifies original upstream source hashes. `scripts/audit-recording-preallocation.py` composes full original-request auditing, exact per-position stage joins and pre-arrival allocation proofs. Archive original JFR, GC, process metrics, logs, snapshots, samples and stage tapes in the private draft release; Git contains manifests, hashes, scripts and compact audit results.

Java [`RandomAccessFile.setLength`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/RandomAccessFile.html#setLength(long)) defines logical length. Linux [`fallocate`](https://man7.org/linux/man-pages/man2/fallocate.2.html) with KEEP_SIZE reserves blocks without extending the file. [`posix_fallocate`](https://man7.org/linux/man-pages/man3/posix_fallocate.3.html) documents fallback-emulation caveats, which is why this diagnostic uses the Linux syscall and fails if unsupported. `FileChannel.force(true)` timing includes OS scheduling and filesystem waits; it does not isolate physical drive latency or certify survival of power loss.
