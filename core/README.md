# Deterministic matching core

`io.vectormatch.core.MatchingEngine` is a single-thread-confined state machine.
It has no network, database, system-clock, random-number, or runtime library
dependency. This module does **not** itself provide replication or durability;
the cluster module supplies ordered committed commands and persists snapshots.

## Contract

- One market, BASE/QUOTE. Prices and quantities are positive `long` integers.
  One `priceTicks * quantityLots` equals quote units. Monetary arithmetic never
  uses floating point.
- Limit GTC/IOC orders. Best price first, then engine acceptance order at the
  same price. Trades execute at the resting maker's price.
- Both sides reserve the entire limit-order requirement before matching. Buyers
  receive price-improvement refunds immediately. Cancels/IOC expiry release the
  unfilled reservation. Fees, withdrawals, market orders and amendments are not
  implemented. Amendment can be expressed as cancel plus a new order.
- At the first crossing maker belonging to the taker, self-trade prevention
  expires the incoming residual; earlier legitimate fills remain. It never skips
  an own order to jump queue priority, and cannot leave a crossed resting book.
- Deposits are simulated issuance. Aggregate supply of each asset is bounded by
  `Long.MAX_VALUE`; orders with overflowing notionals are rejected. Aggregate
  supply bounds make all subsequent conservation-preserving transfers safe.
- Identity is `(accountId, producerId, requestSeq)`. Positive sequence gaps are
  allowed; a later accepted sequence permanently closes earlier gaps. Business
  rejections consume sequence numbers and are cached as well as successes.
- A retained retry returns the identical result, `replayed=true`, and **no new
  events**. A changed payload for the same retained key is a conflict. An evicted
  old sequence returns `STALE_SEQUENCE` and is never executed again.
- Caches are bounded per producer and globally. Global eviction removes the
  oldest command result deterministically. Producer high-water marks remain
  until the engine is replaced, including when all of their results are evicted.
- Account, producer, retained-order and cached-result caps are explicit `Limits`.
  History is intentionally retained, so hitting the order cap rejects new
  orders. Existing orders can still be cancelled. Provision a fresh simulation
  before starting a new long run; do not silently reset funds mid-run.
- `eventSeq` counts all newly emitted events. `marketSeq` is zero on a private
  deposit and increases continuously on public order/trade events. Events are
  facts within a command; query views represent the final command state.
- A successful result means this engine applied the operation. External
  durability, database projection and downstream delivery are separate contracts.

```java
MatchingEngine engine = new MatchingEngine();
engine.execute(new MatchingEngine.Deposit(1, "fund", 1,
    MatchingEngine.Asset.QUOTE, 1_000_000));
MatchingEngine.Execution outcome = engine.execute(new MatchingEngine.Place(
    1, "browser", 1, "my-first-order", MatchingEngine.Side.BUY,
    100, 10, MatchingEngine.TimeInForce.GTC));
MatchingEngine recovered = MatchingEngine.restore(engine.snapshot());
assert engine.stateHash().equals(recovered.stateHash());
```

## Snapshot and verification

Versioned canonical binary snapshots contain balances, complete retained orders,
producer high-water marks, retained command payloads/results, all sequence
numbers, supply totals, and configured limits. Collections are serialized in
stable order; book indexes and the global eviction index are rebuilt on restore.
Text is encoded as UTF-16 code units to preserve exact Java string identity.
A SHA-256 footer detects accidental corruption; this is an integrity checksum,
not an authentication signature. Do not accept untrusted snapshots as authority.

`stateHash()` hashes the complete snapshot, including replay behavior. Snapshot
round-tripping and continued execution must produce identical states and events.
`checkInvariants()` performs expensive diagnostics outside the hot path: supply
conservation, nonnegative balances, reservations equal active-order requirements,
valid order state and an uncrossed book.

Tests cover price/time priority, maker-price fills, price improvement, IOC,
self-trade prevention, cancels, ownership, overflow, identity conflicts, business
rejection replay, global/per-producer eviction, capacity refusal, event sequence
continuity and corrupt snapshots. A separate flat-list reference model compares
generated operation traces, every account, all order states and aggregated book
levels. These tests establish correctness evidence, not performance claims.
