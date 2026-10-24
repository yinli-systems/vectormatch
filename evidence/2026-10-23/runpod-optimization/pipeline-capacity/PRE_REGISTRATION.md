This is preparation for one additional capacity point. It is **not registered and has not submitted SSH, load, deployment or cloud changes**. Existing pipeline controllers and evidence remain unchanged. Local guard tests passed: [23 tests and frozen sources](tool-validation/preparation-validation.json), [test log](tool-validation/preparation-tests.log).

The follow-up compares direct 128 physical sessions with multiplexed 1 physical session, in **A1 / B1 / A2 / B2 order at one fixed selected rate**. Both arms retain 128 logical in-flight producer identities, queue 64 per worker / total FIFO 8192, one shared client driver, node/load NAK delay 1000 ns and retry ratio 100. The complete session/network-owner/dispatch arrangement is the factor; this does not isolate logical in-flight capacity alone.

No node/load source rebuild is allowed. Node and load must both remain revision `e57e341909a49692b9ecbf9693803ed62a240b06`, bundle SHA-256 `f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937`. Fixture/prepared SHA and all other configuration stay pinned: `extended-350k-256` / `capacity-350k-v1`, 350000 arrivals, 2 GiB heaps, appointed leader 0 with term checks per window, sync 2, SHARED node/archive, requested receive buffer 131072 bytes, MTU 1248, max sessions 256, retained orders 360000, outbox 800000, per-producer cache 1024 and the same observer/socket probe. Only rate changes relative to the original 26k experiment; mode is the same registered A/B factor.

The branch is fixed before registration:

| Original 26k evidence | Allowed next point |
| --- | --- |
| All four original attempts are terminal, configuration/leader/raw archive and complete owned-process cleanup verified, and the formal completion timeline exists | **18000/s by default**, four new attempts, 350000 arrivals each, window `19.444444…` seconds |
| The same prerequisites hold, and **both multiplexed B26k attempts** are measurement-valid, canonical-verified and classified `OBSERVED_STABLE_WINDOW` | Root may explicitly choose **35000/s instead**, four new attempts, 350000 arrivals each, window exactly 10 seconds |
| Any original formal attempt or required proof is missing/in-progress, changed, unarchived or not fully cleaned up | Registration refused |

The 35k branch requires the original B repetitions to pass individually. A conditional p99, a single stable repetition, an invalid confirmation count or an average cannot satisfy the condition. A-arm outcomes are recorded and remain visible. The 18k choice remains permitted even when 35k is eligible. One plan fixes one rate; it cannot later switch branches, add unregistered points, or alter stable-window thresholds. At 35k the existing minimum 10-second criterion is retained, without rounding or relaxing it. Either branch remains a finite client-plus-cluster observation, not sustained production capacity or a matching-engine ceiling.

Controller preparation is under `runtime/cloud/optimization-20261024/pipeline-capacity/`. Importing or default registration only prints a draft. After root review and complete original formal evidence:

```sh
# Draft only; no prerequisite inspection, registration or network access:
python3 -B runtime/cloud/optimization-20261024/pipeline-capacity/register.py

# Root-only explicit later registration; choose ONE rate, default 18000:
python3 -B runtime/cloud/optimization-20261024/pipeline-capacity/register.py --rate 18000 --write
# Alternative, only if both original B26k observations meet the rule above:
# python3 -B runtime/cloud/optimization-20261024/pipeline-capacity/register.py --rate 35000 --write

# Separate explicit execution of that immutable plan:
python3 -B runtime/cloud/optimization-20261024/pipeline-capacity/matrix.py --execute
```

These are future operator steps, not actions performed during preparation. New IDs are `pc-direct-RATE-w128-r1`, `pc-multiplexed-RATE-w128-r1`, then their `r2` counterparts; each has a fresh state directory. Existing plans, partial registrations, timelines and IDs refuse overwrite/reissue. A partially executed controller is inspected under the exact existing IDs rather than blindly rerun.

The wrapper verifies the original frozen campaign source SHA and reuses its audited `run_task`, immutable configuration verifier/leader checker and lossless archive tool. A separately identified local streaming postprocessor replaces only the analysis dispatch in the new wrapper process. It does not edit the original source or the old four-round evidence. Registration pins the complete original matrix's input/archive/summary/cleanup/timeline hashes and the new controller sources. Execution first revalidates those hashes, then performs fresh read-only checks of explicitly recorded old owned PID/startTicks/cmdSHA identities. Before each next attempt it also confirms the preceding new state is stopped; missing/reused/running identities fail closed. There is no namespace scan, packet capture or unrelated process signal.

The project cap stays USD 20 **including a USD 2 recovery reserve**, with no new resources. Registration and matrix start reserve 3000 seconds; each next attempt rechecks the remaining conservative time reserve and at least 1 GiB local free space. The whole load-process and canonical-validation limits remain 600 seconds for both arms. A slow/failed arm receives no deadline extension. Full CSVs, including invalid and failed attempts, retain their columns and every arrival; deterministic gzip plus input SHA proofs are archived before any next-round gate, while plaintext remains local.

Unexpected business mismatch, configuration/leader/source discrepancy, export/archive failure or incomplete identity-bound cleanup halts the matrix after available evidence is preserved. Only the frozen controller's exact typed canonical-incomplete `UNKNOWN_UNRESOLVED` guard may continue after full archival and cleanup; unresolved failures remain invalid and never become capacity or validated business success. New unknown identities are not automatically replayed as business work by this follow-up controller.

Report every trial separately: window goodput, scheduled-to-confirmed conditional p99, all-offered p99 eligibility/null, queue/drain, not-sent/reject/error, initial and final unknown, canonical/leader/configuration checks and source/fingerprint. Do not average percentiles or silently discard failed repetitions. No improvement, boundary or result is asserted by this preparation document.


The independent streaming postprocessor is a **separate analysis artifact**, never an e57 node/load build tool. Before root registers this follow-up, generator must finish its exact semantic-parity and complete350k RSS validation, and root must review/commit the source. Only then may root explicitly create the local commit-named release:

```sh
# Future root-only local build, not performed during preparation:
python3 -B runtime/cloud/optimization-20261024/pipeline-capacity/build-postprocessor.py \
  --revision FULL_NEW_POSTPROCESSOR_COMMIT \
  --validation-receipt evidence/2026-10-23/runpod-optimization/tool-validation/streaming-analyzer-validation.json \
  --python /ABSOLUTE/PATH/TO/THE/VALIDATED/PYTHON --execute
```

The helper runs `git archive` for exactly `scripts/analyze-capacity-streaming.py` and its adjacent legacy dependency `scripts/analyze-capacity.py`. The latter must remain byte-identical to e57's analyzer, SHA-256 `5fba16bbdbb5e90318c65f945991f2eb4ddb256fb36f93e28e26133b9e65c80b`. It checks the full source commit, archive commit metadata and SHA, both dependency SHAs, actual Python executable/resolved binary hash/version, and the complete copied parity/RSS receipt SHA. The receipt must identify the same source bytes and Python runtime, at least two successful raw/summary-hashed parity cases, a complete350k successful memory measurement with positive peak RSS, and only `generatedAt` excluded from semantic equality. There is no approximate percentile, altered stability threshold or rewritten historical result.

`postprocessor-identity.json` and `analysisIdentitySha256` are explicit separate fields in the new plan/campaign and per-trial sidecar. Node, load, `build`, `buildTools` and the core comparison fingerprint keep their actual e57 origin. The original26k branch decision still uses its frozen original summaries; the new analyzer never overwrites or reclassifies them. Registration cannot proceed until a validated independent analysis release exists, and both new arms must attest that exact identity.

Each analysis command uses the pinned interpreter with `-I -B`, the immutable entry point and unchanged legacy CLI criteria. Every local dependency/runtime/validation receipt is rechecked before dispatch. Configuration/leader/archive tools continue to use e57's recorded paths and SHAs. The new wrapper records exact argv, identity, raw input SHAs, and immutable per-trial `analysis-summary.json` / `analysis-capacity.csv` output snapshots, so a later cohort summary update does not erase the earlier invocation's bytes. A failed analyzer still triggers lossless archival of every available raw arrival before the matrix halts. No analyzer source commit, local artifact build, capacity registration, SSH or new load has been performed by this preparation.
