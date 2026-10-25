# Review the code without downloading bulk evidence

The repository remains private and retains its original experiment history. A source checkout can omit the large raw archives while keeping the evidence index and every build/test input. Git2.28 or newer is required for the sparse checkout used by CI.

```bash
git clone --filter=blob:none --no-checkout git@github.com:yinli-systems/vectormatch.git
cd vectormatch
git sparse-checkout set --no-cone --stdin <<'PATTERNS'
/*
!/evidence/*
/evidence/index.json
PATTERNS
git checkout main
```

At source `aed9430d133d86bfe9fc6abe47ede623ef3309b2`, the same sparse patterns materialize340 tracked files totalling3,707,864 bytes, including all51 evidence-index records. This size excludes the Git object database and tool/dependency/build output. The recorded pattern verification used a local shared-object clone; it does not measure internet clone time or transfer bytes. The separate GitHub CPU CI uses an actual filtered remote fetch. Missing raw blobs can still be requested on demand through Git.

The code regression suite keeps44 exact historical receipt fixtures (107,508 bytes) under `scripts/tests/fixtures/historical`, with source revision, original paths, SHA-256 and Git blob IDs. The tests check their complete coverage and unchanged bytes. Running code regression tests does not require materializing the multi-GiB experiment tree.

## Correctness execution

The `correctness-existing-cpu` workflow runs a fresh source checkout, pinned JDK/Gradle/Node, a dedicated temporary PostgreSQL18.6 database with fsync enabled, Java checks, three-JVM failover/snapshot/restart, Linux Python regression tests, shell syntax checks, web build and formatting. Test-result counts must include skips. A run that restores test results from Gradle's build cache is distinct from forced execution using `--no-build-cache --rerun-tasks`; both original logs are retained.

The workflow is manually dispatched to a pre-registered one-job, non-root runner on the existing prepaid CPU. It automatically deregisters after its job. Repository source and JUnit/compiler/CI-log archives identify each run's exact revision and hashes. No registration token, job credentials, SSH keys, `.git` authentication state or runner worker diagnostic log is included in those collections. The GitHub-hosted workflow remains subject to the account's billing blocker; a successful self-hosted run does not imply that account issue is fixed.

See [production acceptance](PRODUCTION_ACCEPTANCE.md), [the capacity repeats](CAPACITY_BOUNDARY_REPEATS_V3.md) and [maintenance timing](MAINTENANCE_WRITER_TIMING_V3.md). Software checks, finite benchmarks, sustained operation and real funded trading are separate acceptance gates.
