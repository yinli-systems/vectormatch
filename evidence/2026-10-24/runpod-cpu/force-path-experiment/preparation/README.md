# Synthetic FileChannel write + force(true) probe

This is an independent Java 21 diagnostic, with no production dependency. It opens only new `synthetic-force-writer-N.data` files inside a new `force-probe-...` directory. It never opens an Aeron recording, original PGDATA or service state, starts a service, performs SSH, or provisions resources.

`writers=1` or `writers=3` means threads inside **one JVM**, with one independent data file and CSV per thread. It does not represent three JVMs, Aeron replication, or three physical hosts. Runtime metadata records the actual OS, filesystem and JDK. Local macOS schema smoke is not evidence about the CPU Pod's Linux overlay storage.

## Explicit limits and phases

Every option is required. Supported blocks are exactly 4096, 16384, 24576 and 49152 bytes. Per-file logical extent is aligned and at most64 MiB; the combined **data-file write** budget, including all phases and writers, is at most256 MiB. Each warmup/measurement count is at most100,000 per writer. Admission duration is at most60,000 ms. A remaining-space floor is checked before directory creation and before each I/O operation. CSV/configuration bytes are additional instrumentation, with a row bound recorded in configuration. Production/archive/PGDATA path components, symlink ancestors and existing targets are refused. Files are never automatically deleted or overwritten.

`preallocation` writes the entire fixed logical file with zero-filled direct buffers, then calls `force(true)` once. This is not a guarantee of physical extent reservation, non-compressed storage, or provider durability. `warmup` uses a deterministic nonzero block, then `measurement` repeats that block at circular offsets inside the fixed extent. Each warmup/measurement operation calls `force(true)` once. All writers finish preallocation and warmup before the measurement gate opens. Reused direct buffers are allocated outside timed operations.

Each writer retains its own complete CSV, including preallocation and warmup rows. Those phases must not be pooled into measurement distributions. CSV formatting and flushing use that writer's independent buffer/file **outside** the timed data interval; there is no shared CSV lock. This instrumentation can still influence subsequent iteration cadence and filesystem scheduling. The probe does not calculate a transaction p99 or combine writer means into one.

## Raw timing and failures

CSV records wall UTC, JVM monotonic start, phase, writer/iteration, offset, requested/actually-written bytes, write/force calls, write elapsed, force elapsed, total elapsed, thread CPU, deadline status and error. For a complete row, `write + force = total`, written bytes equal requested bytes and exactly one `force(true)` invocation completed. `write` includes position, buffer limit reset, write-loop and deadline checks. `force` includes the force call plus adjacent clock/deadline overhead. Thread CPU is the current worker's JVM CPU bracket, including clock probes; unsupported/disabled/failed reads are blank, not an invented zero. It is not disk CPU time.

The time limit is an admission deadline, not a portable hard realtime promise. An operation already inside the filesystem/kernel may overrun or resist interruption. The probe cancels further admission, waits a1-second cleanup grace, retains partial files/CSV, and records failure without a success receipt. Failure records disclose whether worker termination was established. OS-level bounded termination requires a separate process supervisor; none is implemented here. SIGKILL/power loss may leave no failure JSON, and never create a success marker. CSV flush is not a separate crash-durability guarantee.

Successful completion requires byte/force-call conservation, exact file extents, complete worker termination and post-measurement file SHA-256 readback. SHA readback is outside measurement and may affect a later run's cache state. Readback, CSV and metadata do not prove power-loss durability. Preallocation/warmup/measurement rows remain separate.

## Local invocation

Compile using an explicit Java21 JDK, without Gradle or dependencies:

```sh
JDK=/absolute/path/to/jdk21
"$JDK/bin/javac" --release 21 -d build ForcePathProbe.java
"$JDK/bin/java" -Xms32m -Xmx64m -cp build ForcePathProbe \
  --output-dir /absolute/new-parent/force-probe-example \
  --block-bytes 4096 --writers 1 --file-bytes-per-writer 8192 \
  --warmup-iterations 1 --measurement-iterations 3 \
  --max-total-write-bytes 24576 --max-duration-ms 5000 \
  --min-free-bytes 1048576 --scope-label schema-smoke
```

The parser rejects abbreviated/combined, missing or duplicate options. `schema-smoke` and `diagnostic` are descriptive labels and never relax any safety or force behavior. Memory filesystems (`tmpfs`, `ramfs`, `devtmpfs`) are refused.

Run bounded local guards:

```sh
python3 -B -m unittest discover -s runtime/cloud/cpu-20261024/force-path-preparation -p test_force_path_probe.py -v
```

`ForcePathProbeClockGuard.java` is test-only. It injects a monotonic clock through an internal Java API to test failure retention. The real CLI has no injected-clock, no-force, overwrite, retry or remote mode. Do not package or invoke the clock guard as a performance probe.

## Interpretation boundary

Later one/three-thread probes may help separate time spent in a synthetic write call from its subsequent force call. They are not the Aeron Archive implementation. File size, preallocation, offsets, buffer types, repeated data, page cache, filesystem/journal, overlay backing storage, other users, JVM/GC and OS scheduling all matter. Shared overlay/fsync or scheduling noise can produce very different repetitions with identical options. Preserve every repetition and failed run. A high force fraction or low worker CPU is an association; it does not establish unique disk saturation, storage hardware behavior, or the transaction-path bottleneck. Actual Linux and trading conclusions require their own independently gated measurements.
