CPU idle experiment: closed final arm4 evidence

This is the configured100us final arm of the fixed1ms/100us/1ms/100us comparison, using the same artifact, window8, chunk6144, batch cap4, fetch16, W128/Q64, leader0, ports42000, sync2 and MTU1248. Three nodes run as processes on one CPU host. The separate four-arm comparison is the appropriate place to assess repeatability; this finite pilot alone does not establish maximum throughput, sustained capacity or hard real-time behavior.

Root independently checked all6400 fresh accepted replies, scheduler timing and nearest-rank arrival latency:

| Observation | Value |
| --- | ---: |
| Scheduled arrivals | 6400 at500/s over12.8s |
| Accepted within the arrival window | 6141 |
| Arrival-window goodput | 479.765625/s |
| All-arrival p99 | 558.369463ms |
| Three maintenance cycles, summed wall duration | 1.286542112s |
| Actual offered read high-water | 8 |
| Retained node warning pairs | 0 |

All-arrival latency runs from the planned arrival through its accepted reply and includes queueing and maintenance pauses. It is not network-only RPC latency. Configured maximum park is not a measured or guaranteed OS sleep duration. Source remains `7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23`, code fingerprint `f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f`.

Both complete compressed originals are unchanged. The archive verifier streamed165 outer regular files,23 directories and1,259,969,876 logical bytes, checking every SHA/size/remote mode/UID/GID and exact directory inventory, and rehashed38 raw inputs. No sparse native payload was extracted. Four duplicate extracted auditor JAR bodies are omitted only because each is fully bound to its complete `source/release/lib` member in the retained outer archive. Remote TAR metadata is distinct from local copied-file ownership.

The explicit source inventory copies217 files: full collection/raw/audit results, exact069ba independent root review source and root4 registration/result/local gate, config4 and execution, launch4 and execution, actual close4 source/output/root receipt. All source-before/source-after/copy SHA, bytes, local mode/owner and mtime match. The generic close-r2 preparation and13-guard proof are referenced by exact SHA from arm2; actual close4 source is retained here and matches that freeze. All three preceding gates remain in config and the full outer archive; launch4 binds the immediate arm3 gate.

Final-arm schema is intentionally different: the finalizer emitted only `LOCAL_COLLECTION_COMPLETE.json`, with no next-arm candidate. Root created a local final collection receipt, SHA `c7ef42f8fe685bc2ddbc9da5178ca6669b886e17eac9c58e77bd0bfbd18a71ae`. `NO_GATE_UPLOAD.json` records that no gate was uploaded and no next arm was authorized. Its note preserves the root wrapper's earlier assumption that a final arm would have a next-arm candidate; that attempt failed before any file write and was corrected against the actual finalizer schema. No candidate file or upload log was fabricated for this final arm.

`ARCHIVED_REFERENCES.json` provides relative review/gate/config/close references without rewriting original absolute-path evidence. Earlier local-native startup or warning failures remain historical records, not new warning events in this zero-warning CPU arm.

No active long-run/native audit or unrelated scope was read or copied. No SSH key, API credential, remote helper body or unrelated workload is included. Archive creation and verification used local reads/copies and Python only: no Git, JVM, SSH, business request, process signal or sparse extraction. This archive launches nothing.
