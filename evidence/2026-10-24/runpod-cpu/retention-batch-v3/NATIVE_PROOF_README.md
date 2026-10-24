# Local V3 batch proof collection

Frozen candidate: `973ff8f9bc4d9266c52d21866480dd45b31c39f9`. Seven distinct native trees are preserved: three agent batch smokes, two agent single-command V3 reference smokes, and two explicitly rerun root smokes. Every attempt reports success and all owned JVMs stopped.

The first root full-project `check` succeeded with 205 discovered tests, 194 passing and 11 PostgreSQL fixture skips. Its `core:test` and `cluster:test` tasks were `UP-TO-DATE`; those XML files refer to existing final agent attempts. It did not create additional smoke runs. Root then explicitly used `--rerun-tasks` for core and cluster: all 175 tests passed with no skips, and both new native trees are preserved here.

**Count correction:** the frozen agent validation manifest says 17 new batch tests. Actual final XML has eight wire tests, seven adapter tests and one three-JVM test: **16 new tests**. The original manifest is retained byte for byte; no raw log or XML was rewritten.

The initial failed attempt stopped during `compileTestJava` because the test used the wrong `AccountView` API. No test or smoke ran in that failed attempt. The preserved failure JSON contains the actual diagnostic copied from the tool output; full initial stdout/stderr was not redirected and is not claimed to be available. All captured subsequent build logs, intermediate/final XML, pre-final and final JARs, and source provenance are retained under `agent-build-validation/`.

The collector independently hashes every native source file, streams the entire tar member content to verify SHA-256, and checks exact file closure, file and directory modes, empty directories, archive size and archive SHA. No full native archive is extracted. Each attempt’s 110 observed artifact inventory entries are matched to the corresponding preserved runtime JARs; the inventory includes repeated dependency observations and is not claimed to contain 110 unique artifacts. Original sparse trees and archives remain in place.

| Native proof | Source provenance | Files | Logical bytes | Gzip bytes |
|---|---|---:|---:|---:|
| `attempt-0d145290-1ef3-49c1-96ea-8bfa725b5b2c` | Agent, pre-final | 62 | 2,029,141,013 | 8,901,669 |
| `attempt-3a800ed2-a189-4a76-84ed-ee4b18d8426c` | Agent, pre-final | 62 | 2,029,141,013 | 8,901,790 |
| `attempt-a6320fa0-39d2-40f5-b61a-ca47ed1ba4c3` | Agent, final | 62 | 2,029,141,013 | 8,901,806 |
| `agent-reference-suite-r1` | Agent, pre-final | 59 | 2,029,150,914 | 8,903,415 |
| `agent-reference-final` | Agent, final | 59 | 2,029,150,920 | 8,903,258 |
| `root-rerun-batch` | Root explicit rerun | 62 | 2,029,141,013 | 8,901,299 |
| `root-rerun-reference` | Root explicit rerun | 59 | 2,029,150,920 | 8,903,296 |

Across seven trees: 425 files, 14,204,016,806 logical bytes, 62,316,533 bytes in seven proof archives. Logical byte totals include large sparse Aeron segments and do not measure accepted orders, durable external storage or traffic volume.

Batch smokes each demonstrate six first accepted orders in a separate small synthetic lineage; single-command reference smokes each demonstrate four. They use three JVMs on one machine, loopback UDP and explicit sync level 2. They are functional restart, replay and canonical-state checks, not capacity or end-to-end latency benchmarks. A discarded reply is an application-level test seam, not actual network loss. The matching reference uses a separate instance of the same engine implementation.

W128 global retry-retention credit, persistent client restart recovery, independent-host durability, cloud batch throughput, capacity curves, long-run retention and all three 100M targets remain unproved. No source/default deployment, SSH operation, process control or deletion is performed by this collector.

Machine-readable closure and digests: `collector/summary.json`, the seven `native-proofs/*/manifest.json` files and per-attempt `artifact-binding.json`.
