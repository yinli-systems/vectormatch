# Strict long-cut closed collection preparation

Status: local source preparation only. No SSH, Java, cloud collection, deployment, SQL, signals, pruning or benchmark was performed for this preparation. Actual release/stage/config and closed-controller proof remain separate root-controlled inputs. `releaseReady` remains false here.

This is one explicitly selected arm: `cpu-long-cuts-cloud-r1/arm-1/idle-arm`, long-cuts-33792-v1, 33,792 arrivals at 500/s (67.584 seconds), window8/chunk6144/fetch16/business batch4, 12 cycles and exactly24 read phases, 100us configured park. Original 6400 and previous <=8-phase collectors remain unchanged. The prospective cloud observation must pass scheduler timing; the earlier local 26-late functional-only proof cannot authorize a cloud performance observation.

The new raw adapter imports seven parser modules byte-exact from qualified freeze `1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3`. It calls `audit_arm(...,workload=LONG)` without the local timing diagnostic opt-in, asserts its False default and requires strict raw scheduler admission. Full original correlations, positive physical offers, replies,24-phase fences,12 cycles, setup, canonical references, actual Image/Header lifecycle, exact idle22 creation evidence, qualified shutdown-warning policy, and original57/PG989 reconciliation remain required.

Remote archive ownership and local materialization ownership are separate records. Full outer and nested TAR payloads are streamed and checked against original size/SHA/mode/UID/GID and empty directories; the strict parser receives a projection only for current exclusively owned regular local files whose bytes/SHA match those originals. No original owner metadata is rewritten or asserted equal to local ownership. `ORIGINAL_TO_MATERIALIZED_BINDINGS.json` records both for every consumed parser input. A missing, changed, linked or unbound input fails.

Long physical-replies.bin exceeds the legacy generic32MiB materialization cutoff. Only four exact paths (physical request/reply and logical maintenance request/reply tapes) may exceed32MiB, within the actual-JAR long trace cap185,514,924B in aggregate. Unrelated large files and all sparse native state remain only in complete compressed TARs. Exceeding this cap does not truncate or skip full archival transfer: it marks tape-materialization admission false, leaves full outer/nested payloads intact, and prevents strict raw/final admission. No bound on a production result is inferred from a cutoff.

`build_config.py` binds exact actual root stage receipt rows (currently expected39) plus three explicit opaque arm execution metadata files. It never traverses PREP recursively. The builder's guard fixture mocks release validation only to isolate schema checks; it is not a real release/plan/CPU observation. Actual builder invocation must use the real release validator and real SHA-bound stage/protected inputs.

Default `collect_and_audit.py` operation is a local config dry-run. Explicit `--collect-readonly` additionally requires a fresh output, preparationSHA, exact reviewed remote-helperSHA and root closure receipt (schema2, scope ROOT_VERIFIED_CLOSED_CPU_LONG_CUTS_CONTROLLER, exact arm1/release/controller/job/maxPark, controllerIdentityGone/allOwnedStopped, inspection source/resultSHA). One manual call; no retries or following arm. Independent root review remains required after local collection completion. Runtime/PythonUTC telemetry is coarse and non-atomic; no SLA or sustained capacity conclusion is emitted.

Validation: guards-r1 retained two positive-fixture failures caused by macOS temporary `/var` symlink. Only fixture canonical paths changed. guards-r2 ran13 meaningful pure tests, PASS; exact source ZIP, command/interpreter/stdout/stderr and receipts retained. Tests cover strict timing default, frozen module change, alias restoration, over32MiB named tapes, overbudget preservation policy, archive/local ownership separation, payload/symlink/closure corruption, source/fingerprint/timing finalization and wrong config/closed-proof inputs. No raw workload or network was scanned by these tests.

Reproducible local guards:

```sh
cd '/Users/kevin/Documents/ChatGPT/App 2/runtime/cloud/cpu-20261024/cpu-long-cuts-collection-preparation-r1'
python3 -B -m unittest -v test_long_collection.py
```

Actual future config interface (root supplies real paths and64-hex SHAs):

```text
python3 -B build_config.py --arm 1 --release FILE --release-sha256 SHA --stage FILE --stage-sha256 SHA --protected FILE --protected-sha256 SHA --execution-metadata arm-1-execution-register.json --execution-metadata arm-1-execution.stdout --execution-metadata arm-1-execution.stderr --output NEW_DIR
```

Root owns actual config binding, closure inspection and execution. No future config or success receipt is fabricated in this preparation.
