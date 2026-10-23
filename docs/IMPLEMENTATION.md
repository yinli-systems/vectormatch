# Implementation contract

## Scope

One simulated BASE/QUOTE market initially. GTC and IOC limit orders, cancel, partial fills, maker-price execution, integer balances, reservations, settlement, idempotency, snapshots, market snapshots and deltas.

No performance number is a product guarantee. Development-machine results are labelled local. Three processes on one host demonstrate process recovery, not machine fault tolerance.

## Authoritative state

Balances, reservations, order books, request deduplication and output events belong to one deterministic state machine. The database is an asynchronous projection. Stateful checks run in the engine even when the gateway has already checked a request.

## Result semantics

An execution result describes an applied command. Local and replicated modes must be explicitly distinguished. Successful transport submission is not a commit. Timeouts require status lookup or retry of the same identity.

## Milestones

1. Executable deterministic core with independent accounting and replay checks.
2. A local, journaled workbench with a real API, WebSocket feed and truthful diagnostics.
3. Three-node Aeron execution with snapshots and tested process-failure recovery.
4. Reliable event export, PostgreSQL projections and cursor recovery.
5. Open-loop load generation, HDR histories, fault timelines and reproducible reports.
6. Market sharding with isolated funding pools and larger connection tests.

## Required evidence

Source revision; exact dependencies; seed and command trace; workload composition; meaningful successful operation counts; planned versus actual send rates; p50/p95/p99/p99.9 and sample sizes; timeout and rejection counts; persistence configuration; CPU, memory, disk and network consumption; invariant-checker results; raw artifacts.

## Safety and bounds

Integer multiplication is checked. Input size, account count, outstanding orders, event retention and connection queues are bounded. Slow consumers resynchronize instead of accumulating unbounded memory. Public market sequencing is separate from private account events. Snapshot format has a version and integrity validation.

