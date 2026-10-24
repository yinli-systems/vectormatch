# Opt-in V3 bounded-retention core prototype

This branch adds a core state-machine foundation for a future continuous-lineage
endurance workload. It has not executed one million or one hundred million
orders, and provides no new Cluster, wire, durability, throughput, latency,
connection-count or failover result. Existing CPU capacity evidence remains tied
to source `433f02bebe2f3109ec363291fa562d5c509c0723` and its original artifacts.

## Explicit version and identity boundary

`MatchingEngine` constructors, default business behavior and public V2
snapshot/restore format retain their previous contract. The only legacy-class
changes are package-private bridges enabled by the private V3 embedded instance,
and a V3-only archived-cancellation reason. Its default V2 path never compacts.

Construct a separate `RetentionEngineV3` with an immutable `Profile` and an
explicit lineage string. A profile includes the legacy account/producer/hot
order/cache bounds plus pending command, event, per-command fanout and serialized
byte bounds. Producers are stable ASCII `[A-Za-z0-9_.-]{1,48}` identifiers scoped
by account. The exact client order ID is
`v3:<positive account>:<stable producer>:<positive requestSeq>`; delimiters cannot
occur in producers. `RetentionEngineV3.place(...)` constructs it. A fresh Place
with an arbitrary legacy client ID is `INVALID_REQUEST`, with no mutation.

Producer high-water marks remain permanent within the bounded producer registry.
`maxProducers` slots are never reclaimed by compaction, cache eviction or restore;
once that explicit limit is reached a new producer is refused.
Compaction never removes producers or their high-water marks, resets request
sequences, or changes bounded retry-cache eviction. An identical cached retry
returns the original result without events; a changed cached payload conflicts;
an evicted request at/below high-water is `STALE_SEQUENCE` and never executes.
These no-mutation attempts still work while new commands are backpressured.

`acceptedPlaceCount()` is the monotonic allocated order count, `nextOrderId - 1`.
Only the first `ACCEPTED Place` advances it. Deposits, cancels, business rejects,
retries, conflicts, invalid/stale attempts and archive maintenance do not count.
Accepted IOC/self-trade-expired orders are orders, even if they execute no trade.

## Bounded admission and full pending history

Each first command that actually advances the business command sequence retains
the complete command, result, returned events, newly terminal full OrderViews,
cumulative accepted-Place/event/market counters, and a deterministic SHA-256
chain link. Command encodings preserve account/producer/request/client-order
identity, unlike the old event-only export. No external database read participates
in matching or deduplication.

Before execution, the facade uses the existing exact event-count preview and a
conservative serialization bound. Encoded text is at most 256 UTF-16 code units;
structured command identities are stricter. Each event has at most two touched
terminal order IDs. Fixed-width primitive fields and their lengths provide an
explicit bound on full result/event/order encodings. Command count, aggregate
event count, fanout and serialized bytes are independently bounded. Reaching any
bound throws `HistoryBackpressureException` before business mutation. Conservative
reservation can backpressure before the actual serialized-byte limit is full.

Per-command terminal detection visits only the accepted order ID and IDs in its
returned events. It does not scan all retained orders. Terminal IDs are indexed
by their actual terminal transition command, not by their original acceptance
command. The expensive diagnostic/snapshot path separately verifies that every
hot terminal order is bound to the exact full terminal record at that transition.

The profile also proves a conservative total snapshot encoding budget from
account, permanent producer, hot order, bounded result cache, terminal index and
pending-history limits. V3 snapshots are capped at 64 MiB. This prototype still
uses bounded byte arrays and copies; it does not implement the later Cluster
chunked/streaming checkpoint transport or claim a multi-gigabyte snapshot path.

## Explicit archive ACK and compaction

`archiveThrough(commandSeq)` is a read-only deterministic prefix export. The
immutable `ArchiveBatch` includes full records and binds profile, lineage,
previous archive counter/hash anchors and record chain. It exposes canonical
bytes and an ACK descriptor named `acknowledgementAfterExternalVerification()`.
That method is not a storage operation or proof of persistence. A future exporter
must seal, store and read back the bytes before submitting the ACK.

`compactThrough(ArchiveAck)` recomputes that exact pending prefix and requires
matching profile, lineage, start/end cut, preceding/ending chain and full payload
digest. It removes only terminal hot orders whose terminal record is covered by
the acknowledged cut. Active orders, price/FIFO position, balances, reserved
assets, supply, producer high-water, retry cache and all business sequences remain
intact. It then releases the acknowledged pending history and advances a separate
maintenance sequence plus archive/counter/hash anchors. There are no timers,
reflection, hash-only client-ID deduplication or automatic reset/compaction.

The most recent exact ACK is idempotent, including after a snapshot restore. An
older ACK is stale and rejected without mutation; its payload is not retained
forever solely to provide an unbounded ACK-result cache. Wrong hashes/cuts and
cross-profile/cross-lineage ACKs are rejected before mutation.

`hotOrder`/`hotOrders` query hot state only. After a terminal has been compacted,
the V3 cancellation result is explicitly
`V3 terminal order archived; hot cancellation unavailable`. It does not assert
account ownership from an absent hot object or consult an external cold store.
Legacy V2 historical queries and cancellation reasons are unchanged. Cold
history pagination/ownership queries are a later, versioned API.

## Snapshot and restore

The independent V3 envelope contains profile and lineage, bounded core account/
order/producer/retry state, full pending records, terminal-transition indices,
business counters, the last archive ACK, maintenance sequence and archive chain/
event/market/accepted-Place anchors. Its private embedded core encoding reuses
the V2 implementation; that core object is not exposed publicly.

`RetentionEngineV3.restore(bytes, expectedProfile, expectedLineage)` requires the
explicit expected contract, checks the full checksum, counts/lengths, canonical
encodings, history/counter continuity, structured identities, complete terminal
cut binding and asset/FIFO invariants. It rejects V2 input and wrong profiles or
lineages. `MatchingEngine.restore` rejects the new V3 envelope. There is no
implicit migration of original snapshots, native backups or Cluster state.
The hash chain/checksums detect corruption; they are not signatures proving a
trusted party or physical storage durability.

## Validation and remaining integration

The independent V2 fixture was captured from exact unmodified source 433 with
its source SHA and capture commands recorded beside the fixture. Its 89 commands
and 92 initial/prefix snapshots compare full Execution strings, event previews,
and complete V2 snapshot bytes. Every prefix is restored and its full remaining
suffix is compared, rather than generating expectations from the modified code.

V3 tests cover repeated explicit compaction beyond a four-order hot cap, 100
first accepted orders in one lineage, active makers crossing archive boundaries,
FIFO/reservations, finite retry/conflict/stale behavior, permanently retained
producer high-water after complete cache eviction, all four admission bounds,
ACK idempotence and mismatch rejection, version/profile/lineage/checksum and
rehashed terminal-cut corruption, immutable export bytes and independently
recomputed SHA links. A deterministic 1,000-command trace compares matching,
orders, assets and book levels to the independent flat reference model; a second
engine repeatedly restores and continues with identical full executions,
exports, compactions and V3 snapshot bytes.

Cluster command/event codecs, replicated archive ACK ordering, durable exporter,
UNKNOWN/result retention-floor handling in a new harness, streaming raw evidence,
cold queries, outbox/PG cursor integration, safe Aeron log retention and native
recovery/failover are not implemented here. Only after those contracts and
independent recovery checks close can million/ten-million/hundred-million stages
be registered. No maintenance or retry activity may inflate fresh-order counts.
