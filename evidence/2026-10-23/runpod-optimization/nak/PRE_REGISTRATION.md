# NAK delay control — preparation only

This document is a design, not a registered experiment or evidence of a performance result. No build, deployment, registration, SSH request or load was submitted by the preparing agent.

The existing 350k concurrency matrix stopped after W128-r1 and failed W256-r1. The W256 run retained unresolved identities and did not pass canonical/per-reply validation. Its reported confirmations are not correctness-validated throughput. No four-point concurrency or capacity conclusion follows.

The proposed factor is explicit Aeron unicast NAK delay **1,000 ns versus 100,000 ns**, applied to both node drivers and the shared load driver. Retry-delay ratio remains 100. The proposed order is A/B/A/B, with a fresh unique state and command namespace per attempt; failed attempts are retained and never silently retried. This tests a recovery-feedback hypothesis, not a proven unique cause of the earlier collapse.

All other formal inputs remain fixed: same new committed node/load artifact, `extended-350k-256` / `capacity-350k-v1`, leader 0 and unchanged term checks, 350,000 arrivals at 26,000/s (13.461538461 s), 256 synchronous workers, queue 64 per worker, one shared client driver with independent Aeron clients, max cluster sessions 256, 2 GiB node/load heap, SHARED node/archive threading, sync 2, MTU 1248, requested receive buffer 131072 bytes, retained orders 360000, global result cache 100000 and per-producer result cache 1024. Total client FIFO remains 16384. Fixture and prepared snapshot SHA must match the prior successful full-350k canonical pilot. That pilot did not prove a replicated Aeron full checkpoint/restart.

Root must choose whether to require an additional B-only W256, 10k/s × 35-second, full-350k canonical pilot. The controller supports it under `--kind pilot`; no pilot is assumed or invented. Formal registration requires an explicit `--pilot-policy require-b350k` or `skip-reviewed`.

## Preparation and execution separation

Controller sources are under `runtime/cloud/optimization-20261024/nak/`; their exact contents and SHA256 are retained in `tool-validation/controller-sources.json`.

1. Root commits the new source. `build.py --revision FULL_COMMIT_SHA` requires that exact current HEAD, exports committed source into a fresh directory, runs all Java tests and installDist, and records the archive SHA. It does not reuse an old build identity.
2. `bundle-node.py` compares JAR entry hashes against 52fbf7f. Only ClusterNodeMain and RemoteCapacityExperiment class entries may differ. Core, ClusterClient, ClusterCapacity and dependencies must remain byte-identical. Launcher changes are explicitly shipped and tested.
3. `deploy-node.py --execute` uploads only the new commit-named immutable release, verifies bundle/file hashes and launcher tests, and starts no nodes/load.
4. `register.py` defaults to a stdout-only draft. `--write` additionally requires immutable uploaded artifacts, explicit pilot policy, unchanged prerequisite hashes, new IDs and budget including a USD 2 recovery reserve.
5. `matrix.py --execute` runs only the exact registered order. Before the first fresh attempt it reads explicit prior owned PID records and requires them stopped. After each attempt it checks/stops explicitly recorded load, controller, observers and nodes by PID/startTicks/cmdSHA, and requires a new live check before the next attempt. PID reuse fails closed. It never scans or signals unrelated processes.

## Failure and evidence gates

Every available arrival CSV is archived to gzip with raw/analyzer SHA and retained locally before postprocessing gates. No failed or invalid attempt is deleted. Cleanup/export/postprocess failure, missing configuration or leader evidence, unexpected business mismatch, or any other unrecognized failure halts the matrix. The only nonzero-process failure allowed to continue is the exact canonical-incomplete guard:

`Confirmed-only replay skipped: N UNKNOWN_UNRESOLVED identities may already have executed; canonical validation is incomplete. Preserve the original identities for same-key recovery; no core business mismatch is established.`

The exception must be `java.lang.IllegalStateException`, N must be positive and match both failure.loadSummary and load-result unresolvedFinal. Such a run remains a failure with reported client counts only. Canonical-pass but scheduler-invalid runs remain invalid. Neither class is a valid capacity observation. Correctness, arrival-window goodput, conditional p99, all-offered finite latency eligibility, client not-sent, server rejection, initial unknown/final unresolved, backlog and drain are reported separately.

The same 1 Hz process/thread/socket/cgroup/CnC observers run on every treatment. Strict arrival-window attribution uses whole collection intervals and monotonic adjacent deltas. Socket lifecycle gaps, races and truncation are explicit; missing metrics are not zero. Observe ingress and control socket drops, driver CPU, NAK/retransmit counts, append/record/sender/commit/service positions, resource quota and observer cost. These establish associations and treatment responses, not unique causality or a universal engine ceiling.
