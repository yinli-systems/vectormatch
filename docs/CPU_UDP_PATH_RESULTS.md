# CPU Pod UDP and storage diagnosis, 2026-10-26

Two temporary CPU5c Pods (4 vCPU, 8GB RAM, 20GB ephemeral disk each) were deployed
in EUR-IS-1 at $0.14/hour compute plus approximately $0.003/hour disk each. The
existing prepaid CPU was preserved. No GPU was rented. Native public UDP mappings
worked; the tested private addresses were unreachable. Different boot IDs establish
different observed kernels, not independent physical machines. No third Pod was
created after this topology limitation was established.

The key result is a measured reliability problem on this raw, NAT-mapped UDP path.
It is not a matching-engine capacity result. The existing directly bindable Aeron
topology was not silently rewritten or represented as a working NAT-aware cluster.

## Original policy comparison

Source `37ec26cd07cc82a5a1d369e913a13062e6401533`, Java source SHA-256
`0045a2b0dce9b12d2273fbd96e5aa75311b8c77cb5019ee53ed9eabba13f6fd5`,
Linux class SHA-256 `ccf548e702f3d139e916e82dbbc219f9bbd46e3ed941039893f8d7f2252f00b1`.
Both endpoints use identical compiled bytes and the same validated JDK. Each arm
has 10,000 independent planned 64-byte packets at 1,000/s over ten seconds, a
128KiB receive-buffer request and no application retries. C parks for at most
1ms when idle; D uses 100us at both endpoints. Each invocation has a fresh run ID.

| Arm | Unique replies | Unknown | In-window replies/s | All-arrival p99 ms | Conditional reply p99 ms | Conditional post-send p99 ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C1 | 9,998/10,000 | 2 | 999.6 | undefined | 2.067411 | 2.004623 |
| D1 | 9,904/10,000 | 96 | 990.4 | undefined | 0.985292 | 0.924792 |
| C2 | 10,000/10,000 | 0 | 999.9 | 2.064061 | 2.064061 | 2.003050 |
| D2 | 9,997/10,000 | 3 | 999.7 | undefined | 0.522358 | 0.462953 |

All original send calls accepted 64 bytes; no not-sent, invalid replies or duplicate
client replies were recorded. The zero-loss gate and both registered optimization
criteria fail. Higher rates were therefore not executed. The smaller conditional
latencies do not justify promoting the candidate, and no sustainable packet-rate
ceiling follows from these observations. Server CPU time over its fixed 25-second
lifetime was 0.30/0.81/0.30/0.75 seconds, respectively; client CPU time was
0.26/0.60/0.22/0.58 seconds. CPU saturation was not observed by these process totals.

Earlier Python reachability probes received 1,000/1,000 replies each: existing CPU
to the first Pod p99 6.127520ms, second Pod to first p99 0.286082ms. These are separate
low-rate echo observations, not a latency guarantee or the Java capacity cohort.
The first preliminary server's per-packet scratch file was replaced by the second
reachability probe; its count log and the complete original client rows remain.
No claim of a complete first-server callback tape is made.

## Improvement: bounded per-packet attribution

The server now validates packet sequence/payload identity and retains bounded
primitive receipt slots, first receipt/echo timestamps and duplicate/send counts.
The independent Python audit pairs original identities without subtracting clocks
from different machines. It refuses forged aggregates, mismatched runs, missing
rows and client replies without a corresponding server send.

This V2 diagnostic uses separate source `28405f26`, source SHA-256
`065fdacf4df0c7436f78ee4b66e29cd8f1f1e1dc19dc56d1a97a8cfe36f6fdc1`, class SHA-256
`7f456f3369494c996a22ce8872dc8aeed5fe9c126525e90361ec3065532d6b7c`.
Its 20,000 planned packets at 1,000/s produced 19,971 unique client replies:

- **17 ingress-unobserved:** accepted client send, no server receipt.
- **0 server-echo-not-sent:** no unknown was explained by server send backpressure.
- **12 egress-unobserved:** server receipt and successful echo send, no client reply.

Both newly created containers' cumulative UDP `InErrors`, `RcvbufErrors`,
`SndbufErrors` and checksum errors remained zero. This narrows investigation to
the path outside the observed application sockets; it does not identify a physical
switch, NAT implementation or host forwarding failure. No receiver queue overflow
was observed in these container counters. Existing-CPU counters include earlier
experiments and must not be attributed to this diagnostic without a baseline delta.

The V2 diagnostic's conditional p99 is 0.790065ms; its all-arrival p99 is undefined
because 29 originals lack replies. Its extra instrumentation and longer window
are not merged into the earlier policy comparison. UDP reliability belongs in the
actual transport protocol; blindly retrying a financial order is not a remedy.

## Forced-write component

Identical Java/JDK inputs wrote 2,048 deterministic noncompressible 4KiB records per
host, each followed by `FileChannel.force(true)`, outside network arrival windows.
Every original sample and all three 8MiB files are retained. An independent
generator verifies every data byte and independently recalculates quantiles.

| Host | force(true) p50 ms | force(true) p99 ms | write-only p99 ms |
| --- | ---: | ---: | ---: |
| Temporary Pod 0 | 1.392443 | 1.457865 | 0.015690 |
| Temporary Pod 1 | 1.388005 | 1.497098 | 0.014848 |
| Existing CPU | 1.467494 | 2.359493 | 0.027630 |

OS-observed forced completion is much slower than the ordinary write in this
fixture. This supports investigating force frequency and batching in the actual
replicated path, alongside its existing JFR evidence. It does not isolate the
cause of a historical trading p99, certify physical media durability or establish
that the previous coalescing optimization succeeded. Durability was not weakened.

## Delivery and evidence

Eleven targeted tests pass on both local Java 21 and an actual Linux CPU Pod,
including real datagrams under both idle policies and negative audit cases.
The production matching/replication implementation is unchanged. Its previous full
CI28 evidence remains separate; these eleven tests are not a new full-suite pass.
Both CI checkout workflows now include the standalone diagnostic sources.

The hosted [correctness run](https://github.com/yinli-systems/vectormatch/actions/runs/40284874162)
did not execute any job steps. GitHub's annotation reports failed recent account
payments or a spending limit; no billing setting was changed and no green hosted
run is claimed. [The annotation](../evidence/2026-10-26/runpod-cpu/cpu-udp-path-r1/HOSTED_CI_ANNOTATION.json)
is retained.

All four original UDP points, the separate V2 receipt ledger, original forced
files/samples, source/class identities, Linux test logs and failed preparation/
collection attempts are in one **26,744,778-byte private draft attachment**,
asset `677395851`, SHA-256
`9b1d7b0e796a0319a2403b3b0a767bb505a4a40db812fed427f96c116567e45d`.
Its complete authenticated download, all 169 outer files and every original file
inside all five nested scope archives were verified. Collection recoveries did not
repeat the native workloads or regenerate missing packets.

[Original manifests, measured outcomes and download proof](../evidence/2026-10-26/runpod-cpu/cpu-udp-path-r1/README.md).
The trading evidence index remains at 135 runs/50 cohorts: UDP packets are not added
as orders. No production default, HFT endorsement, realtime guarantee, independent
physical-host failure claim or funded-trading activation follows from this round.

Both newly created Pods were stopped after the complete private-archive verification.
The console reports compute and container storage not running, total **$0.00/hour**
for each. The existing CPU was subsequently reachable with its original hostname
and boot identity. Incremental rental cost is estimated below **$0.22**, not a
provider invoice; the $2 experiment cap was not approached. The temporary shutdown
heartbeat was paused after both stopped states were verified.
