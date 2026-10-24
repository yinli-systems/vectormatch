# Fixed-rate capacity follow-up: 18,000 arrivals/s

This is a separately registered **A direct / B multiplexed / A direct / B multiplexed** comparison at **18,000 planned arrivals/s**, with 350,000 arrivals per attempt and a 19,444,444,444-ns planned arrival window. It was registered on **2026-10-24 at 00:33:30 UTC** and completed at **00:52:35 UTC**. All four attempts have complete archival and independent full-gzip/identity audits. Every point is valid and canonically correct, with zero UNKNOWN, but **all four are overloaded at 18,000 arrivals/s**. The second multiplexed run is markedly slower and remains visible; this matrix establishes no repeatable throughput/latency advantage, stable 18k boundary or universal engine ceiling.

The actual [registered plan](plan.json) has SHA-256 `426559e90c7969eb55038c441067ecca2eec007bda06b2104af7f4b661536e8e`. The frozen [preparation document](PRE_REGISTRATION.md) records the rules before registration; its preparation-only status is historical. The actual plan and later terminal receipts establish what ran. The [previous 26k matrix](../pipeline/README.md) remains frozen: all four points were canonically correct but overloaded, so the predeclared 18k branch was selected. The alternative 35k branch required both multiplexed 26k repetitions to be stable and was not eligible.

## Factor and unchanged execution artifact

| Input | Direct arm A | Multiplexed arm B |
|---|---|---|
| Logical producer workers / maximum in-flight | 128 / 128 | 128 / 128 |
| One-in-flight rule | One synchronous command per producer | One synchronous command per producer |
| FIFO per worker / aggregate FIFO | 64 / 8192 | 64 / 8192 |
| Load MediaDrivers | One shared driver | One shared driver |
| Physical cluster sessions | 128 | 1 |
| Network ownership | Independent Aeron per client | One physical session / one network owner |
| Explicit transport | `direct` | `multiplexed` |

The factor is the complete physical-session/network-owner/dispatch arrangement, not only the number of sessions. Business identities, logical request concurrency and queues remain distinct through the multiplexed session. Both arms use node/load NAK delay **1,000 ns**, retry ratio **100**, the same request timeout, same-identity UNKNOWN resolution and bounded drain. No matching rules, scheduling algorithm, retries or outcome definitions change between arms.

**Node and load remain exactly `e57e341909a49692b9ecbf9693803ed62a240b06`**, common bundle SHA-256 `f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937`. No node/load rebuild or redeployment under a different identity is introduced by the local analysis change. The original e57 build/build-tool identities remain in the plan. Actual JVM flags, post-ready transport/session/driver counts, NAK context values, startup logs, source/artifact hashes and fixed leader/term are verified for each attempt.

Other fixed inputs are three existing UDP nodes; leader 0 with term checks; 2 GiB node/load heaps; SHARED node MediaDriver and Archive; sync level 2; MTU 1248; requested receive/send buffers 131,072 bytes; maximum cluster sessions 256; `extended-350k-256` / `capacity-350k-v1`; retained orders 360,000; outbox capacity 800,000; global cache 100,000 and per-producer cache 1024. The same observer and socket probe are used in both arms. Load generation is colocated with node 2.

Every attempt starts in a fresh isolated state, with the same 64 pre-funded buyer accounts, fixed seller liquidity and 100 warm-up commands outside the arrival window. Prepared canonical core-view SHA-256 remains **`2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`**. Multiple logical producers may share an account; they retain separate producer/request/client-order identities. Repeated trials reuse this fixture and do not establish an aggregate 100-million unique-order result.

## Independent local postprocessor identity

This cohort uses a **separate local analysis artifact**, rather than changing any e57 node/load code or pretending its new analysis dispatch was part of that old build:

| Identity | Pinned value |
|---|---|
| Postprocessor source commit | `3fd86fe535fc0858e300e0337d4da154f622ae32` |
| Analysis identity SHA-256 | `31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f` |
| Streaming entry point | `scripts/analyze-capacity-streaming.py` |
| Streaming source SHA-256 | `7a086669d07e352dd2cf43f3b5d0a48e1527ad1c643a45001b4648a68f9d860a` |
| Adjacent frozen legacy dependency SHA-256 | `5fba16bbdbb5e90318c65f945991f2eb4ddb256fb36f93e28e26133b9e65c80b` |
| Two-file committed source archive SHA-256 | `451da5a8553205708df8b25f98f35de6a8a4aaced9a4c966fe07e0069147fadf` |
| Validated interpreter | CPython 3.9.6; executable/resolved binary and binary SHA pinned in the identity receipt |
| Parity/RSS receipt SHA-256 | `f04341ba4821a64f757d12925d8316c06b31746d798c710ab39884aee4381523` |

The full [postprocessor identity receipt](tool-validation/postprocessor-identity.json) is copied into the registration. Root created its commit-named local release from `git archive` of exactly the streaming script and unchanged adjacent dependency, with no mutable-working-tree source. Both arms use this same local postprocessor/runtime identity. The streaming entry point refuses a dependency whose SHA differs from the frozen legacy source.

The [validation receipt](../tool-validation/streaming-analyzer-validation.json) and [exact subprocess output](../tool-validation/streaming-analyzer-validation.log) record **15 passing focused tests** and three already-completed real 350k trials compared against their frozen summaries. Every trial field agrees, including stable/overload/invalid classifications, failure artifacts, all-offered eligibility/null, UNKNOWN counts, exact nearest-rank percentiles, backlog OLS, raw hashes and configuration fingerprints. The only excluded summary field is the CLI's top-level generation timestamp; no per-trial metric field is excluded. The old analyzer was not rerun on those real trials.

In fresh child processes the complete all-accepted 350k parity case took 6.061 local seconds with peak RSS **80,412,672 bytes (approximately 76.69 MiB)**. The overloaded and canonical-incomplete cases also passed, taking 9.664 and 4.861 seconds respectively. These are local tool validation measurements, not cloud throughput results or a measured old/new memory ratio. The new tool streams rows and computes the raw SHA in the same traversal, stores compact numerical arrays, and sorts each numerical column once. It preserves the legacy all-or-nothing malformed-CSV behavior, row-level partial-error accounting and exact integer/percentile semantics.

A further [23 local controller/identity/cleanup/archive guard tests](tool-validation/preparation-validation.json) passed; their [test log](tool-validation/preparation-tests.log) and [frozen source archive](tool-validation/controller-sources.json) remain separate from performance observations. They do not themselves prove a completed cloud attempt.

The original 26k tools, registered plans, summaries and raw evidence are preserved. Verified semantic parity supports using the new tool for this new cohort; it does not replace or silently recompute the old results. Analysis identity is recorded independently from node/load identity.

## Registered order and assessment rules

The fixed order is:

1. `pc-direct-18000-w128-r1`
2. `pc-multiplexed-18000-w128-r1`
3. `pc-direct-18000-w128-r2`
4. `pc-multiplexed-18000-w128-r2`

Each attempt retains all 350,000 planned arrivals. No result table is populated until that attempt has complete export, configuration/leader checks and a lossless archive. Independent gzip audits will stream each completed archive once, check all 33 columns/identities/timestamps/outcomes/sequence data, and compute compressed and decoded lengths/hashes during the same traversal. The manifest and original analyzer CSV input SHA must agree. Plain CSV is retained locally; committed gzip is lossless rather than a sample. Final/expected canonical core views are compared separately, with per-reply results and asset/order/outbox accounting retained.

Arrival-window goodput counts only confirmations by the end of the planned arrival window. Drain confirmations remain in final correctness totals and conditional latency, but do not increase window goodput. Scheduled-to-confirmed latency includes scheduler and FIFO delay. Initial API RTT, queue delay, sampled backlog, drain, client not-sent, business rejection, server error, initial UNKNOWN and final unresolved are reported separately. A timed-out request stays UNKNOWN until the exact saved identity resolves; an exception is not treated as a business rejection. Not-started records leave execution/response latency fields empty rather than zero.

The stable-window criteria are unchanged: at least 10 seconds; all offered commands accepted and eventually confirmed; zero initial/final UNKNOWN; at least 95% arrival-window goodput; drain no greater than max(100 ms, 1% of the arrival window); bounded second-half fitted backlog growth no greater than max(2 commands, 1% of arrivals); valid generator timing, canonical state, fixed leader/term and complete source/configuration evidence. At this rate the drain limit is approximately **194.444 ms** and the backlog-growth limit **3,500 commands**. There is no configured latency SLO. Any missing validation invalidates the observation; short windows are not classified as measured stability or overload.

Conditional p99 is never substituted for all-offered p99. If any offer is dropped, rejected, errored or unresolved, all-offered accepted p99 remains null. A flat bounded backlog can mean queue saturation and admission drops, so it cannot alone prove stability. Invalid and failed attempts remain visible; their client-reported confirmations are not validated business throughput. Percentiles are not averaged across attempts.

Resource observations will use whole-collection arrival-window interiors, monotonic durations and owned process/TID/inode/FD lifecycle checks. Sampling gaps, scan caps and errors remain explicit. Archive write-path wall time includes write/force/descheduling, not pure fsync latency. This finite client-plus-cluster path, including its fixed logical request window, cannot by itself establish sustained production capacity, a universal matching-engine ceiling or a unique bottleneck. Canonical core/outbox validation in these runs is not a full replicated Aeron checkpoint/restart experiment.

## Completed observations — all four registered attempts retained

| Attempt | Actual physical sessions | Final accepted / planned | Window confirmations / goodput | Conditional scheduled p99 | All-offered p99 | Client not sent / initial UNKNOWN / unresolved | Drain | Classification |
|---|---:|---|---|---:|---|---|---:|---|
| [A direct r1](direct/runs/pc-direct-18000-w128-r1/trial.json) | 128 | 290,496 / 350,000 | 282,224 / **14,514.377143/s** | **645.284806 ms** | null | 59,504 / 0 / 0 | 526.087470 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |
| [B multiplexed r1](multiplexed/runs/pc-multiplexed-18000-w128-r1/trial.json) | 1 | 297,040 / 350,000 | 288,764 / **14,850.720000/s** | **621.433688 ms** | null | 52,960 / 0 / 0 | 542.329292 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |
| [A direct r2](direct/runs/pc-direct-18000-w128-r2/trial.json) | 128 | 296,044 / 350,000 | 287,768 / **14,799.497143/s** | **628.042642 ms** | null | 53,956 / 0 / 0 | 585.516888 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |
| [B multiplexed r2](multiplexed/runs/pc-multiplexed-18000-w128-r2/trial.json) | 1 | 230,375 / 350,000 | 222,073 / **11,420.897143/s** | **1,101.151558 ms** | null | 119,625 / 0 / 0 | 708.708061 ms | `OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT` |

This first direct point is valid and canonically correct, with zero business rejection/server error/UNKNOWN and all 290,496 started commands accepted. Its 59,504 unsent commands are explicit client FIFO admission drops. Only 80.6354% of offered arrivals confirmed during the arrival window; 8,272 more confirmations completed during drain and are excluded from window goodput. All-offered p99 remains null. Both the 95% window-goodput criterion and approximately 194.444-ms drain bound fail, so this cannot establish stable 18k capacity.

The [immutable per-attempt analysis summary](direct/runs/pc-direct-18000-w128-r1/analysis-summary.json) has SHA-256 **`ac1a2c00d2590ff9c654674995ff0ad9857944a2caab0ec0fc8c6d4bc5bc5c46`**. The [postprocessing receipt](direct/runs/pc-direct-18000-w128-r1/postprocess.json) records the actual isolated streaming argv, exit 0, unchanged input hashes and copied output hashes. The independent check verified its full postprocessor object against the registered plan, `analysisIdentitySha256` **`31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f`**, the two actual isolated-release script bytes/SHA values and recorded `-I -B` invocation. Analysis was not rerun for this audit. Node/load metadata remains the common e57 artifact, with direct/128 physical sessions/shared-one-driver/NAK1000 unchanged.

### A direct r1 independent full-gzip and canonical audit

The independent audit streamed this completed gzip once in 5.12 local seconds, computing both compressed and decoded byte hashes during that traversal. All **350,000 records / 33 columns** were checked for sequential arrival index, absolute planned offset, worker/account/producer/request/client-order identity, timestamp and latency algebra, outcome shape, saved leader IDs, distinct contiguous executed command sequences and per-fresh-reply event/market sequences. Every accepted request has one trade; there are no replayed replies or recorded accepted internal resends. Queue-full rows leave every unstarted execution/response field empty rather than contributing zero latency.

| Audit input/output | Exact verified value |
|---|---|
| [Lossless gzip](direct/runs/pc-direct-18000-w128-r1/arrivals.csv.gz) | 20,667,861 bytes; SHA-256 `424fd1ea9c81fef277a9dbca31efc65f762bd09899beec4b1b03f85729d77b07` |
| Decoded original CSV | 91,327,457 bytes; SHA-256 `d698eebd3334cd0c6cb976ff14a367f75de9cf9c044284e467c8a87bb310f283` |
| [Archive manifest](direct/runs/pc-direct-18000-w128-r1/arrivals-archive.json) | Both lengths/hashes match, including immutable analysis input SHA and pre-analysis input SHA |
| Final canonical core view vs replay | 51,100,267 bytes, compared block for block; SHA-256 `faa99a9e6032be71f528e65d6cf03934e0bdf2f7fa0dc09471b5fd2632a4edad` |
| [Final accounting/result](direct/runs/pc-direct-18000-w128-r1/result.json) | 290,597 retained orders; 581,259 pending outbox events; 100,000 cached results; 195 producers |
| [Configuration verification](direct/runs/pc-direct-18000-w128-r1/configuration-verification.json) | All eight named raw inputs independently rehashed; actual source/transport/configuration metadata agree |
| [Fixed leader/term](direct/runs/pc-direct-18000-w128-r1/fixed-leader-check.json) | Leader 0, pre/post and observed term 0; checker coverage limitations retained |
| [Owned cleanup](direct/runs/pc-direct-18000-w128-r1/all-owned-processes-stopped.json) | Terminal cleanup retained before the next registered attempt |

Exact conditional p99 was independently recomputed with bounded integer latency storage and most-significant-byte radix selection, without sorting the full row table, decompressing twice or rerunning the analyzer. Canonical/per-reply/conservation checks remain same-engine replay plus separate account/order/outbox formulas, not an independent engine algorithm or cloud replicated-checkpoint/restart proof. Final validation lasted **149.985 seconds** outside measurement.

### Logical slot and queue observations

The initial API mean was **8.790072 ms**, with p99 **14.307085 ms**; queue-delay p99 was **636.080649 ms**. Clipping actual execution-to-confirmation intervals to the arrival window gives **127.957 of 128 logical slots occupied on average (99.9661%)**. Individual workers accepted 2,241–2,286 commands and recorded 449–493 queue-full drops; their mean API times were 8.729920–8.898360 ms, with occupied-window fractions 99.9410–99.9875%.

The sampled queue/in-flight/outstanding peaks were **8,170 / 128 / 8,298**. The fitted second-half outstanding growth was zero while bounded queues rejected 59,504 arrivals, so a flat slope is not stability. These facts describe the finite synchronous client-plus-cluster window and its queueing. They do not isolate a server ceiling or justify a conclusion about the multiplexed arm before its completed evidence is audited. Resource attribution will be retained separately after the registered matrix.

### B multiplexed r1 audit and slot observations

B r1 is also valid/canonical but overloaded, with all 297,040 started commands accepted, zero rejection/server error/UNKNOWN, and **52,960 queue-full admission drops**. There are 288,764 window confirmations and 8,276 confirmations in drain; the 542.329-ms drain exceeds the approximately 194.444-ms bound, and all-offered accepted p99 is null. This is the first B repetition; the slower second repetition is retained below, so this point is not selected as representative capacity.

Its [immutable per-attempt summary](multiplexed/runs/pc-multiplexed-18000-w128-r1/analysis-summary.json) SHA-256 is **`31acfb82cf53cd6ba767c06dc56d68ada82a1f401b1b7f6f278da5fbf1df25fb`**. The [postprocessing receipt](multiplexed/runs/pc-multiplexed-18000-w128-r1/postprocess.json) and actual isolated-release script hashes independently match the same registered analysis identity `31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f`; no analyzer was rerun. Common e57 node/load, shared-one-driver/multiplexed-one-session/W128/Q64/NAK1000 metadata and all eight configuration inputs agree, with leader 0 / term 0 and complete owned cleanup retained.

The independent single-pass gzip audit took 21.35 local seconds. It checked all 350,000 rows and 33 columns with the same full identity/timestamp/outcome/unique-sequence/one-trade/fresh-reply rules as A1, including empty unstarted drop fields. No replayed replies or recorded accepted internal resends appear. The elapsed local audit time is not cloud service latency.

| B multiplexed r1 evidence | Exact verified value |
|---|---|
| [Lossless gzip](multiplexed/runs/pc-multiplexed-18000-w128-r1/arrivals.csv.gz) | 20,485,548 bytes; SHA-256 `f43badf46dab3171086af6f529f7726e222dbab5c3cd0956c6dd425489d95a7f` |
| Decoded original CSV | 92,095,008 bytes; SHA-256 `b3c54bfcfd6ddd955368db398e9f367e9698ddd813cd223e8bd4da53c9549801` |
| [Archive manifest](multiplexed/runs/pc-multiplexed-18000-w128-r1/arrivals-archive.json) | Both lengths/hashes agree with the manifest and immutable analysis input SHA |
| Final canonical view vs replay | 51,822,919 bytes, block-for-block equality; SHA-256 `7a656c2539e706827f7a8d3e09ad232b52daa6986f359f76484c0c5febf55ed2` |
| [Final accounting/result](multiplexed/runs/pc-multiplexed-18000-w128-r1/result.json) | 297,141 retained orders; 594,347 pending outbox events; 100,000 cached results; 195 producers |

The independently recomputed API mean is **8.604776 ms** and initial API p99 **13.516352 ms**, versus queue-delay p99 **612.222268 ms**. Arrival-window busy intervals occupy a mean **127.948 / 128 logical slots (99.9591%)**. Per-worker accepted counts are 2,302–2,329, drops 406–432, API means 8.574997–8.676176 ms and occupied-window fractions 99.9243–99.9814%. Sampled peak queue/in-flight/outstanding is **8,190 / 128 / 8,318**, with fitted growth **1.145590 commands**. This small growth does not undo admission loss. Final validation takes **152.737 seconds** outside measurement. The full A/B interpretation retains the second repetition and its slowdown; formal resource observations are kept separate.

### A direct r2 audit and slot observations

The second direct repetition is also valid/canonical and overloaded: **296,044 accepted, 53,956 queue-full not-sent, zero rejection/server error/initial or final UNKNOWN**. It confirms 287,768 during the arrival window, with 8,276 more during drain. The 585.517-ms drain exceeds the unchanged bound and all-offered p99 remains null. Both direct repetitions fail the stable-window criteria at this rate; both multiplexed repetitions also fail, as retained individually.

The [immutable A r2 summary](direct/runs/pc-direct-18000-w128-r2/analysis-summary.json) SHA-256 is **`6daf9d77ca56be86a4dec3950ee7fffae255492d7d940e73de929f720d414bfc`**. Its [postprocessing receipt](direct/runs/pc-direct-18000-w128-r2/postprocess.json), actual two-script release hashes and immutable outputs match registered analysis identity `31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f`. Common e57 node/load, direct/128 sessions/shared-one-driver/W128/Q64/NAK1000, eight rehashed configuration inputs and fixed leader 0 / term 0 all agree. Analysis was not rerun by the independent audit.

One independent gzip traversal took 9.34 local seconds and checked all **350,000 rows / 33 columns**, every original identity, planned/timestamp/latency relation, distinct continuous executed sequence, fresh one-trade reply and empty unstarted drop field. There are no recorded accepted internal resends or replayed replies. The compressed/decompressed byte counts and hashes match the manifest, pre-analysis input and saved immutable analyzer input.

| A direct r2 evidence | Exact verified value |
|---|---|
| [Lossless gzip](direct/runs/pc-direct-18000-w128-r2/arrivals.csv.gz) | 21,012,534 bytes; SHA-256 `60aad4d8d0aa418eaa93405a5be078dc3c10c5abdc20faa7963624decbe8153b` |
| Decoded original CSV | 92,041,991 bytes; SHA-256 `7c5e9909ad5a87b4142921b806751b4da25a7719cab4e0e8e0bc397e1062c501` |
| [Archive manifest](direct/runs/pc-direct-18000-w128-r2/arrivals-archive.json) | Exact byte/hash equality, including immutable analyzer SHA |
| Final canonical view vs replay | 51,712,903 bytes, block-for-block equality; SHA-256 `7aa10d3dfafb361596e63c5ab3bdd364471fcc402197eb2c52b65f9e255f85d6` |
| [Final accounting/result](direct/runs/pc-direct-18000-w128-r2/result.json) | 296,145 retained orders; 592,355 pending outbox events; 100,000 cached results; 195 producers |

API mean is **8.640945 ms**, initial API p99 **14.394286 ms**, and queue-delay p99 **619.109443 ms**. Average logical slot occupancy is **127.953 / 128 (99.9634%)**. Worker accepted counts range 2,298–2,329, drops 406–436, API means 8.578923–8.699297 ms and occupied-window fractions 99.9046–99.9864%. Sampled peak queue/in-flight/outstanding is **8,159 / 128 / 8,287**, with fitted growth zero despite admission loss. Canonical validation lasts **159.115 seconds** outside measurement. The final multiplexed attempt is retained below; formal resource attribution is separate from these business/arrival audits.

### B multiplexed r2 audit — slowdown retained

The final registered attempt is valid/canonical, with **230,375 accepted, 119,625 queue-full not-sent and zero rejection/server error/UNKNOWN**. It confirms only **222,073** during the arrival window, giving **11,420.897143/s**; 8,302 further confirmations complete during drain. Conditional scheduled p99 is **1,101.151558 ms**, all-offered p99 is null and drain is **708.708061 ms**. This is substantially worse than the first B run. It is retained without retry, replacement, deadline extension or exclusion.

The [immutable B r2 summary](multiplexed/runs/pc-multiplexed-18000-w128-r2/analysis-summary.json) SHA-256 is **`60fd2bfab06eab2acb6e0742984e5185576de932fcb9be18bc51949f14e64509`**. The [postprocessing receipt](multiplexed/runs/pc-multiplexed-18000-w128-r2/postprocess.json), source bytes and output snapshots match the same registered `31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f` analysis identity, with common e57 node/load, one shared driver/one physical multiplexed session, W128/Q64/NAK1000, eight rehashed configuration inputs and leader 0 / term 0. No analyzer was rerun by the independent audit.

One independent gzip pass takes **5.62 local seconds** and verifies every one of the 350,000 records and 33 columns, all original identities/timestamps/latency equations, unique continuous executed result sequences, one-trade fresh replies, and empty unstarted response fields. There are zero replayed replies and recorded accepted internal resends. Compressed and decoded byte hashes agree with the archive manifest plus pre-analysis and immutable analyzer input hashes.

| B multiplexed r2 evidence | Exact verified value |
|---|---|
| [Lossless gzip](multiplexed/runs/pc-multiplexed-18000-w128-r2/arrivals.csv.gz) | 17,877,671 bytes; SHA-256 `14fb62d53d7be1037bf667d27b6d851637321001e7a2179b9871594c051f1d2e` |
| Decoded original CSV | 84,934,745 bytes; SHA-256 `07359bbcca55b85b5ed910d73c1306eefcfde4154bd9f0b759974c5fc81b6a6e` |
| [Archive manifest](multiplexed/runs/pc-multiplexed-18000-w128-r2/arrivals-archive.json) | Exact byte/hash equality, including immutable analyzer SHA |
| Final canonical view vs replay | 44,450,154 bytes, block-for-block equality; SHA-256 `da7ef648fbcd9107f223ecc1ef803564b577637cf04a1477277243a0b593dc17` |
| [Final accounting/result](multiplexed/runs/pc-multiplexed-18000-w128-r2/result.json) | 230,476 retained orders; 461,017 pending outbox events; 100,000 cached results; 195 producers |

API mean is **11.182622 ms**, initial API p99 **39.344084 ms** and queue-delay p99 **1,089.954456 ms**. Mean logical slot occupancy remains **127.943 / 128 (99.9558%)**. Worker accepted counts range 1,773–1,816, drops 919–961, API means 11.081857–11.353441 ms and occupied-window fractions 99.9120–99.9850%. Sampled peak queue/in-flight/outstanding is **8,192 / 128 / 8,320**, with fitted growth zero while more than one-third of offered arrivals are not admitted by the full client queue. Canonical validation lasts **143.687 seconds** outside measurement.

The registered [completion timeline](timeline.jsonl) records `pipeline-capacity-matrix-completed` at **00:52:35.191918 UTC**, after all four terminal attempts and complete owned cleanup. The controller exited 0 because the registered attempts and evidence completed; the label is not a stable-capacity pass. The two direct observations give window goodput 14,514–14,799/s and conditional p99 628–645 ms; the two multiplexed observations give 11,421–14,851/s and conditional p99 621–1,101 ms. Tail percentiles are not averaged, and the best multiplexed observation is not used to hide its second-run variability.

The API slowdown appears across the per-worker means rather than only in the admission counter, but these observations do not identify a unique cause. Source/configuration/leader/canonical checks pass and no business effects are lost or duplicated. Formal CPU/socket/CnC/Archive/observer attribution is retained separately below; neither a presumed cause nor repeatable capacity improvement is inferred from these four finite windows. **Stable 18k performance and a universal throughput ceiling remain unestablished.**

## Formal resource and recovery observations

The final [independent attribution report](analysis/attribution-summary.json) is frozen at SHA-256 **`9b0e5671236a1e89c16c4508717fe4be6ab4e695ebf3abc39fe5eb90def1bcab`** (2,861,314 bytes). Its wrapper verifies **169 input/tool hashes**, includes all four requested attempts and preserves every valid/canonical/overloaded classification. It does not rerun the capacity analyzer or replace the per-attempt immutable analysis snapshots. Whole-collection interior selection, process/TID/start-tick/inode/FD ownership, monotonic durations and missing-read accounting remain explicit.

| Recorded formal observation | A direct r1 / r2 | B multiplexed r1 / r2 |
|---|---|---|
| Load JVM CPU, cores | 3.215 / 3.748 | 1.074 / 1.364 |
| Node 0 JVM CPU, cores | 2.537 / 2.630 | 1.268 / 1.112 |
| Node 0 owned UDP sockets / FDs | 134 / 553 | 7 / 45 |
| Load owned UDP sockets / FDs | 129 / 400 | 2 / 19 |

The multiplexed arrangement has lower recorded CPU and fewer descriptors/sockets at the same **offered** rate. Accepted/window throughput differs, especially in B2; these observations must be read with the complete business result table and do not establish equal useful work, stable capacity or a consistent latency advantage. The factor remains physical-session/network-owner/dispatch arrangement, so session count alone is not isolated.

### What the slower B2 observation does and does not show

In the strict approximately 18-second B2 interior, owned UDP socket drop deltas are **zero on node 0, load, node 1 and node 2**. Nevertheless node 0 NAK sent reaches **41,364**, versus **54** in B1; node 1/2 NAK received are **2,103 / 4,318**, with retransmission counts **86 / 148**. This is observed recovery-feedback activity associated with the slower window. Zero matched local socket drops does not locate every possible transport gap, and NAK counters do not uniquely identify a loss location or cause.

B2 node 0 uses **1.112 JVM cores / 1.135 cgroup cores** against quota **5.1**; load uses **1.364 cores**, with total node-2 cgroup CPU **2.252** against quota **23.8**. All cgroup throttle increments are zero. Selected node 0 driver-prefix/consensus/archive/service TIDs use approximately **0.650 / 0.126 / 0.107 / 0.097 cores**; load owner/driver-prefix/java/worker groups use **0.282 / 0.403 / 0.253 / 0.314 cores**. Raw thread-name attribution retains truncation/ownership limits; these observations do not imply all roles were running on separate dedicated cores.

Per-TID cumulative runqueue waits increase from B1 to B2 on node 0: driver **8.83 → 300.84 ms**, consensus **12.72 → 496.79 ms**, Archive **88.81 → 394.43 ms**, service **7.26 → 403.14 ms**, while the load owner's **3.20 → 3.36 ms** is similar. Zero cgroup throttling therefore does not exclude observed scheduling wait. These are cumulative approximately 18-second observations, roughly 1.7–2.8% of the B2 window for the listed node roles, not per-request p99 pause distributions and not proof of a unique host-scheduling cause.

Node 0 Archive write-path wall-time ratio is **0.106 in B2 versus 0.116 in B1**, with approximately **39.19 MB versus 51.30 MB** recorded in those selected scopes; B2 follower ratios are approximately **0.917 / 0.650**. Those wall times include write, force and descheduling and cannot be read as pure fsync time. Sampled node 0 append-minus-commit reaches **24 KiB**, with **19,968 bytes** at the selected-window endpoint; append-minus-record reaches **5,376 bytes**; commit-minus-service reaches **22,272 bytes** and ends at zero. Positions are non-atomic one-second samples rather than exact simultaneous lag or final terminal state. Final canonical correctness and complete accepted-command accounting remain verified separately.

One A1 load thread scan has a partial/read-failure observation, which is retained; the other selected scopes report no read errors and none hit scan caps. The matched log-pattern count is zero. Missing scans are not filled with zero CPU/socket activity. Together these observations preserve a real B2 slowdown with recovery and scheduling signals, while leaving its unique cause unresolved. **The repeated 18k experiment fails the stable-window criteria in both arms; it supports no higher stable rate, consistent p99 gain or universal engine ceiling.**

### Attribution-tool gate and unchanged evidence

An initial local attribution invocation stopped at the frozen controller-archive schema gate **before metric scanning began**: the older reader expected `files` while this registered source archive uses `controllers`. The [original gate-failure receipt](tool-validation/attribution-gate-failure.json) retains exit 1 and its traceback; it is a tooling compatibility failure, not a failed cloud load or permission to discard a benchmark point. No old source, plan, source archive or raw file was edited.

A separately identified [schema adapter](../idle/tool-validation/summarize-attribution-schema-adapter.py), SHA-256 **`64d5b9834303a7558dc7a5606977c8491c94cc086630af06e5aafb7d86fcbc1f`**, maps only the source-archive key in memory. Its [validation receipt](../idle/tool-validation/schema-adapter-validation.json) checks the exact six controller keys and three-way equality of registered/archived/computed SHA values, plus the original wrapper's nine frozen dependencies. Genuine missing/extra/changed sources remain rejected. After that metadata-only gate repair, the unique actual formal metrics execution generated the frozen report above. The capacity postprocessor identity remains **31e4…**. This schema-gate repair invoked no capacity analyzer or benchmark and overwrote no earlier frozen report.

## Lifecycle and budget

The registration preserves the USD 20 project limit, USD 2 recovery reserve and existing three Pods, with no new resources. At registration the launch-time estimate was USD 10.7757 accrued and USD 14.0757 including the matrix/recovery reserves; this is a historical conservative estimate rather than the reconciled bill. Budget and local free-space guards run before further attempts.

The plan pins all previous formal input/summary/archive/timeline/cleanup hashes and verifies recorded old owned identities before execution. Each new attempt stops only its identity-bound load/controller/observer/node processes, confirms cleanup and port release, and preserves all available raw evidence before continuing. PID reuse, missing ownership/cleanup, configuration/source/leader drift, unexpected business mismatch or incomplete export halts the matrix. Whole-process and canonical-validation limits remain 600 seconds in both arms. No deadline extension, hidden reissue, extra unregistered point or changed rate is allowed under these trial IDs.

Only the exact typed canonical-incomplete UNKNOWN guard may continue after complete raw archival, configuration-only verification and owned cleanup; it remains invalid and never creates a successful result. This controller does not automatically replay unresolved business identities. The report will be updated from actual completed receipts, not from preliminary messages during a live export.
