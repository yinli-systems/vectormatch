# Actual CPU capacity pilot: closed evidence and independent audit

This is one completed, functionally valid **finite overload pilot**, using frozen source `4102446b333573efde2b33a0eb53a8177575bad5`. Both arms eventually accepted all 6,400 distinct synthetic load orders, but each returned only 3,069 accepted replies within the fixed 12.8-second arrival window. Neither arm proves stable service at the offered 500 orders/s. Controller attempt `attempt-r1` closed successfully at `2026-10-24T06:03:42.871306Z`; this collection performs read-only SSH inventory/transfer and local auditing only.

| Independently derived result | Cap 1 | Cap 4 |
|---|---:|---:|
| Arrivals at 500/s | 6,400 | 6,400 |
| Accepted load orders eventually confirmed | 6,400 | 6,400 |
| Accepted replies inside the 12.8 s window | 3,069 | 3,069 |
| Window goodput | 239.765625/s | 239.765625/s |
| All-arrival nearest-rank p99 | 7.536495815 s | 7.399907680 s |
| Raw last-reply drain beyond the arrival window | 7.175610967 s | 7.023707470 s |
| Raw final-maintenance boundary beyond the window | 7.792911955 s | 7.642407882 s |
| Reported total source drain | 7.793246221 s | 7.642723548 s |
| notSent / initial UNKNOWN / final UNKNOWN / rejection | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Complete logical maintenance RPCs | 1,785 | 1,785 |
| Sum of three maintenance cycle durations | 14.159243918 s | 14.024982171 s |

All-arrival latency starts at the original scheduled arrival and ends at full reply completion. The raw audit checks every arrival identity, producer/sequence/index, nested physical batch request and accepted reply/order ID. The raw terminal source timestamp is not separately recorded, so total source drain remains labelled as reported; its ordering is checked against the independently decoded reply and maintenance boundaries. Eventual acceptance does not define sustainable throughput.

## Frozen runtime and fixed configuration

The release manifest SHA is `f56126dab203c80b42f950fa7037fb0b58e52103bf4f6fb86e7f578b0bd4dfa4`. Actual JAR bytes independently reproduce code fingerprint `e6243f4639af1cd35c3bbcb0b7ff0d10938320be8e2f1e0cb236ac9ef667dbb3`; every ZIP entry is inventoried in `collection-r1/independent-native-artifact-verification.json`. Node classpath contains the exact cluster/core/Aeron JARs; the parent additionally names Agrona. Actual `MatchingEngine` comes from core, while `MediaDriver` and `DirectBuffer` both come from `aeron-all`; the fingerprint therefore binds Aeron twice by its two actual type sources. It does not substitute the separately present Agrona JAR for `DirectBuffer`.

Both arms use appointed/observed leader 0, sync level 2, MTU 1248, prepared archive cache, W128/Q64, pending capacity 128 and 256 MiB Java heaps. They reuse ports 35982 sequentially with separate fresh lineages. Exact registered PID/startTicks/argv SHA and classpaths cover six node processes and the parent. There are six actual node stop reports. The normally completed parent has a separate kernel identity observation and successful controller return/reap/final-absence proof; it is not presented as a seventh raw stop report. `parent-launch-handle.json` is a pre-observation receipt whose `observedExecIdentityVerified:false` is followed by the actual independent kernel identity observation.

Each arm contains three complete maintenance cycles and 1,785 logical RPCs: 975 ArchiveChunk, 801 FetchEvents, and three each PrepareArchive, ArchiveCommit and EventAck. The first cycle overlaps release of 3,328 new arrivals, directly demonstrating continued scheduled production during serial maintenance. The independent raw report closes every request/reply wire SHA, kind, correlation and timing. These caller RPC durations include transport, server execution, scheduling and evidence writes; they do not isolate fsync latency.

## Archive closure and protected application state

`collection-r1/full-closed-pilot.tar.gz` preserves the full closed job plus the exact 12 staged source/release files and three execution metadata files. Source is a strict allowlist because the remote preparation directory also contains the job; that source directory was never recursively archived. The outer archive is 32,909,476 bytes, SHA `361b66385795b5c0ba643ed8b7431b50f47c8f28d8c2144cb9ed93e82b8d8b9a`, closing 202 files/31 directories and 2,514,886,271 logical bytes.

Its separately retained nested `pilot-after-clean-stop.tar.gz` is 20,281,994 bytes, SHA `91bfe878d2258b04c2313c62e230767e8c9bc2f99c2ef9d2cbbf91e973c93959`. Full streaming verification closes all 159 files/27 directories, 2,489,518,171 logical bytes, recorded 64,634,880 allocated bytes, and exact outer-row binding. Both verifiers check full file SHA/bytes/mode/uid/gid and directory closure, including empty directories. Sparse native segments were streamed, never fully extracted. Bounded raw files and four actual runtime JARs are retained for inspection. Outer and nested inventories intentionally overlap because the complete closed job includes the nested archive and the original pilot tree.

The controller's read-only checks before and after this pilot report the original stopped application's three native trees unchanged: 57 files, 9 directories and 4,444,992,930 logical bytes. The frozen protected manifest SHA is `6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753`, reconciled file-by-file with the prior R3 protected state. The 989-file PG baseline remains `ec9945c4cff254d3a40425a3923fc5696787441d0d011d3124f716af25ddb186`. This collector reconciles those full wrapper checks locally; it does not claim a second independent live rehash of the protected originals or PG. No original state or PG was launched or mutated by the collector.

## Telemetry scope and retained failed preparations

The complete 1 Hz telemetry has 47 samples (128,804 bytes), below the 512-sample/8 MiB bounds. Every node has 22 available samples and 12 within its coarse UTC arrival exposure. The 80 unavailable observations explicitly mean the registered process had exited: 24 for each cap-1 node, two for each cap-4 node, and two for the parent. They are not replaced by zeros. Per-role CPU, sampled RSS and kernel I/O deltas are independently recomputed in `independent-raw-audit/result.json`.

CPU deltas use Python monotonic timestamps and the same PID/startTicks/argv identity. Java/Python monotonic clock origin alignment was not validated; phase labels use approximate UTC only. Observed process spans include setup/warmup/reference work, load, maintenance and shutdown. RSS is sampled, and kernel I/O counts include logs/archive and other process writes. They do not establish pure load-window CPU, force latency, media saturation or provider durability.

The first local staging attempt failed its guard because `release.template.json` was omitted from its test fixture; exact staged source, archive, receipts and logs are retained in `collection-r1/local-staging/capacity-cloud-pilot-staging-r1`. R2 added that fixture and passed 42 Linux guards and preflight; no failed benchmark attempt was hidden. The first independent native verifier assumed seven raw stop reports, found the actual six node reports plus normally exited parent, and stopped. Its exact source/error and then-current four JAR copies remain in `independent-verification-attempt-r1`; corrected R2 explicitly distinguishes the parent proof. The first raw audit failed locally parsing a nine-digit Java UTC fractional second; its source/error are retained, and the corrected parser uses microsecond truncation only for coarse UTC labels. None of these local preparation/audit corrections reran the benchmark or changed raw inputs.

Detailed independent evidence lives in:

- `collection-r1/collection-receipt.json`, `remote-inventory.stdout.json` and full archives;
- `collection-r1/verify-capacity-cloud-pilot-r1.py` and `independent-native-artifact-verification.json`;
- `collection-r1/verify-lifecycle-closure.py` and `independent-lifecycle-closure-verification.json`;
- `independent-raw-audit/README.md`, `audit.py`, `result.json` and hash-bound `FINAL.json`;
- `PROOF_INVENTORY.json` and `LOCAL_REVIEW.json` for this proof-only local collection.

One sequential cap-1/cap-4 pair is not ABAB, a repeatability estimate, a stable capacity curve or a performance promotion. This one-host UDP pilot does not prove independent-host networking/storage, crash durability, zero latency, 100M orders/s, 100M connections or 100M cumulative orders. Its actionable finding is long serial maintenance with continued arrival queueing; a later controlled experiment must isolate and address that bottleneck.
