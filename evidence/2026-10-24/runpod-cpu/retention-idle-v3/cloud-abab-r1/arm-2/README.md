CPU idle experiment: closed arm2 evidence

This directory contains the completed configured100us second arm of the fixed1ms/100us/1ms/100us comparison. It contains no third-arm or other active state. The finite6400-arrival pilot runs three node processes on one CPU host; it does not establish a sustained-capacity limit or performance across independent machines.

Root independently reviewed all6400 fresh accepted replies and observed:

| Observation | Value |
| --- | ---: |
| Scheduled arrivals | 6400 at500/s over12.8s |
| Accepted within the arrival window | 6141 |
| Arrival-window goodput | 479.765625/s |
| All-arrival p99 | 562.917877ms |
| Three maintenance cycles, summed wall duration | 1.292279377s |
| Actual offered read high-water | 8 |
| Retained node warning pairs | 0 |

All-arrival latency begins at each planned arrival and ends at its accepted reply, including queueing and maintenance pauses. Root separately recomputed nearest-rank p99 and the window count, and the scheduler timing gate passed. These observations are one finite arm; the complete comparison and longer stable-load validation remain separate. No speedup, maximum-throughput, sustained-capacity or hard real-time claim is made here.

Source commit remains `7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23`, actual code fingerprint `f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f`. Fixed factors remain chunk6144, batch cap4, fetch16, window8, W128/Q64, leader0, ports42000, sync2 and MTU1248. The experiment changes configured maximum park, not a guaranteed OS sleep duration.

Both unchanged complete compressed originals are retained. Outer SHA: `d5820cbaa4782287c53950e951e4abca95b349a5aa26f9f5ed9329daebbe5bce`; inner SHA: `c74f0b236c087cf4d53d91c925e559dc7f9435de2a4ebe00a98621a92df06fa3`. This archive's read-only verifier streamed all163 outer files,23 directories and1,259,958,295 logical bytes, checking complete SHA, size, remote mode/UID/GID and exact directory inventory, and rehashed all38 audited raw inputs. No sparse native payload was extracted.

The explicit source inventory copies226 files from closed scopes: complete collection outputs, raw tapes/writer payloads/auditors/configuration, independent root review and its exact069ba source, collection execution, config2 and its execution, actual launch2 and its execution, actual close2 inspection, and the frozen generic close-r2 preparation with its13 pure-guard logs/source/preregistration/ZIP. `SOURCE_COPY_BINDINGS.json` verifies all source-before/source-after/copy bytes, SHA, local mode/owner and mtime. Four duplicate extracted auditor JAR bodies are the only omitted source bodies; each is bound to a complete retained `source/release/lib` member of the outer archive. Original remote ownership is preserved in TAR metadata and is not confused with local copied-file ownership.

The generic close-r2 source and frozen13-guard inputs are bound to the actual close inspection source and output. Config/launch/outer archive all retain the exact preceding arm1 gate SHA `f60593c37f3ae23e1368ba8b7d04882738979c654c6d965465f6bcd471019181`. Original finalizer candidate `ROOT_GATE_CANDIDATE_NOT_APPROVED.json` remains false. Root's subsequent independently verified arm2 collection gate is separate, SHA `353b5d0cee3754db758f3902beda163cbff434d4c58ae0bb4999fa1da90ddeaf`; its exclusive upload source, registration and stdout/stderr are preserved. No next-arm launch is performed by the archive or verifier.

Original absolute paths and original evidence are unchanged. `ARCHIVED_REFERENCES.json` provides relative gate/review/close/config references, including the archived prior-arm gate and sibling staging receipt. Earlier local-native startup or warning failures remain historical evidence in their own archive; they are not relabeled as warnings in this zero-warning CPU arm.

No arm3 or active directory was read or copied for this archive. No SSH key, API credential, remote helper body or unrelated workload is included. Creation and verification used only local file reads/copies and Python: no Git operation, JVM, SSH, business request, process signal, or sparse native extraction.
