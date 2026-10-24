# Maintained-load CPU observations

The first offered-rate increase from500/s to1000/s produced substantial backlog. Eventual acceptance is not in-window capacity. Higher presets are deferred while the slowdown is investigated.

|Offered/s|Arrivals|Window s|In-window accepted/s|Scheduled-arrival p50 ms|Scheduled-arrival p99 ms|Sampled queue high-water|Outcome|
|---:|---:|---:|---:|---:|---:|---:|---|
|500|10000|20|499.90|6.502568|265.879867|3|Finite no-loss observation|
|1000|20000|20|666.05|4960.984286|11047.394780|6903|Backlog;1000/s not sustained|

Both runs eventually accepted every planned order with zero observed/final UNKNOWN, rejected/notSent orders and scheduler lateness>20ms. At1000/s the last reply arrived10.767631664seconds after the exposure window; final maintenance/source drain completed12.026292145seconds after it. No throughput ceiling, latency SLA or endurance result is established.

Same application source `b97ef13ecad3279c4c8c4c7b91958d906fbd1d0e`, actual four-anchor installed-JAR fingerprint `2d6267a65f2902e638bb7c005ef20febcb3c6b9b2cdd796ef0fc5f1172ead50e`; leader0, sync2, batch4, chunk6144, event page32, maintenance read32, owner1ms, driver100us, W128/Q64 and one physical client session. All nodes share one CPU host and loopback UDP. Each row uses a fresh lineage and seeds enough inventory for its own finite planned arrivals. Thus duration remains20seconds while offered rate and total planned arrivals vary. The longer read8/32 ABAB experiment belongs to a different artifact/cohort and is not merged into this curve.

Complete original outer/inner native archives and all raw outcomes passed independent local full-member SHA/size/mode/owner/empty-directory streaming checks. CSV p99 was independently recomputed. Candidate-codec full decode/encode tied every arrival's original identity, command hash and result to physical requests/replies and complete frame-index/offer associations. Candidate matching reference and matching three checkpoint logs remain distinct from an independent matching oracle, binary snapshot decode and cold recovery.

Seven maintenance cycles at1000/s took15.134628574seconds total, compared with1.061315932seconds across four cycles at500/s. Disjoint within-cycle spans at1000/s include6.299984432seconds archive reading,4.737553177seconds event reading and2.699358507seconds in verify/writer gaps. Such gaps are not isolated filesystem-force timings. Per-RPC elapsed intervals overlap and are not added as wall time. Slowest1% predispatch shares are97.79%/99.41%. Sampled per-process CPU averaged below one core across setup/load/finalisation spans. Whole-host I/O-wait tick shares were0.28%/3.88%; those counters cannot identify our storage cost. No isolated network/server/disk cause is established yet. Aeron CNC files are absent after normal driver cleanup, so no transport-retransmission claim is made.

Evidence: [500/s complete original qualification](../evidence/2026-10-24/runpod-cpu/retention-maintained-capacity-v3/first-native-500-r1/README.md), [1000/s full original evidence and phase analysis](../evidence/2026-10-24/runpod-cpu/retention-maintained-capacity-v3/native-1000-r1/README.md), [53-test local source/build qualification](../evidence/2026-10-24/runpod-cpu/retention-maintained-capacity-v3/local-validation-r1/README.md).
