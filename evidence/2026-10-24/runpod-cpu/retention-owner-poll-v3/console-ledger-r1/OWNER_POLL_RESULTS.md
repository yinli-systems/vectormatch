# Owner polling A/B/A/B results

The four finite observations do not establish a repeatable p99 improvement from changing the owner requested park cap from 1ms to 100us. Keep the default 1ms. The optional setting remains available for controlled experiments.

Each row is a fresh 33,792-order lineage at 500 scheduled orders/s over 67.584s, with 12 maintenance cycles and 24 read phases. All four accepted every order; UNKNOWN, rejection, not-sent, scheduler lateness over 20ms and qualified log warnings were 0. Counts from separate lineages are not one endurance result.

|Arm|Owner requested cap|All-arrival p99 (ms)|Maintenance wall (s)|Arrival-window goodput (/s)|Parent observed-span average cores|
|---|---:|---:|---:|---:|---:|
|A1|1000us|527.646352|6.380557899|499.955611|0.4135|
|B1|100us|529.979126|6.428236595|499.955611|0.4350|
|A2|1000us|528.734904|6.413005805|499.955611|0.4281|
|B2|100us|498.552924|6.081301120|499.955611|0.4228|

B1 versus A1: p99 increased 0.44%, maintenance wall increased 0.75%. B2 versus A2: p99 decreased 5.71%, maintenance wall decreased 5.17%. Goodput was identical in both pairs. The direction differs; two pairs on a shared host do not support a repeatable benefit or a statistical significance claim. CPU values are 1 Hz observations across each owned process span, including startup/maintenance/shutdown; they are not phase-aligned service CPU or exclusive-core guarantees.

For the same slowest 1% of arrivals in each arm, the timestamp decomposition below includes scheduling, queueing and maintenance waits. Temporal overlap alone does not identify a unique server/network/storage cause.

|Arm|Latency sum before dispatch|Latency sum overlapping maintenance while queued|
|---|---:|---:|
|A1|98.837%|98.374%|
|B1|98.801%|98.371%|
|A2|98.933%|98.400%|
|B2|98.694%|98.129%|

The source keeps its arrival clock running while maintenance pauses business dispatch. About 98% of slow-cohort latency overlaps maintenance. The next isolated candidate increases the event-fetch page from 16 to 32 without changing the retained read-credit bound 8, ACK/force/readback fencing or physical reply limits. Its local correctness tests are separate from a future same-artifact performance comparison.

Fixed controls: leader 0, term 0, sync 2, one CPU host / three JVM nodes / loopback UDP, server and client MediaDriver requested cap 100us, business batch 4, archive chunk 6144, event page 16, read window 8,128 logical workers / one physical client session, 50us business batch flush and the same finite admission/resource plan. Requested park caps do not bound actual OS scheduling delay.

Timing starts at the scheduled arrival and includes queueing, maintenance pauses and reply wait. The all-arrival accepted p99 exists only when every planned arrival confirms a distinct fresh ACCEPTED order. Canonical state reconciliation uses the same candidate reference implementation; no independent algorithm oracle is claimed.

Execution source `977197616ade0283174f2ea6ddfaa700547f6d15`; actual JAR fingerprint `23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884`; frozen release `0751fc006390f8ef94786479b3523f0272d0149df42f400aa8bf7de34f2a3c18`. The earlier 6033 artifact long observation and older three-Pod capacity curves are distinct cohorts.

Full original raw files, outer and inner native TARs, actual runtime JARs, identities/configuration, failed preparations, clean stops, strict audits and independent root reviews are in [arm1](../evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-1-r1/README.md), [arm2](../evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-2-r1/README.md), [arm3](../evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-3-r1/README.md) and [arm4](../evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-4-r1/README.md). [Derived comparison](../evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/comparison-r1/README.md) preserves the source, both paired outcomes, original hashes and portable mappings back to the archived inputs. The protected original native and PostgreSQL baselines remained unchanged.

This is not a throughput-limit, production SLA, hard realtime, 100M cumulative orders in one lineage, 100M orders/s or100M physical-connections proof.
