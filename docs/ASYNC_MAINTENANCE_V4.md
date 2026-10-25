# Bounded asynchronous maintenance: next implementation gate

This is a design for a separate opt-in V4 implementation,not an executed optimization. V3 measurements and artifacts remain unchanged. The proven-exit C1 observation at4,000/s accepts all80,000 synthetic orders/trades with236.456120ms scheduled-to-confirmed p99;96.79% of the slowest1% requests' total latency occurs before dispatch. Its27 maintenance cycles consume5.687831711s. These are descriptive observations on one CPU host,not an isolated causal experiment.

## Implemented isolated components

The separate V4 branch now has nonblocking durable-writer ticket polling,bounded off-caller archive preparation,and a one-cut asynchronous file-prefix pipeline. The pipeline retains owned original inputs and only constructs a combined private receipt after the original archive ticket and,for a nonempty event range,the exact event ticket finish force/full-readback/receipt completion. Empty event ranges require no invented event file. Foreign/double consume,wrong prior event frontier,lifetime cut limits,delayed archive/event force and corrupted event evidence are covered by21 actual forced local Mac tests with zero failure/error/skip. The pipeline never submits a destructive ACK or mutates replicated state;its file-credit consume does not release any network ACK fence. Borrowed workers are not cancelled.

These are locally tested components,not an integrated network coordinator,Linux V4 qualification,an executed optimization or a100M implementation. Read-wave scheduling,business headroom,original maintenance identities/raw schema and binary cold recovery still require the gates below. The current encoding C/D comparison uses none of this code.

## Work that currently blocks dispatch

`RetentionCapacityExperimentV3.dispatch()` drains pending business requests and synchronously calls `maintenance.exportThrough()`. Arrivals continue to accumulate. That call prepares a prefix,reads archive chunks,verifies/forces/readbacks the archive,reads events,verifies/forces/readbacks their payload and receipts,and only then issues both destructive acknowledgements. The archive and event read-bank leases also remain held while their respective writer ticket is awaited. Merely releasing a bank sooner does not unblock a synchronous caller.

The next change must let the owner continue serving business while independent verification/storage work runs. Reducing file force,skipping canonical readback,pausing the arrival clock or reporting only successful dispatch latency cannot satisfy this goal. Current owner/read-bank and raw-tape contracts deliberately reject business/read overlap;an asynchronous implementation must introduce and test an explicit new contract rather than disable those guards.

## State machine and ownership

Use one owner thread for transport polling,original request identities and all credit transitions. A maintenance coordinator advances through these states without blocking that thread:

1. `PREPARE`:capture a definite closed business prefix and its descriptor. Reserve bounded history,outbox,journal,writer-file and raw-ledger headroom before accepting further business.
2. `ARCHIVE_READ`:read the exact prepared immutable prefix with bounded credits. Track every original wire,admission and response. Initially keep each network read wave exclusive;yield business time between fully consumed waves. Concurrent read/business support requires a separately versioned owner/tape contract.
3. `ARCHIVE_VERIFY_WRITE`:close the read lease before sending an owned immutable payload to a bounded worker. That worker performs canonical verification,write,force,full canonical readback,receipt write/force/close. A completed future carries the exact verified command/event prefix and durable receipt. Never block the owner awaiting it.
4. `EVENT_READ`:read only the frozen prefix's event range,even if new business has appended events. Validate exact content against the verified archive and preserve every raw response. Bound the expected-event representation and every retained wave.
5. `EVENT_VERIFY_WRITE`:release the read lease and submit owned event bytes to the bounded worker. Business may continue while the worker verifies and persists. Neither destructive ACK is eligible until both immutable receipts are complete.
6. `ARCHIVE_ACK` then `EVENT_ACK`:admit only after the required business/control exclusion fence. Preserve original maintenance identities across timeout/failover. A lost reply is unresolved;it must not renew permits or create a new identity. Advance each local frontier only after a definite reconciled outcome.
7. `CLOSED`:record the cycle/receipts and release headroom. A failed state is terminal for that coordinator and preserves every unresolved wire and partial evidence file. It never authorizes eviction or ACK.

Only one maintenance cut may be active initially. Worker queues and in-flight payloads have explicit byte/count bounds;there is no unbounded executor. Mutable input buffers cannot escape to a worker. Do not share mutable `budget`,owner tickets or live engine state with that worker. Worker completion is observed by the owner and does not mutate replicated state directly.

## Admission while a prefix is in progress

V3's3,072-command cut and4,096-history-command capacity cannot be treated as unlimited slack. Count retained prefix entries,new business,all possibly accepted in-flight commands and uncertainty before admitting another order. Apply the equivalent bound to outbox events,serialized bytes,per-producer retained results and snapshot size. A pending prefix is not retired merely because its file exists.

If projected headroom cannot cover another maximum-sized operation,admission backpressures explicitly. Preserve these outcomes in the all-arrival ledger;do not hide them by slowing the generator. The finite350,000-arrival limit and journal/file limits remain until the separate anchored-journal/segmented-ledger work in [continuous endurance](CONTINUOUS_ENDURANCE_PLAN.md) is qualified. Asynchronous maintenance alone does not implement100M continuity.

## Qualification before a performance claim

Run the same command stream through synchronous and asynchronous modes and compare canonical state,integer balances,reservations,price/time order,events and original results at every closed frontier. Include duplicate/conflict/stale identities,multiple fills,cancel/replace and IOC residuals;the current one-price seeded-maker workload is insufficient on its own.

Deterministically delay each worker/response and inject failure before/after write,force,readback,receipt completion,each ACK admission/application/reply and snapshot publication. Assert that later business cannot alter an earlier prepared prefix,an old cut cannot retire new history,and missing/corrupt receipts never authorize either ACK. Exercise bounded-queue saturation,retention exhaustion,shutdown with work in flight and completion arriving after abort. Restore actual binary snapshots into a cold application and reconcile the same original identities.

Version raw request/reply/offer schemas to prove every new overlap and credit transition. Preserve command lineage,per-arrival scheduled/dispatch/admission/reply timestamps,maintenance phase/lease generation,worker occupancy,retention frontiers and unknowns. Independent raw verification must reject unsupported overlap instead of silently accepting V4 tapes under V3 rules.

Then qualify actual Linux classes/JAR origins and run a registered synchronous/asynchronous/synchronous/asynchronous comparison at the same leader,rate,durability,CPU/JDK,warm-up and storage setup. Report scheduled-to-confirmed p99,offer-to-reply p99,goodput,backlog,headroom,GC and every rejection/unknown. Only after a repeated finite improvement should a new capacity curve and sustained1M→10M→100M lineage begin. A5ms target,production readiness and independent-host fault tolerance remain separate acceptance gates.
