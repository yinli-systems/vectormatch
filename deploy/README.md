# Local replicated matching cluster

This harness launches **three JVM processes on the same machine**, communicating over loopback UDP. It demonstrates process failover and log/snapshot recovery. It does not demonstrate independent-machine, disk, availability-zone, or power-loss resilience.

The implementation uses the published Aeron 1.53.3 artifacts and APIs. Source references:

- [Official Cluster tutorial](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-samples/src/main/java/io/aeron/samples/cluster/tutorial/BasicAuctionClusteredServiceNode.java)
- [ClusteredService lifecycle](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/service/ClusteredService.java)
- [Archive persistence configuration](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/Archive.java)

## Run

```sh
./gradlew :cluster:installDist
deploy/cluster.sh start
deploy/cluster.sh status
deploy/cluster.sh snapshot
deploy/cluster.sh stop
```

The state path defaults to `runtime/cluster`; it contains separate `archive`, `cluster`, and transient `driver` directories per node. Archive/cluster data is preserved across restarts. The launcher never deletes it. Ports are `19001..19005`, `19101..19105`, and `19201..19205` by default. All endpoints bind to `127.0.0.1`. The node topology is intentionally local and must be replaced before any multi-machine deployment.

```sh
./gradlew :cluster:failoverSmoke
```

The smoke test starts its own isolated cluster and reports process IDs, old/new leaders, observed command results, and canonical core state hashes before/after recovery. Read the generated node logs if it fails. The test leaves evidence behind and cleans up only the processes it owns.

## Durability profiles

`VECTOR_SYNC_LEVEL=0` uses ordinary cached writes. Process termination testing with this profile does **not** establish host-power-loss durability.

`VECTOR_SYNC_LEVEL=2` is the launcher default. It sets Archive data, Archive catalog, and ConsensusModule metadata synchronization to level 2 on every node. This requests file data and metadata synchronization; end-to-end guarantees still depend on the operating system, filesystem, device, and tested fault model. Report this setting with every benchmark. Never compare profile 0 throughput against profile 2 without disclosing the difference. Restarting an already-running node does not change its configuration; inspect its launch command and startup log.

The development profile uses shared media/archive threads, backoff idle strategies, and 128 KiB socket buffer requests. Ingress and Archive control channels explicitly use 64 KiB terms; the replicated log preserves Aeron's default 64 MiB term unless configured otherwise, and other IPC publication sizes follow driver defaults. It is not the final low-latency production tuning profile. Do not run benchmarks while the machine is sleeping, heavily loaded, or sharing CPU with a load generator and describe the results as independent-host measurements.

## State-machine boundaries

Command handling and core snapshot restoration run only in the Cluster service thread. Business decisions use neither local wall clocks nor external database reads. Transport correlation IDs are independent from business idempotency keys. A timeout remains an unknown result and must be resolved with the same command identity.

Snapshot messages are versioned and chunked to Aeron's payload limit. Recovery rejects truncated, out-of-order, or checksum-mismatched snapshots. The client and current command codec are a bounded, versioned development protocol; future generated SBE schemas will need an explicit migration path.

The current cluster checkpoint wraps the core snapshot plus a bounded replicated event outbox and its acknowledgement watermark. It is intentionally incompatible with the earlier core-only development checkpoint. Keep old evidence directories and launch this version against a fresh state directory; do not silently discard or reinterpret old data.

## Reliable event export

`ClusterClient.fetchEvents(fromSeq, maxCount, timeout)` returns events from the inclusive starting sequence. Responses contain at most 16 events, so consumers advance by the last received sequence and repeat. Reading does not consume events. The queue defaults to 65,536 events, configurable via `VECTOR_OUTBOX_CAPACITY`, and is included in the replicated checkpoint.

Commit the events, materialized projection, and contiguous consumer cursor in one PostgreSQL transaction. Only then call `ackExport(throughSeq, timeout)`. Acknowledgement is replicated, idempotent, monotonic, and releases capacity. Requests for reclaimed sequences explicitly fail instead of silently skipping data. A consumer crash after the database commits but before acknowledgement will cause a repeat fetch; unique event IDs and the database cursor handle duplicates.

There is one trusted exporter in this release. The protocol does not provide multi-exporter fencing, consumer groups, authorization, or backup of events already acknowledged and reclaimed. A restored database must retain its committed cursor and data; restoring an older backup requires separate retained logs/rebuild procedures.

Before applying a business command, the core computes a deterministic upper bound on its new event count. If the outbox cannot reserve that space, the service responds with `OUTBOX_FULL` and does not consume the command's request sequence or mutate balances/orders. The same key can be retried after export resumes. Cached idempotent results remain queryable while full. Large sweeps whose event budget exceeds the entire queue are explicitly rejected rather than partially executed.

`ClusterClient.readSnapshot(timeout)` reads a frozen canonical **core** snapshot for mirror initialization. Each wire chunk carries a consistent digest token; the client verifies the complete SHA-256 digest before returning it. It can safely retry if another reader replaces the frozen view or recovery expires it. This administrative path allocates and copies the snapshot on every member; do not run it per order or include its cost invisibly in a low-latency benchmark.

Service egress is attempted once per response. A slow or disconnected client cannot indefinitely block the replicated state machine. Its committed result remains recoverable through business idempotency. The local default binds to loopback; configured remote mode uses explicit private IPv4 addresses. This transport has no authentication, so remote lab access is limited to the authorized private network; production access control belongs at an authenticated gateway.

## Remote process configuration

The [remote launcher](REMOTE.md) checks both process identity and a versioned fingerprint of explicitly non-secret configuration before treating a repeated `start` as idempotent. The fingerprint covers membership, UDP MTU, client return address/port, and the applicable projector lineage/driver/batch/timeout settings. Changed arguments or fingerprint require an explicit `stop` before a new `start`. Older PID records without this fingerprint also require an explicit stop; the launcher does not assume their configuration matches.

PID ownership and `stop` still use only the recorded Linux start ticks and complete command-line hash. Changing or removing current environment settings does not prevent safely stopping the previously owned process. Fingerprints contain only an allowlist; passwords, tokens, JDBC URLs and database usernames are neither saved nor hashed into them. Database connection/credential changes therefore also require an explicit stop/start; a repeated start does not detect those excluded values.
