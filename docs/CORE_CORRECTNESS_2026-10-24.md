# Core sequence-safety and independent ledger audit (2026-10-24)

Status: **verified in a native Linux Java 21 run; no physical-SSD claim.**

## Reproduced failure and fix

A valid, SHA-256-checksummed V2 snapshot can carry event and market sequence counters near `Long.MAX_VALUE`. Before this patch, `MatchingEngine.execute` guarded `commandSeq` exhaustion but could accept a deposit or matching command that emitted events beyond `Long.MAX_VALUE`. This wrapped event identifiers into negative values. Three new, independently specified JUnit tests failed against the unmodified engine and passed after the patch.

The engine now applies a fail-closed, atomic preflight **before command sequence allocation, producer-cache writes, balance reservation, book mutation, and event emission**. The worst-case number of events for one placement is at most:

`1 ORDER_ACCEPTED + retained maker count TRADE + 1 ORDER_EXPIRED`.

Since the maker count is bounded above by the number of retained orders, the ordinary path checks only whether either counter is within `orders.size() + 2` of exhaustion. Only near that extreme boundary is `maximumEventsFor(command)` called to compute the exact event reservation. Rejected or replayed, zero-event commands preserve existing semantics.

`SequenceExhaustionTest` covers:

1. A private deposit using the final legal global event sequence, followed by a clean, side-effect-free rejection.
2. A fully exhausted restored engine rejecting the next event before mutation.
3. A crossing placement that would emit an acceptance plus two trades when only one event slot remains; the entire placement fails atomically, without touching resting orders or reserved funds.

The tests construct checksum-correct snapshot payloads with near-limit counters so they exercise the production `restore` and `execute` interfaces. They are **not** proof that an external attacker cannot tamper with a snapshot.

## Independently reconstructed event ledger

`EventLedgerAuditTest` uses a separate test-only, event-sourced double-entry ledger. It does **not** use the matching engine's private settlement, reservation, book, or snapshot implementation to calculate expected state. Its inputs are the public command, execution receipt, and emitted events.

It independently verifies:

- Exact contiguous global and market event sequences, with private deposits excluded from market numbering.
- No business events for cached retries, conflicts, stale sequences or business rejections.
- Deposit supply and per-account available/reserved balances.
- Acceptance reservation, buyer refunds at maker prices, seller proceeds, lot transfers, partial fills, expiry refunds and cancellations.
- Price-time priority, including the first crossing *own* resting order, by scanning all earlier active opposite orders.
- Every accepted order's remaining quantity/status, public order book and end-to-end asset conservation.
- Canonical snapshot restoration and continued state reconciliation.

The generated regression uses **four fixed seeds × 750 mixed commands** with deposits, BUY/SELL GTC/IOC orders, cancellations, valid retries, altered-payload retries, duplicate IDs, invalid quantities and notional overflow. It reconciles periodically and after restored snapshots. A second test deliberately corrupts a trade's maker execution price and requires the independent ledger to detect it.

This is a deterministic **economic event/accounting consistency oracle**, not a full independently deployed matching implementation. It cannot, by itself, prove that a business rejection *should* have been an acceptance; the existing flat-list `ReferenceModel` property suite continues to cover regular command-decision parity.

## Verification and open limits

Commands:

```bash
./gradlew :core:test --tests io.vectormatch.core.SequenceExhaustionTest --console=plain
./gradlew :core:test --tests io.vectormatch.core.EventLedgerAuditTest --console=plain
./gradlew :core:test --console=plain
./gradlew test --console=plain --no-daemon
```

Observed:

- Pre-fix reproduction: **3/3 new sequence-boundary tests failed**, as expected.
- Post-fix: all **3/3 sequence-boundary tests** pass.
- Independent event ledger: **2/2 tests** pass, including the deliberate tamper-negative case.
- Full core suite after both test additions: **47/47**, no failures, errors or skipped tests.
- Full Java project suite with the core fix: **BUILD SUCCESSFUL in 3m13s**. The combined JUnit report after the extra core tests registered **358 cases**, with **0 failures, 0 errors and 11 skipped integration cases**; thus **347 executed/passed**. The remaining skips must not be reported as passes.

The tests were run on a **single native Linux CPU container overlay**. They do not establish SSD power-loss durability, a multi-host failover guarantee, production trading compliance, or an independently deployed full matching oracle. The associated Pull Request remains a draft.
