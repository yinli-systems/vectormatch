# VectorMatch

**Deterministic execution. Recoverable state. Measured performance.**

A private engineering project exploring a limit-order matching engine, replicated execution, and real-time market data. Every capacity claim must link to its workload, hardware, durability settings, and raw results.

## Delivery principles

- Price-time priority, integer accounting, explicit reservation and settlement.
- A deterministic state machine owns balances, orders, deduplication, and events.
- A timeout is an unknown outcome, not permission to place a second order.
- Local execution, replicated execution, and market delivery are measured separately.
- Performance improvements must pass the same correctness checks as the baseline.

## Implementation status

Active development. The initial commits establish the executable core and local workbench; replicated durability and distributed capacity are reported only after their checks pass. See [the implementation contract](docs/IMPLEMENTATION.md).

## Toolchain

Java 21, Gradle, Aeron, Netty, React and TypeScript. Portable development tools live under `.tools/` and are never committed. Bootstrap instructions and exact verified versions are maintained with the implementation.

