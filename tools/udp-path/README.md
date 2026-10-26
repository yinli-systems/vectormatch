# Bounded UDP path diagnostic

This is a synthetic 64-byte echo protocol, separate from matching, Aeron replication,
maintenance and durability acknowledgments. Its throughput must never be presented as
orders per second. It measures neither one-way delay nor physical-host isolation.

Compile with Java 21:

```sh
javac -Xlint:all -Werror -d /tmp/vm-udp-classes tools/udp-path/UdpPathBench.java
```

Each invocation requires a **new** output directory. Start the listener, wait for
`ready.json`, and use the same random 64-bit hexadecimal run ID at both endpoints.
The server expires after its bounded duration; the client generates independent
scheduled arrivals, never retries and drains for at most three seconds. The echo
does not amplify packet size. Run only on disposable, explicitly authorized test
nodes. A run ID distinguishes experiments; it is not production authentication.

```sh
java -cp /tmp/vm-udp-classes UdpPathBench server /tmp/server-new 22999 1000000 25 12ab345678901234 10000
java -cp /tmp/vm-udp-classes UdpPathBench client /tmp/client-new 127.0.0.1 22999 1000 10 1000000 12ab345678901234 131072
python3 -B scripts/analyze_udp_path.py /tmp/client-new
```

Cloud comparison registration, 2026-10-26:

The original comparison used commit `37ec26cd` and its original aggregate-only
server protocol. The current protocol adds a bounded V2 receipt ledger and an
explicit planned-packet argument. Its results are a separate diagnostic cohort;
older raw records are preserved and never backfilled with invented receipts.

- Server `ohlwuyb375oeva`, client `tw2o4n649kjk6z`, EUR-IS-1, CPU5c,
  4 vCPU/8GB each; NAT-mapped UDP. Different boot IDs do not prove different
  physical hosts. The existing prepaid CPU is a separate low-rate reachability
  initiator, not the client in these capacity comparisons.
- Same JDK, source, compiled bytes, packet size, buffer request (128KiB),
  target and ten-second arrival window. Observe actual socket buffer values.
- C uses a 1,000,000ns maximum idle park; D uses 100,000ns. Both endpoints use
  the selected cap. This is the sole global policy factor, not a busy-spin test.
- C1/D1/C2/D2 at each of 1,000, 5,000, 10,000, 20,000 and 40,000 planned packets/s.
  Escalate only if all four preceding points have zero missing replies, not-sent,
  duplicates or invalid packets and exact server/client count agreement. Stop at
  the first failed level; do not silently rerun or replace it.
- A policy improvement requires at least 10% lower scheduled-to-reply p99 in
  **both** pairs, no worse post-send p99 and no fewer replies inside the arrival
  window. Keep per-process CPU time alongside latency; no percentile pooling.
- Every planned arrival is in the CSV. Any missing reply makes all-arrival p99
  undefined. Conditional reply percentiles remain explicitly conditional.
- Finite windows do not establish a sustained SLA or a network capacity ceiling
  beyond the highest tested rate. Preserve source, configuration, raw CSVs,
  server counts, failures and hashes. Stop all newly rented nodes when finished;
  the existing prepaid CPU stays running.

The Python audit recalculates quantiles and outcomes independently from the original
CSV and refuses missing or duplicated identities, incoherent send/reply timelines,
truncated records and inconsistent summaries. Its tests include actual loopback
datagrams under both policies; loopback timings are correctness evidence only.

V2 keeps one primitive receipt slot per planned packet (at most 500,000), validates
sequence/payload identity before echoing and records first receipt, first echo
attempt and duplicate/send counts. `--server /path/to/server` pairs these identities
with the client's original CSV. It partitions unknown outcomes into ingress
unobserved, server echo not sent and egress unobserved without combining clocks.
These categories identify missing observations, not a specific physical switch,
provider component or one-way delay. The ledger is written after the window.

`ForceProbe.java` is a separate filesystem diagnostic: 2,048 deterministic,
noncompressible 4KiB records, each followed by `FileChannel.force(true)`. It retains
every write/force duration and the original 8MiB file. Use the same JDK and source
on each host, run outside network arrival windows and independently rederive its
percentiles. This measures OS-observed force completion, not physical media
durability, matching latency or a comparison between durability levels.
