# Proposed V3 Cluster, archive and endurance integration

This is an unimplemented next-stage design. The current candidate implements only
the bounded core facade, codec and small local correctness tests described in
`CORE_RETENTION_V3.md`. It is not a new capacity/endurance result or permission to
replace original native state. The legacy V2 profile/wire/capacity harness remains
unchanged.

## Separate profile and wire boundary

Add a new, explicit Cluster profile with a fixed core V3 Profile, lineage,
outbox/history/export limits and expected source/artifact identity. Every node
must report identical effective settings before admitting traffic. No node may
infer a profile from a client packet, restore a legacy snapshot as V3, or silently
upgrade an original archive.

Use a distinct V3 envelope/decoder and snapshot magic. The existing
`CommandCodec` is wire version 2 with operations 0..7, 2,048-byte commands,
4,096-byte replies, at most 16 exported events and 3,072-byte snapshot chunks.
Keep that decoder and its byte-compatibility fixtures. A new bounded V3 decoder
must check profile fingerprint/lineage, operation, lengths/counts and exact
structured identity; unknown versions/tags fail explicitly. Correlation ID is
transport routing metadata, not a business or maintenance identity.

`MatchingClusteredService` currently owns `MatchingEngine` and
`ReplicatedOutbox`. Introduce a separate V3 service/profile path rather than
changing its default engine or reinterpreting legacy opcodes. Its writer needs a
nonmutating V3 admission preview that reserves full-history bytes/fanout and
outbox events together. Bind any preview to the current business and maintenance
state and apply it on that same writer without intervening mutation. The current
facade's private preview is not yet this public Cluster admission interface.

## Maintenance request identity and ordered sequences

Proposed mutating operations include `ARCHIVE_COMMIT` and a separately named
event-projection ACK. A read-only operation prepares/fetches an immutable archive
prefix descriptor and bounded chunks; it does not itself free state.

Every maintenance mutation carries the registered profile hash, lineage,
`maintenanceProducerId`, positive `maintenanceRequestSeq`, and complete bounded
payload. The archive commit payload is the core ArchiveAck descriptor: first/end
business command cut, preceding/ending chain and full payload SHA. Maintain a
separate permanent, bounded maintenance-producer high-water registry with bounded
full-payload/result cache in replicated state. Do not consume business producer
sequences, substitute correlation ID for identity, deduplicate solely by a short
hash, or reclaim a producer namespace. Same cached identity/payload returns its
original result; changed payload conflicts; evicted old identity is stale and
never executes. Client timeout must query/retry that same identity, not create a
new request identity.

Keep these counters distinct:

- Business `commandSeq`: advances only as specified by the core, including fresh
  business rejections; unchanged retry/invalid/capacity attempts may not advance.
- `eventSeq`/`marketSeq`: emitted business events only; maintenance emits none.
- Accepted-Place count: `nextOrderId - 1`, never maintenance/retries/rejects.
- Core `maintenanceSeq`: one increment per effective archive compaction; an exact
  duplicate of the most recent descriptor is a no-op, even after restore.
- A new replicated application-mutation counter: increment once for each
  well-framed business or maintenance mutation envelope applied in log order,
  including no-op/replayed results. Read-only fetch/status requests do not change
  this counter. It is not an Aeron log-entry count, since the underlying log also
  contains other framework/application messages.

Persist the maintenance registry and application counter in the new Cluster
snapshot. Bind archive/checkpoint manifests to the actual framework recording/log
position once the precise pinned Aeron 1.53.3 API is verified; do not equate the
existing POSITION reply's business command sequence to an Aeron recording
position. Persist and verify the tuple of these independent cursors on recovery.
Archive a full maintenance journal (identity, payload/result and cursor tuple)
with its own chain; the core's last-ACK anchor alone is not a complete historical
maintenance journal.

## Immutable export, external verification and no-loss ACK ordering

1. Select a complete pending business-command prefix, never half of a command's
   events. Return a deterministic descriptor bound to profile/lineage/from/to/
   predecessor/end chain/payload SHA and full counter anchors. A bounded number
   of pinned export descriptors must survive retries; no wall-clock timer may
   delete their required pending records. Prefix records are immutable while new
   commands append. If bounded history fills, new commands backpressure.
2. Fetch bounded chunks with descriptor, offset/index, length and checksums.
   Reject mixed descriptors, gaps, overlaps/reordering, truncation and an
   incorrect final digest. The current core batch materializes bounded bytes;
   it is not the later streaming transport. Do not raise the old whole-snapshot
   limits as a substitute for bounded chunked encoding/reading.
3. The exporter writes CREATE_NEW temporary files and a manifest containing full
   commands/results/events/terminal identities, command/event/market ranges,
   accepted-Place totals, predecessor manifest hash, lineage/profile and source
   identity. Flush/close and read back the sealed archive and manifest, verifying
   every length and SHA before marking it complete. The existing FUSE mount is a
   disclosed archive medium; it does not provide an independently proven durable
   fault domain merely because a write/read-back succeeds.
4. Only after that external verification submit `ARCHIVE_COMMIT` with the same
   registered maintenance request identity and exact descriptor. All replicas
   independently match the deterministic pending prefix digest before invoking
   core compaction. The core trusts the explicit ACK assertion and cannot prove
   external disk persistence. No trading decision performs external database I/O.
5. Do not call `ReplicatedOutbox.acknowledge` as a side effect of archive commit.
   That is a separate cursor: the existing `ReliableProjector` commits its exact,
   contiguous PG event transaction before sending the replicated event ACK.
   Preserve its conflict/gap/lineage checks. Conversely, a PG event ACK must not
   free full command/result/identity history or imply the new history archive is
   durable. Both independent outstanding queues remain bounded/backpressured.

Before freeing the only retrievable result for an unresolved request, require a
new harness/exporter result-resolution floor: per-producer contiguous resolved
watermarks plus explicit holes for out-of-order outcomes. A high-water of issued
requests alone does not establish resolution. The current core deliberately
retains the old finite-cache STALE contract and does not implement this external
UNKNOWN floor. A future result-query endpoint may return a complete verified
cold historical result; that lookup must never re-execute a stale business
command or claim the result was a newly accepted Place. It is distinct from the
old bounded retry result API.

Failure behavior must be explicit: a write/read-back failure sends no ACK; a
sealed file with a lost ACK is retried under the same identity/descriptor; an ACK
committed before reply loss resolves from replicated maintenance identity/anchor
state after leader restart. Never issue a new identity to hide uncertainty.
Archive ACK may progress while PG export is behind, but its events remain in the
outbox; PG ACK may progress while full-history archive is behind, but full records
remain pending. Neither cursor alone permits native log deletion.

## Snapshot, native log retention and recovery

Create a distinct V3 Cluster envelope containing bounded core V3 bytes, outbox
state, maintenance registry/cache, the application-mutation cursor, profile/
lineage, export descriptors, history/result-resolution and archive/checkpoint
anchors. Enforce a combined size budget before allocation. The existing core
64-MiB byte-array checkpoint is only the initial bounded correctness phase;
transport/encoding still need real streaming before any larger profile is used.

The snapshot must preserve active FIFO, assets/reserved amounts, every permanent
producer high-water, retry/maintenance results within their declared retention
windows, pending command/event history, both export cursors and recovery
manifests. Restore rejects wrong source contract/profile/lineage and missing,
truncated, conflicting or re-ordered pieces. It must not reset counters or
silently fall back to a fresh engine.

No automatic `.rec`/`recording.log` deletion. A later retention command may use
the pinned Aeron archive API only after a verified recoverable checkpoint plus
sealed full history cover that exact position and all required replicas can
recover/catch up. Retain at least two validated checkpoint generations within the
registered overlay budget. Include unacknowledged outbox/history in the recovery
proof. Explicitly stop/backpressure on slow exporter, missing archive, follower
lag or low space, preserving every invalid observation.

## Implementation and acceptance sequence

First implement bounded V3 wire roundtrips, strict cross-version/profile negative
tests, maintenance idempotency/conflict/stale state, joint admission and a combined
snapshot, with a small in-process service reference. Then run three local JVMs
on the existing CPU only in a separately registered idle window. Exercise leader
failure/reply loss at export prepare, partial write, read-back, archive commit,
PG transaction commit, event ACK and checkpoint boundaries; verify unknown
resolution and all-node canonical replay from both hot and cold recovery paths.

Use a new streaming `EnduranceExperiment`, leaving
`RemoteCapacityExperiment`'s empty-state/350k/no-external-ACK assumptions and all
existing evidence unchanged. It must continue producer sequences and one lineage
across checkpoint/compaction, use bounded inflight state and sample buffers,
stream every outcome/latency into SHA-chained chunks, retain rejected/not-sent/
unknown and scheduler-invalid observations, and independently replay segment
boundaries/assets/FIFO/cursors. Register stop gates before execution; never
concatenate independent fresh trials into one cumulative count.

Only after these recovery/export proofs close: one million first accepted Places
beyond the old hot cap with multiple compactions and cold recovery; then ten
million with measured heap/GC/log/export/space behavior; then a separately
registered hundred-million stage if resources/evidence still close. These are
cumulative-order goals, independent from orders per second or connection count.
