# Private-UDP cross-Pod experiment, 2026-10-26

Status: in progress. Three actual Runpod Pods run the same qualified matching JARs
(source `97db58e20f8dc52bde9be7b5ca7fe469b212da9a`, CI28 `40277635260`, artifact
`a21a720ddfd479faf1129176bc2ff1adff2e34084874ca621999a4cdb4ffe3f3`). No GPU
computation is used. Native private UDP passed both directions for 96/512/1248-byte
HMAC-authenticated preflight packets; Aeron uses MTU 1248 on the observed MTU-1300
interface. Provider private networking is limited to 100Mbps.

The first functional lineage passed actual matching, an externally injected leader
JVM SIGKILL (leader 2 to 0), rejoin/catch-up, a snapshot request, all-three-JVM cold
restart with the same mounted files, canonical snapshot and same-key replay
verification, followed by new accepted trades. The functional client shares Pod 1
with a replica; this is not an independent-generator capacity result. The kill is
between validated writer phases, not during an ongoing load. The 18.56-second
controller recovery probe includes SSH control, client JVM startup, connection,
snapshot/replay checks; it is not isolated election latency or first-new-order RTO.
No physical disk, power, Pod-loss or failure-domain independence claim follows.

A fourth, independent load Pod is being prepared. Its first provider instance
stalled without SSH despite restart/reset; that empty instance was stopped at
$0/hour before replacement, retaining the failure record. At most four roles run
simultaneously. Total incremental budget stays $3; all new test resources stop by
09:30 UTC. Capacity rates, gates and fixed parameters were registered before any
capacity measurement. No throughput or latency result is claimed yet.

Small original event/registration records are in
[`evidence/2026-10-26/runpod-private-cross-node/r1`](../evidence/2026-10-26/runpod-private-cross-node/r1/).
Full raw evidence and terminal resource status will follow after collection.

## Preliminary capacity observations

All six original Java capacity runs completed full canonical validation. An SSH
controller interruption initially lost observation of the last run; reconnecting
collected its original successful result, without rerunning or changing state. The
controller failure and recovery record are both retained. At 500/s, all-offered
p99 is20.071/23.159ms; at4,000/s it is19.841/15.509ms; at8,000/s it is
204.533/26.429ms. Each arm has a ten-second arrival window and two repetitions.
All arrivals were accepted with zero initial/final unknown and no not-sent.
4,000/s is the highest rate passing both registered100ms-p99/99%-goodput gates.
8,000/s has inconsistent tails; this is not a proven hard server throughput limit.

A separate6,000/s A/B/A/B comparison changes only the replicas' maximum data-path
idle park from1ms to100us. All other settings, workloads and artifact bytes stay
fixed. It is not yet complete. An immutable-archive auditor now independently
hashes every member, verifies deployed identities/configuration, and recomputes
all original capacity outcomes, p99 and backlog with the existing tested analyzer.
Seven new archive-boundary tests and38 existing analyzer tests pass locally;
the seven new tests also pass on the actual prepaid Linux CPU Pod. These targeted
tests do not constitute a new full Java/PostgreSQL/Web or hosted-CI pass.
