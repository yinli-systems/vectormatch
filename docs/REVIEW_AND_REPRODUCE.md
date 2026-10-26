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

## Keep new evidence publications small

Before pushing a publication commit, inspect its added and changed Git blobs:

```bash
python3 scripts/check-new-git-blobs.py --base HEAD^ --head HEAD
```

The guard refuses changed blob paths over10MiB and fails closed if the revisions or object sizes cannot be read. Larger raw archives belong in immutable attachments to this same private repository,with committed SHA-256 and complete member inventories plus authenticated download verification. It leaves existing history unchanged;it does not claim that a large historical repository has become small.

Actual read-only repository checks reproduce the accidental97885962-byte admission duplicate,accept the subsequent native manifests and small report,and refuse a missing base. The exact original admission archive is now a fully verified private attachment;its original Git commit and all frozen benchmark inputs remain available. See [the guard records](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/git-publication-size-guard-r1/README.md).


## Download the verified source-only bundle

The private source bundle at publication9b8ea0be is1,285,135 bytes and contains391 tracked build/source/test/doc/index files (4,193,667 original bytes). Its isolated forced compilation executes ten main/test tasks;all265 core/cluster class bodies match actual Linux CI19. Dependency and tool caches are shared;the separate Linux run supplies functional-test evidence.

```bash
gh api repos/yinli-systems/vectormatch/releases/assets/676403866 -H "Accept: application/octet-stream" > vectormatch-source-review-9b8ea0be.zip
shasum -a256 vectormatch-source-review-9b8ea0be.zip
```

Expected SHA-256:`8a3fffdfcddb5550f7eb82eec7b40ba46832631196d0d1987c34f108c1d6d9ac`. The[complete validation and member manifest](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/source-review-bundle-r1/README.md)bind the original Git blobs. This is a private draft attachment;repository visibility and history are unchanged. Raw experiments remain separately available through their authenticated attachment manifests.


## Current overload-candidate source bundle

The frozen `96105d8f443af5a25e2331af4c060fad17717b95` source is also available as a **1,787,457-byte** private bundle: 510 tracked source/build/test/doc/index files, 5,319,649 original bytes. It excludes bulk evidence and Git history. Independent-directory forced compilation succeeds; all 364 application class bodies and all included dependency class bodies exactly match the overload candidate. Tool/dependency caches were shared. No functional tests or performance measurements were executed by this source-export check; the candidate's Linux qualification is a separate gate.

```sh
gh api repos/yinli-systems/vectormatch/releases/assets/679804671 \
  -H 'Accept: application/octet-stream' > vectormatch-source-96105d8f.zip
shasum -a256 vectormatch-source-96105d8f.zip
```

Expected SHA-256: `39999d94e0c7830e0a5e1c3ca2a18b70953c81c5a44e83218a65c8935775cbe0`. [Member-by-member Git object bindings, isolated compile log, class equivalence and authenticated full-download receipt](../evidence/2026-10-27/source-review-r1/) are retained. The archive includes `SOURCE_MANIFEST.json`; original modes, sizes and SHA-256 values can be checked without the repository history.

`python3 scripts/create-review-bundle.py REVISION NEW_OUTPUT` exports a pinned revision. It reads immutable Git objects, preserves executable modes, ignores dirty/untracked working files, omits bulk evidence/runtime files, rejects symlinks and enforces 10MiB/member and 64MiB total bounds. Existing output is refused. Four regression tests cover these boundaries, missing revisions and reproducible bytes. An export is not evidence that its source passed functional tests.
