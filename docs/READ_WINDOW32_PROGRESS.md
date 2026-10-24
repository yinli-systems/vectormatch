# Read credits 8 vs 32: local candidate

Source `605eb43fcafd8fa0a6287304387c93c4d1bbddf6` is pushed on private branch `codex/read-window32-v3`. It is not merged into main or deployed. Its actual installed-JAR fingerprint is `d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea`.

The separate `read-window32-long-cuts` mode selects page 16 or 32 and read credits 8 or 32. A future comparison must keep one page fixed. Each arm remains 33,792 arrivals at 500/s over 67.584s, leader 0, sync 2, batch 4, chunk 6144, owner 1ms and driver 100us. Existing modes, default constructors and their eight-credit budgets remain unchanged.

Both selected windows share the same 32-credit staging and failure envelope: 1,984,256 staging bytes, 1,073,760 failure-reserve bytes and physical registry capacity 129. Four-offer limits, full request flush before arming, completed-but-unconsumed credit, business/control exclusion and force/readback before either destructive ACK remain enforced.

The final actual forced build passed 58 distinct tests in 10 XML reports, with no failures, errors or skips; installDist completed. Tests verify full 32-request flush before first offer, credit limits, out-of-order/duplicate/late replies, and exact original identities across first/middle/last evidence failures. Failure tests reconcile already flushed replies/timings with remaining immutable requests and prevent ACK after failure.

All five preparation/validation attempts are preserved with their available artifacts. The first capture helper failed before Gradle started. Actual r2 and r4 test failures exposed test assumptions; production bytes remained unchanged through the subsequent successful validations. The r2 JUnit temporary raw files were automatically cleaned and are unavailable; they are not represented as fully retained. r3/r4/r5 temporary files are retained, including the complete final r5 proof.

The independent review bound 119 registered inputs, 340 artifact files, 304 class artifacts, every application JAR class and all 17 classpath bodies. The complete available source/build/test/metadata evidence and limitations are in [local-unit-validation-r1](../evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/local-unit-validation-r1/README.md).

Only local installed-JAR metadata has executed. Linux metadata, native functional qualification and an 8/32/8/32 performance comparison remain pending. The previous artifact's event-page results do not qualify this new artifact. No speedup, higher stable throughput, 100M endurance or hard realtime result is claimed for this candidate.
