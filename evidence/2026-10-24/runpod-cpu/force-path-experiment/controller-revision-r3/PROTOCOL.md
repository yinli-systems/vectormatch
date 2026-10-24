# Prospective synthetic write + force(true) diagnostic

This registration is independent of the trading capacity experiments. It uses the existing prepaid CPU host only. It creates no resources and no services, and never opens existing Aeron recordings, PGDATA or application state. No Linux measurement has been performed by preparation or the offline tests.

Eight sequential points, in this registered order:

| JVM writer threads | Block bytes | Preallocation blocks/writer | Warmup/writer | Measurement/writer |
|---:|---:|---:|---:|---:|
| 1 | 4096 | 16 | 10 | 200 |
| 1 | 16384 | 16 | 10 | 200 |
| 1 | 24576 | 16 | 10 | 200 |
| 1 | 49152 | 16 | 10 | 200 |
| 3 | 4096 | 16 | 10 | 200 |
| 3 | 16384 | 16 | 10 | 200 |
| 3 | 24576 | 16 | 10 | 200 |
| 3 | 49152 | 16 | 10 | 200 |

Each point is **one JVM** with one or three writer threads. Every writer has its own synthetic data file and buffered CSV. No shared CSV lock is included in the timed write/force brackets. CSV/flush and scheduler activity can still affect subsequent iteration cadence. Three threads are not three JVMs or an Aeron cluster. Fixed ordering and small samples do not control host, filesystem, JIT or thermal drift.

All data writes, including full logical zero preallocation and warmup, total **85,164,032 bytes (81.21875 MiB)** across eight points; 3,376 calls to `force(true)` are required. Each writer preallocates one sixteen-block circular file, with one force after preallocation and one force after every warmup or measurement write. Preallocation is not a physical extent guarantee. Per point, raw phases and all 211 rows/writer remain available. Measurement distributions must exclude the preallocation and warmup rows. Report write, force and combined brackets separately, with thread CPU when supported; blank CPU values remain unavailable.

The Java admission deadline is 30 seconds/point; the supervisor polls a 35-second allowance/point with a 280-second global **admission/measurement** budget. It may refuse a remaining point if less than its full allowance remains. Cleanup and archive/hash/readback occur afterward and are additional bounded work per process or bounded bytes, not part of a portable 280-second hard-stop guarantee. A kernel write/force or uninterruptible task can outlive admission; such a point fails and blocks all later points. There is no automatic retry, reissue or resume. Preserve the original identity after transport ambiguity and query status.

Minimum free space is 3 GiB on the measured overlay filesystem before every point and before each Java operation. The matrix allows at most 1 MiB CSV per writer, 64 KiB per JSON file and 256 KiB JVM log per point. Planned output cap is 25,952,256 bytes across points including maximum logs; controller inputs/receipts allow a separate 2 MiB archive allowance. Data-write bytes and output bytes are different quantities. Final data extents, all successful raw rows, byte totals, force counts and post-readback SHA must agree. These caps do not include general OS filesystem metadata or imply physical I/O byte accounting.

The immutable Java source `3331268b...` and preparation manifest `5d437f48...` are unchanged. The deterministic artifact includes only the source, pinned preparation manifest and its exact four runtime Java21 classes; no clock test helper. Before and after each point, exact file inventory/size/SHA must match. Actual Linux/overlay metadata and all explicit options must agree with the plan. Hidden JVM environment option hooks are refused without logging their contents.

Before registration/execution, the local prerequisite revalidates all four client-driver ABAB terminal points, pinned configuration verifiers, canonical/zero-UNKNOWN/timing validity, independent analysis inputs, full local native tar SHA and manifest SHA, and exact original owned-stop receipts. Overload is retained and does not imply a performance promotion. The plan binds every receipt and archive SHA. Remote preflight verifies the four existing immutable completion/owned-stop declarations and a fresh project/JMH/probe JVM inventory; it does not redundantly scan multi-GB FUSE archives. This inventory does not prove CPU/disk exclusivity or detect unrelated native preparation activity. Therefore execution additionally requires root's explicit `--idle-window-confirmed` after dependency/native compilation closes.

Local-only commands (no network):

```sh
python3 -B runtime/cloud/cpu-20261024/force-path-preparation/test_force_probe_controller.py
python3 -B runtime/cloud/cpu-20261024/force-path-preparation/force_probe_controller.py
# Only after independent review, root may register the immutable plan locally:
python3 -B runtime/cloud/cpu-20261024/force-path-preparation/force_probe_controller.py --register
```

Remote execution remains a separate explicit root action. A unique CREATE_NEW control directory, artifact directory and data directory are required. The launch records PID, `/proc` start ticks and exact argv SHA. Before any TERM/KILL the original identity is checked twice after pidfd open; only that pidfd receives the signal. PID reuse means the original is gone, and changed argv means cleanup cannot be proven. There is no numeric PID signal, process-group signal or whole-host cleanup. SIGINT/SIGTERM triggers owned cleanup once; repeated cancellation cannot interrupt cleanup. A missing per-point receipt never counts as proof of stop. The Java program does not spawn subprocesses; this controller does not claim cleanup of hypothetical unrelated or escaped descendants.

Full successful closure requires all eight individual receipts, 3,376 force calls, every data/CSV hash, exact staged classes before/after, closed JVMs and a closed archive. Local collection checks the entire archive manifest plus registered plan/controller/artifact identities and recomputes each raw validation. Failed partial attempts remain failed and retain their outputs; later points stay unlaunched. No transaction p99, production SLA, pure fsync latency, exclusive CPU/disk result, unique bottleneck or provider durability claim follows from this microprobe.
