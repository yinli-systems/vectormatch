# V3 Aeron adapter and local three-JVM correctness boundary

This isolated stage is based on `71199b16beea2ccad406bca98d4966faf3d8d0e2`.
It adds separate V3 node/client entries and a real Aeron service adapter for the
bounded service prototype. The previously tested core and service branch refs
remain unchanged. The default `ClusterNodeMain`, `MatchingClusteredService`,
`CommandCodec`, `ReplicatedOutbox`, `ClusterStateSnapshot` and `SnapshotTransport`
are not modified. This stage is local only. CPU capacity nodes and load artifacts
continue using their previously registered source/configuration.

## Requests, bounded replies and failure semantics

`RetentionReplyV3` has separate magic/version and an **8,192-byte complete encoded
envelope limit**, including scope, counters, UTF-8, archive descriptors and chunk
bytes. A State reply carries a bounded business Result or maintenance result,
replay marker and cursors. It never includes the full `Execution.events` list.
Position carries the combined-state SHA. Canonical decoding rejects cross-version
headers, noncanonical booleans, invalid text/enums/counters, truncation and trailing
bytes. An event reply has at most 16 events; an archive chunk has at most 3,072
bytes. Event text/result lengths are checked before encoding allocations.

V3 adds read-only FetchEvents, PrepareArchive and ArchiveChunk operations. These
do not enter application apply or consume business/maintenance identities. A
read-only response that cannot fit its complete bounded envelope returns a small
explicit error rather than truncating data. Wrong scope and invalid ranges also
produce bounded errors; malformed or non-V3 packets are dropped without mutation.
The old outer wire and V3 outer wire reject each other.

The adapter constructs or restores `RetentionServiceV3` in **onStart on the Aeron
service thread**. It does not construct writer-bound state on the node main
thread. Business/maintenance calls use the already tested joint admission and
identity rules. Resource rejection reports ADMISSION_BACKPRESSURE and does not
advance applicationMutation or business state. Reply offer uses at most three
ADMIN_ACTION retries. A lost/unaccepted reply is not a rollback: the result is
UNKNOWN to the caller, which must preserve the same complete business or
maintenance identity and payload when retrying.

`RetentionClientV3` owns one thread, session and inflight request. It retains at
most one matching reply, ignores retired correlations, and retries the identical
encoded request during one exchange. An encoding failure occurs before acquiring
the inflight slot. Timeout explicitly reports V3_UNKNOWN_RESULT; the client does
not replace a timed-out logical identity or claim its outcome was rejected. This
is a small correctness client, not a high-rate load generator or complete cold
result-resolution API. `readArchive` allocates only within the caller and
registered profile byte bound; its timeout is enforced on the subsequent
exchanges, rather than checked before that bounded allocation.

## Immutable archive prefix reads

PrepareArchive returns the core ArchiveAck plus total byte length. Its descriptor
binds core profile, lineage, first/end command cut, preceding/ending chain and
full payload SHA. The outer scope additionally binds the service profile. Every
chunk request repeats the complete descriptor, total length, offset and bounded
count. The adapter recomputes that same pending prefix; appending newer business
commands cannot change its bytes. A mismatch returns ARCHIVE_DESCRIPTOR_MISMATCH.
If an effective ACK has freed any of that original prefix, the response is
ARCHIVE_STALE. The caller must resolve/retry its original maintenance identity;
the server never claims freed bytes remain retrievable.

The client checks descriptor profile/lineage and the explicit profile/allocation
bound before allocating the complete bounded prefix, checks every chunk's exact
descriptor/offset/total, and verifies the final payload SHA. This phase still
materializes the bounded batch inside the core; it is not an unbounded streaming
exporter. A local smoke file write/read-back followed by ArchiveCommit is an
explicit test assertion, not proof of external archive durability. Event ACK and
full-history ArchiveCommit remain independent.

## Independent V3 checkpoint transport

The legacy SnapshotTransport accepts only 256/512 MiB outer limits. The new
RetentionSnapshotTransportV3 follows its chunk/CRC32C framing pattern with a
separate magic and the **actual service profile cap checked before allocation**.
The public prototype cap is at most 64 MiB; the local smoke profile uses 8 MiB.
Missing, reordered, truncated, corrupt, cross-version and over-profile chunks
fail closed. The inner combined snapshot retains its independent magic/contract,
profile/lineage, core/outbox, full maintenance journal/cache and cursor checks.
There is no V2 fallback or implicit migration.

## Separate loopback launcher and actual identity

RetentionNodeMainV3 accepts an explicit local-smoke-v3 profile, lineage, expected
profile SHA and expected code SHA. It supports only three 127.0.0.1 members with
MTU1248 and explicit sync0/2. The actual smoke argv uses `sync=2`, `-Xmx256m`, and appointed leader 0;
its registrations and each node-ready line retain that effective setting.
Sync0 is an accepted launcher option but was not the tested smoke mode. Neither
mode establishes an independent durable fault domain. Before creating or opening
state, the node verifies the expected hashes against its effective profile and
actual code sources. Code identity hashes every class in core/cluster class
directories (including nested classes and private codecs), or complete JARs,
plus the pinned Aeron/Agrona code sources. It is an actual binary inventory,
not a claim that a source label proves the loaded bytes.

A persistent V3 identity marker binds node, membership, code, profile, lineage and
sync setting. Old/unmarked/mismatching state is rejected. An active MediaDriver
is not deleted on start. The launcher is a separate entry and does not hot-change
default services. A code-distribution change requires an explicitly designed
migration rather than bypassing that marker.

## Local smoke and preserved evidence

RetentionAeronSmokeV3 creates a new directory and lineage, probes a random,
separated loopback UDP port range, and launches exactly three owned Java
processes. A port reservation race after probing is allowed to fail; it does not
silently choose a new lineage or retry the workload. Before launch it records
profile/code registration and the exact artifact inventory. Ready checks verify
each actual node PID, loaded code, effective profile and lineage, plus its service
ready record. All nodes use the same explicit controls.

The trace compares complete business results and business/event/market sequences
against an uncompacted matching reference. It exercises a multi-chunk immutable
prefix with an intervening append, exact maintenance replay, explicit stale bytes
after ACK, the complete bounded event stream, independent projection ACK,
three equal canonical combined checkpoints, full stop/cold restart of all three
nodes, identical restored hashes, and continuation with four first accepted
Places. Retries and maintenance are not counted as new Places. This does not
exercise leader loss, storage failure, external exporter failure, long-run
retention, throughput or cross-machine networking.

Evidence includes lossless framed reference inputs, full reference outcomes,
reference V2 canonical checkpoint bytes, prepared-prefix bytes, all node native
archive/cluster files, logs, per-generation PID/start/actual-command receipts,
artifact SHA inventory, all-node checkpoint/restore hashes and cleanup records.
Whole-tree archive manifests distinguish logical sparse-file bytes from actual
allocated bytes; restoring a gzip tar without sparse-aware extraction may require
its full logical disk size. No original state or previous attempt is deleted.
A failed partial restart is preserved and reported.

Cleanup registers each returned Process before fallible identity/receipt work,
checks actual start/command/arguments before signalling, waits for bounded TERM
then rechecks identity before bounded KILL, and records incomplete/unobservable
identities without signalling unrelated processes. Completion passes only if
both the functional trace and owned cleanup succeed. This is small local
functional evidence, not a cloud deployment, independent-machine replication,
external durability or million/100M proof.
