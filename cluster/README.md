# Cluster deployment and network configuration

The Cluster supports directly routed, bindable IPv4 addresses. Local development defaults remain three members on `127.0.0.1`. Remote deployments must explicitly configure membership and the client's return address; no node or client silently falls back to loopback when remote membership is configured.

## Environment contract

| Variable | Scope | Default / meaning |
|---|---|---|
| `VECTOR_CLUSTER_HOSTS` | Every node and client | Unset means three loopback members. Otherwise 1–3 comma-separated literal unicast IPv4 addresses, ordered by member ID starting at 0. |
| `VECTOR_PORT_BASE` | Node CLI when positional port is omitted | `19000`. Existing applications pass the port base to `ClusterClient(Path, int)` explicitly. |
| `VECTOR_SYNC_LEVEL` | Node CLI when positional sync is omitted | `0` for the direct Java entry point; specify `2` explicitly for durable experiments. Deployment scripts may provide a stricter default. |
| `VECTOR_OUTBOX_CAPACITY` | Node CLI when positional capacity is omitted | `65536`, subject to the serialized-state budget. |
| `VECTOR_STATE_PROFILE` | Every node | `default`; explicit `capacity-190k-v1` selects the separate capacity-test limits described in [CAPACITY.md](CAPACITY.md). |
| `VECTOR_CLIENT_EGRESS_HOST` | Client processes | `127.0.0.1` only for a local topology. **Required** for remote membership. Must be assigned to the client host and reachable by all members. |
| `VECTOR_CLIENT_EGRESS_PORT` | Client processes | `0` allocates an ephemeral UDP receive port. A fixed value must be 1024–65535 and not collide with a member endpoint on that address. |
| `VECTOR_AERON_MTU_LENGTH` | Every node and client | `1408`; allowed 64–65504, aligned to 32 bytes. Use **1248** for an IPv4 private link with MTU 1300. |

All participants must use the same membership order, port base, and network MTU. The startup log prints the resolved membership and MTU. Changing membership or recorded MTU on existing state is an upgrade/migration operation; use a fresh experimental state directory unless that migration has been explicitly tested.

Addresses must be canonical dotted IPv4 literals. DNS names, wildcard/unspecified addresses, multicast/reserved addresses, URI fragments, empty members, and mixed loopback/remote membership are rejected. The node's selected address and the client's egress address must exist on a local network interface before a driver starts. Topology construction does not probe remote reachability; test bidirectional UDP before deploying the Cluster.

The same address is used for the node's advertised endpoints and local socket bindings. The client's egress address likewise serves as both receive bind and advertised response address. Separate bind/advertise addresses, NAT port rewriting, public Runpod port mappings, IPv6, TLS and automatic service discovery are not implemented. Run this unauthenticated development protocol only on the authorized private network.

## Ports and routing

For member `n`, a role's UDP port is `base + 100*n + offset`:

| Offset | Role |
|---:|---|
| 1 | Remote Archive control |
| 2 | Client ingress |
| 3 | Consensus |
| 4 | Replicated log |
| 5 | Follower catch-up |

For base 19000, member 0 uses 19001–19005, member 1 uses 19101–19105, and member 2 uses 19201–19205. Archive replication and its response endpoints bind the selected member IP with ephemeral ports. Client responses use the explicitly configured client IP and fixed/ephemeral egress port. Permit the required bidirectional UDP traffic within the private network, including those ephemeral ports; forwarding only TCP or only the five member ports is insufficient.

Local Archive control remains IPC. Every UDP publication gets the configured MTU: client ingress/egress, consensus, replicated log, Archive control, and replication. Both server-side `Archive.Context.controlMtuLength` and client-side `AeronArchive.Context.controlMtuLength` are set explicitly, avoiding the Archive control default overriding the driver's network MTU.

Snapshot publications are recorded over IPC but also receive the network-safe MTU. This is deliberate: [Archive replay builds its publication using the original recording's MTU](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/ArchiveConductor.java#L893). Keeping an IPC snapshot at 1408 could therefore produce oversized UDP packets during later snapshot replication on a 1300-MTU link. Ordinary IPC publication defaults are unchanged. With MTU 1248, IPv4+UDP overhead adds 28 bytes, giving 1276 bytes, below 1300.

## Node CLI

```text
ClusterNodeMain <member-id> <state-parent> [port-base] [sync:0|2] [outbox-capacity] [hosts-csv] [state-profile]
```

Positional arguments override the corresponding environment variables. The optional sixth and seventh arguments override `VECTOR_CLUSTER_HOSTS` and `VECTOR_STATE_PROFILE`; earlier launcher contracts remain supported. Member IDs must exist in the configured membership. The persistent node directory is `<state-parent>/node-<member-id>`.

After `./gradlew :cluster:installDist`, launch this on member 0, substituting its actual private addresses:

```sh
export VECTOR_CLUSTER_HOSTS='10.20.0.1,10.20.0.2,10.20.0.3'
export VECTOR_AERON_MTU_LENGTH=1248
cluster/build/install/cluster/bin/cluster 0 /workspace/vectormatch/state 19000 2 65536
```

Members 1 and 2 use identical environment and arguments except their member IDs. Do not use the illustrative addresses unless they are assigned to those machines. Bind failures and invalid configuration are fatal; they do not trigger localhost fallback.

Two listed members are supported for deliberate connectivity experiments, but both are needed for majority progress and that configuration tolerates no member loss. The two-node UDP provisioning gate does not require starting a two-member Raft cluster. After verifying that network, provision member 3 and launch a fresh three-member experimental Cluster. Do not interpret replacing a two-member CSV with a three-member CSV as a membership-change protocol.

## Client API

Existing application code remains valid:

```java
// Reads membership, egress endpoint and MTU from the environment.
try (ClusterClient client = new ClusterClient(driverDirectory, 19000)) {
    var position = client.position(Duration.ofSeconds(30));
}
```

On a client running at `10.20.0.4`, set:

```sh
export VECTOR_CLUSTER_HOSTS='10.20.0.1,10.20.0.2,10.20.0.3'
export VECTOR_CLIENT_EGRESS_HOST='10.20.0.4'
export VECTOR_CLIENT_EGRESS_PORT=0
export VECTOR_AERON_MTU_LENGTH=1248
```

Embedded callers can avoid ambient environment settings with the explicit constructor:

```java
new ClusterClient(driverDirectory,
    ClusterTopology.parse(19000, "10.20.0.1,10.20.0.2,10.20.0.3"),
    new ClientEndpoint("10.20.0.4", 0), new NetworkTransport(1248));
```

Each client remains confined to one owning thread. Use unique driver directories per process and `pollKeepAlive()` while idle. Aeron's active-driver directory checks remain enabled.

## Verification and evidence

```sh
./gradlew :cluster:test
VECTOR_AERON_MTU_LENGTH=1248 ./gradlew :cluster:failoverSmoke
```

Unset remote membership/client variables before running the local three-process harnesses. Tests cover exact remote endpoint generation, local compatibility, two-member configuration, CLI/environment precedence, invalid/unsafe configuration, callback address requirements, MTU protocol bounds, and actual IPC snapshot publication payload limits with ordinary IPC defaults preserved. The local low-MTU smoke exercises command processing, leader process termination, outbox backpressure/acknowledgement, snapshots, full restart and multi-chunk core snapshot reads.

Local tests establish functionality, not multi-host reachability, physical isolation, or multi-machine fault tolerance. Remote UDP checks and actual remote Cluster results must be recorded separately with their topology, MTU, runtime/host evidence, synchronization settings and limitations. The historical local benchmark evidence is preserved without being relabelled as remote performance.

See [CAPACITY.md](CAPACITY.md) for state bounds and [BENCHMARKS.md](BENCHMARKS.md) for existing measurements and their scope.
