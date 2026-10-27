# Replicated path decomposition and idle-policy comparison

**The empty-service control retains large tails; shortening the replica park does not pass both paired criteria.** All eight comparison arms accept every original. The 30-minute follow-on is still running; no long-window result is claimed in this interim report.

All runs use the same existing CPU host, three actual Aeron UDP replicas and one load JVM, G1, disjoint CPU affinity, leader 0 and sync level 2. These are bounded single-lot IOC fixtures. Source samples are memory-only during arrivals and serialized afterward; R3 used a different durable source recorder and producer/cache population, so these are not a direct before/after against R3.

|Arm|Service|Planned|Accepted|p50 ms|p99 ms|p99.9 ms|Source releases >20 ms|
|---|---|---:|---:|---:|---:|---:|---:|
|path-a1|NOOP|3000|3000|9.259|74.922|175.520|0|
|path-b1|MATCHING|3000|3000|9.411|86.200|127.656|0|
|path-a2|NOOP|3000|3000|14.395|75.113|98.251|0|
|path-b2|MATCHING|3000|3000|9.453|65.137|125.456|0|
|idle-a1|MATCHING|6000|6000|9.241|79.261|127.710|0|
|idle-b1|MATCHING|6000|6000|9.751|173.200|245.039|0|
|idle-a2|MATCHING|6000|6000|34.043|233.276|512.738|0|
|idle-b2|MATCHING|6000|6000|5.611|149.460|236.525|0|

Path A/B compares NOOP with MATCHING for 30 seconds at 100/s, all at explicit 1 ms replica max park. NOOP echoes a same-length successful response with zero business-state sentinels; it does not trade. Idle A/B compares explicit 1 ms with 100 µs for 60 seconds at 100/s, all MATCHING. The source is unchanged. B's p99 is worse in the first pair and better in the second; the precommitted rule retains 1 ms for the long run. Both paired directions, CPU costs and all failed latency gates remain in the raw audits.

The empty-service callback p99 on the leader is 27.460/36.370 µs, while its full p99 is 74.922/75.113 ms. Replica GC pauses are absent in the first empty and matching comparison. File-force calls show long stalls. This supports investigating replication/storage/scheduling ahead of matching logic; marginal percentiles are not additive, and file-force duration includes any OS descheduling during the call. These observations do not prove one exclusive physical-storage cause.

The pinned [Aeron 1.53.3 RecordingWriter](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/RecordingWriter.java) forces file content and metadata at sync2 before advancing its recording position. Durability is not disabled to improve this benchmark. A separate [disposable-buffer placement protocol](REPLICATED_BUFFER_LAYOUT_PROTOCOL.md) tests relocating only reconstructible communication buffers to tmpfs; its new runtime is not used by this frozen path-probe campaign.

The first R1 native qualification is preserved as a measurement-audit failure: the short-lived source exited before a final enclosing CPU sample. R2 adds a two-second post-window polling tail without changing original request times. All R2 original frames, source rows, worker timings, final states, telemetry and closures are member-hashed, privately uploaded and fully downloaded for verification before duplicate retirement. Matching final-state replay uses the same core implementation; Python independently checks the original wire fields and this fixed fixture's sequence/result arithmetic.

See the [frozen protocol](REPLICATED_PATH_PROBE_PROTOCOL.md) and [all thin receipts](../evidence/2026-10-27/replicated-path-probe-r2/). Same-host scope does not establish physical fault isolation, media power-loss durability, continuous outbox export, high-rate replicated capacity or production readiness.
