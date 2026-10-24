# Local SSD qualification and end-to-end test isolation

This document prevents three different claims from being conflated:

1. **Functional regression:** core and cluster behavior under a given filesystem.
2. **Disk-backed experiment:** bytes written to an eligible local NVMe device with ext4/XFS and the unchanged allocated-growth guard.
3. **Physical durability:** independently witnessed local-device topology plus controlled crash/power-loss testing of the persistence chain.

Passing (1) does not imply (2), and passing the preflight for (2) **never** implies (3).

## The 2026-10-24 result and its limits

On the RunPod CPU host, the same `codex/retention-read-window32` source snapshot (`8f65c256d0e28e2d08d22720a511fd48a62f07b0`) was copied from the network-mounted checkout into the container's local overlay filesystem. Temurin OpenJDK **21.0.13+9** was installed from an upstream artifact with verified SHA-256 `d7f5d5cf865a2902b70ff549b97586a7d3f234e016f041ab447ea740c7d66d1c`.

The test command was:

```bash
./gradlew :core:test :cluster:test --no-daemon --console=plain --max-workers=4
```

The local-overlay run finished `BUILD SUCCESSFUL in 3m 29s`: **56 JUnit XML suites, 315 tests, 0 failures, 0 errors, 0 skipped**. The preceding run under the MFS/FUSE-mounted source checkout finished **306 passed, 9 failed** (seven three-JVM readiness timeouts and two strict setup-vs-reference mismatches). This is strong evidence that filesystem placement/test environmental effects explain the discrepancy, **not proof of a specific causal mechanism**. No assertions, guards, readiness deadlines, reference comparisons or production code were relaxed to obtain the green run.

The original XML and HTML reports from the green run were archived to `/workspace/vectormatch-read32-native-r1/overlay-full-test-315-pass-2026-10-24-r1.tar.zst` on the persistent RunPod mount. **SHA-256**: `6e6b0d630a8f8ec40988f099541b3f796ff463943b3dca44982b6ff5fd146f84`; `zstd -t` passed on that saved archive. These reports are not produced by the later SSD-preflight-only documentation commits.

The overlay is suitable for functional test isolation; it **does not** establish device-level SSD durability. The four earlier 8-credit/32-credit native ABAB arms used `/dev/shm` (tmpfs) and likewise provide **RAM-backed** latency evidence only.

### Additional validation on the same isolated source snapshot

- `./gradlew :cluster:failoverSmoke --no-daemon --console=plain --max-workers=4`: **PASS, 30 seconds**. Three local, sync-level-2 node processes; leader 2 was terminated and leader 1 took over; next confirmed command arrived **11,342.035 ms** after kill. Snapshot/cold-restart checks, outbox backpressure/recovery and chunked-core-snapshot verification were reported true. This is single-host process failover, **not** multi-machine partition/power-loss testing. Its complete run directory is preserved in `/workspace/vectormatch-read32-native-r1/overlay-failover-smoke-pass-2026-10-24-r1.tar.zst` (SHA-256 `856f6a6c277ac5b3f8c6cbe4b50639019297f1d70b644b735b750f9df35d125f`; `zstd -t` passed).
- Portable, SHA-256-verified toolchain bootstrap succeeded for Temurin 21.0.13+9, Node **24.22.1** and Gradle **8.14.3**. `npm --prefix web ci --no-audit --no-fund`, `npm --prefix web run build` (TypeScript + Vite) and `npm --prefix web run format:check` (Prettier) all succeeded.
- Python scope: the new SSD preflight has **11/11** unit tests passing; the existing independent preflight/launcher-lock tests have **8/8** passing; the UDP preflight tests have **6/6** passing. These are three separately executed suites, not a claim that the entire Python suite passed.
- Attempting the complete historical Python suite in this intentionally partial source copy ran **170 tests**, with **26 errors and one failure**. The copy had no `evidence/` directory; multiple errors were `FileNotFoundError` for required checked-in historical fixtures, and the single failure observed zero fixture-backed identities. Do **not** treat the full Python suite as green. Re-run it from a complete checkout with its tracked `evidence/` files; do not suppress, auto-skip or alter assertions to hide these failures.

## Fail-closed block-device candidate check

On a Linux host with an **existing empty test directory** on the proposed experiment mount, run:

```bash
python3 scripts/qualify-local-ssd.py \
  --path /mnt/local-nvme/vectormatch-run-01 \
  --required-growth-bytes 754102673 \
  --minimum-reserve-bytes 1073741824
```

The capacities must come from the **actual admitted experiment plan**, not from this example, if the workload changes. This command creates no files and emits one machine-readable JSON report to stdout. Exit code **0** means **candidate for a disk-backed experiment**, while exit code **2** means **rejected**. Save the full JSON, command, exit code, source commit and host/provider evidence before the native run.

The preflight checks:

- Exact `findmnt` target resolves to a read-write ext4 or XFS mount with a direct `/dev/...` block-device source. `fuse.*`, MFS, NFS, overlay, tmpfs, bind-source ambiguity and other filesystems fail.
- `lsblk` identifies a direct disk or partition rooted in a nonrotational **NVMe** disk with a known model; obvious network/virtual-block models such as **Amazon Elastic Block Store** fail even when named `/dev/nvme`.
- `findmnt` and `lsblk` **major:minor device IDs must agree** with each other and with `os.stat()` of the actual test directory; a plausible device name alone is never enough.
- Real free space is at least maximum allocated growth **plus** the runtime reserve. This is point-in-time eligibility, **not a quota**; the in-run allocated-byte guard still applies.
- Missing commands, non-JSON output, unmapped devices, ambiguous ancestry, absent fields, unknown models or read-only mounts fail closed.

The report deliberately always sets `strictPhysicalDurabilityProven: false`, even on a positive candidate. Models and block metadata may be virtualized or mislabeled. NVMe transport, nonrotational status and ext4/XFS do **not** themselves prove local physical placement.

## Additional acceptance gates for strong durability claims

1. Obtain **provider/operator attestation** that the exact device is local non-network SSD, including instance type, disk model/serial when safely exposed, topology and ephemerality. The preflight is a consistency check, not a replacement for this evidence.
2. Record `findmnt`, `lsblk`, device identity, mount options, free bytes, host/cgroup/CPU configuration, JDK, artifact hashes, exact client/server settings and full raw output. Keep the same hard budget and flush/fence settings between arms.
3. Execute **process crash and cold-restart** tests from durable checkpoints with complete recovery/reconciliation. `SIGKILL`, normal restart, `fsync()` or readback are **not** physical power-cut proofs.
4. To claim **power-loss durability**, perform a separately authorized, controlled device/host-power interruption with independent observation or suitable storage-fault tooling; verify committed-prefix recovery, unacknowledged messages, checksums, journal/snapshot invariants and readback. Never disrupt shared or production infrastructure.
5. For performance: predeclare randomized treatment order and multiple paired 8/32 runs, reproduce P50/P95/P99 and maintenance wall from original arrivals/cycle files, preserve failures and quantify uncertainty; disclose client+three-JVM co-location and drift. Do not upgrade two-pair tmpfs observations into disk-backed or statistically significant results.

## Preflight regression test

```bash
python3 -m unittest discover -s scripts/tests -p test_qualify_local_ssd.py -v
```

The tests cover a positive *candidate* and negative cases for FUSE/MFS, tmpfs, overlay, NFS, remote-looking NVMe, read-only mounts, mapped/bind sources, missing metadata, cycles, insufficient capacity and probe failure. No real SSD or power cut is required for these unit tests.
