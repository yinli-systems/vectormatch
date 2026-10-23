# Explicit NAK-delay control on the 350k/W256 path

**The B pilot completed with valid correctness evidence but did not meet stability criteria. No new stable-capacity improvement is established.** The experiment changes the unicast NAK delay on both the three member MediaDrivers and the load JVM's shared client MediaDriver. The two configurations use the same new committed artifact, 256 synchronous workers and all other fixed settings. The preceding W256 failure motivates testing feedback/retransmission behavior; it does not prove this timer is the unique cause or that increasing it will improve capacity.

The [preceding report](../window350k/README.md) remains frozen: its full 350k W128 pilot passed, its 26k/s W128 control overloaded, and its W256 attempt failed with unresolved outcomes. That old formal matrix stopped after two attempts. Its recorded confirmations, post-load cache observations and two unrun repetitions are not new control results for this experiment.

## Intended factor and fixed workload

| Configuration | Member unicast NAK delay | Shared client-driver unicast NAK delay | Retry-delay ratio |
|---|---:|---:|---:|
| A: explicit default | 1,000 ns | 1,000 ns | 100 |
| B: increased delay | 100,000 ns | 100,000 ns | 100 |

Both groups explicitly set `-Daeron.nak.unicast.delay=<integer>` before the JVM classpath. A is an explicit default on the new artifact, not a replay of the earlier 52fb run. The factor changes node and client timer settings together, so it cannot identify which side contributes an effect. Configured timer values do not themselves measure actual packet-feedback intervals or application latency.

The [registered B pilot](pilot-plan.json) is `k-pilot-100000ns-10000-w256`: 10,000 arrivals/s for 35 seconds, **350,000 arrivals**, with 256 workers. The plan was registered at 23:15:05 UTC with policy `require-b350k`; its completed result is reported below. A dry-run draft is not a registration or completed workload. The proposed formal order is A/B/A/B at 26,000 arrivals/s, 350,000 planned arrivals per round, giving an exact integer-nanosecond arrival window of 13.461538461 seconds. Plans may be executed only after source-pinned build, immutable transfer verification, prerequisites and budget gates pass. Registered IDs must never be silently reissued.

All groups retain:

- Workload/state profiles `extended-350k-256` / `capacity-350k-v1`, 350,000 maximum measured arrivals, retained-order limit 360,000, global cached-result limit 100,000, per-producer cache 1,024 and pending-outbox capacity 800,000.
- Three members, fixed leader 0 with recorded term evidence, 2 GiB member/load heaps, 256 maximum cluster sessions, Aeron 1.53.3, node MediaDriver `SHARED`, Archive `SHARED`, sync level 2, MTU 1248 and requested node receive/send buffers 131,072 bytes. Actual owned-socket attestations must confirm the effective kernel buffers separately.
- Independent `BackoffIdleStrategy(10,5,1000,1000000)` instances for the five node driver roles, unchanged matching rules, and the same shared client MediaDriver with 256 independent Aeron clients/sessions and 256 synchronous workers, one in-flight command each.
- Per-worker FIFO 64, total waiting slots 16,384, absolute arrival scheduling and round-robin producer assignment. Four independent producers share each of 64 buyer accounts. Every accepted measured command is one independent one-lot IOC buy and one trade against the seeded maker.
- Initial state of 64 buyers funded with 1,900,000,000 quote units each, a 380,000-lot GTC maker, 100 excluded warmup IOC commands and the pinned prepared core SHA-256 `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`. Every completed new preparation must match its bytes; the prior digest alone is not new execution evidence.
- Initial request timeout 2 seconds, same-identity unknown resolution, 30-second drain, scheduler lateness validity limit 20 ms, connection construction concurrency eight and two 12-second session-reclamation waits outside measurement. The whole load/validation process retains its 600-second outer deadline.

The load still shares member 2's host. Gateway, PostgreSQL projection and subscriber fanout are excluded. This measures the deployed client-plus-replicated-cluster path and its finite bounded queues, not an isolated matching-engine ceiling, synchronized-clock one-way latency or a production capacity SLA.

## Source, runtime and validation identity

The new source is `ab6fc73731642d0d17a242a930a2cb60aba11e16`, extracted using `git archive` of the explicitly pinned commit. Source archive SHA-256 is `6a40f4cebb2818d3a001906f6add908eac4baec42e542975b458341a6313c4a8`. The [isolated Java receipt](tool-validation/java-tests.json) records 118 tests, zero failures/skips and exit 0. The [immutable common node/load bundle](node-release.json) has SHA-256 `5ad30da02ba8cac861efbbbe1b90f3a5ac7952f1488311596555ff6bb9ba08cd`. Its [manifest](node-deployment-manifest.json) limits changed cluster entries to the named node startup/remote-experiment metadata and unknown-validation guard family; unchanged production JAR entries are compared against 52fb. Core matching, ClusterClient transport and profile rules remain byte-identical under that entry comparison. The [three-member upload receipt](node-upload-receipt.json) records matching transferred files and successful Linux launcher tests on every member.

The [Python validation receipt](tool-validation/python-tests.json) records **64 affected launcher/verifier tests**, zero failures/errors/skips and exact subprocess exit 0, with stdout/stderr and four source hashes. Earlier 60/61-test receipts preceded the final compatibility and failed-run configuration changes; they do not replace the final 64-test evidence. The [controller validation](tool-validation/controller-validation.json) records ten offline self-tests, explicit draft-only registration checks and a real verifier invocation on a temporary synthetic terminal-failure fixture. It proves guard/configuration behavior, not Linux deployment or cloud throughput.

Runtime evidence must agree at all layers:

| Evidence | Required values |
|---|---|
| Campaign fixed configuration | All three fields together: `nakUnicastDelayNs`, `clientNakUnicastDelayNs`, `nakUnicastRetryDelayRatio=100` |
| Node argv | Exactly one matching integer `-Daeron.nak.unicast.delay=...`; no repeated/conflicting or other hidden NAK JVM property |
| Node started record | Actual `nakUnicastDelayNs` and `nakUnicastRetryDelayRatio=100` |
| Load argv | Shared-driver flag plus exactly one matching NAK-delay flag; the complete NUL-delimited argv digest must match its process receipt |
| Load configuration | Actual shared-driver `clientNakUnicastDelayNs` and `clientNakUnicastRetryDelayRatio=100`, with `clientDriverMode=shared`, count 1 and independent Aeron clients |

Delay values are strict integers in 1,000–1,000,000 ns. The launcher opt-in is node-only and absent by default; an absent opt-in preserves the earlier argv and non-secret configuration digest. Historical missing runtime fields remain compatible. A complete actual runtime default pair 1,000 ns/100 is also accepted without inventing a new fixed fingerprint field. Partial runtime declarations, undeclared nondefault values, duplicate properties and changed retry ratios fail verification. New explicit fixed fields enter the comparison identity; changing them cannot silently mix cohorts.

## Failed outcomes remain failed

A timeout is unknown, not a rejection. The original business identity must be retained for retries and any later recovery. Worker advancement stops behind its unresolved identity; queued work is explicitly not sent. Per-producer cache 1,024 and global cache 100,000 are finite, so a later stale-sequence response cannot prove the original business command never executed.

The corrected validator refuses confirmed-only reference replay when unresolved identities remain. Its exact terminal guard explains that those identities may already have executed and canonical validation is incomplete. It avoids the earlier misleading sequence/order-ID mismatch caused by replaying an incomplete execution set. It does not turn missing responses into failures or prove matching correctness for the incomplete round.

The verifier's explicit `--include-failed-unknown` path allows **configuration-only** attestation for that one exact terminal guard, a typed nonzero exit receipt, positive matching unresolved count and identical complete load-summary values. It verifies the same actual argv/runtime/startup/prepared-byte evidence, preserves the failure and creates no business `result.json`. Its receipt explicitly sets `configurationOnly=true` and `businessCorrectnessVerified=false`; a passed configuration check is not a passed benchmark. Other failure signatures, including a genuine business-result mismatch, halt the experiment. In-progress evidence is not annotated as terminal.

The runner may proceed past that narrowly recognized incomplete round only after retaining raw data, checking source/configuration/leader evidence and verifying all explicitly owned per-trial processes stopped. PID/start-time/argv ownership gates apply to load, controller, observers and members; no broad process matching is authorized. Export, unknown signature, identity, cleanup, configuration or leader failures stop progression. Any such round remains invalid/incomplete and cannot be included as correctness-validated capacity.

## Complete archive and reporting contract

Every completed attempt must retain its original CSV locally and the full lossless `arrivals.csv.gz` plus `arrivals-archive.json` in the repository. There is no sampling or column reduction. Independent review will stream all 350,000 rows and all 33 columns, verify compressed and decoded SHA-256/bytes against the manifest, local raw and immutable analyzer input hash, and check sequential indices, producer/request/account/client-order identities and outcomes. Missing confirmations receive no invented zero latency.

The report will recompute in-window confirmed goodput and nearest-rank scheduled-to-confirmed p99, separately count FIFO-full/blocked/not-sent, initial unknowns, later resolutions and final unresolved, and clip each worker's execution interval to the arrival window for slot occupancy. Confirmation during drain cannot inflate arrival-window goodput. Any drop, rejection, error or unresolved arrival makes returned-command p99 conditional; all-offered accepted p99 stays null. Invalid and negative results remain visible.

Valid observed stability additionally requires complete correctness/source/configuration/fixed-leader evidence, at least ten seconds of arrivals, >=95% in-window accepted goodput, no loss/rejection/error/unknown, bounded fitted second-half backlog growth and bounded drain. A full finite FIFO can flatten backlog while dropping arrivals; that is not stability. No default latency SLO is assumed. Repeated favorable trials would still establish finite-window behavior only.

Canonical validation reads the checksum-protected MatchingEngine core view and checks outbox counts/watermarks separately. A declared 512 MiB full-checkpoint bound, full 350k business workload or successful final canonical read does not demonstrate a cloud restart from a full replicated core-plus-outbox checkpoint. Linux resource attribution must use actual whole-collection-interior samples, monotonic deltas, exact owned UDP sockets and read/truncation coverage. NAK counts, drops, hot threads and Archive write-path wall-time ratios are observations; the latter is not a direct disk/fsync latency measurement.

## Completed observations

| Run | Workers / planned arrivals | Window | In-window confirmed accepted / s | Scheduled-to-confirmed p99 | Not sent / initial unknown / unresolved | Drain | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| [B pilot, 10k/s, 100,000 ns](pilot100us/runs/k-pilot-100000ns-10000-w256/result.json) | 256 / 350,000 | 35 s | 340,808 / 9,737.371429 | 1,614.795477 ms, conditional | 254 / 0 / 0 | 997.834069 ms | Valid; overload or undersized client |

The [pilot analysis](pilot100us/analysis/summary.json) reports 349,746 eventually accepted commands and 254 explicitly FIFO-full/not-sent arrivals. All 350,000 offered arrivals remain accounted for. Of the accepted replies, 340,808 finish inside the 35-second arrival window and 8,938 during drain. No initial unknown, later unknown resolution, unresolved, rejection or server error occurs, and scheduler lateness remains within 20 ms. The sample still fails observed stability: admission loss makes all-offered accepted p99 null, and 997.834069 ms drain exceeds its 350 ms bound. In-window goodput passes the >=95% criterion, and fitted second-half backlog growth 2,519.338558 commands remains below its 3,500-command limit; those passing subchecks do not cancel the failures. Sampled outstanding peak is 8,938, FIFO peak 8,683 and maximum sampled in-flight count 256. The observations are non-atomic samples, not a simultaneous burst maximum. There is no default latency SLO, and a valid business result is not a stable-capacity result.

Independent streaming review of the actual archived bytes verifies **350,000 rows × all 33 columns**, contiguous indices, round-robin worker/producer/account/request identities, fixed planned offsets, no duplicate identities, no missing/extra columns and no invented latency for unsent rows. Every accepted command has one fresh one-trade reply, one initial attempt and leader 0. Distinct measured command sequences cover 168 through 349,913 without a gap. Recomputed nearest-rank scheduled p99 and arrival-window goodput match the analyzer. All compressed/decompressed/local-original/analyzer digests and sizes match the [manifest](pilot100us/runs/k-pilot-100000ns-10000-w256/arrivals-archive.json):

| Pilot raw representation | Bytes | SHA-256 |
|---|---:|---|
| [Full gzip](pilot100us/runs/k-pilot-100000ns-10000-w256/arrivals.csv.gz) | 23,850,605 | `879577effec65af556e1ac25f2f95c313384681011c85b9915f5fa9e0e164b77` |
| Decoded CSV / retained local original | 99,217,308 | `3a30b180e9fda67c67013d7c7cfd6dea387bb00468c43e1047f31036dc6c29be` |

The actual prepared snapshot matches `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`. Final and same-implementation deterministic-reference core bytes match: 57,749,353 bytes, SHA-256 `bb6dcb8a097793fc50bfb9a284904657904a79671324e8f7738fe40822846f9e`; see [final core](pilot100us/runs/k-pilot-100000ns-10000-w256/final-snapshot.bin) and [reference core](pilot100us/runs/k-pilot-100000ns-10000-w256/expected-snapshot.bin). Every reply, account conservation, remaining maker quantity and event/market/command sequence check passes. Final retained orders 349,847 equal `101 + accepted`; pending outbox 699,759 equals `267 + 2 × accepted`. Global cached results are 100,000 and producers 323. This reference uses the same MatchingEngine class, so it is not an independent matching algorithm; per-account/event accounting is supplemental evidence. Validation took 174.367764 seconds outside measurement and the process exited 0 under its unchanged 600-second deadline. No full replicated-checkpoint/restart claim follows.

The [configuration receipt](pilot100us/runs/k-pilot-100000ns-10000-w256/configuration-verification.json), raw argv/startup and actual shared-driver context independently agree on node/client delay 100,000 ns and ratio 100. Each member has exactly one explicit NAK property; the load uses the shared-driver flag plus the exact delay flag and still has 256 independent Aeron clients. Before/after owned-socket attestations pass on all members at kernel receive/send buffers 262,144 bytes. The [fixed-leader check](pilot100us/runs/k-pilot-100000ns-10000-w256/fixed-leader-check.json) retains sampled term 0 and leader 0. Outside-window session-reclamation waits are 12.000541 and 12.000284 seconds.

The mean first API time is 23.933729 ms, initial-API p99 120.063640 ms and FIFO-delay p99 1,588.568805 ms. Clipping every execution interval to the arrival window gives average occupancy 234.528487 of 256 worker slots (91.612690%). Worker mean API times range 22.912609–24.746413 ms, occupancy 89.233583–93.278779%, accepted counts 1,342–1,368 and FIFO-full counts 0–25. The diagnostic ratio `256 / mean API seconds` is 10,696.2/s at this load; it is not a throughput prediction and cannot isolate an engine limit. Tail waits and uneven bounded queues remain visible even with aggregate worker occupancy below 100%.

The B pilot demonstrates feasibility of this larger W256 fixture and full canonical-core checks, while its measured 10k/s finite window is nonstable. No new A/B repetition has yet been independently audited here. In particular, the earlier source's failed W256 run cannot substitute for a new explicit-default A control on the same artifact.

The total project cloud budget remains USD 20, using the existing three Pods and a separate recovery reserve. Budget receipts are conservative launch-time/rate estimates, not reconciled provider billing. The separate 100-million cumulative-unique-command, commands-per-second and simultaneous-connection targets remain unverified; fresh benchmark lineages intentionally reuse identities and cannot be pooled into a globally unique 100-million-command run.
