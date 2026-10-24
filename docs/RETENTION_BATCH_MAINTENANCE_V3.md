# V3 finite maintenance lifecycle: functional stage

This opt-in successor to the bounded batch owner adds one maintenance RPC slot on the same owner thread, Aeron session and shared driver. A separate file-writer thread has at most one active and one queued job. It retains complete business history and events before acknowledging their exact prefixes. This is a local correctness prototype, with no 350k capacity run, independent-host performance, external storage durability or 100M endurance claim.

The existing V2 service, original V3 snapshot/wire encodings, two-argument service adapter and default transport constructor retain their previous paths. Prepared-prefix caching requires an explicit adapter constructor opt-in; the node additionally requires the finite profile and a ninth `bounded-maintenance-v1` argument. The actual startup log reports the selection. The finite profile and its fingerprint are unchanged from the owner stage; runtime code identity changes and is checked from actual classes/JARs.

## Bounded maintenance and immutable export

The owner accepts exactly one unresolved maintenance operation at a time. It shares the business correlation allocator and never sends an untracked single Business. A same-operation resubmission reuses the original bytes and permit without renewal. Definite negative offers roll back the pre-reserved maintenance journal charge; throwing offers retain it as possibly executed. Timeout, close and failure preserve the original full request and never imply that an ACK was applied.

A maintenance RPC allows at most four possibly accepted physical offers. Exhaustion closes the new-business gate immediately, although a late matching reply can still arrive; it does not silently restart under a fresh maintenance identity. The finite owner additionally limits possible mutating offers to 1024 and reserves `encodedOperationBytes + 1024` journal bytes for each before offer. Read-only prepare/chunk/event-fetch calls do not consume maintenance journal records, but they still travel through the replicated log and their time is real system work.

The coordinator keeps a run budget across its smoke's definite owner stop and node restart. It reserves all four possible journal entries for each new ArchiveCommit or EventAck identity before submitting it. A 350000-command arithmetic example with cuts of at most 3072 needs 114 cycles and normally 228 ACKs; reserving four physical attempts each uses 912 of the stricter 1024-record run budget. Setup commands, actual bytes, retries and final partial cuts must be included in a future registered workload. Constructor/unit arithmetic is not evidence that a 350k run completed. The profile's 4096-record/4MiB maintenance journal still has no lifetime reclamation.

With the cache explicitly enabled, PrepareArchive creates at most one immutable canonical prefix byte array. Repeating the same cut and archive anchor reuses it; a different cut replaces it, and a chunk must match that currently prepared descriptor and total length. Chunk reads slice that array instead of re-encoding the entire prefix each time. A successful advancing archive ACK invalidates it, as does service start/restore. It is ephemeral and excluded from canonical snapshots. After restart a client must prepare again. The resident limit is the smaller of `core.maxPendingSerializedBytes + 1024` and the core encoding cap; construction can temporarily hold two bounded copies. Core ArchiveCommit still performs its existing one full-prefix verification encoding. The test encoding counter measures adapter preparation/chunk work only and does not conceal that ACK cost.

## Verification and ACK order

The new read-only archive verifier checks the complete bounded envelope, exact profile/lineage, initial archive frontier, contiguous fresh command sequence, structured identities, canonical entries, accepted-order counters, event/market continuity, terminal-order bounds, every chain link, final descriptor and complete payload SHA. It reuses the existing canonical entry decoder without changing the format. Its success proves consistency with the supplied descriptor; it does not authenticate an external party or prove storage durability.

For each functional cycle the coordinator:

1. Requires known closure of current business tickets and chooses a nonempty cut of at most 3072 commands.
2. Retrieves the descriptor and all bounded chunks; verifies the exact archive chain/range and full payload.
3. Sends an immutable copy to the bounded writer. The writer verifies it, creates a new file, writes all bytes, calls `force(true)`, and performs a fixed-size full readback and re-verification. Size changes are rejected before unexpected allocation. A separate bounded verified receipt is also forced.
4. Fetches the exact outbox event prefix, matches every Event against the verified history, and writes/forces/readbacks its complete framed replies with the same discipline.
5. Only after both nonempty payloads have successful verified receipts does it submit ArchiveCommit and then EventAck, each with the original dedicated maintenance identity and full request retained. An empty event prefix needs no EventAck.

Failure leaves raw/partial files and closes the coordinator to further attempts. If evidence writing fails after submit, the exception retains the exact original request and the failure record reports whether a disk copy actually succeeded. File-channel force and logical readback are observed actions; no directory-fsync, independent storage replica or provider power-loss guarantee is claimed.

This functional coordinator deliberately requires no pending business at a maintenance boundary. It allocates no arrival scheduler or Q64 FIFO. A future open-loop capacity harness must keep scheduled arrivals running, use bounded backlog/backpressure while maintenance executes, and include all maintenance latency, journal retries, queue drops, credit stalls, unknowns and final drain in the same measured window. It cannot pause the arrival clock or subtract maintenance time.

## Local evidence contract

The new three-JVM fixture targets 10000 IOC orders plus three setup commands, four complete archive cuts, one real application-layer ArchiveCommit reply discard/retry, and checkpoint/cold continuation after two cycles. It checks original retry wire identity, every full archive/event file before the first destructive ACK offer, actual accepted request order against a sequential V3 adapter, and fresh command results/events/terminal views against a separate MatchingEngine instance. That separate instance uses the same algorithm, not an independent implementation. This document specifies the fixture; the validation manifest and actual XML/native receipts separately state whether it ran successfully.

All native attempts, including failures, must retain their actual source, class/JAR inventories, full state trees, request/reply streams and owned-stop receipts. The full logical gzip archive is not a physical sparse-extent copy. Original stopped sparse directories remain until independent archival closure.
