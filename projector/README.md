# Recoverable PostgreSQL event projection

This module exports the **Aeron Cluster replicated outbox**, not the standalone workbench journal. It stores private events, small durable counters, and the export cursor in a single PostgreSQL transaction. There is no public HTTP endpoint in this module.

## Commit and recovery contract

1. Read the durable database cursor and fetch from `cursor + 1`, inclusively, with at most 16 events.
2. Lock the cluster's cursor row with `SELECT ... FOR UPDATE`.
3. Validate contiguous event sequences and public market sequences. Existing event IDs must match both canonical SHA-256 and JSONB content. A different payload is a terminal integrity error.
4. Insert events and update event/trade counters and cursor in the same transaction. PostgreSQL `synchronous_commit=on` is set locally; `fsync=off` is rejected.
5. Only **after** PostgreSQL commits, acknowledge the cursor to the replicated outbox.

If the projector dies before commit, PostgreSQL rolls back and the events remain in the source. If it dies after commit but before acknowledgement, the next process reads the committed cursor, fetches from the next sequence, and acknowledges the already committed position. Retrying an overlapping batch verifies and skips duplicates. Multiple exporters serialize at the same cursor row; a source-reclamation race causes a database-cursor reread before retrying.

The source cluster ID is a **stable lineage identifier**, not just a display name. Never reuse it for a reset cluster or a different PostgreSQL database. A source that has reclaimed events beyond the restored database cursor is a terminal gap; the projector does not silently jump forward or pretend that a current snapshot contains historical events. Restore matching durable data or rebuild from retained original input logs. Back up the database after source acknowledgement; an acknowledged outbox does not retain a second copy of that history.

These guarantees depend on PostgreSQL storage and hardware honoring persistence. This module does not establish database replication or independent machine failure domains.

## Run

Initialize the three-node cluster using the repository's cluster instructions. Run from the repository root:

```sh
source scripts/env.sh
export VM_PG_URL='jdbc:postgresql://127.0.0.1:55432/postgres'
export VM_PG_USER='vectormatch'
export VM_CLUSTER_ID='local-cluster-generation-1'
# If required, provide VM_PG_PASSWORD through your environment or secret manager.

gradle :projector:run --args=init
gradle :projector:run --args=once
gradle :projector:run --args=watch
gradle :projector:run --args=status
```

`once` performs **one batch**, not an unbounded drain. `watch` drains available batches, sleeps when caught up, and retries database/transport failures with bounded exponential backoff. Gaps and payload conflicts terminate with a nonzero exit. `status` only reads PostgreSQL and does not connect to the cluster; initialize the schema first.

Set a different `VM_PROJECTOR_DRIVER` directory for each concurrent projector process. Cluster clients are thread-confined and must not share the same embedded driver directory.

| Environment | System property | Default |
| --- | --- | --- |
| `VM_PG_URL` | `vm.pg.url` | Required PostgreSQL JDBC URL |
| `VM_PG_USER` | `vm.pg.user` | JDBC/URL default |
| `VM_PG_PASSWORD` | `vm.pg.password` | JDBC/URL default |
| `VM_CLUSTER_ID` | `vm.cluster.id` | Required stable lineage ID |
| `VM_CLUSTER_PORT_BASE` | `vm.cluster.portBase` | `19000` |
| `VM_PROJECTOR_DRIVER` | `vm.projector.driver` | `runtime/projector-driver` |
| `VM_PROJECTOR_BATCH_SIZE` | `vm.projector.batchSize` | `16`, supported range 1–16 |
| `VM_PROJECTOR_TIMEOUT_MS` | `vm.projector.timeoutMs` | `10000` |
| `VM_PROJECTOR_POLL_MS` | `vm.projector.pollMs` | `100` |

The Gradle `run` task runs a child JVM. Use environment variables for configuration when invoking Gradle; `-D` properties need to reach the application JVM when running the installed distribution directly. Generate it with `gradle :projector:installDist`, then use `projector/build/install/projector/bin/projector watch` and `JAVA_OPTS` if system properties are preferred. Credentials are never emitted in the configuration string or CLI JDBC diagnostics.

## Measurements

JSON reports contain durable `cursor`, `marketSeq`, `eventsStored`, `tradesStored`, `batchesCommitted`, and `sourceLastObservedSeq`. `lag` is the last observed source high-water mark minus the committed database cursor; it is not a claim about the source's current unseen position.

Process counters distinguish inserted rows, verified duplicates, acknowledgements, gap/conflict failures, retryable failures, actual subsequent retry attempts, and acknowledgement failures. They reset on process restart; durable projection counters do not. Watch reports are limited to about once per second while draining. A zero lag observed before acknowledgement is not proof that the acknowledgement succeeded; inspect the acknowledgement counters and source position.

## Privacy boundary

`vm_projection.events` contains **private account/order IDs and private event details**. Its JSON must not be forwarded to public API clients. The tables and view receive no `PUBLIC` privileges.

`vm_projection.public_market_events` explicitly emits only `marketSeq`, `type`, `side`, `priceTicks`, and `quantityLots`. It excludes deposits, account IDs, order IDs, maker/taker IDs, private details, and private event sequence numbers. A future public API role should receive only schema usage and view SELECT, for example:

```sql
GRANT USAGE ON SCHEMA vm_projection TO market_reader;
GRANT SELECT ON vm_projection.public_market_events TO market_reader;
```

Use a dedicated non-owner database role for readers; owners retain access to their own private tables. The view is an explicit privacy projection, not an authorization system or a complete client recovery feed.

## Real PostgreSQL verification

```sh
export VM_TEST_PG_URL='jdbc:postgresql://127.0.0.1:55432/postgres?user=vectormatch'
# Optional VM_TEST_PG_USER and VM_TEST_PG_PASSWORD override JDBC defaults.
gradle :projector:test --rerun-tasks
```

Without `VM_TEST_PG_URL`, JDBC tests are explicitly **skipped**, never reported as having exercised a fake database. Tests use real PostgreSQL transactions with a failure-injected event source: commit-before-ack visibility on a second connection, lost-ack recovery, duplicate identity conflicts, gap rollback, cursor locking across concurrent workers, source lineage rollback, and public-view privacy. Cluster consensus/failover is verified by the cluster module's separate smoke test.
