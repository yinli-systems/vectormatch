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

Every selected role has a distinct mutable strategy. The control clients used outside the arrival workload retain their original drivers and polling policy. Business batching, read credits, retry policy, force level, leader selection and protocol bytes are unchanged.

After a separately reviewed native/release gate, the single-arm entry is:

```sh
java --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED \
  --add-opens=java.base/java.util.zip=ALL-UNNAMED \
  -Dvectormatch.retention.idleMaxParkNs=100000 \
  -cp 'release/lib/*' io.vectormatch.cluster.RetentionCapacityAeronPilotV3 \
  /new/arm-directory idle-window8 42000
```

Use `1000000` for the control arm. The single-arm CLI requires an explicit selection. It fixes 6,400 arrivals at 500/s, batch cap 4, read window 8, chunk 6,144, event fetch 16, leader 0 and file sync 2. The same conservative read-window plan remains raw 38,033,404 bytes and allocated 589,327,865 bytes; the hard raw 2GiB / allocated-growth 2.5GiB caps remain unchanged. This short workload compares finite latency behavior and cannot establish sustained capacity.

The selected policy enters registration, source configuration, completion and source summary. The owner's transport observation binds its actual shared-driver context object and strategy description. Node attestations are recorded only after both launch calls return, using contexts retrieved from the launched components. They bind the exact installed context identities, shared-driver object and the strategy objects returned when the pinned role constructors consumed their suppliers. Aeron exposes no supplier getter; attestation does not invoke a supplier again to create a fresh witness. The evidence does not detect arbitrary post-consumption mutation of a private context or measure the actual time spent asleep.

Before a selected node launches, it exclusively reserves `node-N/idle-observations/idle-000.intent.json` through `idle-255.intent.json`. A successful launch writes the corresponding new `.actual.json`; a failed launch retains its intent and consumes that slot. Restarts retain previous observations without overwriting them. Unsafe entries, missing intents and inventory exhaustion fail before another launch. A same-state restart must retain the exact code/profile/lineage/sync/idle identity.

The effective tuples and dispatch points are pinned to primary source: [Agrona 2.6.1 BackoffIdleStrategy](https://github.com/real-logic/agrona/blob/2.6.1/agrona/src/main/java/org/agrona/concurrent/BackoffIdleStrategy.java), [Aeron 1.53.3 driver Configuration](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-driver/src/main/java/io/aeron/driver/Configuration.java), [Archive](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/Archive.java), [ConsensusModule](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModule.java), [ClusteredServiceContainer](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/service/ClusteredServiceContainer.java), and [ClusteredMediaDriver](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ClusteredMediaDriver.java). The backoff alias in Aeron's factory has a fixed 1ms maximum; its factory properties select a strategy class, not a numeric park duration.
