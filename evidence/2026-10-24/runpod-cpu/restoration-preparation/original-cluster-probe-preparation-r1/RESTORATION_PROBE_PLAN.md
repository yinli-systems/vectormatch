# Original e1db cluster restoration probe

This preparation is local only. No SSH, cloud operation, PostgreSQL operation, Aeron process, node, gateway or projector has been started. Original backup archives and both original/capacity worktrees remain unchanged. `ProbeOriginalRestoration` is compiled but has never been executed.

## Verified starting point

Original application source is `e1db2e755a834234efb60b7a1ed291b31ce33c16`, tree `b831a37dbc24ca686a2df87b065c879394c5e04f`. Ten restoration-relevant source files match `app-restore-build/BUILD_PROVENANCE.json`; the worktree is clean. The existing rebuilt bundle is a same-source rebuild. The original cluster JAR was not retained, so original cluster binary identity cannot be claimed. See the prior build provenance for reused compile cache and JAR-container differences.

The exact runtime Aeron 1.53.3 JAR SHA-256 is `4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2`. Runtime JAR, helper source/class and inspection hashes are frozen in `FROZEN_PREPARATION.json`.

The three `nodeN-pre-stop-state.json` inventories prove stopped original state and exact files; they do not record launch settings. Actual launch arguments in `evidence/2026-10-23/runpod-cluster/egress-final-release/nodeN.json` bind all three nodes to the e1db release, sync level 2, outbox capacity 65536, port base 19000, MTU 1248 and `-Xmx1g`. Their exact source hashes and proposed clone-specific arguments are retained in `PROPOSED_NODE_ARGUMENTS.json`.

## Offline three-replica checkpoint result

`inspect-original-service-checkpoints.py` has executed locally against all three original compressed backups. It verified each whole compressed archive SHA and the entire selected 134217728-byte recording `archive/7-0.rec` against the stopped inventory. It retained only the first 1776256 bytes through the terminal zero frame; every remaining byte in the original recording is zero. No full native tree was extracted.

The helper validates unfragmented Aeron DATA framing, service BEGIN/END markers, checkpoint identity, chunk sequence/bounds, original SnapshotTransport CRC32C, independent ClusterStateSnapshot SHA, original MatchingEngine decoder and exact canonical round trip. Eleven admission/corruption guards passed before the actual inspection.

All three latest service checkpoints are byte-identical after canonical decoding:

| Field | All three nodes |
|---|---:|
| Service recording | 7 |
| Leadership term | 9 |
| Checkpoint log position | 4643360 |
| Command sequence | 4539 |
| Event sequence / exported sequence | 6106 / 6106 |
| Public market sequence | 6086 |
| Outbox capacity / pending events | 65536 / 0 |
| Accounts / retained orders | 5 / 3105 |

Canonical engine SHA: `4450df5dc1a6662fec3c8addd55452657ee6fd1ccd0aeae92cc6dbb7e18c780b`.

Combined core/outbox checkpoint SHA: `dcc1bc3dfbdc5bc851f17b5a6dc96fecfd8d319b04ba0f3df26142d6ae5b7cee`.

This proves the latest checkpoint contents. It does not prove post-checkpoint consensus-log replay, current CPU node recovery, PostgreSQL correspondence, independent hosts or performance.

## Pinned membership behavior

The exact JAR bytecode and tag-pinned primary source agree:

- ConsensusModuleAgent constructs its final active-members array from `ctx.clusterMembers()`; bytecode assigns it once.
- The removed `clusterMembersIgnoreSnapshot` option is absent from the current Context API.
- ConsensusModuleSnapshotAdapter retains the legacy ClusterMembersDecoder, template 106, but explicitly ignores its record. In this JAR, switch case 106 jumps directly to the common return path; the snapshot listener has no membership callback.

Therefore the legacy snapshot membership record does not override newly configured loopback members in this pinned release. This is configuration reasoning backed by the actual artifact; successful startup and active membership must still be measured. Primary sources are preserved with URL and SHA receipts:

- [ConsensusModuleAgent, tag 1.53.3](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModuleAgent.java)
- [ConsensusModuleSnapshotAdapter, tag 1.53.3](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModuleSnapshotAdapter.java)
- [ConsensusModuleSnapshotListener, tag 1.53.3](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModuleSnapshotListener.java)

One metadata lookup initially used the nonexistent class name `ConsensusModuleSnapshotLoader`; its failure is recorded. A first static assertion incorrectly assumed no legacy membership decoder existed; its correction is recorded. Neither attempt started a node or changed data.

## Minimal future root-controlled probe

1. Freeze/upload the existing e1db bundle plus the separately named helper classes into a new release/preparation directory. Verify remote whole-file and runtime artifact SHA before invocation. Keep the original compressed archives, source inventories, local prefixes and clean restoration receipt.
2. Freshly verify no capacity benchmark or other restoration node owns these native paths; no unrelated workload owns UDP ports 19001–19005, 19101–19105 or 19201–19205. Confirm loopback bindability, adequate resources, original clone SHA closure and absence of active/stale unowned driver state. Preserve every new failed attempt independently; do not clear a driver directory automatically.
3. Start only the three unchanged e1db ClusterNodeMain processes, using the clone-specific parent arguments from `PROPOSED_NODE_ARGUMENTS.json`. For node N, state-dir is `/opt/vectormatch-cpu/restorations/original-native-r1/nodeN/runtime/cloud-20261023-01`; ClusterNodeMain appends `node-N`. Use explicit sync2, outbox65536, loopback CSV and MTU1248. Do not set a new state profile, appoint a leader, alter recording logs, seed/reset a lineage or initialize a fresh state directory. The normal election may choose any valid leader.
4. Root's process supervisor must bind each owned PID to startTicks and exact argv SHA, enforce a finite startup/probe deadline and write logs under a new owned attempt directory. Stop only an exact still-matching owned process; no broad process-name kills. Keep gateway, projector, generators and `RemoteClusterExperiment run/verify` stopped. The latter modes execute business/retry/conflict operations. Its `state` mode is only a position probe and does not prove canonical bytes.
5. Validate all three startup logs show the frozen restored checkpoint, active membership lists only the configured loopback peer endpoints and all nodes converge to a leader. Original snapshots also contain two old client-session response channels. These are separate from cluster membership and may retain old addresses until those sessions expire; record this separately and do not claim every restored session address was rewritten by the peer CSV.
6. Invoke the compiled `io.vectormatch.cluster.ProbeOriginalRestoration` once with a fresh owned output directory. Its explicit topology/client are loopback, port base19000, MTU1248. It calls state, reads canonical bytes, fetches **6107/count1** for frontier-only empty events, reads canonical bytes again, then state. It requires exact command4539/event6106/market6086, canonical SHA, exported6106, pending0 and unchanged before/after state. It never submits Deposit/Place/Cancel, ACK, bootstrap, replayed unknown or maintenance operation. Nine static guards and compilation pass; no runtime result exists yet.
7. Compare the frozen read-only PostgreSQL audit for **`runpod-cloud-20261023-01`** with source exported6106/last6106, durable cursor6106, public market6086 and retained row/payload checks. Do not call PostgresEventStore's constructor merely to inspect it: it creates schema objects. Do not force a cursor, reset clusterId, ACK an empty range or start ReliableProjector as part of this verification. Equality of frontiers plus separately validated PG payload hashes is not a cryptographic proof that the entire historical exported event stream matches this checkpoint: the outbox has already reclaimed every event. Full historical correspondence would require a separately reviewed log/event replay comparison.
8. Stop the owned probe and nodes after the bounded recovery attempt; retain logs, actual artifact inventory, PID/start receipts, before/after inventories and every changed native file. Original backups remain unchanged. Recovery and query sessions append consensus metadata even when business core and export frontier remain unchanged; do not label the native working clone read-only.

The leader probe returns one leader's response. Pinned ClusteredServiceAgent bytecode returns a dummy success without publication for follower ClientSession.offer. Repeating a client query or connecting to different seeds does **not** independently prove three replica canonical states.

## Three current replica canonical states after replay

Preferred extension keeps MatchingClusteredService byte-identical: after the quiescent read-only probe, root can prepare a separately frozen maintenance-checkpoint step using pinned `ClusterTool.snapshot(File, PrintStream)` on the current leader. This is an explicit cluster control mutation that appends snapshot metadata and writes new recordings; it applies no business command and sends no export ACK. Then verify a new complete service0/consensus-1 snapshot pair at the same term/log position on every replica, stop the exact owned nodes, preserve all new native files, and decode each new service snapshot independently.

The current offline helper is deliberately hard-bound to original recording7/term9/position4643360. It must not be passed a newly created snapshot and silently treated as a generic recovery verifier. Prepare a new manifest-bound reader for the newly observed recording IDs, term and position; retain the original helper and proof. Require all three new core and combined outbox bytes to match each other and the original canonical baseline. This extension is a plan; no control toggle, new snapshot or wrapper service has been executed here.

An alternative observer service would change the node harness and require its own functional equivalence review. It is unnecessary for the minimal initial boot probe.

## Resource/admission budget

- Preserve original three-node archives and clean clone. Current sparse logical native state is not evidence of its physical allocation or available headroom; measure fresh `statvfs`/allocated blocks before launch.
- Same original heap setting: three JVM heaps at most 3GiB total, plus a 128MiB probe heap. Admit only with at least 8GiB cgroup memory headroom and separately sample RSS/native Aeron mappings; this is admission allowance, not a hard resident-memory bound.
- Require at least 3GiB root-filesystem free before boot. Bundle staging is approximately 36.9MB; helper/class artifacts are small. Allow up to 512MiB additional allocated blocks for driver/log/control work and stop at that owned-path growth limit or below 2.5GiB free. These are proposed supervisor bounds; this preparation has not enforced them remotely.
- Three members × five fixed UDP ports = 15 peer endpoints, plus bounded dynamic client/archive response endpoints. Client connections create session metadata. No port is exposed externally by this plan.
- Suggested root supervisor wall admission: 120s to establish recovery, 180s maximum probe process (client connect20s, two canonical reads40s each, other reads10s each), finite owned cleanup. Blocking kernel I/O is not claimed to obey Java cancellation deadlines.
- Any maintenance snapshots may add six large **logical** sparse segment files; reserve physical growth based on measured allocated bytes and never fully materialize multi-GiB archive zeros during collection. Do not run a capacity benchmark concurrently.

Actual offline preparation artifact inventory is in `FROZEN_PREPARATION.json`; all future cloud execution remains pending root review and a frozen controller.
