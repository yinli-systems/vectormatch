# Continuous endurance toward 100M accepted orders

This is an implementation plan based on the current source, not a completed benchmark. The immediate CPU experiment remains fixed-page32 read8/32/8/32; none of the changes below belongs in that fixed-factor comparison.

The three targets are separate:100M fresh accepted orders in one continuous lineage,100M accepted orders per second, and100M simultaneous physical connections. Completing the first does not establish either of the others. Multiple reset lineages, virtual workers, read RPCs, replayed results and event fanout must not be relabelled fresh accepted orders or physical connections.

## Current source limits

`RetentionCapacityPlanV3` rejects arrivals above350,000. The finite batch profile has4,096 maintenance-journal records,4MiB journal bytes and a64MiB combined snapshot bound. The planner permits1,024 total writer files including receipts. The service appends an entry even for replay/conflict/stale maintenance outcomes, refuses a full journal without eviction, and validates its cursor/cache/high-water projection by replaying the entire journal from genesis.

At3,072 commands per cut,100,000,000 fresh orders plus3 setup commands need32,553 prospective maintenance cycles. Two ACK operations per cycle mean65,106 journal mutations without extra offers, or260,424 records under the four-offer envelope. Two payloads and their receipts per cycle imply130,212 files. These are arithmetic requirements, not observed runs; increasing only MAX_ARRIVALS would invalidate the bounded-state/storage admission assumptions.

## Separate V4 journal anchor

Introduce an opt-in version and keep V3 modes and snapshot decoding unchanged. A bounded journal anchor must retain the previous anchor hash, cut mutation, cumulative maintenance-mutation count, retained suffix starting point, core maintenance sequence, history command cut/hash, event-export cursor, latest effective archive acknowledgement, permanent producer high-water marks and complete still-retained maintenance cache entries. Canonical encoding and profile/lineage identity are mandatory.

An explicit replicated roll operation derives its prospective anchor from current deterministic state. It must compare the requested cut/hash/frontier against that state; it must not accept client-supplied arbitrary cache/cursor state. The old prefix remains until admission, verified durable archive/event frontiers and the roll outcome are complete. Keep headroom for the roll command and its possible original-identity replay before a full journal can block recovery.

The anchor must account for its own command/result without recursion: define an explicit before-roll cut and retain the roll record as the first suffix entry. All subsequent roll operations chain to the previous anchor. Permanent producer sequence high-water marks and retained original results survive a roll, so old identities replay identically, conflict deterministically, or return explicit STALE without executing again. Counter overflow and insufficient anchor/suffix budget fail before mutation.

Snapshot v2 serializes the anchor and retained suffix with strict lengths and canonical hashes. Invariant checking starts from the anchor's cursor/cache projection and replays only the suffix. Replace any equation using retained journal length as lifetime maintenance count with the explicit cumulative maintenance count. Existing core/order/outbox bounds continue to apply. A hash/checksum detects corruption; it is not an independent matching oracle or a Byzantine-authenticity guarantee.

## Streaming source and evidence

Use a monotonic absolute64-bit arrival/order index and one lineage across all segments. Segment boundaries do not reset producer request sequences, accepted-place count, server command/event cursors, account state, journal anchor chain or arrival clock. Bound in-memory pending work and samples independently of total lifetime volume.

Preserve every outcome, including observed/final UNKNOWN, rejection, not-sent, retries and replay flags. A streamed ledger binds each raw segment's exact byte SHA, size, first/last absolute arrival, command/event frontiers, prior-segment hash, configuration/artifact fingerprint and original physical publications/callbacks. Its summary reconciles every arrival once; it cannot replace missing raw bodies. Preserve failed partial segments explicitly.

Rotation requires independent full readback and an explicit retention receipt before local copies are retired. Filesystem FUSE receipts remain archival evidence rather than proof of crash durability. Active write/force/readback needed for destructive ACK remains on the admitted runtime filesystem. Account for compressed upload/download and retained native logs before starting the campaign; do not assume compression ratios or silently discard evidence to fit a budget. The currently authorised private repo/raw-evidence destination must be honoured; an alternate artifact destination needs an explicit agreed destination.

## Correctness qualification before endurance

1. Compare anchored and unanchored services on the same generated command stream, including boundary duplicate/conflict/stale identities and out-of-order completions. Compare full canonical business state, counters, outbox and retained results after every roll.
2. Inject failure before archive force, during readback, before/after each ACK and before/after roll admission/application/snapshot publication. No failed evidence path may authorise deletion or renew original permits.
3. Restore actual binary service snapshots into a cold application, resume the same lineage and retry original identities. Three matching log messages alone do not establish this recovery proof.
4. Cover malformed anchors, truncated/oversized fields, broken previous hashes, wrong profile/lineage, missing producer high-water/cache entries, overflow, journal headroom exhaustion and old-version decoding. Retain each failed attempt.
5. Qualify new homogeneous Linux JAR/class origins and strict native/raw collection on the new artifact before any performance or100M claim. Preserve fixed leader, replication/sync, page/window and durability semantics across comparisons.

## Endurance and capacity acceptance

Start with one continuous lineage through1M,10M and100M fresh accepted orders. Report the cumulative count plus each fixed-duration window's offered/accepted rate, all-arrival latency percentiles, scheduling lateness, backlog, UNKNOWN, rejection/not-sent, CPU/GC, memory, retained journal/outbox occupancy and evidence growth. Check full frontier/ledger/canonical closure at boundaries and after final cold recovery. A segment restart is a failure/recovery event, not a new reset lineage hidden in a total.

Then run separate fixed-configuration open-loop capacity curves and repeated trials. The sustained limit is the highest admitted offered rate that remains stable for the specified duration and meets the stated tail-latency/error policy; peak completions during backlog drain are not steady throughput. Report p99 from scheduled arrival, not only from dispatch or successful samples.

The current container's memory cgroup is64,000,000,000bytes. For100M physical connections that is only640bytes per connection before application, kernel buffers, TLS and replication state. Measure actual per-connection cost and partition across real hosts before claiming feasibility.100M orders/s similarly needs measured independently partitionable books, per-book sequencing and cross-shard risk/account semantics; virtual users or multiplying a single shard result is not an executed aggregate benchmark.
