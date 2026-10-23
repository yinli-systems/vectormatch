# Session and network ownership arrangement control — preparation only

This is a controller design, not a registration or measured result. Preparing these files does not build, deploy, register, SSH or submit load. All older NAK source, plans and evidence remain unchanged.

The proposed factor compares **direct: 128 physical cluster sessions** with **multiplexed: 1 physical cluster session**, both with 128 logical synchronous in-flight requests, 128 independent producer identities, queue 64 per worker and aggregate FIFO 8192. Each arm uses one shared MediaDriver. Multiplexed mode routes replies through one network owner; the complete session/ownership/dispatch arrangement changes, so this is not a pure in-flight-window or matching-engine comparison.

Both arms explicitly fix node and load unicast NAK delay to 1000 ns and retry ratio to 100. Other formal inputs remain identical: same new committed node/load artifact; `extended-350k-256` / `capacity-350k-v1`; 350000 arrivals at 26000/s; 2 GiB node/load heaps; max cluster sessions 256; appointed leader 0 with term checks; sync 2; SHARED node/archive drivers; MTU 1248; requested receive buffer 131072 bytes; retained orders 360000; outbox 800000; global cache 100000; per-producer cache 1024; unchanged fixture/prepared snapshot SHA.

The new explicit JVM property is `-Dvectormatch.capacity.client.transport=direct|multiplexed`, with `-Dvectormatch.capacity.client.driver=shared` and `-Daeron.nak.unicast.delay=1000` in both arms. Campaign fixed fields and actual configuration/load metadata must agree on `clientTransportMode` and `clientSessionCount` (128 direct, 1 multiplexed). `clientAeronMode` is `one-independent-Aeron-per-client` for direct and `one-session-one-network-owner` for multiplexed. Node and load runtime NAK values are independently verified.

## Mandatory pilot and formal order

Before formal registration, a separate multiplexed B pilot must accept the complete 350000 commands at 10000/s for a 35-second arrival window. Canonical snapshot validation and scheduler validity must pass; client not-sent, business rejection, server error and final unresolved counts must all be zero. This validates finite canonical core state, outbox/assets and the new client path; it does not prove a full replicated Aeron checkpoint/restart.

Formal order is direct / multiplexed / direct / multiplexed at 26000/s and W128, each 350000 arrivals with fresh unique state. Every registered attempt is retained individually. No previous failed NAK pilot is silently treated as valid, and no repeated capacity conclusion is claimed before actual repeated valid observations.

## Separate root execution steps

Controller source is under `runtime/cloud/optimization-20261024/pipeline/`; exact source and hashes are retained in `tool-validation/controller-sources.json`.

1. After the implementing agents finish and root commits, `build.py --revision FULL_COMMIT_SHA` exports exactly that current committed revision into a fresh isolated build and records its source-archive SHA. Java tests and installDist must pass with zero skip/failure.
2. `bundle-node.py` compares exact JAR filename sets and every non-directory ZIP entry against the ab6fc73731642d0d17a242a930a2cb60aba11e16 NAK artifact. Only ClusterClient, RemoteCapacityExperiment and new MultiplexedLoadTransports class families may differ. NodeMain, matching core, ClusterCapacity and dependencies must remain byte-identical. Existing release identities cannot be overwritten.
3. `deploy-node.py --execute` uploads and verifies only the new immutable commit-named release and launcher unit tests. It starts no nodes/load.
4. `register.py` defaults to a stdout-only draft. Root explicitly uses `--kind pilot --write`, then `matrix.py --kind pilot --execute`. Formal `register.py --kind matrix --write` requires the complete valid pilot; `matrix.py --kind matrix --execute` executes only the registered order and controller/artifact hashes.

Budget guards retain the USD20 limit and USD2 recovery reserve; no additional resources are provisioned. Before a fresh attempt, explicitly recorded prior owned PID/startTicks/cmdSHA identities must be stopped. Each attempt stops/checks its load, controller, observers and nodes, with a fresh live identity check before the next trial. PID reuse fails closed and no unrelated process is scanned/signaled.

## Failure and interpretation rules

All available arrival CSVs are archived with raw/analyzer SHA into gzip before validity gates; raw plaintext remains local. No failure or invalid round is erased or replayed under the same ID. Only the exact typed canonical-incomplete UNKNOWN guard, with positive unresolved count and identical full failure.loadSummary/load-result dictionaries, may continue after complete owned cleanup. Its opt-in configuration receipt uses `--include-failed-unknown`, remains configuration-only and never manufactures result.json or business success. Any unexpected business mismatch, fixed-leader/configuration/source discrepancy, cleanup/export failure or incomplete evidence halts the matrix.

Keep conditional p99, all-offered finite eligibility, arrival-window goodput, client not-sent, server rejection, initial unknown/final unresolved, backlog/drain, API occupancy and resource observations separate. Use the same observer on both arms, with whole-collection arrival-window selection and monotonic/process/TID/inode lifecycle checks. Gaps, missing metrics and scan truncation are explicit. A resource or throughput improvement in this finite client+cluster path does not establish a universal engine ceiling, a sustained capacity guarantee or unique causality.
