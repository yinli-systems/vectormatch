# Bounded V3 batch owner: functional stage

This opt-in prototype adds a single network owner and one Aeron session for 128 logical producers to the fresh V3 batch endpoint. `RetentionBatchOwnerV3` permits batch caps 1 or 4 on the same explicit `finite-batch-load-v3-v1` profile. It does not change the default V2 service, the original V3 smoke profile, the original `RetentionClientV3`, matching behavior, snapshot formats, sync level, or Archive force policy.

There is no open-loop arrival generator in this stage. The owner API and local three-JVM tests establish bounded ownership and result/retry behavior. They do not establish a throughput curve, an end-to-end latency percentile, independent-host UDP performance, persistent client restart recovery, external archive durability, or any 100M target. A future comparison must run fresh batch1 and batch4 controls with identical artifacts, profile, workload, producer identities, W128, taskQ64, session/driver counts, deadlines, flush policy and maintenance schedule. Historical V2 capacity points are a different system.

## Explicit dimensions

| Dimension | Value and ownership |
| --- | --- |
| Logical workers | 128, one fixed `(account, producer)` binding per worker for the owner lifetime |
| Arrival task queue | Declared Q64 per worker: 8192 positions in an external scheduler; this owner allocates no such FIFO |
| Internal pending slots | 128 total; at most one unresolved logical command per producer |
| Ready queue | At most 128 references to those slots |
| Physical frames | At most 128, each with 1–4 commands; configured cap is 1 or 4 |
| Aeron transport | One network-owner thread, one actual shared MediaDriver and one AeronCluster session |
| Batch flush | Full batch immediately, otherwise nominal 50us from oldest ready command; OS scheduling can make it later |
| Offer permit | Absolute monotonic deadline, at most 2 minutes; waiting or duplicate submission does not renew it |
| Retry | Same original complete wire, nominal 500ms after an accepted offer; definite negative offer nominal retry 100us |
| Owner idle wait | Deadline-aware park up to 1ms; driver idle policy remains the existing `ClusterClient.launchDriver` policy |

The profile has 256 business producer identities, 16 cached results per producer and 512 global cached results. It allows 8192 retained orders, 4096 pending command-history records, 8192 pending events and an 8192-event service outbox. The conservative complete snapshot upper bound is 43,739,648 bytes within its 64MiB cap; constructor tests independently derive the arithmetic and reject a one-byte smaller bound. Maintenance producer/cache/journal bounds are 16/128/4096 records with a 4MiB journal byte limit. These finite limits are admissions, not automatic reclamation or an endurance guarantee. Neither the unit fixtures nor the native owner smoke run indefinite maintenance.

## Credit and exclusive-write precondition

All business writes while this owner is active must pass through this one owner. Setup writes occur before it starts; read-only Position/checkpoint operations can follow its definite stop. A second business client could advance server cache eviction beyond this owner's knowledge; the transport does not enforce cluster-wide exclusive ownership. External exclusion and actual node profile/readiness checks are mandatory before using this mechanism in a benchmark.

For each first possibly accepted logical command the owner reserves an increasing local ordinal **before** calling nonblocking `offer`. Its global credit span is the inclusive distance from the oldest unresolved first-offer ordinal through the latest such ordinal, including intervening commands that have already returned results. New first offers require `span + frameSize <= 512`. As a result, other producers cannot evict an unresolved earliest result by making unlimited progress. A definite negative first offer rolls back only its exact reserved tail. A throwing offer is ambiguous and retains its reservations. Reoffers retain the original ordinals.

Per-producer credit is stricter than the profile cache of 16: only one unresolved command can exist for a bound producer. Timeout, revoke, interrupted waiting, permit expiry, publication failure and close do not free possibly executed credit. Only a complete validated matching `APPLIED` per-command result closes it. `APPLIED` describes service execution of that identity; its business Result can itself be rejected, stale, or conflicting. Credit cannot be safely recreated in a new owner from an in-memory UNKNOWN after restart; no persistent recovery protocol is implemented.

The unit fixture withholds the first result, permits 511 later first offers across the other 127 producers, fills the actual global cache to 512 results, and proves the next command remains unoffered even after the earliest ticket is revoked and expires. Its late bound result releases the protected span. This is a finite functional credit test, not a distributed exclusivity proof.

## Original bytes, authority and UNKNOWN

A frame is encoded and full request/reply budget-validated before any offer. Its original complete bytes and SHA are retained. The IO boundary receives a clone and cannot mutate that original. Tickets return clones for caller evidence. A pending same-command submission returns the same operation without extending its permit; a different command for that producer is refused.

Every member authorizes the complete immutable frame. Revoke takes the same monitor as the fresh permit check immediately before each nonblocking offer. Revoking or expiring any member before the first possibly accepted offer aborts the whole frame as known `NOT_SENT`; it is never silently repacked. After an accepted or ambiguous offer, any member's revoke/expiry disables all further reoffers of that complete frame. Late responses are still polled. A successful revoke does not retract already accepted bytes or roll back server state.

A wait timeout reports `UnresolvedCommandException` with identity, payload SHA, the original complete wire when a frame exists, and separate `mayHaveExecuted`/`mayStillBeOffered` flags. It is not a business rejection or rollback. The original bytes are caller-owned in-memory evidence; the caller must persist them for a separate recovery workflow. `Ticket.isDone()` also becomes true on an exceptional owner stop and does not mean the business outcome is known.

The entire batch response is decoded and checked for scope, frame correlation, every identity/SHA and prefix/frontier shape before publishing any completion. A malformed last item cannot publish earlier successes. Partial resource admission closes the new-business gate and disables all reoffers. Its committed prefix may complete; admission-rejected/not-attempted members conservatively retain unresolved credit because a response can precede a later already accepted retry. Late matching applied results may close that credit, but they do not silently reopen the run. Such a run must retain evidence and stop rather than proceed as a valid capacity point.

IO construction, observation, poll, offer and close run on the same owned thread. User completion callbacks are not exposed on that thread. Fatal failures preserve original slots/credit, fail waiting callers explicitly, and are surfaced again by `close`. Close is bounded in the controller-facing API but cannot promise portable hard cancellation of a blocked third-party IO call; a failure to stop is an explicit failure, not successful cleanup.

## Actual evidence and validation

`RetentionBatchAeronTransportV3.observation()` reads the actual concluded driver directory, threading mode, selected shared strategy, MTU, NAK values, actual Aeron client/session/leader IDs, and owner thread. Scope profile/lineage in this map describe the locally validated protocol scope; they are not independent evidence of the remote node configuration. The native smoke separately checks all three actual node readiness logs against the expected loaded code/profile/lineage.

The new profile is selected explicitly by `RetentionNodeMainV3`; the old `local-smoke-v3` profile fingerprint stays fixed. The new runtime code fingerprint hashes complete actual core/cluster classes or JARs plus dependencies. The smoke keeps actual class/JAR inventories, request/reply bytes, per-round owner observations, node identity/stop receipts, failure/completion records, canonical references and native checkpoint state. All attempts are retained, including failures; there is no silent retry with a new ID.

Focused unit tests cover W128/Q64 separation and producer binding, flush/deadline behavior, immutable wire retries, whole-frame revocation, definite negative rollback, throwing-offer ambiguity, global credit starvation protection and late resolution, atomic malformed-response rejection, partial-admission run closure, explicit IO-close failure, and profile bounds/default identity. Local three-JVM validation is recorded separately with actual test XML counts and exact artifact hashes; test names or this design description alone are not proof that a native run completed.
