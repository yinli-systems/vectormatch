# V4 asynchronous maintenance: finite capacity results

Application source: `6716f74aceb1eb8bb53c4f8ced6cb9630cd1c5da`. Actual Linux artifact: `2ea38974a2f57f6a5f6817b7063a7496fdfff0e171943cb5b2d3acaa5b8a0b8f`.

The full Linux run passed 435 Java tests and 197 Python tests, including 11 PostgreSQL integration tests, with no failure, error or skip. All five Java test tasks actually executed in a fresh Gradle home without result cache. All 261 application JAR classes match actual CI compiled bodies, and all 454 CI/runtime JDK file bodies match. The stricter independent checker passed eight semantic checks. Hosted account billing remains unresolved; this successful workflow used the existing prepaid CPU.

The [prospective protocol](ASYNC_CAPACITY_PROTOCOL_V4.md) fixes the rates, policies, budgets and decision criteria before cloud execution. Each complete raw point is attached to the same private repository with a committed SHA-256 and member inventory; full authenticated re-download and every-member verification precede progression. All previous 73 runs and 32 capacity cohorts remain unchanged. V3, encoder and V4 results remain separate configurations.

## 500 scheduled arrivals/s

Two PAUSE/CONTINUE pairs use the same compiled artifact, leader 0, sync 2, three JVMs on one physical CPU, 127 active load producers, batch 4, cut 1536, read window 32, event page 32 and chunk 6144. Every arm uses a fresh lineage and an independent 20-second arrival clock. Statistics exclude the three setup commands.

| Arm | Policy | Accepted/planned | In-window goodput/s | End-to-end p50 ms | End-to-end p99 ms | Post-offer p99 ms | notSent | UNKNOWN final |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | PAUSE | 10000/10000 | 499.8 | 9.349 | 286.782 | 31.669 | 0 | 0 |
| D1 | CONTINUE | 10000/10000 | 499.8 | 8.172 | 65.651 | 11.935 | 0 | 0 |
| C2 | PAUSE | 10000/10000 | 499.75 | 8.194 | 175.014 | 11.671 | 0 | 0 |
| D2 | CONTINUE | 10000/10000 | 499.85 | 8.123 | 59.925 | 11.242 | 0 | 0 |

Both pairs satisfy the registered direction criterion: lower all-arrival p99, no worse post-offer p99, and no lower in-window goodput. Global p99 falls by 77.11% in C1/D1 and 65.76% in C2/D2. Post-offer p99 falls by 62.31% and 3.68%; in-window goodput changes by 0.00 and +0.10 orders/s. These are two finite comparisons, not a statistical significance claim.

All four arms pass the prospective finite acceptance gate. Every scheduled order is accounted for, every accepted IOC executes one unique one-unit trade, and there are no rejections, notSent or observed/final unknown outcomes. The 10 ms end-to-end p99 target remains unmet in both CONTINUE arms.

Independent Python parsing binds each arrival identity, command hash and batch index to observed original requests/results, unique trade events, complete exported event sequences, original deadlines, read credits and forced/readback receipts. The Java reference replays positive physical offers in their actual order and checks every received reply through the same adapter; it is not an independent matching algorithm. All three snapshots and actual cold restores agree with each arm's complete canonical state.

This establishes finite same-host observations. It does not establish sustained capacity, a hard real-time or millisecond SLA, independent host/storage durability, new client orders after cold restore, continuous 100M lineage, HFT endorsement or funded external trading. No default performance promotion follows. The next preregistered rate is 1,000/s after this review is privately published.
