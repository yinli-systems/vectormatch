# Fixed-page32 read window8/32: actual CPU observations

The completed8/32/8/32 campaign reduced all-arrival p99 by47.90% and42.45% in its two paired comparisons. Maintenance wall time fell42.44% and37.35%. The direction repeats at fixed500/s; this is not a stable-throughput ceiling or a hard-realtime result. The read32 mode remains an explicit experiment; default constructors retain their original policy.

|Arm|Read window|All-arrival p99 ms|Maintenance wall s|Observed read offered high-water|Sampled backlog high-water|Arrival-window goodput/s|
|---|---:|---:|---:|---:|---:|---:|
|A1|8|461.636399|5.585550780|8|209|499.955611|
|B1|32|240.505770|3.215141554|32|121|499.955611|
|A2|8|426.612864|5.213499026|8|244|499.955611|
|B2|32|245.508282|3.266074240|32|108|499.955611|

Each row is one fresh33792-order lineage scheduled at500/s over67.584s. Every planned order was uniquely accepted. All four rows had zero observed/final UNKNOWN, rejection, not-sent and scheduler lateness>20ms.33789 confirmations fell inside each arrival window. Separate reset lineages cannot be added into a single endurance total.

The same application source605eb43fcafd8fa0a6287304387c93c4d1bbddf6, actual four-anchor code fingerprintd0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea and release35652d5dd4175e2f7fff500147ce084a41d9ae7a3c6951b9c67374b780ec05d0 run both arms. Fixed factors: page32, batch4, archive chunk6144, owner requested park1ms, server/driver requested park100us, appointed leader0/sync2, W128/Q64, one physical client session, physical registry129 and common max-read32 staging/failure envelope. Only requested maintenance read credits change8→32. An actual shared-host three-JVM loopback UDP cluster is used; this is not three physical machines.

The replacement CPU container33ace3d92505 has a separately qualified boot, affinity/cgroup budget, JDK and homogeneous installed-JAR class origins. Its old restoration/preparation trees are absent and protected as absent. It does not inherit the old container's57-file/PG989 state or performance qualification. The user-authorised idle Gradle daemon was stopped through an exact pidfd SIGTERM before preflight; no forced kill was used.

All5 full-collection/byte/native/raw/finalisation steps passed, followed by separate root full outer-member SHA/size/mode/owner/empty-directory streaming verification, original-to-materialised metadata binding, complete raw-input rehash and33792-row scheduled-arrival p99 recomputation. Canonical reference uses the candidate matching implementation and3 matching checkpoint logs; no independent algorithm oracle, binary snapshot-record decode or cold application restart proof is claimed.

p99 measures scheduled arrival through final reply, including client queueing and maintenance. Requested park caps do not bound OS scheduling. Higher read credits improve both fixed500/s pairs; this does not isolate network, server and disk costs or establish a throughput ceiling. Overlapping per-RPC elapsed intervals are not added as wall time. Backlog is sampled, not a continuous maximum.100M lifetime orders,100M orders/s,100M physical connections and hard realtime remain unproved.

Full evidence: [A1](../evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-1-r1/README.md), [B1](../evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-2-r1/README.md), [A2](../evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-3-r1/README.md), [B2](../evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-4-r1/README.md). B2 also preserves the complete four-arm comparison, all input bindings and independent four-CSV arithmetic review. A1 retains the initial read-only collection failure and corrected collector preparation; no orders were rerun. Each arm's complete native archives, source/configuration, wire/CSV, actual process closure and raw/root reviews remain retained. B1 also retains A1's actual private-push/readback and continuation gate.
