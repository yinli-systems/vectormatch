# Fresh recording initialization: preregistered sync2 ABAB

The [closed force-wait campaign](FORCE_WAIT_RESULTS.md) observes mostly off-CPU force tails and D-state waits in XFS log synchronization, writeback and block flush. Exact scheduler/storage durations remain unavailable. Test one narrower hypothesis: writing all bytes of a fresh recording segment and forcing its content and metadata **before accepting traffic** reduces later extent-allocation/conversion work and improves tail latency. Existing `fallocate` reservation failed and is disabled.

## Change and limits

Both sides run the same pinned Aeron overlay and application artifact. Only `vectormatch.stage.initializeRecording` differs. B creates new segments using `CREATE_NEW`, writes exactly the bounded length with zero bytes and calls `FileChannel.force(true)`. A retains upstream sparse segment creation. B refuses any existing segment, including an all-zero historical file, and all symlink/unowned targets. It leaves a partial newly created file on failure and aborts that original experiment; it never retries or deletes it in place. This is an opt-in diagnostic for fresh synthetic states, not a recovery-path or production-default change.

All original RecordingWriter forces, recorded positions, quorum and client acknowledgments remain unchanged. Archive, catalog and consensus stay at sync2. No tmpfs archive, durability reduction, host-wide tuning, new resource or new filesystem. Startup cost is explicitly retained, and any later rollover cost belongs in measured latency. A successful finite experiment cannot establish rollover or crash-recovery performance.

## Frozen conditions and arms

Same prepaid CPU host/boot; fixed leader 0; fixed disjoint CPU sets; G1; 1–2 GiB heap; four active processors per JVM; shared drivers; 1 ms parks; MTU 1248; original overlay filesystem; same synthetic MATCHING workload. Stage tracing **and force-wait diagnostics are ON in every arm**. Set stage capacity to 2,097,152 per thread in **all** arms, sufficient for a conditional 30-minute run; native capacities remain 250,000 forces and 2,000,000 samples per recording thread. The previous observer campaign used 1,048,576, so do not make cross-campaign causal comparisons.

First functional A/B, 2 seconds each at 10/s. Then A1/B1/A2/B2, **60 seconds each at 100/s**, preserving every original outcome. After all replicas report ready, both sides wait **30 seconds**, verify recording initialization/allocation evidence, then launch the source. Record the segment logical size, allocated bytes, whole-file hash, startup receipts and creation timing before source startup. Require B files to be fully allocated, and their initialization receipts to verify a full all-zero readback immediately after the startup force, before Aeron writes any records. At the later pre-source capture the files already contain cluster-control records, so they need not remain all-zero. Startup requires up to 384 MiB of zero writes for three 128 MiB segments; report actual measurements. Capture A identically, including the same pre-source whole-file reads and settling policy.

Freeze source/artifact hashes, exact launch matrix and controller before starting. Require the four measured states and both functional states to be pairwise identical within their workload sizes. Require every request outcome, source timing, fixed leader, complete exact stage/native joins, zero recorder drops and read errors, all runtime/archive hashes and owned-PID closure.

## Selection before looking at outcomes

Both paired B/A full-latency p99 ratios must be ≤0.90 and both p99.9 ratios ≤1.00. Both B arms must additionally pass p99 ≤25 ms, p99.9 ≤100 ms, every minute p99 ≤25 ms and the existing source/completion/correctness gates. All A arms must pass the source/completion/correctness gates; their latency limits may fail because that is the defect being addressed. Preserve those failures explicitly. Do not average contradictory pairs into a win.

Only if all these conditions hold, run B for **30 minutes at 100/s, 180,000 original requests**, with exactly the same launch configuration, instrumentation capacities and 30-second settling policy. Audit all original outcomes and per-minute latencies; any gate failure prevents promotion. Otherwise record rejection and do not start the long candidate run. The 100/s experiment establishes a durability-tail result only, not high-rate capacity, independent physical nodes or production readiness.
