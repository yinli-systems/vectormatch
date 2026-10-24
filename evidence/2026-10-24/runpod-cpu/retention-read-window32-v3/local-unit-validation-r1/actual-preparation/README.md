# Local read-window32 candidate preparation

Candidate branch `codex/read-window32-v3`, commit `605eb43fcafd8fa0a6287304387c93c4d1bbddf6`, based on `d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8`. The full nine-file diff is `candidate.diff`; actual final source inputs, compiled classes, XML, logs and installed JAR bodies are retained in validation/scoped-r5, with a separate installed-JAR metadata invocation in metadata-r1.

Final result: 58 distinct JUnit test identities in 10 XML suites, zero failures/errors/skips; eight forced Gradle tasks including installDist. Local macOS only: no Linux, SSH, native UDP/cluster pilot, cloud benchmark or new resource. No feature push has occurred. The metadata helper derives Plans using temporary in-memory reference engines; these are not native application sessions or performance observations.

All attempts remain:

- scoped-r1: source ZIP capture helper variable shadowing TypeError, before any Gradle process; original helper, registered arguments, partial ZIP and failure diagnostics retained.
- scoped-r2: actual 58 tests/10 XML, one new-test assumption failure (expected all32 in exception when15 completed/consumed originals already lived in logical tapes). Full source/class/JAR/XML/stdout/stderr retained. This attempt used normal JUnit temporary cleanup, so those unit raw temporary bodies are not retained.
- scoped-r3: actual58 tests/10 XML PASS after correcting the test; installDist and all subsequent unit temporary raw files retained.
- scoped-r4: actual58 tests/10 XML, one test boundary failure (post-abort failed timing rows were incorrectly counted as pre-failure success rows). All source/class/XML/logs and unit raw files retained.
- scoped-r5: actual58 tests/10 XML PASS with exact pre-injection snapshots of last-successful-flush bytes across all three streams. It verifies full32 flushed requests before any offer; completed prefix reply/timing bytes before consumption; all outstanding immutable original identities/bytes; and no ACK/new identity after failure. Production source never changed between r2 and r5.

The final passing tests run both page16/page32 with8/32 windows through real engine/service/codec/file-writer logic and controlled reversed/duplicate transport delivery. Tests are correctness evidence, not a performance benchmark.

Additional Gradle module build files were captured after execution and verified byte equal to the base commit; they were not individually pre-registered before the builds. JDK java/javac/release are hash pinned; a full JDK runtime is not archived. All17 actual test-classpath file bodies are retained in each completed attempt's external-test-classpath.zip.

`LOCAL_ARTIFACT_CLOSURE.json` binds registered sources, every captured artifact, all app JAR class entries, actual loaded JAR origins and four final distribution JAR bodies. Root's independent review is still required before feature push or cloud preparation. `INVENTORY.json` and `CLOSED.json` close this whole local scope, including failures and empty directories.
