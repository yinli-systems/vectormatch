# Preserved local idle startup failure

The first direct-JAR native attempt at source `93ca0f11b64647c2ef1da1aa1e67c7fa1e86fa1a` **failed during startup**. Its strategy factory incorrectly allowed only one creation per logical role. Aeron 1.53.3 requests another Archive idle strategy, triggering the guard. Source inspection also found two factory consumptions for consensus and service on the selected path.

The 1ms control parent exited 1; all three owned nodes stopped, without forced kill or broad process signals. The 100us treatment was not launched. No latency or throughput result is claimed. This experimental source was pushed on its feature branch and was not merged into main.

The [complete original archive](closed-failure-originals/failed-native-originals.tar.gz) retains the failed native files, exact changed sources, distribution inputs, process records and stop evidence. [The manifest](closed-failure-originals/manifest.json) binds all 58 entries. [Independent archive review](ARCHIVE_REVIEW.json) checks every byte, permission, owner and empty directory, plus the listed strong private-key markers in the payload and all 2,062 JAR entries. Original files remain intact.

The correction must return fresh, distinct strategies for each bounded constructor consumption, distinguish source-inferred internal waiting from actual runner assignment, and retain the per-role spin/yield/minimum-park values. A new source/JAR build and fresh functional/control/treatment attempt are required. The existing read-window CPU ABAB results use a different, unchanged artifact.
