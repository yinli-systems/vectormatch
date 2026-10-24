# Experimental V3 source integration

This integration joins main `d007caa7c66759423287927f0ba27baff716919a` with the independently frozen chunk feature `e3c4885a8854c3edfbfdea4848633efc75951894`. It keeps the main passive gateway startup behavior and the explicit experimental V3 entry points. It does not switch the default V2 service to V3.

The merge was performed in a source-only sparse worktree, without checking out historical evidence. The initial automatic merge had no conflicts: all 74 feature paths matched e3 exactly, and all nine main server files matched d007 exactly.

## Integration defect and bounded fix

The first forced suite found two failures in the functional owner/maintenance smoke recorders. The owner now obtains a final actual transport observation; the older recorders attempted to create the same `*-actual-observation-open.json` a second time. Both failures and their original source, actual classes/JARs, XML, logs, complete native files and stop receipts were retained before editing.

Only those two functional recorders were adjusted. They obtain and return the fresh delegate observation on every call, keep the original open observation, and save later observations under numbered paths using `CREATE_NEW`. Each recorder permits at most 256 observations. Transport-close evidence remains separate. Three regression tests exercise both recorders: fresh values and preserved initial bytes, refusal to overwrite, and the hard bound without extra transport calls. Core matching, business batching, transport and maintenance behavior were not changed for this fix.

## Actual validation

The second full invocation used Java 21 and the repository's pinned Gradle, with:

```text
check :cluster:installDist --rerun-tasks --no-build-cache --no-parallel --max-workers=2 --no-daemon
```

A test-input capture init script recorded actual classpath bytes and JAR hashes before each test task. All **23 actionable tasks executed**. The result was **291 passed, zero failures/errors/skips**: core 42, cluster 211, server 17, projector 13, bench 8. JMH harness compilation was included; no JMH performance workload was run.

Coverage includes the V2 compatibility test over 92 golden prefix rows (one JUnit method, not 92 methods), all six V3 native test methods, the fresh W128 owner batch-1/batch-4 continuation, 10,000-command maintenance with a discarded ACK reply and cold continuation, both capacity functional arms, both chunk functional arms with actual egress evidence, and both passive gateway startup tests.

The PostgreSQL integration tests used one newly created, uniquely named local database. No existing database was dropped. Normal application PostgreSQL observer environment variables were cleared; the original shared application schema and remote PostgreSQL were not test targets.

The successful run lasted 317.107 seconds; the minimum observed local free space was 7,800,176,640 bytes, above the 1 GiB admission floor. No tested source changed during the run. Full readback verified all 776 files in 7 new native trees (15,155,383,160 logical bytes; 91,098,060 archive bytes), including empty directories and file modes. All nine native completion receipts report owned processes stopped. Original sparse native trees were retained without extraction or deletion.

The reproducible commands, source ZIPs, actual classpath inventories, XML, failed and successful archives, stop receipts and readback manifests are under `build/integration-validation/r1` and `build/integration-validation/r2` in the isolated integration worktree. This document was added after the successful source validation.

## Limits

These are local functional and integration proofs. They do not establish independent-host capacity, latency targets, external storage durability or any 100-million-operation target. This integration has a different source/artifact identity from e3; the frozen CPU chunk experiment remains its own cohort. This validation did not deploy or promote the integrated artifact.
