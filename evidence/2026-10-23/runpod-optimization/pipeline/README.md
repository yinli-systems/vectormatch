# Physical session and network ownership control

This phase compares direct client sessions with a multiplexed client transport while keeping the logical request window fixed. The source-pinned artifact has been built, tested and uploaded, and the separately registered full-size multiplexed pilot has completed with **all 350,000 commands accepted, zero UNKNOWN and a verified 35-second stable observation window at 10,000 arrivals/s**. Its lossless archive and every arrival were independently checked after export. This qualifies the new client path for formal comparison. The four-attempt matrix was registered on **2026-10-24 at 00:07:11 UTC** and completed at **00:32:42 UTC**, with all four attempts valid and canonically correct but overloaded at 26,000 arrivals/s. Multiplexing repeatedly reduces measured resource use; this experiment does not establish higher stable capacity.

The frozen [pre-registration](PRE_REGISTRATION.md) describes the intended experiment; the actual [pilot registration](pilot-plan.json) records its source, artifact, controller, prerequisite and budget identities. The pilot passes the strict gate. The actual [formal registration](plan.json) pins the four-attempt order and pilot prerequisite; its SHA-256 is `cd90cab3c80c29ffc48571b669e34e6666155e46e5be4817b3ddf2250f1ea95f`. Earlier [NAK results](../nak/README.md) retain their original validity and failure labels.

## Factor and causal scope

| Input | Direct arm A | Multiplexed arm B |
|---|---|---|
| Logical workers and maximum logical in-flight commands | 128 / 128 | 128 / 128 |
| Independent business producers | 128 | 128 |
| Per-worker bounded FIFO / total slots | 64 / 8192 | 64 / 8192 |
| Per-producer in-flight rule | One synchronous request | One synchronous request |
| Load MediaDrivers | One shared driver | One shared driver |
| Physical cluster sessions | 128 | 1 |
| Aeron/network ownership | Independent Aeron per client | One session driven by one network owner |
| Explicit transport property | `direct` | `multiplexed` |
| Actual `clientAeronMode` | `one-independent-Aeron-per-client` | `one-session-one-network-owner` |

The selected factor is the complete **physical-session, network-ownership and dispatch arrangement**. It changes both the number of physical sessions and who polls/offers their messages. It does not change the logical 128-request window, and cannot isolate session count from owner-thread dispatch by itself. It is not a comparison against the prior 256-worker NAK phase.

Both arms must use `-Dvectormatch.capacity.client.driver=shared`, `-Daeron.nak.unicast.delay=1000` and the explicit `-Dvectormatch.capacity.client.transport=direct|multiplexed`. The node and load NAK retry ratio remains 100. Runtime metadata after the workers are ready must attest `clientTransportMode`, `clientSessionCount`, `clientAeronMode`, one actual shared driver and effective NAK context values. Exact JVM argv, duplicate/hidden-property rejection and argv hashes are checked by the pinned verifier. The default transport remains direct; historical campaigns without the new opt-in retain their old fingerprint behavior.

Each multiplexed proxy retains its original worker/producer identity and one outstanding command. The owner routes replies by correlation, rather than reassigning business identities to the physical session. A timeout remains UNKNOWN until resolved with the same full command identity. Explicit retries reuse the pending correlation/future; the owner cannot keep offering after the current execute deadline without a new explicit retry. A fatal owner error invalidates the experiment, preserves the original arrival/backlog/failure evidence and is rethrown. These are correctness requirements, not throughput optimizations inferred from an observed run.

## Pinned source and completed preparation

Node and load both use **`e57e341909a49692b9ecbf9693803ed62a240b06`**. The isolated build was created from an explicit `git archive` of that commit, rather than the mutable working tree:

- Source archive SHA-256: `0dc974c7d2a251b473d83c97a819f4f0ec51ae93dbcbfaea3cbd9f7e448432e7`.
- Immutable bundle SHA-256: `f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937` (4,006,242 bytes).
- Cluster JAR SHA-256: `51211b1bb55b9f6f90f4c3ae68b75de96d77b3d8ed104b63d56b796991423c4a`.
- Core JAR SHA-256: `6364ae5546eba7545720d64c379ec72abb74a9b9a3f05a2e51ed6d16eebf8a92`.

The [deployment manifest](node-deployment-manifest.json) compares every non-directory JAR entry against the preceding `ab6fc73731642d0d17a242a930a2cb60aba11e16` artifact. Only the `ClusterClient`, `RemoteCapacityExperiment` and new `MultiplexedLoadTransports` class families may differ. `ClusterNodeMain`, `MatchingClusteredService`, `ClusterCapacity`, snapshot transport, command codec, matching core and dependency JARs remain byte-identical. Both arms use the same new common artifact; no old/new source split is used as a performance control.

Completed preparation receipts are:

| Check | Actual result | Evidence |
|---|---|---|
| Isolated full Java build and `:cluster:installDist` | 128 tests; zero failures or skips; exit 0 | [Java receipt](tool-validation/java-tests.json), [build stdout](tool-validation/java-build.log), [XML suites](tool-validation/java-xml/) |
| Launcher/verifier Python regressions | 69 tests; zero failures, errors or skips; exit 0 | [Exact argv/output/source hashes](tool-validation/python-tests.json), [log](tool-validation/python-tests.log) |
| Controller/offline guards | 14 tests; exit 0; stdout-only draft registrations create no campaigns | [Controller validation](tool-validation/controller-validation.json), [frozen source archive](tool-validation/controller-sources.json) |
| Multiplexed focused tests | Real three-JVM cluster plus fake-owner lifecycle/deadline/late-response tests and load metadata/fatal-evidence tests | [Focused receipt](tool-validation/focused-java-validation.json), [integration XML](tool-validation/focused-java-MultiplexedClusterIntegrationTest.xml) |
| Immutable transfer to existing three nodes | All three per-file hashes verified; each Linux launcher suite passed 32 tests | [Upload receipt](node-upload-receipt.json), [release identity](node-release.json) |

The upload receipt proves transfer/hash and launcher test completion. It does not itself prove that a performance trial ran. Tests cover more than 64 outstanding asynchronous replies, distinct producer identities through one physical session, same-key timeout recovery without duplicate business effects, no offers after the current execute deadline, and preservation/rethrow of the original fatal error. They do not replace full cloud arrival/canonical audits.

## Inputs held fixed

The pilot and proposed formal arms use three existing UDP nodes with appointed leader 0 and term checks, 2 GiB node/load heaps, maximum cluster sessions 256, `extended-350k-256` / `capacity-350k-v1`, retained-order limit 360,000 and outbox capacity 800,000. Global cached results remain 100,000 and per-producer cache 1024. Node MediaDriver and Archive threading remain SHARED, sync level 2, MTU 1248, requested socket receive/send buffers 131,072 bytes, and the same observer is used on both arms. Actual kernel buffer sizes and startup values are recorded separately from requested settings.

Each attempt starts in a fresh isolated state. The fixed fixture uses 64 buyer accounts, the same seller maker liquidity and funding, and 100 warm-up orders outside the measured window. The expected prepared canonical core-view SHA-256 remains **`2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`**. Sharing accounts among logical producers and routing several logical producers through one session do not merge request identities. No aggregate unique-order or 100-million-order target is established by repeating this fixture.

Setup and final validation retain their legacy clients outside the arrival window. Connection ramp, fixed session-reap waits, initial timeout, same-identity resolution, bounded queues, deadline handling, scheduler validity criteria and final drain are held fixed. The process timeout is 600 seconds. Canonical core-state comparison, per-reply replay, asset/order accounting and pending outbox counts validate the finite business state. The reference uses the same matching-engine implementation, so agreement is not an independent matching algorithm proof. This cloud capacity pilot does not exercise a full replicated Aeron checkpoint/restart.

## Pilot gate and formal status

The [registered pilot](pilot-plan.json) is **350,000 planned arrivals at 10,000/s over 35 seconds, W128, multiplexed**. Formal registration requires complete canonical correctness, a valid generator/measurement, all 350,000 accepted, and zero client not-sent, business rejection, server error and final unresolved outcomes. The completed pilot meets every requirement. This policy was fixed before observing the pilot and is stricter than the preceding NAK pilot gate.

The registered formal order is **A direct r1 / B multiplexed r1 / A direct r2 / B multiplexed r2**, each **350,000 planned arrivals at 26,000/s** (integer arrival window 13,461,538,461 ns). All four attempts have completed cloud load, owned cleanup, local postprocessing and independent gzip/identity audits. The controller exited 0 after retaining every registered attempt; the [completion timeline](timeline.jsonl) records `pipeline-session-ownership-matrix-completed` at 00:32:42.734081 UTC. A completed matrix does not mean every point is stable. Every actual registered attempt will be retained individually, including failed or invalid attempts.

The complete pilot result is:

| Attempt | Offered / window / logical workers | Final accepted | Window confirmations / goodput | Conditional scheduled p99 | All-offered p99 | Not sent / initial UNKNOWN / final unresolved | Drain | Classification |
|---|---|---:|---|---:|---:|---|---:|---|
| [B pilot](pilot/runs/p-pilot-multiplexed-10000-w128/trial.json) | 10,000/s / 35 s / 128 | 350,000 / 350,000 | 349,922 / **9,997.771429/s** | **41.870822 ms** | **41.870822 ms, finite** | 0 / 0 / 0 | 6.683714 ms | `OBSERVED_STABLE_WINDOW` |

The [raw result](pilot/runs/p-pilot-multiplexed-10000-w128/result.json), [frozen analyzer summary](pilot/analysis/summary.json), [process exit receipt](pilot/runs/p-pilot-multiplexed-10000-w128/receipt.json), [configuration verification](pilot/runs/p-pilot-multiplexed-10000-w128/configuration-verification.json) and [owned-process cleanup](pilot/runs/p-pilot-multiplexed-10000-w128/all-owned-processes-stopped.json) are retained. The analyzer summary SHA-256 is `b13be2488442da06a645b32ac979cd3dd17f7f6a2d50705c22d7adbeee63f981`. No formal row is filled before that attempt's complete archival and independent audit.

This stable label is the registered finite-window criterion, with no latency SLO configured. The pilot achieved 99.9777% window goodput and all commands eventually confirmed; 78 confirmations occurred during drain and are excluded from window goodput. The drain bound was 350 ms and observed drain was 6.684 ms. One-second backlog observations peaked at 16 queued, 128 in flight and 144 combined outstanding, with fitted second-half growth 5.686 commands against a 3,500-command limit. These are sampled, non-atomic queue/in-flight observations, not an exact burst maximum.

All 350,000 confirmations qualify for the all-offered accepted-command latency distribution, so its finite p99 equals conditional p99 in this pilot. Initial API p99 was 13.825283 ms; queue-delay p99 was 29.029891 ms and scheduler-lateness p99 0.048141 ms. The maximum scheduler lateness was 10.071 ms, below the 20 ms generator limit. There were 5,448 execution starts more than 20 ms after their planned arrival, reflecting queue/dispatch delay; this is a separate measure from scheduler admission lateness and is retained.

The independently recomputed initial API mean was 6.297205 ms. Arrival-window clipped busy intervals occupied a mean **62.963 of 128 logical slots (49.1902%)**. Individual workers accepted 2,734–2,735 commands, with mean API times 6.260369–6.338243 ms and window occupancy 48.9024–49.5104%. These measurements describe this 10,000/s pilot, not a prediction that service time stays constant at a higher arrival rate.

### Independent full-arrival and canonical audit

After controller exit 0 and completed export, one independent 12.13-second local audit streamed the gzip exactly once. It hashed compressed and decompressed bytes during that same traversal, parsed every record, and retained only bounded identity/sequence bookkeeping and latency integers. Exact nearest-rank p99 used most-significant-byte radix selection with at most eight passes over latency integers, without sorting the full arrival table, re-decompressing the archive or rerunning the frozen analyzer.

The audit checked all **350,000 rows and 33 columns**, sequential arrival indices, round-robin worker assignment, 64-account mapping, producer/request/client-order identities, absolute planned times, timestamp and latency algebra, all leader IDs, one trade per accepted request, no replay, and unique contiguous actual command sequences 168–350,167 with matching reply/private/public event sequences. No dropped/unknown records were fabricated or omitted. The 128 per-worker transport counters agree with accepted command counts, with no accepted resend or timeout.

| Lossless archive check | Exact value |
|---|---|
| [Compressed arrival archive](pilot/runs/p-pilot-multiplexed-10000-w128/arrivals.csv.gz) | 20,707,730 bytes; SHA-256 `06d526575455b2075e530f4780756c32c444f0475bd0d2accb0b42e4d84f1b73` |
| Decoded original CSV | 97,148,303 bytes; SHA-256 `fb3baf6cec51dbd8edf0b024f98bd50115445695553158e0cc7bee4ff4758a61` |
| [Archive manifest](pilot/runs/p-pilot-multiplexed-10000-w128/arrivals-archive.json) | Both byte counts and hashes match; decoded SHA also equals the frozen analyzer's `inputSha256["arrivals.csv"]` |
| Prepared canonical core view | SHA-256 `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`, unchanged |
| Final canonical core view vs replay | 57,682,277 bytes, compared block for block; both SHA-256 `fe441b2ef5c20878572bf83de40da166ed55112964a5697759e72db682c8baa2` |

The independent check also rehashed all eight raw inputs named by the configuration receipt and checked the common artifact/source identity, actual shared driver count 1, physical session count 1, multiplexed mode, effective load NAK 1,000 ns / ratio 100 and fixed leader 0 / term 0. The [term check](pilot/runs/p-pilot-multiplexed-10000-w128/fixed-leader-check.json) retains sample/coverage limits. The two session-reap waits were 12.000598 and 12.000310 seconds, explicitly outside measurement and validation timing.

Final command/event/market sequences were **350,167 / 700,267 / 700,201**, with **350,101 retained orders, 700,267 pending outbox events, 100,000 cached results and 195 producers**. Full final core bytes agree with the same-engine replay, every returned result is checked, and independent seller/buyer asset and maker-quantity formulas passed in the experiment. The validation interval was 172.049 seconds and is excluded from load latency/throughput. This remains a canonical core-view and outbox/accounting validation rather than a cloud replicated-checkpoint/restart experiment.

## Formal observations — all four registered attempts retained and audited

Every formal row offers 350,000 arrivals at 26,000/s over 13,461,538,461 ns, with logical W128/FIFO8192. Current results are:

| Attempt | Physical sessions | Final accepted | Window confirmations / goodput | Conditional scheduled p99 | All-offered p99 | Client not sent / initial UNKNOWN / unresolved | Drain | Classification |
|---|---:|---:|---|---:|---|---|---:|---|
| [A direct r1](direct/runs/p-direct-26000-w128-r1/trial.json) | 128 | 207,664 / 350,000 | 199,372 / **14,810.491429/s** | **607.845506 ms** | null | 142,336 / 0 / 0 | 584.659542 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |
| [B multiplexed r1](multiplexed/runs/p-multiplexed-26000-w128-r1/trial.json) | 1 | 208,963 / 350,000 | 200,692 / **14,908.548572/s** | **668.094016 ms** | null | 141,037 / 0 / 0 | 578.905523 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |
| [A direct r2](direct/runs/p-direct-26000-w128-r2/trial.json) | 128 | 207,908 / 350,000 | 199,632 / **14,829.805715/s** | **635.631768 ms** | null | 142,092 / 0 / 0 | 530.194827 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |
| [B multiplexed r2](multiplexed/runs/p-multiplexed-26000-w128-r2/trial.json) | 1 | 215,255 / 350,000 | 206,949 / **15,373.354286/s** | **608.066280 ms** | null | 134,745 / 0 / 0 | 564.506641 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |

All four completed points are valid and canonically correct: every started request was accepted, with no business rejection, server error, initial UNKNOWN or final unresolved result. Unsent requests are explicitly **load-generator queue-full admission drops**, rather than exchange rejections or UDP loss. Only 56.96–59.13% of offered arrivals confirm during the arrival windows. The all-offered p99 remains null despite finite conditional p99, and all drain intervals exceed the 134.615-ms bound. Multiplexed window goodput is 0.662% and 3.665% higher than its respective preceding direct repetition (arithmetic-mean difference 2.165%), while conditional p99 is worse in the first pair and better in the second. These are descriptive observations from two overloaded pairs, not a stable-capacity gain or a consistent tail-latency improvement.

The [direct summary](direct/analysis/summary.json) after r2 has SHA-256 `94f4ece5ad3ad0677a1633857462213c6644753b0a8a08b8f77873ab1b0319a3`; the final [multiplexed summary](multiplexed/analysis/summary.json) after r2 has SHA-256 `15e15a5f0f4afef53484000f9717c43f4e2056e0796f995c59c33c71b8093b47`. The prior B r1 summary SHA was `7168b069b2c3268eda4081e5c183b9b7d0fdac6947d7cf4fb2ed88b1e655b951`. These cohort summaries may append subsequent registered repetitions without changing completed trial raw evidence. The original direct r1 summary SHA was `70bca22f09dd32db9a9f348e218aa22e175733c988e9abc016ca903dd03c5964`.

### Full-arrival and canonical audit of completed formal attempts

Independent single-pass gzip audits took 5.21 / 4.21 / 6.23 / 4.49 local seconds for A1 / B1 / A2 / B2. For each run they checked all **350,000 rows and 33 columns**, saved business identities, timestamp/latency equations and unchanged workload parameters. Accepted commands each returned one fresh one-trade result, with unique contiguous actual command sequences. All four had zero replayed replies and zero recorded accepted internal resends. Queue-full rows retain planned/admission/end timestamps but leave unstarted execution/confirmation/response fields empty; they never contribute fabricated zero latency.

Each run's eight configuration-receipt inputs were independently rehashed, and common e57 source/bundle identity, the actual direct/128-session versus multiplexed/one-session arrangement, one shared driver, effective NAK 1,000 ns / ratio 100, prepared SHA and leader 0 / term 0 agreed. Per-run configuration receipts and cleanup remain linked under their trial directories. Compressed and decoded hashes were computed in the same gzip traversal and match the manifest plus original analyzer CSV SHA.

| Run / lossless archive | Compressed bytes / SHA-256 | Decoded CSV bytes / SHA-256 |
|---|---|---|
| [A1 gzip](direct/runs/p-direct-26000-w128-r1/arrivals.csv.gz), [manifest](direct/runs/p-direct-26000-w128-r1/arrivals-archive.json) | 16,178,915 / `645145a274428d547821d618729797bae634912c5074796c734ceedff4a7b138` | 81,304,415 / `5f7530b5bc9165aa0e55d3f7a6acdeb76701b6ba57c97b8fae3418f2a18d48a1` |
| [B1 gzip](multiplexed/runs/p-multiplexed-26000-w128-r1/arrivals.csv.gz), [manifest](multiplexed/runs/p-multiplexed-26000-w128-r1/arrivals-archive.json) | 15,939,088 / `3637b68afe64ab8d3def64224d229bccc6271dd29968e5e4f9ea9ecf873e1398` | 81,467,432 / `97db5bd677d7e16b38e0c02577dbcf0eac0790a58ac7d7b8c1752a12b2d4835f` |
| [A2 gzip](direct/runs/p-direct-26000-w128-r2/arrivals.csv.gz), [manifest](direct/runs/p-direct-26000-w128-r2/arrivals-archive.json) | 16,294,019 / `4bc7c55f13290e6c26c873ca50594c16b21e99b0a586c91f3aec295e3d9d4566` | 81,419,828 / `a56616151a6e6c3ca8ed5161f53091df023e7974fcd293bf0b509e298bd0ad13` |
| [B2 gzip](multiplexed/runs/p-multiplexed-26000-w128-r2/arrivals.csv.gz), [manifest](multiplexed/runs/p-multiplexed-26000-w128-r2/arrivals-archive.json) | 16,221,620 / `9119082f9d475434281e5e990fdd313c663579d1e9bf51a12fcb2ddb92856e33` | 82,166,906 / `42fafaaab86f91f05396a7a803289f5bfd09d21a0d60defd3878d32ee4199f96` |

| Run / canonical result | Final core view bytes / SHA-256, equal to replay block for block | Retained orders / pending outbox | Cache / producers | Validation outside measurement |
|---|---|---|---|---:|
| [A1 result](direct/runs/p-direct-26000-w128-r1/result.json) | 41,953,347 / `0f9f8853815b617aad0dd68aa6c8eba4052f31c2b002d3dc3f8358485592dbf8` | 207,765 / 415,595 | 100,000 / 195 | 122.711 s |
| [B1 result](multiplexed/runs/p-multiplexed-26000-w128-r1/result.json) | 42,103,406 / `b1977afa5a4a54238e14f4e28f63c1635ec2c0d78f126f2e3c1032ff37424a48` | 209,064 / 418,193 | 100,000 / 195 | 123.957 s |
| [A2 result](direct/runs/p-direct-26000-w128-r2/result.json) | 41,979,565 / `77a72d89edf25235dd6efe0602557042f25ba885c6dc5cbe2b190f07bb71aa14` | 208,009 / 416,083 | 100,000 / 195 | 124.036 s |
| [B2 result](multiplexed/runs/p-multiplexed-26000-w128-r2/result.json) | 42,793,236 / `281aa801c57242bf33c32ff55e0ffbd7d8e942ab07749f3dc63aac7fabbf721c` | 215,356 / 430,777 | 100,000 / 195 | 125.146 s |

All canonical views were compared block for block with their saved expected views. Actual command/event/market deltas, retained-order counts, outbox continuity/pending, every returned business result and independent seller/buyer/maker conservation formulas pass in the experiment. The reference remains the same engine implementation. This does not turn the capacity runs into independent algorithm or full replicated-checkpoint/restart proofs.

### Logical request-slot and queue observations

| Independently recomputed measure | A direct r1 | B multiplexed r1 | A direct r2 | B multiplexed r2 |
|---|---:|---:|---:|---:|
| Initial API mean | 8.646201 ms | 8.586062 ms | 8.602900 ms | 8.334089 ms |
| Initial API p99 | 15.236009 ms | 14.387955 ms | 14.227934 ms | 14.072224 ms |
| Queue-delay p99 | 598.758846 ms | 658.610031 ms | 626.131627 ms | 599.405779 ms |
| Mean occupied logical slots / 128 | 127.952 / 99.9628% | 127.951 / 99.9614% | 127.952 / 99.9627% | 127.950 / 99.9606% |
| Per-worker accepted range | 1,609–1,635 | 1,615–1,638 | 1,605–1,639 | 1,658–1,687 |
| Per-worker queue-full drop range | 1,100–1,125 | 1,097–1,119 | 1,096–1,129 | 1,048–1,077 |
| Per-worker API mean range | 8.577633–8.711982 ms | 8.559129–8.682360 ms | 8.525759–8.703082 ms | 8.309231–8.454054 ms |
| Per-worker window occupancy range | 99.9289–99.9863% | 99.9243–99.9848% | 99.9367–99.9870% | 99.9173–99.9848% |
| Sampled peak queue / in-flight / outstanding | 8,192 / 128 / 8,320 | 8,192 / 128 / 8,320 | 8,172 / 128 / 8,300 | 8,192 / 128 / 8,320 |
| Fitted second-half outstanding growth | 0.214246 commands | 22.714289 commands | 4.071374 commands | 0 commands |
| Confirmations during drain, excluded from window goodput | 8,292 | 8,271 | 8,276 | 8,306 |

These measurements distinguish API confirmation time from the long bounded-FIFO wait. The nearly full synchronous logical window and bounded queues rejecting arrivals explain why a small fitted backlog slope cannot be read as stability. They describe the tested client-plus-cluster path; they do not isolate a universal engine ceiling or justify indefinitely adding workers. The repeated resource observations below apply to these four formal points; they do not turn the overloaded finite window into a stable-capacity result.

The new [streaming-analyzer validation receipt](../tool-validation/streaming-analyzer-validation.json) independently recomputes completed A1 and two other frozen points with **every trial field equal** to existing summaries. It is a separate postprocessing parity check. The current registered four-attempt matrix still uses its original pinned analyzer; its tool identity and frozen summaries are not replaced.

## Pilot resource observations

The separate [pilot attribution report](analysis/pilot-attribution-summary.json) is frozen at SHA-256 `9ecf658e71e66584aad67a1fcf8ea12976638e08621f7fa10441359f335f246e` (652,621 bytes), with 45 raw/tool input hashes checked by its wrapper. It confirms the actual one-session/one-driver multiplexed arrangement, logical W128/FIFO8192, NAK settings and prepared state. The strict whole-collection arrival-window interior spans approximately 34 seconds; these observations describe this pilot alone.

| Strict interior observation | Pilot |
|---|---:|
| JVM CPU, nodes 0 / 1 / 2 | 2.029 / 1.234 / 1.129 cores |
| Load JVM CPU | 5.664 cores |
| Load owner / raw driver-prefix TID / worker-group CPU | 0.837 / 0.604 / 4.030 cores |
| Owned UDP socket drop deltas, node 0 / load / node 2 | 0 / 0 / 0 |
| Follower node 1 owned LOG port 23104 drop delta | 32 |
| Node 0 NAK sent / retransmits | 409 / 4 |
| Cgroup quota-throttle increments | 0 on all three hosts |
| Observer CPU, nodes 0 / 1 / 2 | 0.0158 / 0.0149 / 0.0345 cores |

Selected observations have no reported scan truncation or read errors; the load scan reached 175 TIDs and 19 FDs, below observer caps. Load is colocated with node 2. Low loss here does not mean the UDP transport is lossless: the follower LOG socket still recorded 32 drops and retransmission activity exists. No throughput/resource A/B inference is made by comparing this 10,000/s pilot to an earlier 26,000/s direct run.

Node 0 Archive recording was approximately 65.28 MB over the selected scope; write-path wall-time ratios were approximately 0.255 / 0.989 / 0.979 for nodes 0 / 1 / 2. These include write/force/descheduling and cannot be interpreted as pure fsync latency or proof of a single storage bottleneck. Formal attribution is retained separately from this pilot and appears below; the pilot is not used as a different-rate control.

## Formal resource observations at the same offered load

The formal [attribution report](analysis/attribution-summary.json) was generated once after all four registered attempts completed. Its SHA-256 is **`d680a033f7040c2c809973b8c42e47af7c974863ea2633d152c5ab4e22b88a76`** (2,607,120 bytes), with 140 raw/tool hashes verified by its wrapper. All four actual configuration/source/transport/prepared identities pass, and every point remains valid/canonical/overloaded. The whole-collection arrival-window interior provides approximately 12–13 seconds of comparable samples per formal run.

| Same-rate formal observation | A direct r1 / r2 | B multiplexed r1 / r2 |
|---|---|---|
| Node 0 JVM CPU, cores | 2.562 / 2.589 | 1.263 / 1.394 |
| Load JVM CPU, cores | 4.072 / 4.105 | 1.724 / 1.855 |
| Node 0 owned UDP sockets / FDs | 134 / 553 in each direct run | 7 / 45 in each multiplexed run |
| Load owned UDP sockets / FDs | 129 / 400 | 2 / 19 |
| Load observed TIDs | 299 | 172–175 |
| Load worker-group CPU, cores | 2.003 / 2.006 | 0.213 / 0.200 |
| Multiplexed network-owner CPU, cores | Not present | 0.201 / 0.222 |
| Node 0 / load / node 2 owned UDP drop deltas | 0 in every run | 0 in every run |
| Node 1 owned LOG port 23104 drop deltas | 315 / 91 | 0 / 0 |
| Node 0 NAK sent | 38 / 465 | 39 / 0 |
| Node 0 cgroup average CPU, cores | 2.669 / 2.684 | 1.287 / 1.419 |
| Node 0 cgroup throttle time increments | 24.53 / 1.94 ms | 0 / 0 |
| Node 0 Archive write-path wall-time ratio | 0.405 / 0.423 | 0.118 / 0.128 |

The physical-session/ownership arrangement repeatedly reduces JVM CPU, descriptor/socket counts, observed threads and selected follower LOG drops at the same offered load and logical window. Node 0's quota remains 5.1 cores, other hosts have zero observed throttle increments, and the source/configuration/observer are common. No selected scan-cap truncation, read/gap errors or matched log-pattern errors were reported. These are sampled process and owned-socket observations; they are not a proof of no possible unsampled burst or error.

The causal comparison is the composite session/owner/dispatch arrangement. Resource savings cannot be assigned to session count alone, and the smaller measured Archive wall-time ratio cannot be interpreted as a pure fsync improvement. Both arms still occupy approximately 99.96% of logical request slots, reject a large fraction at the bounded client FIFO and exceed the drain bound. The observed goodput changes are modest and tail latency changes direction between pairs. **A repeatable resource reduction is established for these observations; a higher stable capacity, consistent p99 improvement, unique server bottleneck and 100-million target are not established by this matrix.** A separately registered lower-rate capacity curve is needed to bracket stability without conflating the new client arrangement with a different load or postprocessor identity.

## How completed results will be assessed

Every planned arrival must survive into the 33-column CSV, including queue-full, not-started and UNKNOWN rows. The committed gzip is lossless: compressed SHA/bytes, decompressed SHA/bytes, exact 350,000 data rows, unchanged columns and the analyzer's raw CSV hash must agree with its manifest. Plaintext CSV remains local and is not replaced by sampled records. Each completed run is streamed once for the independent audit; prior frozen cohorts are not reparsed to manufacture a new result.

Arrival-window goodput counts replies confirmed by the end of the planned arrival window. Confirmations during drain remain in final correctness totals and conditional scheduled-to-confirmed latency, but do not enter window goodput. Conditional p99 includes scheduler and bounded-worker-queue delay. All-offered p99 is unbounded/unknown when any offered request is dropped, rejected, unresolved or otherwise unconfirmed; those rows are not assigned zero latency. Initial UNKNOWN and final unresolved counts remain separate even when a same-key retry resolves the original identity.

Backlog, queue occupancy, drain time, initial API RTT and occupied synchronous slots will be shown separately. A full bounded queue with a flat fitted slope can reflect saturation and admission drops; it is not evidence of stability. Timing-invalid and canonical-incomplete points remain visible. Conditional p99 and client-reported confirmations from a failed canonical experiment cannot establish verified business throughput or a stable capacity boundary.

Attribution uses whole-collection timestamps inside each measured arrival window, monotonic durations and process/TID/inode lifecycle ownership. Sampling caps, collection errors and missing coverage remain explicit. Socket counters, configured NAK timers, Archive wall time and one busy thread do not individually identify a universal bottleneck. Archive write-path wall time includes write, force and descheduling; it is not pure storage latency. Load generation is colocated with node 2, and these finite-window observations do not establish sustained production capacity or the 100-million target.

## Lifecycle and budget boundaries

The registered plan uses only the existing three Pods, retains the USD 20 project limit and a USD 2 recovery reserve, and records a launch-time estimate rather than a reconciled bill. At pilot registration the estimate was USD 9.6523 accrued and USD 12.0423 including the next-trial and recovery reserves. At formal registration it was USD 10.0951 accrued and USD 13.3951 including the registered matrix reserve and recovery reserve. These are historical estimates, not a current balance or reconciled bill.

Each trial records its load/controller/observer/node PID, start ticks and command hash, stops only owned identities, and checks port/process release before another attempt. The exact canonical-incomplete UNKNOWN guard can continue only after full same-identity evidence, configuration-only verification and owned cleanup; it does not create a successful result or reclassify unknown requests. Unexpected business mismatch, source/configuration/leader drift, incomplete export or cleanup failure halts the matrix. No extra resource provisioning or silent retry under an existing trial ID is permitted.
