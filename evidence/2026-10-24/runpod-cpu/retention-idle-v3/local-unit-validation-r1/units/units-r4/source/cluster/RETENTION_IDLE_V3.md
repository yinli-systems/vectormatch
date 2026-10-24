# Retention V3 bounded park experiment

This is an opt-in configuration for the separate retention prototype. It changes the maximum requested backoff park and retains the spin, yield and minimum-park tuple for each selected role. It does not promise a sleep duration or a real-time latency bound: the OS may wake a parked thread later than requested. CPU cost and end-to-end latency must be measured together.

Without `vectormatch.retention.idleMaxParkNs`, the existing node driver and owner driver still use Agrona's no-argument backoff. Archive, consensus and service keep their existing library supplier paths and permitted external defaults. The normal launcher and other `ClusterClient` users retain their original settings.

The explicit property accepts exactly `1000000` or `100000` nanoseconds. Both arms must use the same new distribution and fresh experimental directories. Hidden selection through JVM option environment variables and conflicting Aeron idle-strategy overrides are rejected. The pilot validates before binding test ports or creating its output directory, then forwards the selected property explicitly to each owned node JVM.

| Selected owning role | Maximum spins | Maximum yields | Minimum requested park | Compared maximum requested park |
| --- | ---: | ---: | ---: | ---: |
| Each node's shared MediaDriver | 10 | 5 | 1,000ns | 1,000,000ns / 100,000ns |
| Each node's shared Archive | 10 | 20 | 1,000ns | 1,000,000ns / 100,000ns |
| Each node's consensus agent | 10 | 20 | 1,000ns | 1,000,000ns / 100,000ns |
| Each node's clustered service | 10 | 20 | 1,000ns | 1,000,000ns / 100,000ns |
| The sole batch owner's shared MediaDriver | 10 | 5 | 1,000ns | 1,000,000ns / 100,000ns |

Every successful creation returns a distinct mutable strategy. The pinned shared Archive, consensus and service paths each consume their factory twice; the shared driver has one explicit object. This gives seven creations per node plus one owner-driver creation (22 total across the three-node workload), associated with 13 selected logical roles. These are not counts of active threads or sleeps. The control clients used outside the arrival workload retain their original drivers and polling policy. Business batching, read credits, retry policy, force level, leader selection and protocol bytes are unchanged.

After a separately reviewed native/release gate, the single-arm entry is:

```sh
java --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED \
  --add-opens=java.base/java.util.zip=ALL-UNNAMED \
  -Dvectormatch.retention.idleMaxParkNs=100000 \
  -cp 'release/lib/*' io.vectormatch.cluster.RetentionCapacityAeronPilotV3 \
  /new/arm-directory idle-window8 42000
```

Use `1000000` for the control arm. The single-arm CLI requires an explicit selection. It fixes 6,400 arrivals at 500/s, batch cap 4, read window 8, chunk 6,144, event fetch 16, leader 0 and file sync 2. The same conservative read-window plan remains raw 38,033,404 bytes and allocated 589,327,865 bytes; the hard raw 2GiB / allocated-growth 2.5GiB caps remain unchanged. This short workload compares finite latency behavior and cannot establish sustained capacity.

The selected policy enters registration, source configuration, completion and source summary. The owner's transport observation binds its actual shared-driver context object and strategy description. Node attestations are recorded only after both launch calls return, using contexts retrieved from the launched components. Schema v2 binds the exact installed context identities, shared-driver object and every factory-created instance. Each record includes a per-role consumption ordinal, full configured tuple, bounded observed caller trace and source-derived intended use. Archive first creates a control-subscription retry strategy, then its shared runner strategy; consensus and service each create an internal-wait strategy before their runner strategy. The retry object may never idle. Per-role counts are exactly two; a third request fails before allocation. Driver creation is bounded to one. No ordering is assumed between different roles. Aeron exposes no supplier getter; attestation does not invoke a supplier again to create a fresh witness. The trace retains at most five frames with class/method strings capped at 256 UTF-8 bytes and explicit truncation information. The evidence does not read private runner fields, detect arbitrary post-consumption context mutation, count active agent threads, or measure actual sleep time. Exact inventory requires an enabled Archive control channel, SHARED mode and non-invoker consensus; unsupported scope is rejected before agent installation.

Before a selected node launches, it exclusively reserves `node-N/idle-observations/idle-000.intent.json` through `idle-255.intent.json`. A successful launch writes the corresponding new `.actual.json`; a failed launch retains its intent and consumes that slot. Restarts retain previous observations without overwriting them. Unsafe entries, missing intents and inventory exhaustion fail before another launch. A same-state restart must retain the exact code/profile/lineage/sync/idle identity.

The effective tuples and dispatch points are pinned to primary source: [Agrona 2.6.1 BackoffIdleStrategy](https://github.com/real-logic/agrona/blob/2.6.1/agrona/src/main/java/org/agrona/concurrent/BackoffIdleStrategy.java), [Aeron 1.53.3 driver Configuration](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-driver/src/main/java/io/aeron/driver/Configuration.java), [Archive](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/Archive.java), [ConsensusModule](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModule.java), [ClusteredServiceContainer](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/service/ClusteredServiceContainer.java), and [ClusteredMediaDriver](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ClusteredMediaDriver.java). The backoff alias in Aeron's factory has a fixed 1ms maximum; its factory properties select a strategy class, not a numeric park duration.

The internal constructor consumptions are pinned in [ArchiveConductor](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/ArchiveConductor.java#L232), [ConsensusModuleAgent](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModuleAgent.java#L226), and [ClusteredServiceAgent](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/service/ClusteredServiceAgent.java#L184). Intended private uses follow these pinned call sites; runtime factory traces remain observations of construction calls.
