# Prospective 7k/8k overload controls

Execution is now complete on the corrected r2 artifact: [all eight results and phase exposure](OVERLOAD_RESULTS_V4.md). All correctness/replay/cold-restore gates pass, all finite capacity gates fail, and the full paired promotion criterion fails. The prospective text and failed preparations below are retained as the original registration history.

This registers two additional **finite overload diagnostics**, not an escalation of the passed-capacity claim. The exact-cut campaign's 6k/s failures remain failures. The anchored in-process endurance runner is a separate path and cannot qualify this replicated experiment.

The input parser now recognises explicit 7,000 and 8,000/s requests so the planner can produce their full bounds. **Both remain refused by the default resource profile.** The window remains 20 seconds. All codec-derived raw/writer/journal/file/RPC bounds, the 2.5GiB allocation ceiling and the 1GiB runtime free floor remain enforced. No refusal can be reclassified as a measured latency result.

The first qualification incorrectly expected the higher points to fit; its two failed tests and source are preserved. Actual 7k planning requires 2,771,546,418 bytes of allocated growth and 3,845,288,242 initial free bytes, exceeding the original growth cap. The 8k point additionally exceeds the 2GiB raw bound. Tests now verify the required refusal and equal bounds for both policies. A separately named storage profile is now qualified for these finite controls; it does not remove the actual free-space admission requirement or establish a performance result.

Prospective order on a quiet, unchanged CPU host is 7k PAUSE A1, CONTINUE B1, PAUSE A2, CONTINUE B2; then the same four arms at 8k. This explicitly tests overload after the previous capacity failure. Freeze one artifact, leader 0, sync 2, three 256MiB JVMs, base port 22000, batch 4, exact cut 1536, read-window 32, page 32, archive chunk 6144, original idle/owner policies and durability fences. No endurance, compilation, audit or unrelated load may overlap measurement. Every arm uses fresh state and a separate evidence directory; the arms are not one continuous lineage.

Preserve every planned arrival, queue/dispatch/pending interval, negative offer, rejection, not-sent and observed/final unknown. Report scheduled-arrival latency and in-window goodput. With any missing planned acceptance, all-arrival accepted p99 is undefined; conditional latency must be labelled. Both A/B pairs must improve without worse goodput or post-offer tails to support a performance claim. A mixed direction or failure is published unchanged.

Before running, qualify both policies on the new artifact and verify the original native/raw audit, replay and three-node cold-restore gates. Retain complete raw evidence privately and verify it before retiring stopped state. If current disk cannot admit a point, record the refusal and free only independently verified, fully archived experiment data. Do not lower the guard.

After finite diagnostics, a 30–60 minute replicated experiment still needs a continuous, replicated maintenance-journal anchor and bounded streaming source/evidence integration. Repeating 20-second fresh states does not satisfy it. This document supplies no measured 7k/8k or sustained result.

## Explicit finite overload storage profile

`-Dvectormatch.v4.capacity.resource.profile=overload-4g-v1` permits only the unsealed 7k/8k controls. The default remains `standard-v1`; unknown values, lower-rate combinations and sealed-read combinations are rejected. This changes the experiment's storage ceiling, not the business/state profile, arrival clock, deadlines, journal bounds or execution policy. It admits a maximum 3GiB raw envelope and 4GiB allocated-growth envelope; the exact calculated limit is still enforced at runtime and the 1GiB free floor is unchanged.

| Planned rate | Exact raw bound | Exact allocated growth | Required initial free bytes |
| --- | ---: | ---: | ---: |
| 7,000/s | 2,078,479,731 | 2,771,546,418 | 3,845,288,242 |
| 8,000/s | 2,368,347,117 | 3,082,525,261 | 4,156,267,085 |

PAUSE and CONTINUE calculate identical bounds. Tests cover default refusal, explicit profile admission, strict configuration selection, the forbidden combinations, initial free-space refusal and runtime enforcement of both exact allocated growth and the free floor. No cloud arm has been run on this new profile yet. A disk shortfall must stop launch; only independently verified stopped experiment artifacts may be retired to make space. The ongoing 100M native lineage must close before any other CPU measurement starts.


## Registered execution on 27 October

The candidate bundle is frozen at source `96105d8f443af5a25e2331af4c060fad17717b95`, SHA-256 `92398ebaad14e40e9b61224c20d0ca9e84f3a3dc3b7d4df34dc6cef02f58aed6`. [Preparation sources and immutable registration](../evidence/2026-10-27/overload-r1/preparation/) record a dependency on successful 100M lineage closure before any new native CPU work. A targeted 25-test standalone Linux run precedes all eight points. Each native run and its independent raw audit must close before compression, private upload or the next point. The parent uses 768MiB heap; replica settings above remain fixed. Per-process CPU/I/O and parent GC logs are collected; this does not claim per-replica GC pause tracing.

The collector computes an exact deterministic compressed size and SHA before admitting the local stream, bounds the stream by that size, verifies every raw member and performs a full authenticated private-asset download. It can retire stopped large duplicate files only after those checks. Native measurements never overlap compression or replay. A local prelaunch parser fixture exposed a Python streaming-tar CSV compatibility error; the failed source is retained and the corrected parser passes both complete-acceptance and missing-arrival fixtures. These are tool fixtures, not measured capacity results.


Before any native overload work, the retention selection was tightened using an actual closed 6k inventory: it left 78.5MB below the previous 1MiB large-file cutoff, including 76.9MB of writer payloads. Eight arms would unnecessarily accumulate those duplicate bytes. Revision 3 additionally retires the exactly manifested, fully archived `native/load/writer/*.bin` payload copies after full private closure, while retaining receipt text, small diagnostics and canonical snapshots. Every selected byte hash is rechecked before unlink. A fixture executes the actual selection expression and verifies protected paths; the previously qualified compressed-size/stream code is unchanged. The measured candidate and disk-admission guards are unchanged.


## Preserved first native refusal and corrected ledger contract

The candidate `96105d8f` passed its 25 targeted Linux tests, but its first 7k PAUSE point refused before scheduled arrivals: `RetentionCapacityLedgerV4` still capped arrival columns at 120,000 while the explicit plan required 140,000. The complete failure is private asset 679836958 and all owned JVMs stopped. No throughput/latency result exists for that attempt. Its Linux qualification is private asset 679835851; passing those tests did not cover the newly discovered plan/ledger mismatch.

The planner now owns the 8,000/s × 20s maximum, and the ledger derives its maximum from it. New tests allocate and release every original row for both 140k/160k plans under both dispatch policies, verify producer sequencing through 160k and refuse 160,001. Default high-rate storage admission remains refused. Nineteen relevant local tests pass. A fresh artifact and fresh experiment root will qualify 27 Linux tests and restart the entire ABAB order; no old arm is carried forward into the new performance comparison.


## Corrected artifact and operational pauses

Source `a9f21f1fc408bd70f09a231c55d33ad3a5093926`, candidate bundle SHA-256 `199941e7fd69fd661017963ffe1987c053c455c3193be162dccc6aaf9e8e9b98`, passed all **27 targeted Linux tests** with zero failure/skip/abort/container failure. The [r2 evidence index](../evidence/2026-10-27/overload-r2/) identifies this fresh comparison. Every measured arm uses this artifact, including both repetitions at both rates.

Its 7k A1 completed native correctness, physical-order replay, all three cold restores and independent raw audit. Local compressed-archive admission then refused insufficient controller disk. Only byte-verified derived materializations of eight older experiments were retired, retaining their complete compressed original archives and all metadata. The same native A1 archive resumed; no business workload was rerun. A subsequent controller-Python parser error concerned Java's nine-digit UTC fraction when slicing CPU telemetry. Original output and failure are retained; the corrected UTC parser is separately qualified for 0/3/6/9 fractional digits. Per-order latency calculations remain integer nanoseconds. The original A1 bytes, identities, state and elapsed measurements are unchanged.

The offline phase analyser checks the original archive SHA, embedded member hashes, trace frame sequence, phase continuity and exact clipping to the 20-second arrival window. Three tests qualify clipping, missing/disordered phases, the unsupported read-yield mode and malformed/truncated frames. It reports coordinator-state exposure, not CPU busy time or a causal attribution of every request's wait.
