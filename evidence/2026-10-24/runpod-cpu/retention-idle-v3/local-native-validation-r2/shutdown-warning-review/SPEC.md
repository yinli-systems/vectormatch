# Narrow post-checkpoint follower EOS warning classification

This local review does not change the frozen campaign preparation, Java source,
the original failed wrapper, native bytes or any existing gate. No Java, SSH,
SQL, cloud mutation, Git action or business rerun was performed.

## Actual observation

Both fresh7aa single-arm parents exited0. Recorded native receipts report6400
distinct accepted orders, no final UNKNOWN/notSent, three maintenance cycles,
matching all-three final checkpoint logs and owned clean stop in both arms.
The original Python wrapper still failed at its broad `'ERROR' not in text`
assertion while inspecting the100µs arm. Its original failure is preserved.
Both local arms also report `schedulerTimingValid:false`; these are functional
proofs and cannot be represented as valid CPU performance points.

Among the six bounded original node logs, only100µs followers1 and2 contain a
warning. Each matching final checkpoint is line4, followed by exactly these
terminal lines5–6:

```
VECTOR_V3_ERROR node=N
io.aeron.cluster.client.ClusterEvent: WARN - log recording stopped: eos=true
```

Each two-line raw suffix is100 bytes at byte offset10267. Node1 suffix SHA is
`fca51c78635817102e3a2596fe10f67d769462e23f09768bfa841e3cac6607d8`;
node2 is
`e480d21456d3286ecd423a9ecf2a6fce8af9446b9bf17cd55228debd8fce745c`.
`REVIEW.json` retains each full log SHA, line/byte indices, exact text and all
77 input SHA/byte bindings. All original inputs and all33 frozen preparation
source/plan/doc hashes were checked unchanged after investigation.

## Pinned taxonomy and effect

The application `RetentionNodeMainV3` error handler prints
`VECTOR_V3_ERROR node=N` unconditionally and then invokes `printStackTrace`.
That project prefix is not a severity decoder.

Pinned primary Aeron1.53.3 `ConsensusModuleAgent.pollArchiveEvents` receives a
`RecordingSignal.STOP` matching `logRecordingId`. When state is ACTIVE and no
election exists, it checks `logAdapter.isLogEndOfStreamAt(position)` and calls
`enterElection(..., "log recording stopped: eos=" + isEos)`. `enterElection`
sets FOLLOWER, reports `new ClusterEvent(reason)` via the counted error handler
and creates/drives an Election. This event can initiate recovery/election; it is
not a harmless no-op guarantee. Source anchors and the pinned primary URL/SHA
are included in `REVIEW.json`.

The actual installed `aeron-all-1.53.3.jar` SHA is
`4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2`.
Read-only class-file parsing, without class loading or Java, confirms:

- `ClusterEvent(String)` loads `AeronException.Category.WARN` and invokes
  `AeronEvent(String,Category)`.
- `AeronEvent` extends `AeronException`; `fillInStackTrace()` bytecode is
  `aload_0; areturn`, explaining the deliberate short event printout.
- The actual LogAdapter end-of-stream predicate checks a nonnull Image and
  equality with `Image.endOfStreamPosition()`.

Full relevant constructor/method bytecode and class SHA values are retained in
the review. There was no javap/JVM invocation or assumed default category.

## What phase is proven

The pilot launches nodes in0,1,2 order, stores that order in its owned list, and
`stopOwned` destroys and waits each node in that same order. Node0 is therefore
handled before nodes1 and2. This is consistent with followers observing EOS
during leader-first teardown, but does not uniquely prove causality.

The warning is **after the matching final checkpoint by node log byte order**.
The stop receipt has no per-signal clock. Different agent threads can also
produce output at different scheduling times. Do not label the warning as
proven after SIGTERM, assign a wall timestamp, or infer the event-generation
instant from its line position. Source-derived interpretation and observed log
order remain separate fields.

## Proposed new predicate, separate from the frozen failed gate

`shutdown_warning.py` is a pure candidate predicate for this exact fresh
single-arm fixed-leader pilot. It keeps all lines and their hashes. It can
recognize only one exact, terminal two-line pair per follower1 or2 after one
checkpoint matching the actual profile, lineage and final combined hash.
The actual node/PID, expected fixed topology/readiness, one initial service,
separately validated actual idle object and final checkpoint must all bind.

It refuses leader0 warnings, warnings before checkpoint, wrong scope/hash,
missing/truncated pairs, EOS=false, another WARN/error category, duplicate
warnings/checkpoints, any extra ERROR/exception/cause/suppressed/stack tail,
unknown log lines and oversized/incomplete logs. It does not strip text,
rewrite source receipts, zero error counters, claim no event occurred or
suppress the fact that an election may have started.

Acceptance of this candidate classification requires **separate** full
functional/reference/raw correlation/prefix/6400-identity/archive closure,
actual idle/JAR/profile binding, and all-owned-stopped proofs. The predicate
alone cannot authorize another arm, change a performance classification or
override the original failed wrapper. Every later cloud arm must retain its
warning report. Before-checkpoint or any nonexact error remains a failure.

The peer post-close audit receipt is linked with its exact SHA in
`RAW_CLOSURE_LINK.json`; this review did not rerun or impersonate that raw audit.
Root review remains the approval boundary for using a separate new predicate.

## Focused guards

Ten pure positive/negative guards passed under the exact registered sources.
They cover the narrow acceptance and every rejection above. Source ZIP,
command/interpreter, complete stderr/stdout and exit receipt are in `guards-r1`.
Python3.8 syntax was parsed locally, not claimed to be executed on Linux.
