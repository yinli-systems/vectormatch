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
