This protocol was prepared before registration. Root subsequently completed the separately registered18k capacity matrix and its cleanup, built and uploaded the committed node artifact, then registered and submitted the strict [pilot](pilot-plan.json). Its result is pending at this update; the formal matrix remains unregistered. The original pipeline and pipeline-capacity source/plans/evidence remain unchanged. [Local preparation tests and exact sources](tool-validation/controller-preparation-validation.json) are distinct from any cloud result.

The next factor is the common maximum park interval of designated **node data-path idle strategies**: A explicitly uses `1000000 ns`, B explicitly uses `100000 ns`. Both arms use the same new node artifact and fixed **e57 multiplexed load: one physical session, one shared client driver, logical W128, Q64 / total FIFO8192, NAK1000 ns / retry100**. The repeated prior multiplexed comparison reduced resource consumption without establishing stable throughput at26k; this motivates retaining multiplexed mode in both new arms. Any later before/after comparison spanning the session and node-idle changes must identify both factors rather than attribute their combined benefit to one change.

Node driver strategies retain spins/yields `10 / 5`; archive, consensus and service strategies retain `10 / 20`. Every strategy retains minimum park `1000 ns`; only the shared maximum changes. The node property is `-Dvectormatch.node.dataPathMaxParkNs=N`, supplied through node-only `VECTOR_DATA_PATH_MAX_PARK_NS`. The controller injects this environment value only into node supervisor calls, never into the load environment or load JVM. The load revision stays `e57e341909a49692b9ecbf9693803ed62a240b06`, bundle SHA `f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937`.

The two arms must use one identical new commit-named node artifact. Registration rechecks the archived bytes and independently compares every JAR entry with the e57 load artifact: only `ClusterNodeMain.class` and its nested class family may differ, including `DataPathIdlePolicy` and its configuration record. Core, client, all other cluster class/resource entries and dependency entries must match exactly. Outer ZIP packaging timestamps are excluded from this bytecode comparison. A claimed manifest diff alone is insufficient. New isolated Java tests must pass without skips, and immutable upload/hash/Linux launcher-test receipts must exist for all three nodes.

The new configuration verifier belongs to the actual new node build. The unchanged leader checker, legacy analyzer dependency and archive tool retain exact known bytes, with their real paths/source identity. Evidence analysis uses the separately committed streaming postprocessor revision `3fd86fe535fc0858e300e0337d4da154f622ae32`, analysis identity `31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f`; it is never mislabeled as an e57 build tool. Both new arms attest that same analysis identity and immutable per-trial output snapshots.

All other node/workload settings stay fixed: `capacity-350k-v1` / `extended-350k-256`, prepared-state SHA inherited unchanged from the completed capacity campaign, 350000 arrivals, 2 GiB node/load heaps, sync2, appointed leader0 with single-term evidence per measurement, SHARED node/archive, MTU1248, requested receive buffer131072 bytes, session limit256, retained orders360000, outbox800000, cache1024 per producer, same fixture/producer identities, observer and effective-buffer probe. No global sysctl, client idle, FIFO, scheduler, retry interval, NAK or matching algorithm changes are included.

The new fixed fields are `nodeDataPathMaxParkNs`, `nodeDataPathIdlePolicyVersion=1`, `nodeDataPathIdleAgentMaxYields=20`, `nodeDataPathIdleMinParkNs=1000`, and the corresponding `driverIdleMaxParkNs`. The descriptive `idleStrategy` string names both driver10/5 and agent10/20 policies. Actual startup evidence must include every configured role's strategy class, exact parameters and distinct per-JVM instance IDs. `runnerSelected` describes whether that idle instance is selected by a runner, not whether its underlying agent executes. In SHARED mode, the native-resource agent executes inside the shared composite; its separately configured native idle instance is unselected. The source/configuration verifier independently checks all eight role records without creating extra instances merely for logging.

Registration gates and order are fixed:

1. Every original18k capacity attempt must be terminal with raw/analyzer SHA agreement, lossless arrivals archive, configuration/leader checks, per-trial analysis identity/output proof, complete explicit owned-process cleanup and one four-attempt completion timeline. The previous original26k inputs remain pinned transitively. Invalid attempts remain invalid; they do not become a capacity success.
2. Run **one separate B pilot** `i-pilot-park100000-10000-w128`:350000 arrivals at10000/s, a35-second window, same fixed multiplexed load. It must accept all350000, pass canonical and measurement/timing validation, and have exactly zero not-sent, rejected, server-error, initial-unknown, final-unknown and above-limit scheduler-lateness counts. A resolved timeout still fails this strict pilot.
3. Only after its full raw/archive/config/leader/analysis/cleanup proof and completion timeline exist may root register the formal four attempts: `A1 / B1 / A2 / B2` at26000/s,350000 arrivals each,13.461538…seconds. IDs are `i-park1000000-26000-w128-r1`, `i-park100000-26000-w128-r1`, then their `r2` counterparts. Both explicit values use the same node artifact; there is no comparison between old unset and new explicit defaults.

Controller source is under `runtime/cloud/optimization-20261024/idle/`. Default commands print drafts or refuse execution; they neither inspect live nodes nor register jobs:

```sh
python3 -B runtime/cloud/optimization-20261024/idle/register.py --kind pilot
python3 -B -m unittest discover -s runtime/cloud/optimization-20261024/idle -p test_guards.py -v
```

Root separately builds/reviews the isolated node release and supplies its immutable artifact/upload receipts. Registration and trial execution additionally require all prior capacity gates. The future explicit trial steps are:

```sh
python3 -B runtime/cloud/optimization-20261024/idle/register.py --kind pilot --write
python3 -B runtime/cloud/optimization-20261024/idle/matrix.py --kind pilot --execute
# Only after the strict pilot has actually passed:
python3 -B runtime/cloud/optimization-20261024/idle/register.py --kind matrix --write
python3 -B runtime/cloud/optimization-20261024/idle/matrix.py --kind matrix --execute
```

The pilot registration and submission commands have now been performed once by root, after preparation and prerequisite completion; they must not be reissued. Pilot/formal plans, source hashes, artifact identities and unique states refuse overwrite or automatic replay. The wrappers reuse the already frozen trial/cleanup machinery in a separate process; no source edit is applied to the registered earlier campaigns. Fresh read-only checks of explicit recorded PID/startTicks/cmdSHA identities must pass before first/next trials. A future formal plan must pin the strict pilot's complete proof hashes.

The total project cap remains USD20 including a USD2 recovery reserve, with no new resources. The pilot reserves900seconds, formal matrix3000seconds, and each next attempt checks its conservative remaining-time reserve. Every trial requires at least1GiB local free space. Both load-process and full canonical-validation limits remain600seconds for both arms; an arm cannot receive an undisclosed timeout extension. Available raw CSVs, including every failed/invalid arrival, are losslessly archived before any next-attempt decision and plaintext stays local.

Any unexpected business mismatch, source/configuration/leader inconsistency, archive/export error or incomplete cleanup halts after evidence preservation. The frozen machinery's exact canonical-incomplete UNKNOWN guard may retain a formal failure and continue only after full archive/cleanup; that failure remains invalid, and the strict pilot always refuses it. No unknown business key is automatically recovered or reissued by this controller. Report every repetition's goodput, conditional versus all-offered p99, loss/rejection/error, initial/final unknown, backlog/drain, correctness/leader/configuration and resource scope separately. Finite shared-host windows do not establish a continuous production limit, a bare engine ceiling or unique causality beyond the registered factor.


Local artifact helpers are separate from registration and measurements. Each defaults to a stdout draft unless root explicitly selects `--execute`; none depends on18k trial completion merely to prepare bytes. Root has already run the full isolated source build of `87ad09c11807a78d4f8e3b2ad6088e6940e33261`: **132 Java tests, zero failures and skips**, plus installDist. The [actual build receipt](tool-validation/java-tests.json), [log](tool-validation/java-build.log) and module XML files preserve that result. `build.py` remained frozen at SHA-256 `099119ca1a6e9a9075d63c243e4a3601f36f4143d55899b6ea9336d4e317705b` throughout root execution.

```sh
# Already performed separately by root; refuse to overwrite this build:
# python3 -B runtime/cloud/optimization-20261024/idle/build.py --revision 87ad09c11807a78d4f8e3b2ad6088e6940e33261 --execute

# Separate root-reviewed immutable packaging and optional transfer:
python3 -B runtime/cloud/optimization-20261024/idle/bundle-node.py --execute
python3 -B runtime/cloud/optimization-20261024/idle/deploy-node.py --execute
```

The bundler checks the recorded source archive and complete green build, compares all JAR-entry bytes with e57, packages only the new node release and verifies the packaged diff again. It never rewrites the old load artifact. The deployment helper only uploads to the new commit-named directory, verifies every archived file, and runs Linux launcher unit tests. It starts no node/load/gateway/PG service and changes no kernel setting. Existing release/receipt paths refuse overwrite. These preparation tools do not imply that the strict pilot or formal comparison has run.

The [real namespace handshake receipt](tool-validation/namespace-import-validation.json) records a local call through `idle.common.capacity_module()` to the registered capacity plan's actual `validate_plan()` and artifact-only gate. `sys.modules['common']` remains the idle module, the capacity module has its own distinct namespace, and `postprocessor` resolves to the registered capacity helper. The earlier26k and analysis31e4 identity checks passed without requiring18k results, and all protected capacity source/plan SHA values stayed unchanged. The [final preparation receipt](tool-validation/controller-preparation-validation.json) records all seven frozen helper/controller sources and14 passing local guards. No synthetic guard test is treated as a cloud result.
