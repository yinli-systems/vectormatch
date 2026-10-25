# Exact-cut V4: recorded queue-wait diagnosis

This is a read-only analysis of the four complete 500/s raw archives from artifact `65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69`, source `0c8303b2`. It executes no orders and changes no benchmark input or result. Each arm has 10,000 accepted one-unit trades. The slowest 1% means the 100 largest scheduled-arrival-to-reply intervals in that arm.

| Arm | Fraction of tail queue wait overlapping forbidden business-admission phases | Tail wait overlapping a previous request from the same producer |
| --- | --- | --- |
| C1 | 99.1903% | 0 ns |
| D1 | 96.9373% | 0 ns |
| C2 | 98.0678% | 0 ns |
| D2 | 97.1009% | 0 ns |

These are sums of per-request waiting intervals, not wall-clock phase durations. Temporal overlap supports a dispatch-gate investigation; it is not independent causal attribution. It does not isolate network, disk force, GC or service execution, and overlapping categories must not be added. The zero same-producer overlap concerns these tail requests at 500/s; it does not rule out a client-window ceiling at higher rates.

The measured CONTINUE post-offer p99 is 11.586/11.893 ms; global p99 is 66.299/67.375 ms. These percentiles are separate distributions and cannot be subtracted to invent a queue percentile. The original per-point analysis provides the actual recorded schedule-to-dispatch distributions. A 10 ms global target cannot be established merely by shortening maintenance while the observed post-offer p99 already exceeds it.

The approximately one-second backlog sampler can miss short maintenance queues: a zero sampled maximum is not proof that no request waited. Raw per-arrival timestamps and per-worker high-water observations remain available. The console wording now makes this observation limit explicit.

## Candidate work after the registered curve

`RetentionAsyncMaintenanceV4.businessAllowed()` permits business in IDLE and, for CONTINUE, VERIFY_WAIT and FILE_WAIT. Its read turns hold an exclusive read bank. `RetentionBatchOwnerV3.openReadBank()` requires completed business/control closure, and `submit()` refuses business while the read bank is open. Simply relaxing the phase predicate would violate this ownership contract.

A bounded experiment can yield to a limited business burst only between fully consumed and closed read banks, then drain those original tickets before opening the next bank. It must preserve history/event/byte credits, fixed cuts, exact original identities and deadlines, four-offer limits, full receipt verification and the before-ACK fence. New phases and burst budgets need explicit trace/auditor qualification and the same-artifact control comparison. This is a candidate, not an implemented or proven optimization.

A larger alternative is an immutable prefix-export channel outside the replicated query path. Only the single writer may publish committed immutable bytes; the exporter must never read mutable engine state or influence replicated decisions through local reader state. Bound the current and active-reader buffers, connection count, payload bytes and original deadlines. Keep destructive ACKs on the replicated path after complete durable verification. This requires a new protocol and failure tests; no latency claim follows from the design.

A smaller allocation candidate reuses an already encoded event-page reply for trace and persisted event data. It requires complete byte-equivalence checks and a controlled comparison. It cannot by itself establish the end-to-end target.

[Complete derivation, input hashes and private raw references](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2/rate-500-queue-diagnostic-r1/analysis/RESULT.json). The current fixed-configuration capacity curve remains the prerequisite for choosing the next candidate.
