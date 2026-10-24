# Closed chunk ABAB collection preparation

Source-only preparation. **No cloud collection, benchmark, launch, signal, Git operation or frozen evidence edit has been performed by this preparation.** Root must supply the final frozen release, exact staged-file receipt and three execution metadata names, then explicitly invoke the read-only collector after a CPU round has closed. The current upstream candidate is revision r3; the preparation revision comes from the root-frozen config and must match the release's exact owned paths. No source commit or runtime fingerprint is assumed here.

Each round is separate: `<PREP>/round-{1,2}/chunk-pair/chunk-{3072,6144}`. Both arms use batch4, W128/Q64, pending128, 6400 arrivals at 500/s over 12.8 s, ports42000, appointed/observed leader0/term0, sync2 and the same common finite limits. Four ordered observations are A/B/A/B only after both rounds close and round1 has been independently collected and root-attested. A round is not promoted on eventual acceptance or a one-pair latency difference.

## Inputs and execution boundary

Copy `collector-config.template.json` to a new root-owned config and fill:

- exact remote PREP `/opt/vectormatch-cpu/preparation/chunk-cloud-abab-rN`, hostname and round;
- actual local frozen release JSON + full SHA; exact successful staging receipt JSON + full SHA;
- prior original R3 protected-state JSON + full SHA (not a stale earlier original baseline);
- exactly three actual execution metadata basenames at PREP root;
- for round2 only, the independently root-approved local round1 gate JSON + full SHA. It is added as one exact allowed source file and checked against the round2 `before.priorRound` receipt.

The source allowlist is **only** the staging receipt's `stagedFiles`, plus those three metadata names and, in round2, the exact approved gate. No recursive PREP archive is ever allowed: PREP contains both round trees. Only the selected closed JOB is recursive. Configuration rejects unsafe source names, arbitrary remote roots and future round gates in round1. All destinations are create-new; failed/partial attempts remain present.

The collector's default invocation validates local frozen inputs only and does not import the SSH helper or contact the Pod:

```sh
python3 -B collect_closed_round.py --config /absolute/root-frozen-config.json
```

Only after root's explicit instruction following closed CPU completion:

```sh
python3 -B collect_closed_round.py \
  --config /absolute/root-frozen-config.json \
  --dest /absolute/round-1/collection-r1 \
  --remote-helper '/Users/kevin/Documents/ChatGPT/App 2/runtime/cloud/cpu-20261024/remote.py' \
  --collect-readonly
```

It requires `allOwnedStopped` and no forced/numeric-PID fallback, but permits collecting a **closed functional failure** so failed raw evidence is retained. A functional failure cannot pass subsequent strict audits or generate a ready receipt. A blocked/active native tree is not hashed or copied by this full-native collector. No automatic retry is performed.

## Independent local verification

Run each auditor into a fresh directory, retaining stderr/stdout and previous failed attempts:

```sh
python3 -B audit_native_artifacts.py \
  --config /absolute/root-frozen-config.json \
  --collection /absolute/round-1/collection-r1 \
  --out /absolute/round-1/native-audit-r1

python3 -B audit_raw.py \
  --config /absolute/root-frozen-config.json \
  --collection /absolute/round-1/collection-r1 \
  --out /absolute/round-1/raw-audit-r1
```

The collector checks every outer file's full SHA/bytes/mode/uid/gid and exact directory closure, including empty directories. It saves the full closed outer gzip plus the nested `pilot-after-clean-stop.tar.gz`; bounded raw files are extracted, sparse native segments are not. The native auditor streams every nested native/raw leaf and reconciles its metadata to both the stopped inventory and outer archive. It extracts only the exact four runtime JARs, inventories every ZIP entry, recomputes the actual type-source fingerprint (MatchingEngine from core, DirectBuffer from Aeron), binds process argv/PID/startTicks, actual plans and immutable configuration, and compares all protected original native files and PG baseline to the wrapper's unchanged before/after checks. It distinguishes **six raw node stop reports** from normal parent exit/reap/final-absence source/result evidence. It does not claim a second live protected-tree rehash or external storage survival.

The strict raw auditor first inventories **every** planned arrival identity, including any unreleased/notSent/rejected/UNKNOWN row, and writes `all-arrival-terminal-inventory.json`; nonzero/partial results remain recorded and fail strict successful-round closure. On full acceptance it decodes every nested business batch/result, all physical wire/index/offer rows, logical maintenance request/reply bytes and timing rows. The new requested-chunk/event-count CSV fields must equal actual requests. It verifies actual complete descriptor/offset chunk assembly, full archive SHA and immutable writer file bytes, event continuity and exact event writer frame bytes, ACK targets and cycle boundaries. It checks the prospective counts against actual prefix sizes: 1785 logical RPCs at3072 (975chunk+801fetch+9barriers), 1298 at6144 (488+801+9). Unexpected legitimate retries or schema changes fail explicitly and retain the first audit error for review; they are not silently discarded or relabelled as successful measurements.

Nearest-rank p99 covers scheduled arrival through full accepted reply only when all6400 planned arrivals confirm distinct accepted orders; otherwise the all-arrival accepted percentile is null, with conditional percentiles separately labelled. The auditor recomputes fixed-window goodput, scheduler lateness, backlog, notSent/rejection/initial/final UNKNOWN and last-reply drain. Final-maintenance boundary drain comes from raw cycle receipts; full source drain is reported and checked for ordering because there is no separate raw terminal event. Finite overload remains a valid possible outcome; no sustained capacity or zero-latency claim is inferred.

## Actual Image evidence and limits

The current Java schema has **no per-reply Image-ID CSV**. Actual Header/Image association is enforced on every callback in frozen source. The auditor independently checks actual receiver term/MTU/derived maximum, bounded ever-seen immutable geometry (≤16), active-set/lifecycle closure (≤256 append-only events), nonregressing counters and maximum reply sizes. Valid receiver Images may be added/retired; the active set is not falsely required to remain fixed. Terminal per-Image association totals must equal decoded raw reply count, and aggregate largest reply must equal actual raw maximum. This is runtime association attestation with independent aggregate reconciliation, **not independently reconstructed per-packet/Image correlation**.

The generic supported Chunk application envelope is6919 plus32 Aeron session bytes =6951. The actual fixed-workload plan witness can be6727 and is not required to equal or exceed the generic maximum; both complete plans must match their frozen observations. Actual receiver geometry is checked from recorded metadata, never from ingress defaults. Telemetry uses variable bounded sample counts, exact process identities and explicit unavailable/exited records; coarse UTC phases do not establish Java/Python monotonic alignment or pure fsync timing.

## Root attestation gate

After both audits pass, create a new local summary:

```sh
python3 -B finalize_local_collection.py \
  --config /absolute/root-frozen-config.json \
  --collection /absolute/round-1/collection-r1 \
  --native-audit /absolute/round-1/native-audit-r1 \
  --raw-audit /absolute/round-1/raw-audit-r1 \
  --out /absolute/round-1/local-completion-r1
```

`LOCAL_COLLECTION_COMPLETE.json` binds actual reports/raw inputs/closed archive/native inventory. It does not alter the original collector receipt's pending marker; the new receipt supersedes that collection-only stage. `ROOT_GATE_CANDIDATE_NOT_APPROVED.json` deliberately has `collectionComplete:false` and `allRawInputsAndFailuresRetained:false`. Root must independently inspect the full source, local staging/build failures, all collection/audit attempts and raw closure before signing those two assertions and publishing the separate approved gate. This tool never uploads a gate, authorizes round2, deletes native files or changes their ownership. The native-removal approval remains false.

Preparation history is retained: superseded unexecuted r1-path draft; wrong-cwd local preparation failure before any write/network; guard-r2's real `.` path rejection failure; corrected r3 (14guards) and r4 (15guards) passes. Source-only syntax/pure guards are not a fresh cloud/natively executed benchmark proof. The final source still awaits validation against actual closed r3 cloud outputs and root's exact staged receipt.
