# Anchored retention V4: implementation qualification

This is an opt-in, in-process state-machine prototype. It is not connected to the default Aeron service, the asynchronous capacity runner, or production trading. It removes a finite maintenance-history limit without resetting business state. It does not establish a 100M-order result, a capacity improvement, or physical disk durability.

`AnchoredRetentionServiceV4` and `AnchoredRetentionWireV4` use separate envelopes, profile fingerprints and snapshot version 2. V3 code and decoding remain unchanged. The existing asynchronous file-work coordinator continues to use V3; the names describe different parts of the V4 work.

## Roll contract

A fresh `JournalRoll` claims the current application mutation, lifetime maintenance count, prior anchor hash, journal head, archive cut and event-export cursor. The owner derives the immutable anchor from its own state. It accepts a roll only when both pending business history and the outbox are empty, the journal is nonempty, and every claimed frontier matches. Archive and event ACKs remain the caller's explicit assertion of verified external retention. A checksum is not an external storage receipt.

The anchor retains permanent maintenance-producer high-water marks, every currently cached original operation/result, the latest effective archive ACK, export/compaction cursors and prior chain hashes. It represents the **before-roll** state. The roll's own command/result is the first retained suffix record. Its original identity can later replay, conflict, or become explicitly stale without another roll or any repeated business execution.

Ordinary maintenance must leave one record and a conservative byte reserve. A valid fresh roll can consume this boundary; invalid rolls cannot reclaim it. The suffix immediately after a roll also has retry headroom. An old retry at a subsequently full boundary may receive nonmutating admission backpressure; this is not a successful replay. Counter exhaustion and stale admission tokens fail before mutation.

Snapshot restoration verifies bounded canonical encodings, checksums, profile/lineage, structural anchor invariants and the complete retained suffix against the anchor projection. It does not authenticate an adversarially replaced entire history. Independent archived prefixes and receipts are required to audit the full chain.

## Qualification

The local targeted run passes **41 tests**: 10 anchored-service tests, 14 unchanged V3-service tests and 17 existing asynchronous-maintenance tests. XML and the failed initial fixture attempt are in `evidence/2026-10-27/anchored-v4-qualification-r1/`.

The anchored comparison executes 250 rolls, 500 fresh accepted orders and 752 fresh business commands, restoring canonical binary snapshots every 11 cycles. Every business reply and core snapshot matches an unanchored V3 reference service. This checks retention equivalence, not an independent matching algorithm. Additional cases cover both export fences, reserved headroom, before/after-roll recovery, original replay/conflict/stale identities, stale tokens, wrong anchor hashes, defensive copies, truncated snapshots, cross-version rejection and structurally invalid anchors with recomputed checksums.

## Next acceptance gates

1. Native full-readback evidence and real matching through at least 1M accepted orders in one lineage, with no renewal of producer IDs, balances or counters at retention boundaries.
2. Bounded segment storage and recoverable evidence receipts before progressing through 10M and 100M. Full raw commands/results/events must remain available.
3. Integrate the anchored protocol with the replicated service, owner and asynchronous coordinator; qualify retry/unknown and leader-failure semantics before changing endurance claims.
4. Separate same-artifact PAUSE/CONTINUE ABAB and sustained capacity work. Existing failed 6k/s trials remain failures; this state-machine change supplies no 7k–8k/s result.
5. Independent hosts and physical storage-failure recovery require separate infrastructure and measurements.
