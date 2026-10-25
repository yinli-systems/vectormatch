# Independent Linux correctness results

The latest [forced complete run40210159252](https://github.com/yinli-systems/vectormatch/actions/runs/40210159252) passes on immutable-handoff candidate source `23f9c070e2cb394a13d1bc80d60a3b532e032204`. It uses a fresh filtered source checkout and a new Gradle user home on the existing prepaid CPU, with `--no-build-cache --rerun-tasks`. The actual core, cluster, server, projector and bench test tasks all execute; no test result is restored from cache. The preceding timing source `aed9430d` remains qualified separately by run5 below;the four timing benchmarks do not execute this candidate.

| Check | Result |
| --- | --- |
| Java/JUnit |394 tests,0 failures,0 errors,0 skips|
| Real PostgreSQL integration |11 of those tests; dedicated temporary PostgreSQL18.6,fsync and synchronous commit enabled;0 skips|
| Linux Python regression |171 tests,0 skips|
| Three-JVM failover/snapshot/restart |Passed,sync2,fresh lineage:57 commands/59 events/6 market events|
| Web |`npm ci`,TypeScript/Vite production build and Prettier checks passed|
| Frontend dependency audit |Separate current-lockfile `npm audit`:0 known vulnerabilities;not a security certification|

The fresh failover smoke observes old leader2 -> new leader1 and11,393.947ms from leader kill to the next confirmed command. That duration includes client failure handling and reconnection; it is not isolated election latency. This is three local JVMs on one CPU host, not independent physical machines or a recovery-time SLA. Its final state hash `b064fc0f0e58768bcb2d0fd4ad34a4b0965d89ca29ecd4b5689e69f437e1fb5e` also matches the preceding successful smokes. Healthy trading latency and fault-affected requests require their own workload measurements.

## Earlier results remain visible

| Attempt | Revision | Outcome |
| --- | --- | --- |
|[1](https://github.com/yinli-systems/vectormatch/actions/runs/40200139438)|`c765671f`|Git2.25 cannot perform the action's sparse checkout and falls back to a full archive download. A diagnostic inspector cleanup uses an unavailable `require` and ends the checkout process. No software test executes.|
|[2](https://github.com/yinli-systems/vectormatch/actions/runs/40201846818)|`0f7fa74a`|Git2.56 sparse checkout passes. The JDK vendor API rejects the shorter build identifier;no software test executes.|
|[3](https://github.com/yinli-systems/vectormatch/actions/runs/40202202158)|`f142508e`|389 Java tests,1 failure,0 skips:an old adapter test still rejects event page17 although the supported maximum is32.|
|[4](https://github.com/yinli-systems/vectormatch/actions/runs/40203098509)|`3ed6be30`|All checks pass with390 Java result records and0 skips. Some unchanged modules restore test results from the local Gradle cache;this is not the forced execution above.|
|[Workflow validation](https://github.com/yinli-systems/vectormatch/actions/runs/40203862181)|`f111f478`|A runner-only expression is placed in an unsupported job environment context. Rejected before any CPU job;fixed at step scope and validated with actionlint1.7.12.|
|[5](https://github.com/yinli-systems/vectormatch/actions/runs/40204254478)|`aed9430d`|Forced execution of all test modules and all remaining gates passes.|
|[6](https://github.com/yinli-systems/vectormatch/actions/runs/40210159252)|`23f9c070`|Immutable verified archive handoff candidate:394 Java results,11 real PostgreSQL tests,171 Python tests,all0 skips;all five test modules actually execute,with failover and web gates passing. Performance comparison remains separate.|

The adapter fix preserves default page16 and the explicit supported maximum32. It verifies a complete32-event response,canonical encoding/decoding,read-only counters and rejection of33. No runtime limit is enlarged to make the test pass. The JDK request now matches the vendor's `21.0.13+9.0.LTS` identifier;Git is built from pinned upstream2.56.0 source in the CI tool directory using its supported C implementation. No system package is replaced.

The GitHub-hosted runner still cannot start because of the account's payment/spending-limit condition. These are actual self-hosted GitHub Actions jobs,with one-job non-root runners that deregister after completion. No hosted billing limit or paid cloud resource was added. Source checkout excludes bulk evidence;see [review and reproduction](REVIEW_AND_REPRODUCE.md).

The evidence collection retains every materialized tracked source file,compiled class/resource/JAR,JUnit result body and CI result log,plus whitelisted public runner metadata. Failed attempts are retained alongside success. Registration tokens,job credentials,SSH keys,Git authentication state and worker diagnostic logs are excluded. These checks establish software correctness evidence for this revision;they do not certify production readiness,physical-host fault tolerance,millisecond latency or funded trading.
