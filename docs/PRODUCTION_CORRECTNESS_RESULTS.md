# Independent Linux correctness results

The latest [forced complete run40213694660](https://github.com/yinli-systems/vectormatch/actions/runs/40213694660) passes on process-sampler revision `4198aaddf02588429de207eef4d7b4a46e9f3282`. It uses a fresh filtered source checkout and a new Gradle user home on the existing prepaid CPU, with `--no-build-cache --rerun-tasks`. The actual core, cluster, server, projector and bench test tasks all execute; no test result is restored from cache. The immutable-handoff application source remains unchanged from `23f9c070`,qualified by CI6;timing source `aed9430d` remains qualified separately by CI5. Benchmark artifacts retain their original build/source identities.

| Check | Result |
| --- | --- |
| Java/JUnit |394 tests,0 failures,0 errors,0 skips|
| Real PostgreSQL integration |11 of those tests; dedicated temporary PostgreSQL18.6,fsync and synchronous commit enabled;0 skips|
| Linux Python regression |189 tests,0 skips;includes18 process-identity tests|
| Three-JVM failover/snapshot/restart |Passed,sync2,fresh lineage:57 commands/59 events/6 market events|
| Web |`npm ci`,TypeScript/Vite production build and Prettier checks passed|
| Frontend dependency audit |Separate current-lockfile `npm audit`:0 known vulnerabilities;not a security certification|

The fresh failover smoke observes old leader1 -> new leader0 and11,465.454ms from leader kill to the next confirmed command. That duration includes client failure handling and reconnection; it is not isolated election latency. This is three local JVMs on one CPU host, not independent physical machines or a recovery-time SLA. Its final state hash `b064fc0f0e58768bcb2d0fd4ad34a4b0965d89ca29ecd4b5689e69f437e1fb5e` also matches the preceding successful smokes. Healthy trading latency and fault-affected requests require their own workload measurements.

## Latest forced execution

[CI8](https://github.com/yinli-systems/vectormatch/actions/runs/40216970368) on source`bd936811` passes394 Java tests,including11 real PostgreSQL integration tests,and197 Linux Python tests,all with0 skips. All five Java test tasks execute with a fresh Gradle user home and no restored test results. Failover/snapshot/restart and web build/format gates pass. The revised identity sampler has26 focused tests,including six512MiB natural exits;all26 also pass on the actual controller Python3.8 runtime. All227 actual CI8 application classes equal qualified CI6 classes;performance JAR identities remain unchanged.

The fresh one-host three-JVM failure smoke observes leader2→0 and11,231.716ms from kill to the next confirmed command,including client failure handling/reconnection. Its final state hash matches earlier smokes. This is neither a millisecond failure-recovery SLA nor physical-host fault isolation. GitHub-hosted runner billing remains blocked;CI8 is an actual one-job non-root self-hosted job on the existing prepaid CPU.

## Previous forced execution

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
|[7](https://github.com/yinli-systems/vectormatch/actions/runs/40213694660)|`4198aadd`|Process identity observer:394 Java results,11 real PostgreSQL tests,189 Python tests,all0 skips;all five test modules actually execute,with failover and web gates passing. Includes actual Linux proc observations and30 naturally exiting owned children.|

The adapter fix preserves default page16 and the explicit supported maximum32. It verifies a complete32-event response,canonical encoding/decoding,read-only counters and rejection of33. No runtime limit is enlarged to make the test pass. The JDK request now matches the vendor's `21.0.13+9.0.LTS` identifier;Git is built from pinned upstream2.56.0 source in the CI tool directory using its supported C implementation. No system package is replaced.

The GitHub-hosted runner still cannot start because of the account's payment/spending-limit condition. These are actual self-hosted GitHub Actions jobs,with one-job non-root runners that deregister after completion. No hosted billing limit or paid cloud resource was added. Source checkout excludes bulk evidence;see [review and reproduction](REVIEW_AND_REPRODUCE.md).

The evidence collection retains every materialized tracked source file,compiled class/resource/JAR,JUnit result body and CI result log,plus whitelisted public runner metadata. Failed attempts are retained alongside success. Registration tokens,job credentials,SSH keys,Git authentication state and worker diagnostic logs are excluded. These checks establish software correctness evidence for this revision;they do not certify production readiness,physical-host fault tolerance,millisecond latency or funded trading.

## 2026-10-26: bounded coalescing source, CI22

[Actual CPU CI22](https://github.com/yinli-systems/vectormatch/actions/runs/40252989718), source `b6c850c69b03258eb1f5a1c625269bfbee5efa07`:453 Java tests and202 Python tests,zero failures/errors/skips,including11 real PostgreSQL integration tests. All five Java test tasks executed in a fresh Gradle home with result/build caches disabled. Web build/format passed. The actual three-process failover/snapshot/restart passed with leader1→0 and kill-to-next-confirmed-command11,368.923ms,including client behavior;this is not isolated election latency. Final state hash remains `b064fc0f0e58768bcb2d0fd4ad34a4b0965d89ca29ecd4b5689e69f437e1fb5e`.

All269 core/cluster JAR classes equal the actual CI22 compiled class bodies;core classes are unchanged from CI21. All454 actual CI/runtime JDK image bodies match. All22 loaded Linux origins bind to the four staged JARs;actual artifact `fb1068ddddcfce49d093f9004c8c85a89b52ef0ccc89faa452e07d238c6ef403`. The native500/s candidate qualification accepted10000 unique trades,verified both actual owner snapshots and all six node process lifetimes,and passed all three snapshots and cold restores. Subsequent four finite4000/s comparison arms passed financial/replay/cold-recovery checks but failed the registered paired optimization criterion. Default coalescing remains50us.

[Complete CI22/source/artifact qualification and frozen native inputs](../evidence/2026-10-26/runpod-cpu/v4-batch-coalescing-r1/linux-admission-r1/README.md) contains references to private asset676620021,17,429,074bytes,SHA-256 `42e50aaf0b8ba073c9dd7936ecb3c0b53e49a2fe6364dd8ea00540ed41a05bff`. All885 original CI bodies and every admission scope were verified after a full authenticated download. The first collector refused attempt22 before mutation because its allowlist ended at21;both that refusal and the corrected successful collection remain archived. A later transient GitHub connection refusal during report metadata recheck was resolved by a read-only retry;no native workload was repeated.

This is a successful manually dispatched job on the existing CPU. The separate hosted-runner account/billing block remains unresolved. These correctness and finite capacity observations do not certify production readiness,hard realtime,independent-host durability or continuous100M.

## 2026-10-26: explicit owned JFR, CI23

[Actual CPU CI23](https://github.com/yinli-systems/vectormatch/actions/runs/40255455589),source `35dd60457b17e55f420bb1b97b4deeb0c1f2726f`:461 Java and202 Python tests,zero failure/error/skip,including11 real PostgreSQL integration tests. All five Java test tasks executed in a fresh Gradle home without result/build cache. Web build/format passed. Actual three-JVM failover/snapshot/restart passed,leader0→2,kill-to-next-confirmed-command11,285.902ms including client behavior;not isolated election latency. Final57commands/59events/6market events match state hash `b064fc0f0e58768bcb2d0fd4ad34a4b0965d89ca29ecd4b5689e69f437e1fb5e`.

All271 core/cluster class bodies match actual CI23 outputs;core and hot matching/service bodies are unchanged. All454 CI/runtime JDK image bodies and24 actual Linux loaded origins match. Qualified artifact `c38e86a6a74b0fe1eed8fae540c2c8e7b171fd74e4ebc9f4b0c9051358c3cd27`. [Complete qualification](../evidence/2026-10-26/runpod-cpu/v4-jfr-diagnostic-r1/linux-admission-r1/README.md) retains893 original CI files and private asset676693155,17,548,271bytes,SHA-256 `f4612378e0c714e81a3df440d97e99705221166b28e8f645ef4284f1eea441e9`. Full authenticated download and every original scope member were verified. Prelaunch helper branch substitution was corrected before staging/native execution;both original and corrected bodies remain archived.

Both500/s and4000/s native JFR points passed full raw/replay/financial/snapshot/cold-recovery audits,all seven owned profile identities/settings,and zero observed JFR DataLoss. The [diagnostic report](V4_OWNED_JFR_RESULTS.md) keeps profiling overhead and finite observation limits explicit. The hosted-runner billing block remains unresolved. No hard realtime,independent-host durability,continuous100M or funded-trading certification follows.
