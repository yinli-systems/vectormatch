# Fully initialized recording segments: sync2 ABAB rejected

Fully writing and synchronizing fresh 128 MiB recording segments before traffic **did not pass either paired optimization gate**. Keep the option disabled. No 30-minute candidate test was started because stable benefit was the preregistered prerequisite.

| Original arm | New segment initialization | Accepted / planned | Full p99 ms | Full p99.9 ms | Critical force p99 ms | Absolute latency gate |
|---|---|---:|---:|---:|---:|---|
| A1 | OFF | 6,000 / 6,000 | 20.218 | 46.345 | 9.387 | pass |
| B1 | ON | 6,000 / 6,000 | 65.768 | 107.057 | 35.515 | fail |
| A2 | OFF | 6,000 / 6,000 | 30.962 | 73.324 | 15.545 | fail |
| B2 | ON | 6,000 / 6,000 | 35.122 | 58.008 | 18.123 | fail |

Each comparison arm lasts 60 seconds at **100 planned arrivals/s**. Both functional arms also accept all 20 originals. All **24,040** requests are accepted, with no unknown, rejected or unsent originals. Original canonical states agree, source timing and fixed-leader gates pass, and every request joins to exact stages and native force diagnostics with zero overflow/read errors.

Paired B/A p99 ratios are **3.253 and 1.134**; p99.9 ratios are **2.310 and 0.791**. Both fail the registered rule (p99 ≤0.90, p99.9 ≤1.00, plus candidate absolute gates). Controls also vary, so this establishes rejection in these original windows, not universal causation or a claim that preinitialization slows every deployment.

## What was held fixed

Same prepaid CPU host and boot, artifact, leader 0, CPU sets, G1, 1–2 GiB heap, four active processors, 1 ms parks, shared media drivers, MTU 1248, original overlay storage and archive/catalog/consensus **sync2**. All arms enable the same stage and force-wait diagnostics; stage capacity is 2,097,152 per thread. The sole A/B launch difference is the initialization flag. Both sides wait 30 seconds after node readiness and perform the same pre-source recording capture. This cohort must not be causally compared with earlier campaigns that used a smaller trace capacity or different initialization/settling policy.

B uses atomic `CREATE_NEW`, writes the entire segment with zeros, calls `FileChannel.force(true)`, and verifies a full readback hash before Aeron writes records. It refuses existing files, including zero-filled historical segments; it never overwrites or retries them. Actual B recordings are fully allocated on the original device. The existing recording forces and confirmation rules are unchanged.

Each B cluster initializes **384 MiB** across three replicas. The measured-arm startup costs are **196.6–235.6 ms per node**; the functional B range is 231.3–239.9 ms. These costs are outside the arrival window and explicitly retained in startup receipts. No segment rollover or recovery-path performance is established.

## What the failed intervention narrows

The [preceding observer campaign](FORCE_WAIT_RESULTS.md) already found off-CPU force tails and sampled filesystem waits. Those remain after full initialization: for the slowest 1% of requests, associated force off-CPU lower bounds are **99.641% / 99.593%** in B1/B2. **99.360% / 99.366% of valid samples** observe D state; these are sample proportions, not duration attribution. XFS log synchronization, page/writeback waits and block flushes remain visible.

For B1, archive-delivery/poll waiting accounts for **53.328%** of slow-tail latency; **99.898% of that waiting overlaps an earlier force on the same recording**. A slow synchronous recorder holds up later records as well as its own request. This temporal overlap cannot identify exact packet-arrival or wakeup/runqueue delay.

The evidence rejects the narrower hypothesis that moving initial extent allocation/conversion out of the window is sufficient here. It does not isolate the physical disk, device queue, shared-host writers or kernel wakeup costs. In upstream [Linux 6.8 XFS fsync](https://github.com/torvalds/linux/blob/v6.8/fs/xfs/xfs_file.c), fsync can wait for file data, logged metadata and device flush even when space is already allocated. That code explains why startup initialization need not remove the observed blocking; it is not a measurement of this host's individual storage layers.

Exact scheduler and storage nanoseconds remain unavailable because the container has no enabled schedstats/delay accounting or usable perf/tracefs access. No global kernel settings, mount options, new resources or durability levels were changed. Shared-host synchronous durability, not a CPU-heavy force body, remains the measured bottleneck boundary. No claim of an optimized p99, sustained capacity, separate physical replicas or production readiness follows.

## Evidence and verification

- [Preregistered protocol](RECORDING_INITIALIZATION_PROTOCOL.md), frozen before the originals.
- [Verified summary and selection](../evidence/2026-10-27/recording-initialization-r1/SUMMARY.json), including every original gate and actual launch configuration.
- [Closure proof](../evidence/2026-10-27/recording-initialization-r1/POST_CAMPAIGN.json): all 24 owned test JVMs exited; no Java workload remains; existing CPU retained.
- Six raw private release assets retain all CSV, native samples, JFR, GC, launch identities, binaries and final states. Every compressed asset and original member was downloaded and verified before duplicate retirement.
- The B-arm force-attribution CSVs are independently recomputed locally from downloaded raw inputs, byte-identical to the archived CSVs.
- Three targeted initialization tests pass: full-byte/readback correctness, preservation of existing nonzero and zero files, and path/symlink/length guards. The preceding force-observer candidate separately passed 529 cluster tests.
- Candidate source `8d373f9cc68be38b49e7eb30958cb42e95204024`; shadow JAR `e027055627385d975636cb843700633fbdba907a4050f8957ec41e71f7e9c41b`; private runtime asset `681739266`. Exact file hashes are in preparation manifests.

```sh
python3 scripts/summarize-recording-initialization.py evidence/2026-10-27/recording-initialization-r1 --output /tmp/initialization-summary.json
python3 scripts/fetch-replicated-evidence.py evidence/2026-10-27/recording-initialization-r1/initialization-b1 /tmp/initialization-b1 --include-force
python3 scripts/replay-force-wait.py /tmp/initialization-b1 evidence/2026-10-27/recording-initialization-r1/initialization-b1 --output /tmp/initialization-b1-replay.json
```

Further application-side experiments should target bounded recording/force pipelining and its durable-position watermark, with explicit failure, close and rollover correctness tests before performance ABAB. Simply moving force to another thread is insufficient: a record must never be acknowledged before its covering `force(true)` completes. That pipeline is not implemented or validated by this experiment.
