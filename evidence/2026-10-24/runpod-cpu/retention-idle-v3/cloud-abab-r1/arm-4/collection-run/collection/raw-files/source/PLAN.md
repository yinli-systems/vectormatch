# CPU idle ABAB revision2 — local source/candidate freeze

Revision1 and the original local native outer failure remain unchanged. This
revision integrates the root-accepted exact warning predicate into controller,
native auditor and raw auditor. No Java, SSH, stage, benchmark, process signal,
prune, new resource or Git action was performed by this revision.

## Single factor and ownership

Same7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23 source and four actual JARs for
all arms. Exact order: arm1=1,000,000ns, arm2=100,000ns, arm3=1,000,000ns,
arm4=100,000ns, explicitly selected with
`-Dvectormatch.retention.idleMaxParkNs=N` in parent and child-node argv.
Canonical PREP remains `/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1`;
these are four separate `arm-N/idle-arm` roots. CLI:
`RetentionCapacityAeronPilotV3 <freshArmRoot> idle-window8 42000`.

Fixed:6400 arrivals at500/s (12.8seconds), readWindow8, cap4, chunk6144,
eventFetch16, W128/taskQ64, one owner/session, leader0, sync2/force(true),
MTU1248, prepared-prefix cache and the same bounded maintenance/profile policy.
Arrivals continue through maintenance. Business-owner wait loop remains the
original deadline-aware maximum1ms. The factor covers the actual configured
node driver/archive/consensus/service strategies and measured owner driver,
not an OS sleep/wakeup guarantee.

No automatic arm loop, rerun, alternate ID or resume. Controller defaults to
read-only preflight and requires explicit `--arm N --start-new` plus a separately
root-frozen release SHA. Arms2–4 require the preceding independently verified
collection gate SHA. Each fresh arm has one parent plus three node JVMs.
Reviewed Linux ownership/TERM/closure/protected-original logic is unchanged;
PID+startTicks+full argv SHA are checked with pidfd, with no broad kill, KILL or
numeric-PID fallback. Unconfirmed closure blocks hashing/archiving/next arm.

## Actual artifacts and finite budget

`candidate/release/release.json` is filled from root-closed Linux metadata but
remains `releaseReady:false`. Actual code fingerprint:
`f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f`.
Profile: `732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68`.
Exact class-source binding deduplicates the node classpath to three JARs;
DirectBuffer is supplied by aeron-all. The parent classpath has exactly four.
Canonical Linux Java/release SHA values are9cad3f…/f83f6d….

The actual Linux-JAR plan, shared by both parks, has raw bound38,033,404B,
allocated growth589,327,865B, staging1,282,496B, failure reserve1,054,872B,
1379maintenance RPCs and upper reply6791B. The explicit codec shape fixture6727B
is not an observed network reply or a minimum. Generic envelope6919B plus32B
session header is unchanged. Hard raw2GiB/growth2.5GiB ceilings remain unchanged.
Per-arm free admission is growth+16MiB monitor+256MiB archive+1GiB floor:
1,948,282,361B with this plan. No assertion that four uncollected arms fit is made.

All original57 native and989 stopped PG files retain SHA/bytes/modes/owners/
directory protection under immutable6769aa… manifest before and after each arm.
No SQL or original-state writes are introduced. The controller never deletes
native data. If space blocks a later arm, root must separately review exact
closed-owned-tree removal backed by independent full local archive readback,
manifest/path/owners/modes/SHA and stopped process proof; compressed archives
and original/PG/JDK/releases/other jobs must remain. The next gate explicitly
attests any absent owned native tree. Insufficient space is not deletion consent.

## Qualified local native and warning policy

The7aa Java parents both exited0 with6400 accepted identities, three maintenance
cycles, all-three matching final snapshots and owned stop. The original outer
Python gate failed because it rejected any ERROR substring. It remains failed.
Both local schedulerTimingValid flags are false; functional proof is accepted
only with that qualification, never as a valid CPU performance point.
Root separately checked all234 archive members and89 inputs; the independent
post-close raw audit retained the original failure and all bytes.

Only100us followers1/2 emitted one exact terminal two-line pair each, after
their matching final checkpoint by node log order:

```
VECTOR_V3_ERROR node=N
io.aeron.cluster.client.ClusterEvent: WARN - log recording stopped: eos=true
```

Aeron1.53.3 actual JAR constructor proves categoryWARN; the application marker
is unconditional for all errorHandler callbacks. Pinned source shows this event
may initiate election, so it is never described as a harmless no-op. Node0-first
owned stop is consistent with teardown EOS but does not establish causality.
There is no per-signal clock: afterSIGTERM walltime/event-generation time is
not proven. Counters/events are never zeroed or hidden.

Exact pure predicate bb8725c5… is a release/preflight identity. It is called in
all three gates and returns full original log SHA, marker/event byte+line indices,
pair SHA/count and `AFTER_MATCHING_FINAL_CHECKPOINT_BY_NODE_LOG_ORDER`. It accepts
at most one terminal exact pair per follower1/2. Leader0, before-checkpoint,
wrong scope/finalhash, otherWARN/error/exception/stack, extra/duplicate/truncated
pair or any unknown line fails. All source/raw/log bytes and warning reports remain.
This predicate alone never overrides old receipts or authorizes another arm.

## Collection and approval

Root owns a separate ready release/stage gate and one-at-a-time launch. Local
`build_config.py` requires exact actual stage/release/protected-reference SHA and
all preceding independently collected-arm gates. Source allowlist is explicit;
PREP is never recursively tarred. Three current-arm opaque execution files are
`arm-N-execution-register.json` (may be JSONL), stdout and stderr.

`collect_and_audit.py` defaults to local validation and additionally requires
root's exact schema2 `ROOT_VERIFIED_CLOSED_CPU_IDLE_CONTROLLER` receipt before
read-only collection. It binds arm/park/release/controller/job, controller absence,
all-owned stop and actual inspection source/result SHA. Exit alone is insufficient.
Full outer/nested bytes/modes/uid/gid/empty dirs are verified without sparse
extraction. Raw gates retain6400 identities, six read phases/three cycles,
positive-offer overlap, actual Image/Header lifecycle, durable prefix/serialACK
and all failures. Only a root-approved collection gate allows the next arm.
A finite same-host12.8second observation cannot prove sustained maximum/100M.

## Validation and provenance

`guards-r1`:27 delta/integration/predicate guards and122 unchanged frozen guards
passed, including all six real closed local log fixtures and meaningful negative
phase/severity/binding cases. Exact registered source ZIP, interpreter/commands,
stdout/stderr and exit receipts are retained. Python3.8 syntax parsed locally;
actual Linux execution is a future root stage gate. Frozen revision1 source
hashes and input evidence were checked unchanged. `candidate/CANDIDATE.json`
binds the root source/native/unit/Linux metadata proofs. These do not promote
releaseReady or start anything.
