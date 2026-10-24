# CPU chunk comparison: round 1 independently closed

The first ordered 3072/6144-byte chunk pair completed at `2026-10-24T06:28:09.052916Z`. One explicit read-only SSH collection and first local native/raw audits passed. Both arms confirm all 6400 unique synthetic load orders, but both still have replies outstanding at the end of their 12.8-second arrival window: these are **valid finite overload observations**, not sustained-capacity measurements. Round2 and an independently root-approved gate are separate actions.

| Independently decoded result | Chunk3072 | Chunk6144 |
|---|---:|---:|
| Offered arrivals | 6400 at500/s | 6400 at500/s |
| Eventually confirmed distinct accepted load orders | 6400 | 6400 |
| Accepted replies within12.8s | 3069 | 6141 |
| Fixed-window goodput | 239.765625/s | 479.765625/s |
| All-arrival nearest-rank p99 | 7.368829634s | 4.888360956s |
| Last-reply drain beyond arrival window, raw | 7.012967443s | 4.408074524s |
| Final-maintenance end beyond window, raw | 7.611589788s | 4.865718733s |
| Total source drain, reported/ordering checked | 7.611856655s | 4.866026470s |
| notSent / rejected / initial UNKNOWN / final UNKNOWN | 0 /0 /0 /0 | 0 /0 /0 /0 |
| Scheduler maximum lateness | 1.104386ms | 2.926055ms |
| Sampled external backlog high water | 2989 | 2486 |
| Maintenance cycles / logical RPCs | 3 /1785 | 3 /1298 |
| ArchiveChunk / FetchEvents calls | 975 /801 | 488 /801 |
| Three maintenance-cycle duration sum | 13.978515761s | 10.321075933s |

The source clock continues through maintenance. Raw receipts independently count **3327** released arrivals in control and **2490** in the6144 arm; the latter's second cycle overlaps another255 arrivals. P99 begins at scheduled arrival, includes queue/maintenance wait and ends at full reply completion. The total source terminal timestamp is not separately logged, so that drain remains labelled as reported rather than independently timestamped. No result from this first pair authorizes a performance promotion.

## Frozen runtime and exact proof scope

Source commit is `e3c4885a8854c3edfbfdea4848633efc75951894`; release SHA is `5d8bd210f5f7e78cb421a1dc80f3367ecee07e90bcba9a54c6c0a88db05a92c7`. The actual four archived JARs and every ZIP entry are verified. Actual type-source hashing reproduces `68943a1eb48e2da1d4ef99d10b2717b112b5e698e6c87db2fa9c8b25ae5dbd14`, with MatchingEngine from core and DirectBuffer from Aeron. Both arms use the same artifact, business batch4, W128/Q64, pending128, event page16, ports42000, leader0/term0, sync2, MTU1248, prepared-prefix cache and identical common finite operational limits. Exact process PID/startTicks/argv/classpaths cover six nodes and the parent. Six raw node stop reports are distinguished from successful normal parent return/reap/final-absence source/result evidence.

`collection-r1/full-closed-round.tar.gz` is32,347,909B, SHA `5bb0be214820ce7f4ce26ab1e29be8ec719d4a9e82833fb94e7466c04df0eacc`. Its209files/31directories preserve2,512,561,132 logical bytes: the full closed selected JOB and exactly22 allowed source/execution metadata files. PREP was never recursively archived. `remote-inventory.stdout.json` records all SHA/bytes/modes/uid/gid and exact directory closure, including empty directories; its SHA is `b86d8866879fd84a2fe7426e5556fdee56f39c9ff8ce83e17dbd416132f1698d`.

The separately retained nested `pilot-after-clean-stop.tar.gz` is19,968,022B, SHA `13a0331411578db2e26a4067cfebd269f0b11f10e1d7f6caceec41710fbbce3d`. Streaming checks verify every159file/27directory member,2,487,399,571 logical bytes, recorded60,174,336 allocated bytes, and exact binding to the outer rows. Sparse segments were never fully extracted. Canonical nested inventory SHA is `e8a75e84260de571993502870c2325a822d880d67debd259ec1520d76848e0b5`. Outer and nested inventories intentionally overlap because the full closed job retains both native tree and its archive.

The native audit reconciles the frozen original57-file three-node state and989-file PG baseline to unchanged wrapper before/after full checks. The collector does not claim a separate live rehash of those protected originals, nor independent physical storage survival. It launched no application or PG, sent no signal, purchased no resource and deleted nothing.

## Raw checks and actual receiver evidence

`RAW_AUDIT_INPUTS.json` binds all65 input files, SHA `f57097a272f7478dda4789303f34b1a6d6b3d47b0befa4dc6d6eb4d29d4ba65a`. The auditor verifies every planned identity/producer sequence, nested batch request/reply/order ID, physical index/offer row and logical RPC correlation/kind/timing. Requested chunk/event CSV columns equal actual wire requests. It reconstructs exact chunk offsets and full payload SHA, compares immutable archive/event writer bytes to raw transfers, closes event continuity and exact ACK targets. RPC counts derive from actual complete descriptors/event pages; prospective975/488 is only a comparison. Safe payload-size differences are retained: cycle2 archive1,437,276B versus1,437,510B and final121,792B versus121,558B; both complete prefixes verify.

Actual receiver Images7/11 have16MiB terms, MTU1248 and derived maximum2,097,152B. Runtime source validates actual Header/Image association per callback, then preserves bounded ever-seen geometry, active-set/lifecycle events and per-Image aggregate counters. The raw tape has no Image ID. Independent audit therefore verifies lifecycle progression, geometry, counter totals and maximum sizes, **without claiming independently reconstructed per-reply Image mapping**. Attested/raw reply totals are5751/5599; observed largest application replies are3629/6701B. The generic complete supported Chunk bound remains6919+32=6951B, distinct from the6727B actual-workload plan witness. Receiver geometry comes from actual Image records, not ingress defaults.

All44 bounded telemetry samples close, with71 explicitly unavailable/exited records retained. CPU/RSS/I/O are sampled and UTC phases are coarse; Java/Python monotonic clock alignment is unvalidated. RPC timings include caller/transport/server/record/quorum/reply/evidence waits and do not isolate fsync or network latency. Three JVM nodes share one host's CPU/network/storage; no independent-host or100M/zero-latency claim follows.

## Review handoff and preparation history

`native-audit-r1/result.json` SHA is `6a764f7b28e9a6417437aaac3c5190bf0f819bb85f873bb3c625efcf5b3c5794`; `raw-audit-r1/result.json` SHA is `9840f8f79c794c99619d0d7bf6ab04bb67c0753e34dba2f5569746f57316826e`. `local-completion-r1/LOCAL_COLLECTION_COMPLETE.json` SHA is `8cb74c169eaf4f3615e071e6b7d9b04c64b49a99a5aad64681bea0ec64232c15`. It supersedes the collection-only receipt's pending marker. The neighboring `ROOT_GATE_CANDIDATE_NOT_APPROVED.json` SHA is `1c0123c864d6dcc959b6c8b812eec2b879b9ef450c54c15fb9a35f37d2b64ebf`; its approval assertions deliberately remain false. Root independently reviews/signs/uploads a different approved gate before any round2 action.

`local-preparation` preserves the verified49-file source-only collector preparation (`e197903da92dfd352ee0f34b00ccc6a0ceede0074a665e6a04f277c165f134d0`), all local guard/preparation failures and superseded draft, and the new executed auditor version. The new version was prepared before collection solely to derive actual RPC inventory without rejecting safe prefix-size variation. Every actual collection/audit/finalizer invocation has exact source/argv/exit/log receipts. No actual cloud collection or audit failure was retried or hidden. Upstream candidate build/native failures are separately retained by the candidate preparation proof; this directory does not replace those records.
