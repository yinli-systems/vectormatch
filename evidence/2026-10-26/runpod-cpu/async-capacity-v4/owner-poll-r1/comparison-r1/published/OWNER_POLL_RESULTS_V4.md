# V4 owner polling: full registered criterion fails

All four finite gates pass at4000 scheduled arrivals/s, confirming all80000 unique synthetic one-unit trades per arm. Both100us candidates lower global p99 but raise post-offer p99, so neither pair passes the complete preregistered direction criterion. **No default change is promoted.** This is separate from the completed exact-cut capacity curve.

[Prospective protocol](OWNER_POLL_PROTOCOL_V4.md) fixes unchanged artifact65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69/source0c8303b2,CONTINUE maintenance,leader0,sync2,127 active producers,Q64,batch4,cut1536,read32/page32/chunk6144,three actual UDP JVMs on one prepaid physical CPU. Only the explicit actual constructed-owner requested park cap changes;node argv and all server agent settings remain identical.

| Arm | Actual owner cap | Accepted/planned | In-window goodput/s | Global p50 ms | Global p99 ms | Post-offer p99 ms |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | 1000000 ns | 80000/80000 | 3993.45 | 17.898 | 99.418 | 13.642 |
| D1 | 100000 ns | 80000/80000 | 3993.45 | 12.172 | 84.046 | 16.408 |
| C2 | 1000000 ns | 80000/80000 | 3993.45 | 24.316 | 117.514 | 15.034 |
| D2 | 100000 ns | 80000/80000 | 3993.45 | 14.627 | 93.453 | 15.817 |

C1/D1: global p99 change -15.462%; post-offer p99 change 20.275%; goodput change 0.0/s. Complete criterion passed: False.
C2/D2: global p99 change -20.475%; post-offer p99 change 5.206%; goodput change 0.0/s. Complete criterion passed: False.

Every arm has zero notSent,server rejection,duplicate or observed/final UNKNOWN. Exact cuts, full event/trade/receipt audit, original physical-order canonical replay, three snapshots and three cold restores pass. All four complete raw assets were authenticated,re-downloaded and every member verified before progression. The1ms and100us values are requested sleeps,not OS scheduling bounds. Stage percentiles remain separate distributions. These20-second observations provide no statistical significance,long-run capacity,SLA,HFT approval or100M continuity.

The owner cap alone does not establish the10ms target or higher sustainable throughput. The next isolated candidate yields a bounded business turn only between closed read banks and drains original tickets before opening another. It remains a separate implementation/correctness experiment with no transferred performance claim.

[Complete comparison, process CPU/backlog, original asset SHA references and orchestration sources](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/owner-poll-r1/comparison-r1/README.md).
