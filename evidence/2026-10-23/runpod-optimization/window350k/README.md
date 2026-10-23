# Larger-fixture concurrency-window comparison

**The full-scale pilot passed; the formal concurrency comparison is registered. No capacity improvement is claimed yet.** The pilot completed 350,000 arrivals at 10,000/s over 35 seconds with 128 synchronous workers, including canonical core-state and separate outbox checks, within the unchanged 600-second whole-process deadline and 2 GiB heaps. It is a full 350k-command cloud workload, not a 10,000-command smoke. This establishes fixture feasibility for the comparison; it does not establish a throughput ceiling or a full replicated-checkpoint cloud restart.

## New configuration identity

The [registered pilot plan](pilot-plan.json) pins node and load to the same new committed source. Older 190k-fixture results remain independently reviewable and are not substituted for new controls.

| Component | Identity / value |
|---|---|
| Node and load source | `52fbf7fa46ed274891a2bbf0d9fba9d87456d1f5` |
| Common bundle SHA-256 | `cfed7303d46fd69e65f190022cecacfcf4135a7c7732ef6fc20a90182bb71cd6` |
| Attribution observer identity | `b51226cc3902e77e457836e2ea2545b71fe7b1722caa7da9ee0630f118aa5dee` |
| Actual socket-buffer probe SHA-256 | `29eaef020c644e9f64384c0b1773a5b4ede25326552b2cf6c68bf61799ebaf50` |
| Lossless arrival-archive tool SHA-256 | `9e35dd40dc2ec7ea6403e287fe988015f7240dcfcd9587f5914be401c352020b` |
| Workload / node state profile | `extended-350k-256` / `capacity-350k-v1` |
| Maximum measured arrivals | 350,000 |
| Retained-order / global cached-result limit | 360,000 / 100,000 |
| Per-producer result cache | 1,024 |
| Pending-outbox capacity | 800,000 |
| Full replicated-checkpoint bound | 536,870,912 bytes, 512 MiB |
| Maximum cluster sessions in every comparison group | 256 |
| Member / load heap | 2 GiB / 2 GiB |

The [node release](node-release.json), [artifact manifest](node-deployment-manifest.json), transfer receipts, actual process arguments/startup logs and configuration verification establish the execution identity. The [committed-source validation receipt](tool-validation/java-tests.json) records 117 tests, zero failures/skips and exit code 0. Small local fixture/boundary/restore tests do not prove the full 350k cloud terminal state's memory or validation time; those require the completed cloud pilot. Independent inspection of the deployed 33e6 and 52fb archives finds all 27 core `.class` files byte-identical; whole-JAR hashes differ, so class-byte equality is stated separately from archive identity.

The [pilot campaign](pilot/campaign.json) fixes node MediaDriver `SHARED`, Archive `SHARED`, leader 0, sync level 2, Aeron 1.53.3, MTU 1248, a 131,072-byte node receive request, unchanged send request and identical independent driver-role `BackoffIdleStrategy(10,5,1000,1000000)` instances. The load keeps one shared client MediaDriver and independent Aeron clients/sessions/workers, each with one synchronous in-flight command. Gateway, PostgreSQL projection and subscriber fanout are excluded, and the load host still shares member 2. No matching rule or durability setting is weakened.

Preparation remains fixed across intended worker groups: 64 buyer accounts funded with 1,900,000,000 quote units each, a 380,000-lot maker and 100 excluded warmup IOC buys. Every measured accepted command buys one lot and produces one trade. The larger fixture changes declared state limits, not that business workload. The pilot established the prepared canonical core SHA-256 `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4` from its complete 44,909-byte [prepared snapshot](pilot/runs/w-pilot-10000-w128/prepared-snapshot.bin). The [formal plan](plan.json) pins this digest. The old 190k digest is not reused.

## Pilot, comparison factor and stopping rule

The registered pilot is `w-pilot-10000-w128`: 10,000 arrivals/s × 35 seconds = 350,000 scheduled arrivals, 128 workers and 64 FIFO slots per worker. The whole load/validation process has a 600-second outer deadline; validation exchanges retain the same 600-second limit. A timeout/failure is preserved and is not silently rerun under a longer deadline. Two 12-second session-reclamation waits, connection setup, canonical replay and snapshot checks remain outside the arrival window. The load client's `readSnapshot` freezes and reads the canonical MatchingEngine core state. Outbox watermarks/counts are checked separately. That path alone does not demonstrate a full replicated core-plus-outbox checkpoint encode/decode or a cloud restart from such a checkpoint; the phase label `full-checkpoint-pilot` is not substituted for those missing operations.

After the pilot completed, the [formal plan](plan.json) was registered at 22:44:54 UTC. It uses 350,000 arrivals at 26,000/s, an exact integer-nanosecond window of 13.461538461 seconds, alternating 128/256/128/256 workers. Both groups use the same new node/load/profile, 256 maximum sessions and the pilot preparation digest. Registration is not a measured result; completed formal rounds are reported below without replacing failed or invalid rounds.

| Registered worker configuration | Maximum synchronous requests in flight | FIFO slots per worker | Total FIFO waiting slots |
|---|---:|---:|---:|
| 128 workers | 128 | 64 | 8,192 |
| 256 workers | 256 | 64 | 16,384 |

The factor is the complete concurrency configuration: service slots, client/session/producer count and total FIFO capacity change together. It is not a queue-independent test. Less client admission loss alone could reflect more waiting capacity; it cannot establish higher throughput. In-window accepted goodput, scheduled-to-confirmed p99, backlog growth and drain must distinguish faster completion from buffered work. Account assignment remains `worker % 64`; independent business requests remain one-lot IOC buys without place/cancel dependencies.

Absolute arrival scheduling, round-robin assignment, 2-second initial execute timeout, 30-second drain, 20 ms scheduler-lateness validity limit, constructor concurrency eight and same-identity unknown resolution remain in force. Unknown does not mean rejected; unresolved identities prevent producer advancement. Every offered arrival, including invalid/failure rounds, must remain accounted for. The existing stability criteria remain at least ten seconds of arrivals, complete source/configuration/state/leader validation, >=95% in-window accepted goodput, no admission loss/rejection/error/unknown, bounded fitted backlog growth and bounded drain. There is no implicit latency SLO, and no finite window proves indefinite capacity.

## Lossless raw evidence

Raw `arrivals.csv` stays available locally. The scoped Git representation is the complete `arrivals.csv.gz` plus `arrivals-archive.json`; it is not a sample, selected subset or changed schema. The [archive-policy receipt](pilot/campaign.json) records a 256 MiB decoded-byte bound and forbids direct staging of CSV at or above 100 MiB. Compression is deterministic gzip with empty embedded filename, timestamp zero and compression level nine. Analysis must establish the original input SHA before archiving; invalid/failure rows are retained too.

The [independent archive round-trip receipt](tool-validation/arrival-archive-real-roundtrip.json) passes 13 tool tests and verifies a complete 20,000-row synthetic source through archive, restoration and already-present-file validation, without changing that source. This validates the tool path but is not proof of any future 350k archive. Each new run must independently verify compressed SHA/size, decompressed SHA/size, byte identity with the local raw CSV and immutable analyzer input digest, exact header/column structure, sequential indices and all 350,000 data rows. No omitted columns, sampled rows or regenerated substitute requests are acceptable.

For a fresh clone, `python3 scripts/archive-capacity-arrivals.py restore RUN_DIR` restores the exact ignored local CSV after checking its manifest; an existing mismatched file must not be overwritten. Reviewers can also stream the gzip directly. The report's independent audit streams all decoded rows to recompute outcomes, in-window goodput, nearest-rank scheduled p99, initial API RTT and execution-through-resolution worker-slot occupancy. Missing confirmations receive no invented zero latency. If any offered arrival is dropped/rejected/errored/unresolved, returned-command p99 is conditional and all-offered accepted p99 remains null. Drain confirmations cannot inflate arrival-window goodput.

The [prelaunch sequencing guard](tool-validation/prelaunch-guard.json) preserves an initial refusal to register before asynchronous upload verification was present. It created no trial and submitted zero arrivals; it is neither a cloud benchmark failure nor a hidden rerun.

## Completed observations

| Run | Arrivals / workers | Arrival window | In-window accepted / s | Scheduled-to-confirmed p99 | Client not sent / initial unknown / unresolved | Drain | Classification |
|---|---:|---:|---:|---:|---:|---:|---|
| [Pilot 10k/s](pilot/runs/w-pilot-10000-w128/result.json) | 350,000 / 128 | 35 s | 349,933 / 9,998.085714 | 38.016316 ms | 0 / 0 / 0 | 6.901085 ms | Valid; observed stable window |

The [pilot analysis](pilot/analysis/summary.json) has every validation and stability check true: no generator timing violation, admission loss, rejection, server error or unknown; 99.9809% in-window goodput; second-half fitted backlog growth zero; and drain 6.901085 ms against its 350 ms bound. Sampled outstanding peak was 484, including sampled FIFO peak 356 and maximum 128 in flight. These are non-atomic 1 Hz observations, not an instantaneous burst maximum. All 350,000 arrivals eventually returned accepted, so this pilot's all-offered accepted p99 is defined and equals the conditional accepted p99. Sixty-seven responses arrived during drain and do not inflate in-window goodput. Initial API p99 was 13.433560 ms and FIFO-delay p99 25.180325 ms; neither replaces scheduled-to-confirmed p99.

Independent streaming audit of the actual archived CSV verifies all 350,000 rows and all 33 original columns, contiguous indices, round-robin workers, no missing/extra fields, no duplicate producer/request identities, and distinct command sequences covering 168 through 350,167. Every response has one trade, a fresh result, one initial attempt and leader 0. Each worker handles 2,734–2,735 commands. Recomputed nearest-rank p99 and in-window goodput exactly match the analyzer. The final and deterministic-reference canonical core files are both 57,682,277 bytes with SHA-256 `2295cdc63e603aa5a225e6e39fbb9f7316c47daf1faf7b064b8345045dc28c06`; see the [final core](pilot/runs/w-pilot-10000-w128/final-snapshot.bin) and [reference core](pilot/runs/w-pilot-10000-w128/expected-snapshot.bin). The replay uses the same MatchingEngine implementation, not an independently implemented matching algorithm. Supplemental checks cover every reply, asset conservation, per-account balances, remaining maker quantity, event/command/market sequences and outbox count. Final retained orders are 350,101, global cached results 100,000, producers 195 and pending outbox events 700,267, below the declared fixture limits. Completed state validation took 171.667 seconds outside the arrival window; the whole load/validation process exited 0 without increasing its 600-second deadline.

The pilot's mean initial API round trip is 7.228206 ms. Clipping every execute-through-confirmation interval to the arrival window gives average occupancy 72.274966 of 128 synchronous slots, or 56.464817%. Worker mean API times range 7.149561–7.327791 ms, worker occupancy 55.848283–57.246662%, and worker in-window completions 2,733–2,734. The diagnostic ratio `128 / mean API seconds` is 17,708.4/s for this particular load; it is not a capacity forecast because API time changes with load. At this offered rate the worker slots are not continuously occupied. The [fixed-leader check](pilot/runs/w-pilot-10000-w128/fixed-leader-check.json) validates term 0 and leader 0 across all recorded member samples and pre/post membership views, within the check's sampling limits. Before/after actual-socket attestation passes on every member with receive/send kernel buffers 262,144 bytes for the 131,072-byte requests.

| Archived pilot evidence | Bytes | SHA-256 |
|---|---:|---|
| [Complete gzip](pilot/runs/w-pilot-10000-w128/arrivals.csv.gz) | 20,863,855 | `9a203c97fa812c3c525fcb1abaabb3295980cae1559c0806feaef1e478919bf7` |
| Decoded CSV / retained local original | 97,140,996 | `0d3edc29dfcc29ddfee005ef9e2d3c0fcf9ee9603c27c27a39db375cd5a165ff` |

The independently recomputed compressed and decoded hashes/sizes match the [archive manifest](pilot/runs/w-pilot-10000-w128/arrivals-archive.json); decoded bytes match the retained original and the analyzer's immutable input digest. Gzip contains the full CSV rather than a sampled or reduced-column representation. The pilot's raw scope remains canonical core-state validation with separate outbox accounting, not a demonstrated cloud recovery from a full replicated core-plus-outbox checkpoint.

Formal 26k/s results are pending. A higher offered rate, more workers or a larger FIFO is not itself evidence of a higher stable capacity.

The project cloud budget remains USD 20 with no new resources planned. Budget receipts are launch-time/rate estimates, not reconciled provider billing. The separate 100-million cumulative-unique-command, commands-per-second and simultaneous-connection goals remain unverified. Fresh trial lineages intentionally reuse business identities for comparison and cannot be pooled into one globally unique 100-million-command run.
