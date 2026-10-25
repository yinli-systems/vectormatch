# Read-only Aeron counter probe qualification

Local and pinned Linux JDK 21/Aeron 1.53.3 tests passed. The probe uses OS read-only mapping, checks CnC size/version/identity, bounds counter count and labels, and refuses wrong PID, truncation and symlinks. Three snapshots preserve synthetic test-counter values. The owned Linux test process exited; no cluster or business orders were started. All original local/Linux sources, compiled classes, logs and raw test data are preserved in the compressed archive with full member verification.

This is a one-shot probe, not an observed production profile. Fixture counter values are synthetic, not measured archive latency. A workload controller must additionally verify process birth/arguments and register observer overhead before collecting timed experiments. Cumulative max is not p99; time/bytes is not mean write-call latency.

Official references: https://aeron.io/docs/cookbook-content/aeron-read-counters/ and https://github.com/aeron-io/aeron/wiki/Monitoring-and-Debugging . Pinned counter definitions: https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/Archive.java .
