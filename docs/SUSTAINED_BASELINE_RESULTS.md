# Repeated instrumented 30-minute baselines

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
Both registered repetitions completed in separate fresh lineages. Both failed the
combined acceptance because the generator exceeded its unchanged scheduling gate.

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

Reproduce the audit with Python3.8+ and Java21 `jfr` against a verified extracted
archive: `python3 scripts/audit-sustained-soak.py CASE_ROOT --jfr JDK/bin/jfr --output NEW_REPORT.json`.
The raw archive stays in a private release, outside Git history. Thin results are
in `evidence/2026-10-26/cpu-soak-r1/`. Nine local auditor regression tests pass.
The latest user cloud constraint is **USD0 new cash, no bank card and no paid
subscription upgrade**; verified student credit may fund bounded later tests.

## Second repetition and repeatability

| Same hardware, configuration and deployed bytes | Repetition 1 | Repetition 2 |
|---|---:|---:|
| Arrival duration | 1800s | 1800s |
| Scheduled / accepted | 180000 / 180000 | 180000 / 180000 |
| P50 scheduled-to-confirmed | 9.013493ms | 8.942836ms |
| P99 scheduled-to-confirmed | 24.892470ms | 11.130440ms |
| P99.9 scheduled-to-confirmed | 44.238345ms | 33.772764ms |
| Maximum | 120.136273ms | 96.365167ms |
| Scheduler delays >20ms | 37 | 3 |
| Rejected / error / not-sent / initial or final unknown | 0 | 0 |
| Original identities / terminal checkpoint rows checked | 180000 | 180000 |
| Complete minute windows | 30 | 30 |
| Combined registered acceptance | FAIL | FAIL |

The second archive is 77246590 bytes, SHA-256
2ce92b19354224e9f104bd6b4a07591c46ae3905c29b54ff56599a9fbf6d2377,
private asset677990229. Full authenticated download and all84 member hashes were
verified. The raw archive is outside Git history. Its nine-test auditor also ran
successfully on the CPU host's Python3.8, reconciling the original JFR dump with
streams, original CSVs and checkpoints. The first remote audit exposed an
unsupported Path.is_relative_to API; the compatible version and original failure
remain recorded. All four metric streams cover the arrival window, with maximum
sample gaps below1.01s and no failed recording closure / observed DataLoss.

Repetition2 whole-life FileForce P99 was4.09–4.42ms, versus10.15–10.71ms in the
first repetition. This is a possible storage / host variability lead, not a
controlled causal result. No code or configuration changed, so the lower order
P99 is not advertised as an optimization. The second repetition's minute16
exceeded25ms P99. These two bounded180000-order lineages are not one continuous
360000-order lineage or a high-rate capacity / production latency proof.

Local extraction of repetition2 ran out of disk space because the initial local
admission check was missing. Only recoverable task-generated extraction copies
were retired; complete compressed originals, authenticated download copies and
private assets remain. The successful second audit ran on the existing CPU host
with explicit disk admission; the original failed attempts remain evidence.

## Empty-directory backup restore

Twenty-two backed-up state members were restored from the fully verified first
archive into a new directory on the same CPU and disk. Three new replica JVMs
started with unchanged server artifacts. A native ColdRestoreProbe checked exact
pre-trade canonical bytes, retried original command180167 as a cached replay
without mutation, then accepted and matched fresh synthetic command180168.
The post-trade canonical bytes equal replaying exactly that one fresh command;
the matching invariants passed. The probe JVM exited0. Its single fresh request
RPC was9.134435ms; a single request is not a percentile or SLA.

The controller exited1 because tail --pid omitted the final buffered stdout line.
The persisted native proof, both snapshot hashes, loaded-class origins and all
four process exits were independently checked afterwards. Functional checks
passed, but recovery timing is unqualified and no physical-fault RTO is reported.
This is same-host backup restore / matching-core evidence, not a disk power-loss,
independent-host, PostgreSQL or whole-production recovery certification.

The restore archive is23789680 bytes, SHA-256
0cd6ff34a502b5f6c262bebee93c3e90f555ac3a58eae4d455df846e10a73079,
private asset678063367. Full authenticated download and all71 members were
verified. The original controller failure and separate functional attestation
are preserved; no failed outcome was silently changed into a timing pass.
