# Three-host Linux lab launchers

These launchers run one member per Linux host and optional gateway/projector processes, without systemd, Docker, a compiler, or Gradle on the remote host. They also work in root-capable containers with Linux `/proc`. They do not create cloud resources, configure routing/firewalls, or install PostgreSQL. Validate directly routed private IPv4 **UDP in both directions before deploying three members**. Processes on one host are not independent machine failure domains.

## Transfer a reproducible bundle

Build locally with JDK 21 and transfer the resulting artifacts together with the launchers:

```sh
./gradlew :cluster:installDist :server:installDist :projector:installDist
# Build web/dist locally with the existing web build instructions.
```

Expected remote tree (example root `/workspace/vectormatch`):

```text
vectormatch/
  deploy/remote-node.sh
  deploy/remote-workbench.sh
  deploy/remote_service.py
  dist/cluster/lib/*.jar        # cluster/build/install/cluster/lib
  dist/server/lib/*.jar         # server/build/install/server/lib
  dist/projector/lib/*.jar      # projector/build/install/projector/lib
  web/dist/                    # optional built workbench assets
  evidence/index.json          # optional verified evidence catalogue
```

Install JDK 21 on each host, set `JAVA_HOME`, and use Python 3.12 on Linux with `pidfd_open`/`pidfd_send_signal`. Jars are architecture-independent; the JDK must match the remote host. The defaults cap each node's Java heap at 1 GiB and gateway/projector heaps at 512 MiB. This is a development resource budget, not a tuned throughput profile; set `VECTOR_MAX_HEAP=2g` per role if measurements justify it. Keep adequate memory outside the Java heap for Aeron buffers, mappings, OS cache, and PostgreSQL.

`VECTOR_DIST_ROOT` can override `dist/`. In a complete source checkout the launcher also detects each module's `build/install/<module>` distribution. Launchers use a direct Java command, so they do not consume `JAVA_OPTS` from Gradle's generated scripts.

## Start exactly one member per host

Use the **same ordered member list**, port base, sync setting, outbox capacity, and MTU on all members. Replace these example addresses with the private addresses actually assigned to the three hosts:

```sh
cd /workspace/vectormatch
export JAVA_HOME=/workspace/tools/jdk-21
export VECTOR_CLUSTER_HOSTS='10.40.0.2,10.40.0.3,10.40.0.4'
export VECTOR_PORT_BASE=19000
export VECTOR_AERON_MTU_LENGTH=1248
export VECTOR_SYNC_LEVEL=2
export VECTOR_STATE_DIR=/workspace/vectormatch/runtime/cloud-generation-1

# Host at 10.40.0.2 runs node 0; host .3 runs node 1; host .4 runs node 2.
bash deploy/remote-node.sh start 0
bash deploy/remote-node.sh status 0
```

The launch success means the Java process survived initial launch; it does **not** mean quorum is ready. Inspect `runtime/cloud-generation-1/node-0/process.log`, then confirm a quorum-acknowledged command through a client. A two-node deployment of this three-member topology can form a majority, but cannot tolerate losing either of its running members. Do not report it as tested three-node failover.

Node ports are `19001..19005`, `19101..19105`, and `19201..19205` with the default base. Aeron peers also require routable dynamic response ports. Keep cluster traffic on the private network and permit it between trusted lab hosts in host firewalls; do not expose an unauthenticated cluster ingress publicly. A private link MTU of 1300 permits the default Aeron UDP payload MTU 1248 (plus IPv4/UDP headers). Recheck the actual path and packet captures rather than assuming the interface MTU proves path behavior.

```sh
# Run snapshot against the current leader only; failure on a follower is expected.
bash deploy/remote-node.sh snapshot 0
bash deploy/remote-node.sh stop 0
```

Every role has its own append-only `process.log`, `process.json` PID identity record, and `process.lock`. The launcher compares Linux process start ticks and the complete command-line SHA-256. `stop` opens a pidfd and rechecks identity before SIGTERM, waits up to 20 seconds, and never falls back to `pkill` or SIGKILL. A stale PID that now belongs to another process causes a refusal, never an unrelated signal. Persistent Archive/Cluster state is never deleted. Aeron may remove its own transient driver directory during normal shutdown.

If the environment terminates all descendant processes after an SSH/job session ends, keep the supervising remote job alive or use the platform's persistent process facility. `start_new_session` prevents ordinary terminal hangup propagation; it cannot override a provider's container/job lifecycle.

## Gateway and browser access

The gateway connects to all three members and uses a reachable client-side private IP for Aeron egress. A gateway may run on a member during a functional smoke test; run it on a separate host for an uncontaminated performance measurement. Keep a distinct state directory and embedded driver for every client process.

```sh
export VECTOR_CLIENT_EGRESS_HOST=10.40.0.2  # This host's private IP
export VM_HTTP_PORT=8000
bash deploy/remote-workbench.sh gateway start
bash deploy/remote-workbench.sh gateway status
```

The HTTP/WS workbench remains bound to `127.0.0.1`. Open an SSH tunnel from the local Mac:

```sh
ssh -N -L 8001:127.0.0.1:8000 -p SSH_PORT root@PUBLIC_SSH_HOST
# Then open http://127.0.0.1:8001 locally.
```

Use `bash deploy/remote-workbench.sh gateway stop` for graceful shutdown. `/health` and a committed command establish more than PID liveness. The UI sends synthetic trading flow by default; pause that flow before collecting controlled benchmark evidence.

## Optional PostgreSQL exporter

Connect to an existing PostgreSQL instance using a dedicated database role. PostgreSQL itself must run as a **non-root OS user**, even when the Java cluster and exporter run as root in the container. This launcher deliberately does not invoke local `deploy/postgres.sh` as root. For a local database, first install and initialize it under a dedicated OS user, bind it to loopback, and enable `fsync=on` and `synchronous_commit=on`. No replication/disk durability claim follows just from these settings.

```sh
export VM_PG_URL='jdbc:postgresql://127.0.0.1:55432/postgres'
export VM_PG_USER=vectormatch
export VM_CLUSTER_ID='cloud-generation-1'  # Stable ID for this specific source lineage
# Supply VM_PG_PASSWORD via the environment when authentication requires it.
export VECTOR_CLIENT_EGRESS_HOST=10.40.0.2
bash deploy/remote-workbench.sh projector init
bash deploy/remote-workbench.sh projector start
bash deploy/remote-workbench.sh projector status     # Process identity only
bash deploy/remote-workbench.sh projector db-status  # Real committed database cursor
bash deploy/remote-workbench.sh projector stop
```

`once` exports one batch in the foreground and refuses to share the running watch process's driver directory. `init` and `db-status` only access PostgreSQL, so they do not require cluster host/egress environment. The gateway reads the same PostgreSQL observation only when its own environment includes `VM_PG_URL` and `VM_CLUSTER_ID` at startup. Passwords and JDBC URLs are inherited through the environment and are not written to launcher PID records.

Never reuse `VM_CLUSTER_ID` for a reset source cluster, and never restore an old database behind already acknowledged source events. See [the projector contract](../projector/README.md) for commit-before-ack, terminal gaps, and the limits of lineage detection. A projector on a member host is a functional convenience, not an independently replicated database.

## Verify the supervisor locally

```sh
python3 -m unittest discover -s deploy -p 'test_remote_service.py' -v
```

These tests exercise process identity parsing, stale-PID and signal-race refusals, remote network defaults, and secret-free process arguments. They do not count as cloud UDP, quorum, or independent-host fault evidence.

## Isolated fixed-leader capacity tests

The recorded [capacity campaign](../docs/CAPACITY_RESULTS.md) uses separate trial directories and port base 23000. `VECTOR_APPOINTED_LEADER_ID=0` pins Aeron's **test-only** appointed leader; `VECTOR_MAX_CLUSTER_SESSIONS=128` permits the declared client concurrency. Leave these unset for normal application election and session defaults. Both settings enter the supervisor's non-secret configuration fingerprint.

For the separate 190k-arrival fixture, select the same explicit settings on every member:

```sh
export VECTOR_STATE_DIR=/opt/vectormatch/runtime/FRESH-CAPACITY-TRIAL
export VECTOR_PORT_BASE=23000
export VECTOR_SYNC_LEVEL=2
export VECTOR_MAX_HEAP=2g
export VECTOR_APPOINTED_LEADER_ID=0
export VECTOR_MAX_CLUSTER_SESSIONS=128
export VECTOR_STATE_PROFILE=capacity-190k-v1
export VECTOR_OUTBOX_CAPACITY=524288
```

The node's recorded arguments include its heap, state profile and outbox; startup logs include exact core limits, cache policy and checkpoint bound. The state profile also enters the configuration fingerprint. This test profile requires exact limits and rejects incompatible checkpoints; it does not upgrade the original application state. See [checkpoint capacity](../cluster/CAPACITY.md). Use the pinned immutable node/load artifacts and prepared-state hashes for comparisons; the larger fixture is a separate curve from the default profile.
