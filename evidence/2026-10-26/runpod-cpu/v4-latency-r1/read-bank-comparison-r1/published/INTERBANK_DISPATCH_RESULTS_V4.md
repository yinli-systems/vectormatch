# Closed versus bounded inter-bank dispatch,agent100us fixed

[Prospective protocol](V4_AGENT_IDLE_PROTOCOL.md) · [Complete Linux/source/loaded-origin qualification](../evidence/2026-10-26/runpod-cpu/v4-latency-r1/linux-admission-r1/README.md).

All four safety/correctness gates passed. All finite gates passed: True. Both registered pair directions passed: False. Both candidates meet the10ms global p99 target: False. No default promotion.

| Arm | Actual agent cap ns | Actual read-bank policy | Accepted/planned | In-window goodput/s | Global p99 ms | Post-offer p99 ms | Read-yield turns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 100000 | CLOSED | 80000/80000 | 3993.45 | 60.758 | 12.599 | 0 |
| D1 | 100000 | BOUNDED_TURN | 80000/80000 | 3993.9 | 42.061 | 13.100 | 260 |
| C2 | 100000 | CLOSED | 80000/80000 | 3993.45 | 67.470 | 12.423 | 0 |
| D2 | 100000 | BOUNDED_TURN | 80000/80000 | 3994.95 | 47.816 | 13.367 | 260 |

Each finite arm retains all arrivals,physical publications/replies,trade/event prefixes,original permits,forced/readback receipts,three matching snapshots and actual cold restores. All six original/cold node processes and owner driver configured objects/factory consumptions are checked;these are not measured OS sleeps or private-agent-field readbacks. All recorded leader/term observations are0 and no client-observed leadership change occurs.

C1/D1: {"candidate": "d1", "control": "c1", "globalP99ChangeFraction": -0.30774138859017397, "inWindowAcceptedDifference": 9, "postOfferP99ChangeFraction": 0.03978115384752767, "registeredDirectionPassed": false}
C2/D2: {"candidate": "d2", "control": "c2", "globalP99ChangeFraction": -0.2913058727507918, "inWindowAcceptedDifference": 30, "postOfferP99ChangeFraction": 0.0760184293248336, "registeredDirectionPassed": false}

The criterion uses exact integer nanoseconds and in-window acceptance counts:both finite gates,at least10% lower global p99,no worse post-offer p99,and no lower in-window goodput. Conditional percentiles never replace undefined global p99. CPU is recorded separately per process over observed in-window samples;backlog sampling can miss short queues. Two repeats do not establish statistical significance or a sustained service level.

[Complete raw asset SHA/member references and comparison derivation](../evidence/2026-10-26/runpod-cpu/v4-latency-r1/read-bank-comparison-r1/README.md). Earlier artifact65c41d51 curves and the negative owner-poll experiment remain separate.
