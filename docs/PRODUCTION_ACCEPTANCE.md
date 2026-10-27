# Production acceptance and trading rollout

This is an implementation and evidence contract, not a production certification. Each gate remains unverified until its linked results pass. No HFT firm endorsement, hard real-time guarantee, zero latency, 100M/s or 100M physical connections is established by this repository.

## Latest evidence: 27 October 2026

### Four outstanding acceptance gaps

These are unresolved delivery gates, not deductions that can be offset by a larger cumulative order count. **None of these four has final acceptance.** The [machine-readable review](../evidence/2026-10-27/production-status-r1/STATUS.json) reproduces three complete cohort summaries and binds its inputs by SHA-256. It is a historical evidence review, not an exhaustive production certification.

| Area | Current status | Evidence boundary | Required next acceptance |
| --- | --- | --- | --- |
| Production latency | **Failed** | The latest replicated 30-minute diagnostic at 100/s has p99 202.051 ms and p99.9 402.291 ms; its source-timing gate also fails. Later 60-second storage ABABs do not replace it. | Preserve the original **p99 ≤5 ms / p99.9 ≤20 ms** target below, with all arrivals, concurrent maintenance, three fixed-config repeats and a qualified load rate. Diagnostic 25/100 ms thresholds are not a relaxed production target. |
| Sustained high throughput | **Unverified** | Two finite 250k/s TCP candidates succeed for five seconds; that path excludes replicated durability. Continuous 100M in-process business lineage also does not prove sustained replicated rate. | Predeclare the high-rate objective, measure the same-artifact sustainable knee, then repeat 30–60 minute replicated sync2 runs with bounded maintenance, complete outcomes and no accumulating backlog. |
| High availability | **Partial; not accepted** | A leader-process fault probe resolves all 128 orders, with a controller-observed 13.828 s progress upper bound. New-VM/disk backup continuation is verified. Neither is a complete production RTO or physical-media-fault proof. | Predeclare RTO/RPO per failure class; cover partition/quorum loss, node loss/rejoin, disk full/I/O errors and independent failure domains under load, with no duplicate settlement or divergent acknowledged state. |
| External venue integration | **Unverified** | Current business simulation trades synthetic local balances. There are no reviewed external venue sandbox order/fill receipts in this evidence set. | Authenticate a chosen paper/testnet venue; reconcile venue order/fill IDs and balances; verify partial-fill/cancel races, reconnect/retry, restart and rate limits. Funded trading is a separate gate with explicit account and limits. |

The [force attribution](FORCE_WAIT_RESULTS.md) identifies off-CPU force tails and sampled XFS synchronization/writeback waits; exact storage/runqueue durations remain unavailable. The [full segment initialization ABAB](RECORDING_INITIALIZATION_RESULTS.md) fails both p99 pair criteria. It stays disabled and does not qualify for a long candidate run. All-request correctness passes do not close latency or availability gates.

Reproduce the status review with:

```sh
python3 scripts/audit-production-status.py --output /tmp/vectormatch-production-status.json
python3 scripts/audit-production-status.py --require-ready
```

The second command intentionally returns **2** for the current reviewed evidence. A successful evidence audit means the recorded results reproduced, not that production acceptance passed. New qualifying experiments require a new review; this snapshot does not auto-certify future code. The four highlighted gaps also do not replace the authentication, risk, history and market-distribution gates below.

Prioritize the durable recording/confirmation boundary first, then repeated healthy long runs, then faults on that qualified configuration. External paper/testnet integration can develop separately, but its receipts cannot substitute for internal capacity or durability evidence. One CPU host remains suitable for implementation and local process-fault tests; it cannot establish independent physical failure domains.

The [mixed-flow same-host comparison](COMMON_ENGINE_COMPARISON_RESULTS.md) closes all 16 five-second arms and checks every original against independent Java/Python business models. VectorMatch passes twice at 50k/s, once at 100k/s and zero times at 250k/s; the exchange-core compatibility cohort passes eight finite gates. All 8.2M planned arrivals are accounted for, including 17,420 not sent, 1,649 business rejections and zero unknowns. Neither callback timing (unequal settlement positions), finite observation duration nor this memory-only path qualifies production or replicated latency. Exact stock-dependency failures and all failed capacity points remain retained.

The [100M anchored campaign](ANCHORED_CONTINUITY_RESULTS_V4.md) completes 100,000,000 accepted orders and 99,999,999 synthetic trades with 23 fully replayed private raw packs, one funding genesis and 22 explicit cold-continuation boundaries. It satisfies the no-reset business-lineage count for this in-process path. It does not establish uninterrupted service uptime or replicated continuous operation.

The [same-artifact 7k/8k overload ABAB](OVERLOAD_RESULTS_V4.md) completes all eight arms with full correctness, independent raw audit and three-node cold restore. All eight finite capacity gates fail. CONTINUE improves goodput in all four pairs, but every arm loses planned arrivals before sending; global accepted-arrival p99 is undefined. A fresh 27-test targeted Linux qualification covers this candidate; it is not a replacement for the earlier full CI28 execution. The source-only bundle is independently compiled and all 364 application class bodies match the candidate.

The [30-minute managed-VM experiment](PHYSICAL_SOAK_RESULTS_20261027.md) uses three distinct provider fault domains and a separate cross-region generator. All 180,000 orders reconcile, but 69,323 scheduler delays violate the 20ms timing bound: it does not qualify sustained latency. [Replacement-VM/disk recovery](SNAPSHOT_RECOVERY_RESULTS_20261027.md) restores exact archived state onto new VMs/disks, replays an original identity and settles a fresh order. All temporary resources are deleted. Deliberate offline volume replacement is not an actual disk-controller failure or power-loss durability test.

The next unresolved integration gate is an anchored replicated service plus bounded streaming source/evidence rotation. The present finite V4 coordinator cannot establish a 30–60 minute high-rate run by increasing a duration constant or adding reset runs. No production or HFT certification follows from these narrower results.

## Earlier evidence: 26 October 2026

CI28 passes556 Java/209 Python tests with zero failures/errors/skips,including11 actual PostgreSQL tests,on the existing one-job CPU runner. All308 application class bodies,454 JDK files,59 observed Linux class origins and1009-file CI evidence are verified. Both CLOSED and BOUNDED_TURN sealed direct-read capacity regressions complete10000 synthetic orders each,physical-order replay,three snapshots and cold restores. Independent audits verify32 bounded turns and300 actual business admissions;CI latency is not a benchmark. The earlier source78a native sealed-read qualification remains failed/unqualified. The repaired sourcef99 qualification and all four4000/s route comparisons pass financial/replay/snapshot/cold-recovery checks. Both direct-read candidates reduce globalp99,but the second regresses post-offerp99,so the registered two-pair optimization criterion fails;default remains unchanged. See [the complete comparison](V4_SEALED_READ_EXPORT_RESULTS.md). The complete native first-segment comparison accepts80000 orders in each arm,with3993.45/s in-window goodput and globalp9955.03–59.09ms;both registered paired optimization criteria fail. See [correctness](PRODUCTION_CORRECTNESS_RESULTS.md) and [native comparison](V4_SEGMENT_PREPARATION_RESULTS.md). These finite tests do not close the continuous operation,physical-host failure,production latency,authentication or external-venue gates below.

The [CI28-qualified bounded-dispatch comparison](V4_SEALED_BOUNDED_DISPATCH_RESULTS.md) completes four80000-order finite lineages with full original financial/replay/snapshot/cold-recovery and bounded-turn audits. Both registered pair criteria pass: **False**. Default remains CLOSED;the sustained5ms target,continuous100M,independent-host failure isolation,authentication and external venue gates remain unverified.

## Starting point: 25 October 2026

Delivery update:the latest [forced independent Linux run](PRODUCTION_CORRECTNESS_RESULTS.md) passes394 Java tests with0 skips,including11 real PostgreSQL tests,plus189 Linux Python tests,failover/snapshot/restart and web checks. Its observer revision is `4198aadd`;all test modules actually execute with a new Gradle home and build-result caching disabled. Application source remains `23f9c070`;the preceding timing artifact remains qualified by source `aed9430d`. The GitHub-hosted account billing blocker remains. This closes concrete correctness runs,not the other production gates below.

The maintained five-point V3 curve uses three JVMs on one CPU host, loopback UDP and fresh 20-second lineages. At 7,500/s, the first observation has 294.01ms all-arrival p99 and 24/46 cut intervals that clear recorded waiting. At 8,000/s, p99 is 380.73ms, 0/49 intervals clear waiting and the finite progression gate fails. Boundary repeats use the same qualified application artifact; see [the repeat contract](CAPACITY_BOUNDARY_REPEATS_V3.md). These results do not pass the trading latency target below. Historical three-Pod results use a different workload and cannot be combined with this curve.

The [four-arm writer timing comparison](WRITER_TIMING_RESULTS_V3.md) is closed with complete private native/raw evidence. At4,000/s each80,000-order arm accepts all arrivals;global p99 spans229.15–249.92ms. In both instrumented arms,repeated archive prevalidation consumes15.6–17.3% of maintenance wall time. The [immutable verified handoff candidate](VERIFIED_ARCHIVE_HANDOFF_V3.md) passes29 targeted local tests,the394-test forced Linux run and complete artifact qualification. Its controlled performance comparison remains incomplete;no repeated gain is established. None of the four timing arms executes that candidate.

The [initial candidate comparison](VERIFIED_ARCHIVE_HANDOFF_INITIAL_RESULTS_V3.md) is incomplete. C1/D1 show a small all-arrival p99 decrease but worse offer-to-reply p99;C2 remains invalid after a process identity observation failure and D2 never executes. All original orders/trades and unknown partitions are preserved. The sampler defect has deterministic regression coverage and18/18 tests on the actual Python3.8 runtime,plus the full189-test Linux Python3.12 run. A common qualified sampler and new registered lineages are required before another complete comparison;no repeated optimization or millisecond target is established.

GitHub Actions run [40197642613](https://github.com/yinli-systems/vectormatch/actions/runs/40197642613) did not start either job. Both check annotations report failed account payments or an insufficient spending limit. No runner steps executed. This is an account-level blocker, not evidence that code tests failed. Hosted spending limits have not been changed. A separately labelled, manually dispatched one-job runner on the existing prepaid CPU can provide independent Linux verification without a new cloud resource. Preserve its logs and identify it as self-hosted; do not disguise the hosted failure.

## Gates and required evidence

| Gate | Required behavior | Acceptance evidence |
| --- | --- | --- |
| Reproducible delivery | Clean source checkout without bulk evidence; exact toolchains; all tests, real PostgreSQL integration, failover smoke, Python regression tests and web checks | Actual CI job and source SHA, commands, exit codes, full JUnit results including skips, toolchain hashes and logs. No test exclusions to obtain green. |
| Authenticated trading | TLS; explicit principals; account and producer authorization; public market feed separated from private data; default-deny administrative routes | Wrong-account, revoked-credential, malformed-frame, replay, stale-sequence and rate-limit tests; no secrets in logs. The loopback workbench remains a development tool. |
| Replicated risk controls | Bounded notional, price/size and outstanding orders; deterministic integer risk; operator kill switch; cancel-only mode; auditable risk changes | Boundary and overflow tests; replicated replay/snapshot equality; unauthorized risk changes denied; kill switch still allows authorized cancels. Gateway checks alone do not suffice. |
| Complete command history | Stable lineage + producer + sequence + payload digest; final outcomes queryable after hot-cache eviction; timeout does not mean rejection | Commit/reply-loss tests and a durable history lookup that returns the original final result or explicitly unknown. Conflicting retries cannot create a second trade. |
| Continuous operation | 1M, then 10M, then 100M new orders in one business lineage with bounded memory and disk | [V4 endurance contract](CONTINUOUS_ENDURANCE_PLAN.md); exact counts, segmented original evidence, archive acknowledgements, invariant checks, checkpoint anchors and binary cold recovery. Fresh short runs cannot be added together. |
| Failure tolerance | Leader loss, follower loss/rejoin, gateway disconnect, exporter failure, disk full and disk I/O failure during load | Fault timeline, every admitted command reconciled, no divergent balances/trades, no silent ACK before the documented durability boundary. Recovery bounds measured separately from healthy latency. Independent physical-host failure remains unverified on one CPU host. |
| Millisecond trading latency | Initial target: all-arrival scheduled-to-confirmation p99 <=5ms and p99.9 <=20ms for 10 minutes at a predeclared rate <=70% of the measured sustainable knee, with concurrent maintenance | Three repeats at the same artifact/configuration; all planned arrivals retained; zero unknown, rejection or notSent for this target workload; latency histogram, per-second backlog and resource traces. Also report offer-to-reply and core-only latency separately. This target is not currently met and is not a contractual SLA. |
| Market distribution and scale | Bounded subscriber queues, explicit gaps and resynchronization; per-market sequencing; private account isolation; shard ownership and cross-market risk protocol | Slow-consumer and disconnect/replay tests; actual physical connection counts; fan-out throughput, bandwidth, tail latency and shard failure tests. Logical clients are not physical sessions. |
| External venue paper/testnet | Separate adapter from the deterministic core; authenticated venue protocol; client-order identity; partial-fill/cancel races; restart reconciliation; venue rate limits | Sandbox order/trade IDs and sanitized protocol receipts reconciled with balances and local ledger; disconnect and retry tests. Synthetic matching, paper trading and funded trading remain distinct evidence. |
| Funded trading readiness | Explicit account/venue, asset allowlist, capital and loss limits, strategy, operator ownership, reconciliation and emergency stop | All preceding applicable gates; a concrete dry-run report and reviewed limits. No funded orders until the user explicitly authorizes those account/strategy/amount parameters. Technical readiness alone does not authorize live trading. |

## Execution order

The [CPU UDP/storage diagnostic](CPU_UDP_PATH_RESULTS.md) confirms NAT-mapped UDP
reachability but fails its finite zero-loss gate and cannot provide the directly
bindable private topology required by the current Aeron launcher. Its receipt-ledger
improvement and OS force timings narrow investigation; they do not qualify a new
trading cluster or change the acceptance thresholds above.

1. Close both already registered boundary repeats and retain every original outcome; repair reproducible CI and record the hosted account blocker.
2. Instrument maintenance phases before optimizing. Compare each change with the control on the same newly qualified artifact. Never weaken fsync, canonical readback, acknowledgement ordering or evidence bounds to improve a number.
3. Build a separate authenticated trading gateway and deterministic risk controls with recovery tests; maintain local workbench compatibility. Choose the first venue through supported sandbox capabilities and user account availability.
4. Implement versioned continuous retention and history lookup, then run 1M ->10M ->100M with fault injection and cold restore. Advance only after the previous level closes.
5. Verify the healthy latency target, sustained capacity and market distribution independently. Physical-host isolation and external venue latency require their own environments and budget; the current prepaid single host cannot prove either.

All gates require reproducible evidence rather than a numeric project score. Raw synthetic evidence remains private under the existing authorization. No history rewrite, public publication, new paid resources or funded-trading activation follows from this contract.
