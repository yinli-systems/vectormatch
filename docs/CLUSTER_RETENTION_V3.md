# V3 service admission and maintenance prototype

This isolated candidate builds on core commit
`109ae1800f0b76620af344a3dd7543849ffffd69`. It adds an **in-process single-writer
service state machine**, a separate bounded request codec, and a combined
checkpoint. It does not implement an Aeron `ClusteredService`, a node launcher,
a network reply/export protocol, an external archive writer, PG integration,
cold-result lookup, or an endurance harness. `ClusterNodeMain`, the default
`MatchingClusteredService`, `CommandCodec`, and their default profiles are
unchanged. Nothing in this candidate has been deployed.

## Explicit wire and profile

`RetentionWireV3` uses a distinct magic (`0x564d5733`) and version 3 with a
4,096-byte request cap. Every request has the exact service-profile SHA-256,
lineage, transport correlation, and one operation:

- `Business(Command)`;
- `ArchiveCommit(MaintenanceIdentity, ArchiveAck)`;
- `EventAck(MaintenanceIdentity, throughEventSeq)`;
- read-only `Position`.

Maintenance identity is `(ASCII producer[1..48], positive requestSeq)` in its own
permanent namespace. Transport correlation never participates in idempotency.
The service profile fixes the core profile plus all outbox, maintenance registry,
cache, journal and combined-snapshot bounds. An archive descriptor still carries
its **core** profile fingerprint; the outer scope carries the **service** profile
fingerprint. Both must match their respective registered contracts.

Business command fields deliberately reuse the existing V2 command encoding
inside this new envelope, with nested correlation zero and only Deposit, Place
and Cancel allowed. Nested queries or legacy maintenance opcodes are rejected.
Canonical re-encoding rejects alternative tags/enum representations, malformed
UTF-8, trailing bytes and incorrect lengths. This is representation reuse, not
implicit acceptance of a V2 outer envelope. The core independently enforces its
structured `v3:account:producer:requestSeq` Place identity. Nullable invalid
business enums remain representable and receive the core's business rejection.
Direct in-process requests also pass the bounded encoder before admission.

## Two nonmutating admission layers

`RetentionEngineV3.previewAdmission(command)` returns a privately constructed,
one-use token with the complete immutable command, exact event count and
conservative full-history byte reservation. It is tied to its engine instance,
current business sequence, core maintenance sequence and actual core generation.
`apply(token)` rejects foreign, consumed or stale tokens before mutation. A real
business mutation or effective compaction invalidates previous tokens. Exact
retries/conflicts/invalid identities produce zero new events and reserve no fresh
history. Existing convenience `execute(command)` performs preview then apply.
This API does not change default V2 behavior or encoding.

`RetentionServiceV3.previewAdmission(request)` jointly checks core history and
outbox event capacity, or maintenance journal and permanent-producer capacity,
and application-counter exhaustion. Its private token also binds the service
instance and application-mutation generation. A no-op EventAck, business replay,
conflict or stale result invalidates a previously prepared service token even
when the core business and maintenance sequences do not change. A token cannot
cross restore boundaries. Every service mutation, preview and snapshot must run
on the thread that created or restored that service instance.

**Counter contract:** applicationMutation increments once for an envelope that
passes service admission and enters deterministic apply. This includes accepted
business commands, business rejections, retries, conflicts, stale results,
invalid business identities, and admitted maintenance replays/rejections.
Read-only queries/fetches/prepared exports do not increment it. Wrong scope,
malformed wire, resource/counter admission rejection, and stale/foreign/consumed
tokens do not increment it or change state. The counter is not an Aeron log
position, not a count of first accepted Places, and not a business command
sequence. First accepted Places remain the core's independent accepted counter.

## Independent maintenance and event cursors

Every admitted maintenance attempt retains its full operation and result in a
SHA-chained journal, including replay/conflict/stale attempts. A fresh maintenance
identity advances its permanent high-water even if its validly framed payload is
rejected. The bounded per-producer/global retry cache stores complete original
operations and results. Same cached identity plus exact payload returns the
original result with a replay marker; changed payload conflicts; an evicted old
identity is stale and never executes. Cache eviction never frees producer slots
or permits a high-water reset. Producer capacity is a lifetime bound.

ArchiveCommit invokes only the core's digest-matching prefix compaction. It does
not acknowledge event projection. EventAck advances only the retained outbox
cursor; it does not compact hot orders or full business history. The same latest
core ArchiveAck under a new maintenance request identity remains an effective
core no-op, although it is a fresh admitted service mutation/journal record.
The exact original maintenance request can still replay its original result.
Rejected ACKs change neither export cursor.

The journal has independent record-count and actual serialized-byte limits.
The retained byte accounting includes both 64-hex chain strings and their UTF
length fields. Admission reserves the complete bounded operation plus 1,024
bytes for the journal frame and bounded result before invoking maintenance.
There is **no journal eviction or journal-archive ACK operation in this phase**.
A full maintenance journal rejects further maintenance before any mutation,
even a replay attempt. Business history and the outbox independently backpressure
as their own bounds fill. This finite prototype does not promise indefinite
operation. An internal invariant/proof failure is fatal; transactional rollback
for JVM OOM or implementation bugs is not claimed.

Constructing or applying ArchiveAck proves only the deterministic core prefix
and the caller's explicit assertion. The service performs no external disk I/O
and cannot establish archive durability, PG commit, result-resolution floors,
client UNKNOWN resolution, or safe native-log deletion.

## Combined checkpoint and recovery checks

A separate snapshot magic (`0x564d5333`), format version 1 and contract string
contain the registered service profile, lineage, full V3 core checkpoint,
retained outbox, applicationMutation, every permanent maintenance high-water,
complete bounded retry cache, and full maintenance journal. The profile rejects
an unsafe conservative combined-size upper bound at construction. Snapshots
remain whole byte arrays with a maximum 64 MiB cap; this is not streaming.

Restore requires an expected profile and lineage, checks the whole checksum,
collection/blob limits and exact canonical roundtrip, and rejects implicit
legacy/core-only restore. It independently replays the journal's maintenance
metadata through a temporary bounded retry cache. This derives exact permanent
high-waters, cache contents/eviction, original replay/conflict/stale outcomes,
effective core maintenance count/archive cut/hash, and event-projection cursor.
Those anchors must equal the restored core/outbox. It also requires
`applicationMutation >= businessSeq + journalRecords` without overflowing.
Deleting cache/journal/producer sections and merely recomputing the outer SHA is
therefore rejected when the retained core/export anchors prove those operations.
This is consistency checking, not an authenticated external anti-rollback anchor;
a different complete valid checkpoint still needs external lineage/checkpoint
selection and durability proof.

## Local validation and next boundary

New tests cover both admission layers, scope and cross-version rejection,
complete maintenance identity semantics, separate export cursors, journal count/
byte/producer limits, mid-lineage combined restore and continuation, rehashed
semantic corruption, and a small continuous trace against the uncompacted legacy
matching reference. A 10,000-record tiny-profile test verifies the exact journal
serialization budget and snapshot roundtrip at its declared boundary. It is a
maintenance-byte-accounting test, not a throughput or cumulative-order result.
The original V2 prefix golden still checks the default engine and snapshot bytes.

Next work requires a separate explicit node profile, bounded replies and prepared
export chunks, replicated journal archive/ACK with external read-back verification,
combined streaming checkpoints, real framework log-position binding, a result
resolution floor/holes, and local replicated failure recovery. Only after those
close can a separately registered one-lineage endurance run establish cumulative
order counts. No million/100M, Cluster replication, external durability or
performance claim follows from these in-process tests.
