# Explicit fixed-page32 LONG read8/32 parser source preparation

This scope is an independent source-only parser namespace. It does not alter the
old closed event-page parser or any old archive, helper, index or controller.
`baseline` preserves the entire old parser preparation, including both original
guard attempts and its 42-guard final receipt. `collector-baseline` preserves the
actual c913 adapter, isolated loader and freeze for interface review.

New calls explicitly select page32 and read8 or read32:

```
audit_raw.audit_read_window32_arm(selected_window, arm_root,
    event_fetch_count=32, workload=LONG, local_functional_only=False)
read_phase_audit.audit_read_window32_phases(..., selected_window,
    event_fetch_count=32, maximum_read_phases=24, expected_phase_count=24)
workload_contract.validate_actual_plan_observation(observation, registered_plan,
    actual_code, selected_window=selected_window, event_fetch_count=32)
```

There are no old `audit_arm` or `audit_rpc_phases` aliases. Explicit page16 is
rejected by these new experiment entry points. The unchanged general wire decoder
still decodes valid FetchEvents count1..32; the selected full-page/final-partial
contract then requires page32. New `common.load_config` fails closed before file
access. A future separately reviewed controller/common schema, exact new release,
actual Linux class origins, closed lifecycle, native collection and full raw gate
must be supplied. Old d923/87a qualification cannot qualify source605/d0.

The only active metadata fixture is the actual local installed-JAR observation
for source `605eb43fcafd8fa0a6287304387c93c4d1bbddf6` and fingerprint
`d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea`.
It is explicitly local macOS metadata, not actual Linux/native execution. Both
selected-window Plans at fixed page32 must match this full observation and differ
only in requestedReadWindow. Both reserve maxRead32, raw182433396,
growth754102673, staging1984256 and failure1073760. Actual codec/RPC bounds are
5131 logical/2113 event/2982 archive, with unchanged journal96/117792, offer4,
raw2GiB/growth2.5GiB/floor1GiB and complete reply6919+32 envelope. The actual
runtime configuration additionally binds constructed owner1ms and driver100us.
An equal Plan observation proves selected policy and prospective bounds only.

The strict workload remains 33792 scheduled arrivals at 500/s, 67.584 seconds,
three exact setup commands, 12 maintenance cycles, 24 consecutive ordered read
phases, ten setup-free full load cuts, and the exact final partial command/event
prefix. All-arrival identity/unique-result reconciliation, 13-column RPC schema,
complete original/callback SHA and earliest owner-completion binding, four-offer
and finite retry caps, scheduler admission, UNKNOWN rejection, business/read and
control/read exclusion, full cycle dispatch exclusion, canonical bytes and
force/readback before both ACKs remain. Every completed-unconsumed read retains a
credit; actual occupancy is source-enforced/runtime-attested and cannot be
independently reconstructed from CSV without consume timestamps. Overlapping RPC
elapsed sums are not wall time.

The new failure-bundle seam reconciles zero through selected32 outstanding
originals, exact correlation/SHA/scope/kind, four possible offers and original
absolute deadlines. It distinguishes consumed identities already present in full
logical tapes from outstanding failure originals. A failed disk write is never
relabelled durable or ACK-authorizing. It does not replace full all-outcome byte
archival. The unchanged physical registry stays129 because read and business or
control phases remain exclusive.

Pure Python guards exercise actual local metadata semantics, synthetic32-credit
overlap and invalid33, strict selected8, full24 phases, complete originals and
failure variants, malformed/maximum UTF8 codec, and actual receiver geometry
schema. They also preserve the inherited correlation, callback, logical/control
phase, setup, scheduler and archive closure guards. Synthetic binary fixtures and
invented timestamps/identity/geometry rows are explicitly protocol/schema guards,
not captured JVM wires, native data, cloud benchmark evidence or runtime success.

This preparation does not run an actual raw/native auditor, Java, Gradle, SSH,
Git, or a business session. It claims no release readiness, Linux/native
qualification, speedup, throughput ceiling, hard real-time or 100M result.
