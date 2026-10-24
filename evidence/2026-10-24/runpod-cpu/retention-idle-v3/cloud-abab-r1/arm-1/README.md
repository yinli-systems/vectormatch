CPU idle experiment: closed arm1 evidence

This is the first configured1ms arm of the fixed1ms/100us/1ms/100us comparison. All four arms use one artifact and window8; this directory contains only the completed first arm. It is a finite6400-arrival pilot on three processes on one CPU host, not three independent machines or a sustained-capacity limit.

The independently reviewed first-arm observations are:

| Observation | Value |
| --- | ---: |
| Scheduled arrivals | 6400 at500/s over12.8s |
| Fresh accepted replies eventually reconciled | 6400 |
| Accepted within the arrival window | 6141 |
| Arrival-window goodput | 479.765625/s |
| All-arrival p99 | 899.508607ms |
| Three maintenance cycles, summed wall duration | 1.988772353s |
| Actual offered read high-water | 8 |
| Retained node warning pairs | 0 |

The all-arrival latency starts at each planned arrival and ends at its accepted reply; it includes queueing and maintenance pauses. It is not a network-only RPC measurement. Root independently recalculated the6400-row nearest-rank p99 and window count, and the recorded scheduler timing gate passed. This archive makes no speedup, maximum throughput, sustained-capacity or hard real-time claim. The other arms require separate closed evidence.

Source commit is `7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23`; actual code fingerprint is `f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f`. Fixed factors remain chunk6144, batch cap4, fetch16, window8, W128/Q64, leader0, ports42000, sync2 and MTU1248. Only configured maximum park is the comparison factor; no OS sleep duration or live-agent-thread count is inferred from factory records.

`collection-run/collection/full-closed-round.tar.gz` and `pilot-after-clean-stop.tar.gz` are unchanged complete compressed originals. The outer archive SHA is `695c15dfbae50e22fb320b3473474eb5dfb2049197cfdb1baca903a9023cb67e`; the inner archive SHA is `3485a1bc42a1c96582bfeb41e2aec7a7a3bae7d56465128a00803db3f264a059`. The full outer stream was independently verified here:162 regular files,23 directories and1,259,885,433 logical bytes, including full SHA, size, remote mode/UID/GID and exact directory/empty-directory inventory. No sparse native payload was extracted. The38 audited raw inputs were also rehashed from their retained small files.

The archive copies194 source files from explicitly registered closed scopes, preserving source-before/source-after/copy SHA, byte count, local mode/owner and mtime. All raw tapes, arrivals, timing CSV, writer payloads, logs, actual idle evidence, audit code/results, source/release configurations, errors and completion records remain. The four duplicate JAR bodies under the native auditor's extracted-artifact directory are the only omitted source bodies; each is bound by SHA/size to its retained `source/release/lib` member in the full outer archive. Remote metadata is authoritative in the original TAR inventories; local copied-file ownership is recorded separately and is not presented as remote ownership.

`root-review-source.py` is the exact executed independent review source with SHA `069ba00caf54ccbd2c599bc46d267dca1e66a8179a4c575a8ad8d68b59d87c39`. Root review/registration, full collection execution logs, and exclusive gate-upload source/registration/stdout/stderr are retained. The original `ROOT_GATE_CANDIDATE_NOT_APPROVED.json` remains false. Root's later independently verified collection gate is retained separately with SHA `f60593c37f3ae23e1368ba8b7d04882738979c654c6d965465f6bcd471019181`; gate upload does not start another arm.

Original absolute runtime paths are unchanged. `ARCHIVED_REFERENCES.json` maps root review and gate references to retained relative files, including the archived sibling staging receipt. `SOURCE_COPY_BINDINGS.json` and `verify.stdout.json` provide the independent copy and stream-closure observations. The new verifier performs read-only local checks and was not used to launch, collect remotely, replay business or signal a process.

No second arm, active directory, SSH key, API credential, remote helper body or unrelated workload is included. Earlier local-native startup/warning failures and source proof remain in the separate local validation evidence; this successful CPU arm does not rewrite that history.
