# Same-key recovery after the failed W256 trial

The user explicitly authorized recovery of these 256 synthetic unknown identities. The fixed job `u-recover-w256-r1-v1` completed outside the original measurement window on the preserved failed-trial state, using unchanged `52fbf7f` node binaries and a separately compiled, SHA-pinned helper.

[Verification](runs/u-recover-w256-r1-v1/verification.json) confirms all 256 identities: 252 returned cached accepted results; four identities absent from the frozen snapshot were resolved by retrying their original keys. The live pre-core had to match the frozen core byte-for-byte before any recovery command. The four resulting new executions produced exactly eight new events; command/event/market sequences ended at 3730/7393/7327. Canonical post-core, per-command results, asset deltas, invariants and all eight new event payloads passed. The helper took 9.507 seconds, excluding orchestration; this is not a failover or capacity latency measure.

Outbox exported cursor remained zero and pending grew from 7385 to 7393. No ACK was sent. The old outbox payloads were not independently enumerated. All three owned test member processes were confirmed stopped at completion; Pods were retained.

The original capacity CSV, 563 initial unknowns, 256 unresolved outcomes, latency samples and INVALID classification remain unchanged. Later same-key recovery does not turn that overloaded round into a valid capacity point. Snapshot absence alone was not treated as proof of historical nonexecution. Reference validation uses the same MatchingEngine implementation.

The [plan](plan.json), [exact controllers](tool-validation/controller-sources.json), [helper source](tool-validation/source/UnknownRecoveryProbe.java), local real-fixture validation and per-identity recovery receipts retain artifact/input/source hashes. Exclusive local/remote start markers forbid automatically replaying an interrupted recovery job. No original application state or native PostgreSQL backup was exported.
