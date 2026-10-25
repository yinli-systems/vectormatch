# Verified handoff candidate: finite capacity curve

The registered progression stops at7,500 scheduled orders/s because74,531 of150,000 planned arrivals are definitively NOT_SENT/QUEUE_FULL. This is a valid severe overload observation,not an invalid control or an optimization success.8,000/s was never executed. No lost arrival is replaced by an accepted-only percentile.

[Prospective registration](VERIFIED_HANDOFF_CAPACITY_V3.md) fixes candidate source23f9c070/code79e5a932,leader0,sync2,ROTATING_CONTINUE,read128/page32/batch4/chunk6144,owner1ms/driver100us,W128/Q64,one physical session,three JVMs on one CPU host with loopback UDP and256MiB heap each. All three use the same qualified sampler,original-PID readiness gates around5s read-only warm-up,and project-only cache preconditioning. No JFR was enabled. Each point is one fresh20s synthetic lineage,one seeded maker at10 ticks,one-unit IOC buys. All accepted load orders produce exactly one unique trade. Multi-level/cancel workloads and external trading are separate.

| Scheduled/s | Planned | Accepted/trades | NOT_SENT | In-window goodput/s | Global accepted-arrival p99,ms | Accepted-only p99,ms | Clearing comparable intervals |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6000 | 120000 | 120000 | 0 | 5990.25 | 208.340423 | 208.340423 | 36/36 |
| 7000 | 140000 | 140000 | 0 | 6968.05 | 317.321132 | 317.321132 | 35/43 |
| 7500 | 150000 | 75469 | 74531 | 3361.45 | undefined | 4557.860156 | 0/19 |

All three points retain zero server rejection,observed UNKNOWN and final UNKNOWN.6,000/s is the highest tested rate clearing recorded waiting in every comparable full-cut interval.7,000/s passes the registered finite gate,but only35/43 intervals clear. Neither observation establishes a sustained capacity ceiling. At7,500/s the128-request window and8192-slot total client queue fill;the measured bottleneck is not thereby uniquely identified as client,network or service. Global accepted-arrival p99 is undefined because74,531 arrivals have no accepted result.4,557.860156ms describes only the75,469 accepted arrivals. In-window goodput counts67,229 confirmations within20s;the remaining accepted orders complete during drain.

## Startup and maintenance evidence

Before the first maintenance starts,all three have completed3,069 load orders and drained pending business. Read-only reconstruction from original CSV and cycle timestamps finds:

| Scheduled/s | Time to first maintenance,ms | Observed accepted/s before it | Mean offer-return→completion,ms | p99 offer-return→completion,ms | Mean admitted logical concurrency |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 6000 | 518.300548 | 5921.27 | 9.485348 | 29.304261 | 56.165 |
| 7000 | 445.172113 | 6893.96 | 10.612709 | 27.400484 | 73.164 |
| 7500 | 630.717160 | 4865.89 | 22.903896 | 53.659331 | 111.448 |

The7,500/s slow round trip is already present before archive maintenance. This interval includes client polling and synchronous raw-evidence work,loopback transport,replication/log storage and service. Startup/JIT/GC and shared-host variability remain unseparated. Submit-to-positive-offer p99 does not rise in that startup comparison. These observations justify instrumented diagnosis;they do not prove a pure network,window,disk or service cause. No queue-full loss occurs before first maintenance;the first7,500/s loss arrives2.311122277s after the scheduled origin.

| Phase,total seconds | 6000/s | 7000/s | 7500/s |
| --- | ---: | ---: | ---: |
| Maintenance wall | 7.069737544 | 8.400829081 | 8.433749100 |
| Coordinator canonical archive verification | 1.084942527 | 1.473823641 | 0.860867192 |
| Archive writer elapsed | 1.714486617 | 1.901621460 | 1.825318270 |
| Archive full readback,inside elapsed | 1.413791066 | 1.482087586 | 1.006731520 |
| Event writer elapsed | 0.807455605 | 0.921745689 | 1.126781072 |
| All payload/receipt forces,inside writer elapsed | 0.340333850 | 0.520478579 | 1.142749243 |

Writer subphases are not added to elapsed again. Complete payload canonical verification,force(true),full readback and receipt force remain before either destructive ACK. This does not establish storage survival after a physical-host loss. An asynchronous-maintenance implementation remains a separate candidate;it cannot alone explain the observed pre-maintenance slowdown.

## Reproduction and boundaries

- [6000/s complete original native/raw package](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/capacity-6000-arm-d1-native-r1/README.md),private commit`3b3b5c76c61952dbf9ecda615db01260aefc6756`,asset`675772189`,SHA-256`9c710e50c2d06f1d6253150d1cd78aa4ae47c377ec4b672035e9e7360aa85e01`.
- [7000/s complete original native/raw package](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/capacity-7000-arm-d1-native-r1/README.md),private commit`d48a265091ea8427e33a40a895571094fd6be2ba`,asset`675801496`,SHA-256`42999afb1750e1b1a928f8bda8007e6823f96ed9f31dc62755af6526746376a3`.
- [7500/s complete original native/raw package](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/capacity-7500-arm-d1-native-r1/README.md),private commit`1ffed897d844f803e25ddbb3385410ea15e6750c`,asset`675823953`,SHA-256`ed17a7a9af3d09a30a32841075abd4cf0613b9166bf606b0050fc7fda3bbb14e`.

[Complete curve derivation](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/capacity-reporting-r1/README.md) retains reporting/diagnosis sources,original and derived UI index,all source pins,proofs,phase/recovery/trade audits and stop decision. Each native private asset was authenticated-downloaded in full and every original member verified before progression. All150,000 original7,500/s outcomes reconcile as75,469 accepted unique trades plus74,531 definite pre-offer queue refusals;the three final state snapshots agree. No failure is discarded or renamed noise. Candidate-codec checks are not an independent matching oracle or cold recovery.

The console preserves all64 previous runs/28 cohorts and appends3 runs in one distinct cohort,67/29. Existing historical three-Pod and other one-host curves remain separate. HTTP-data verification is not browser rendering. One observation per rate does not establish statistical significance,an optimization gain,independent physical-node isolation,hard realtime,a millisecond SLA,production certification,HFT endorsement,external/funded-trading readiness or any100M target. The next performance experiment requires a newly registered diagnostic protocol;the failed progression does not authorize8,000/s.
