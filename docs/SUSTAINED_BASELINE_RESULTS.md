# Instrumented 30-minute baseline, first repetition

The first 30-minute run completed 180,000/180,000 synthetic IOC orders at a planned
100/s, with no rejection, error, not-sent or initial/final unknown. Full canonical
snapshot bytes, deterministic replies, balances and fixed leader were verified.
**The registered combined acceptance failed:** 37 scheduler dispatches exceeded
the unchanged 20ms gate, so the generator reports `measurementValid=false`.
Application `passed=true` is not the registered combined acceptance result.

| First repetition | Result |
|---|---:|
| Arrival window | 1800 seconds |
| Scheduled / accepted | 180000 / 180000 |
| Scheduled-to-confirmed P50 | 9.013493ms |
| Scheduled-to-confirmed P99 | 24.892470ms |
| Scheduled-to-confirmed P99.9 | 44.238345ms |
| Maximum scheduled-to-confirmed | 120.136273ms |
| Scheduler delay >20ms | 37 |
| Complete minute windows | 30 |
| Minute windows with P99 >25ms | 1,2,3,4,14 (zero-based) |
| Canonical post-run verification | 105.68 seconds, outside arrival window |

This is three replica JVMs and one generator JVM in the **same existing CPU
container, loopback UDP**, with fixed leader0, 2GiB heap, sync2, shared driver /
multiplexed session and unchanged bounded capacity-190k-v1 state. It establishes
an instrumented low-rate run, not sustained 4000/s, independent physical machines,
continuous 1M/100M orders, production HFT latency, or journal-retention stability.
The final 360267-event outbox is not being drained by a PostgreSQL exporter.
Two repeated runs were registered; the second is still in progress at this commit.

All 180000 original intent identities and terminal checkpoint rows match the
final CSV. Whole-life per-PID metrics and explicit JFR event streams cover the
arrival window. The independent auditor reconciles the original JFR dump with
the streamed events using multiplicity; native JFR thread ID 0 corresponds to
consumer thread ID -1, so GC events are not double counted. No DataLoss or failed
recording closure was observed. Maximum metric / CPU-event gap was below 1.01s.
Whole-process-lifetime FileForce P99 was about 10.15–10.71ms across the four JVMs;
this includes setup / validation and is not isolated physical disk durability or
a causal attribution of order tails. GC, queue and force timelines remain raw
for subsequent phase-specific analysis. Observer overhead is included in latency.

The matching / server artifact is a21a720ddfd479faf1129176bc2ff1adff2e34084874ca621999a4cdb4ffe3f3
(source97db58e); the explicit soak-client overlay and agent are from source0a270d18.
Their exact class / JAR hashes are retained in `OVERLAY_V4.json`; later escrow
source is not deployed into this experiment. No cross-build performance comparison
is made.

The complete first archive is 77,301,603 bytes, SHA-256
f90dad9cb33664bada7e219f47a452f9761de329238f449f9f51a69469380a15,
private draft release423510304 asset677884689. A full authenticated download and
all84 original member hashes were verified. Two complete local copies remain.
Only this task's stopped first-run cloud directory was retired to that recoverable
archive to meet the unchanged 3.3GB second-run disk admission gate. No other state
or Pod was removed. Cold-restore/fresh-order RTO is not yet claimed.

Reproduce the audit with Python3.9+ and Java21 `jfr` against a verified extracted
archive: `python3 scripts/audit-sustained-soak.py CASE_ROOT --jfr JDK/bin/jfr --output NEW_REPORT.json`.
The raw archive stays in a private release, outside Git history. Thin results are
in `evidence/2026-10-26/cpu-soak-r1/`. Seven local auditor regression tests pass.
The latest user cloud constraint is **USD0 new cash, no bank card and no paid
subscription upgrade**; verified student credit may fund bounded later tests.
