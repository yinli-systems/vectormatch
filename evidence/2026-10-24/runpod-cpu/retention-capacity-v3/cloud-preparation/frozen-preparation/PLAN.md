# Existing CPU functional capacity-source pilot: local preparation only

This directory is a draft lifecycle wrapper, not a frozen executable benchmark release. No SSH, cloud API, JVM, Postgres, resource creation or real process signal was used by its author. `release.template.json` intentionally has `releaseReady:false` and missing actual artifact inputs. The wrapper refuses it. It also requires an explicit independently recorded `--release-sha256`, so a mutable manifest cannot silently select its own inputs.

After the source agent froze commit `4102446b333573efde2b33a0eb53a8177575bad5` and the independent collector closed R3, `candidate-release` was prepared locally with four exact distribution JAR copies, the current 57-file/9-directory protected original-state manifest and `release.candidate.json`. It deliberately still has `releaseReady:false`. Python independently reproduced the complete-JAR code fingerprint `e6243f4639af1cd35c3bbcb0b7ff0d10938320be8e2f1e0cb236ac9ef667dbb3`. Its candidate plans come from the byte-verified actual same-source native pilot maps, with provenance retained; root must review their binding to the distribution and Linux before enabling execution. No claim of a completed cloud release or new cloud measurement is made.

## One finite attempt

The only host is `ed6c0673f5cb`, the existing CPU Pod. All new state is below `/opt/vectormatch-cpu/preparation/capacity-cloud-pilot-r1/attempt-r1`. The Java pair root is the new `pilot-pair` child. The attempt directory is created atomically and never reused; failure is retained, not retried in the same directory. No original restoration directory is passed to any launched Java process.

One fixed `RetentionCapacityAeronPilotV3` main runs 6,400 scheduled arrivals at 500/s for cap 1, then cap 4, each using three fresh JVMs and a distinct lineage. Both arms must retain the same actual JARs, profile, appointed leader 0, sync level 2, W128/Q64, prepared archive cache, MTU 1248 and the same base ports. Only the batch cap changes. This is a functional cloud pilot, not a capacity promotion, sustained rate claim or cumulative endurance claim. Raw overload, invalid scheduler timing and undefined all-arrival p99 stay visible.

The execution allowance is 240 seconds; the remaining 120 seconds reserve independent clean process closure within a 360-second overall process-observation deadline. Each stop allows at most 30 seconds and never extends the remaining global allowance. Bounded file reads, fsync, hashing, compression and kernel scheduling do not have a hard real-time deadline guarantee. A missed stop deadline creates `BENCHMARK_BLOCKED.json`; no forced kill, next benchmark, active-native hash or active-native archive follows.

Initial admission requires at least 3 GiB free and 8 GiB system/cgroup memory headroom. If the sum of both actual derived allocation bounds, 16 MiB wrapper budget, 256 MiB possible compressed archive and 1 GiB reserve exceeds 3 GiB, that larger initial free-space bound applies. Runtime uses the explicit finite plan's 1 GiB free-space floor and the sum of both independently frozen per-arm allocation bounds plus the wrapper budget. This is a sampled stop threshold, not an atomic quota or proof arbitrary packet loss can finish the workload. Logs are capped at 4 MiB per file, the owned tree at 8,192 paths/12 GiB logical bytes, each file at 512 MiB and stopped compressed archive at 256 MiB. The archive additionally requires its full 256 MiB reserve above the 1 GiB floor after closure, then checks the floor again after writing. Allocated scans include directory as well as file blocks.

## Ownership and shutdown

`owned_linux_base_8eeb.py` is an exact copy of the reviewed original lifecycle controller, SHA `8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87`. It is imported only after its byte hash passes; its CLI is not invoked. This reuses Python 3.8-compatible Linux x86_64 pidfd syscalls 434/424 and strict PID/startTicks/raw NUL-terminated argv SHA ownership checks. The second identity check happens after the stable pidfd opens and before SIGTERM. There is no numeric-PID signal fallback and no node SIGKILL.

The direct parent Popen handle is retained immediately, before fallible post-launch receipt writes. Its actual `/proc` identity is saved independently. Each arm's `node-M-identity.json` must contain the root-added `linuxStartTicks` and `linuxCommandSha256`; its existing `command` plus `arguments` form the complete argv. Python re-reads actual `/proc` identity and records it before later validation. A mismatching observation is preserved as untrusted evidence and is never admitted to the signal registry.

Independent `/proc` discovery also recognizes a node started before its identity JSON was written, but only if its entire argv matches the frozen exact node template, registered fresh arm root, member, ports, profile, lineage and code fingerprint. Other Java VMs or any Postgres process block the run and are never signalled.

On error, Python first clean-stops and reaps the exact parent so it cannot spawn more children, discovers nodes again, then independently clean-stops every registered node. It does not assume Java finally blocks run on SIGTERM. Unknown/mismatching identities or unconfirmed stops block archival. Successful proof requires exactly one parent plus six distinct node identities, both Java clean-stop receipts and Python's independent closure.

Java's existing `ports()` attempts fresh binds of all 15 loopback UDP candidates before registering the first arm, then releases them. Python verifies the configured base ports, all exact argv templates and the same ports across arms. It records all 15 expected loopback ports, without rebinding sockets after node launch. The metadata explicitly does not claim a separate Python pre-launch availability proof or an atomic port reservation.

## Bottleneck telemetry

`owned-cpu-rss-io-1hz.jsonl` contains at most 512 samples and 8 MiB. Each record includes UTC, monotonic nanoseconds, elapsed time, phase, role, registered arms, active arms observed through successful metric reads and lineage mapping. Every owned process is checked by exact kernel identity both before and after reading counters.

Only aggregate `/proc/stat` CPU ticks and context/process count counters are read globally. Per owned PID, the observer records stat user/system ticks and RSS pages, selected status RSS/anonymous/file/swap bytes and threads, and kernel IO `read_bytes`, `write_bytes`, `syscr`, `syscw`. Clock tick rate and page size are explicit. No environment, peer list or packet data is read. Missing permissions, process exits, incomplete fields and identity changes produce explicit unavailable or partial samples, never fabricated zeroes. Signal interruptions are propagated to clean closure.

Rows flush during execution, without an observer fsync during the load. The telemetry file is fsynced once only after confirmed process closure; an unconfirmed stop skips that force and says so. This instrumentation adds observation overhead and shares the same host/filesystem. CPU or IO deltas do not isolate pure fsync time or establish independent physical-storage saturation. Java monotonic timestamps and Python monotonic timestamps need a validated common host-clock origin before fine-grained alignment; UTC and arm/lineage remain available regardless.

## Inputs root must still freeze

1. Commit the exact candidate source and preserve its build/functional validation, including failed attempts and scheduler-invalid arms.
2. Freeze the actual distribution JARs to `PREP/release/lib`. Parent `classPath` and actual CodeSource-derived `nodeClassPath` are separate. `DirectBuffer` may load from `aeron-all`, so four parent JARs must not imply four node JARs. Retain every loaded file's bytes and SHA.
3. Evaluate actual `codeFingerprint()` and profile fingerprint from those JARs. A local class-directory fingerprint or older maintenance JAR fingerprint is not a substitute. The fingerprint includes complete JAR containers.
4. Obtain both actual admitted `Plan.observation()` maps for 6,400 arrivals with the pilot's exact global extra/negative-offer budgets. Copy the complete observations into `derivedPlans`. The stopped pilot's `load/admission-plan.json` must match exactly.
5. Freeze actual canonical JDK executable and release-file SHA.
6. Build a current stopped original-state manifest from the R3 current-checkpoint closure, not the earlier initial-clone/R1 inventory. It must have scope `CURRENT_STOPPED_ORIGINAL_RESTORATION`, exactly the three native roots and complete file SHA/bytes/mode/uid/gid plus directory mode/uid/gid. Its `postgres` object contains `pgData`, `pgBaseline`, `pgBaselineSha256` for the unchanged stopped post-r2 PG baseline. The frozen manifest itself is read-only input.
7. Set `releaseReady:true` only after independently reviewing all actual inputs. Save it at `PREP/release/release.json`, record its exact SHA independently, and run the local pure guards plus the same guards on Linux before preflight. No Java process should run during the guards.

The future root-controlled command shape is:

```text
python3 capacity_cloud_pilot.py --release-sha256 <independently-frozen-sha>
python3 capacity_cloud_pilot.py --release-sha256 <same-sha> --start-new
```

The first invocation only reads preflight and never creates an attempt. The second is the explicit one-attempt mutation. This author has executed neither command against the CPU host.

## Stage and collect

Root should upload only these controller sources, the final guarded test source, exact release manifest, current original-state manifest and exact candidate runtime JARs into the fixed preparation directory. Verify every staged byte SHA before running Linux guards and read-only preflight. Keep credentials and SSH private keys out of the stage and evidence.

After all owned processes are confirmed absent, the wrapper hashes the entire fresh pilot tree and makes a full logical-byte archive, including sparse native files, raw request/reply tapes, per-arrival CSV, maintenance files, node logs, identities and receipts. It retains the original tree. A separate collector must download and SHA-check the compressed archive, then stream every member to verify file SHA, bytes, mode and exact files/directories/empty-directory closure against `after-clean-stop.json`. It must not extract multi-GiB sparse archives just to verify them. Keep full original and partial failed attempts. Same-host archive/readback is not independent storage durability.

Both actual `artifact-inventory.json` files must match the frozen loaded JAR closure and fingerprint. Actual arm registrations, plans, initial/final owner transport observations and every new-leader callback must retain leader 0. The wrapper validates full identity-bearing startup log lines and prepared cache mode. Follower role changes after the load during clean shutdown are outside the load-window leader gate. Existing raw source/reference and checkpoint proofs remain necessary; this lifecycle wrapper does not replace independent correctness verification.

## Local guard evidence

The first guard attempt failed before execution on a fixture-only Python SyntaxError. Its exact three source inputs and a failure receipt are retained under `guard-attempt-r1`. The corrected final suite contains 42 tests, with meaningful subcases for configuration and identity changes. It uses fixtures/mocks only: no real child process, JVM, SQL, SSH or signal. Final guard output and exact preparation file hashes are stored alongside this plan. This validates the lifecycle contracts locally; it does not prove Linux runtime, network, capacity, independent durability or any 100M target.
