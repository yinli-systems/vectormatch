# Fixed-leader capacity campaign — 2026-10-23

This protocol is registered before cloud measurements. Results belong to the complete client + three-member replicated matching path. The load generator shares member 2's container; physical host anti-affinity is unverified. They are not HTTP, PostgreSQL, WebSocket fanout, or unconstrained matching-engine capacity measurements.

## Fixed configuration

* Leader 0, Aeron 1.53.3's **test-only** `aeron.cluster.appointed.leader.id=0` on all members. Normal HA deployments leave it unset. Check leadership term and role before, during (read-only CnC counters), and after every run; a change invalidates that run.
* Three existing Runpod containers in EU-RO-1, directly routed private UDP, MTU 1248, sync level 2, 1 GiB node heap, shared driver/archive threading, 128 KiB UDP socket buffers, outbox 65,536. Session limit 128 on every member for every trial; Aeron's default 10 would prevent the concurrency sweep.
* Stop the original application's Java processes and PostgreSQL during measurement. Preserve all original state and restore it afterwards. Use fresh, separate trial directories and port base 23000. Never reset the original lineage.
* Fixed preparation: 64 funded buyer accounts, one seller with 60,000 base lots, one GTC ask at 10,000 ticks, 100 warm-up IOC buys. Compare prepared canonical snapshot SHA across all trials. Each measured command is an independent one-lot IOC buy and should produce exactly one trade. At most 30,000 arrivals per fresh trial, within retained-order and outbox bounds.
* A source revision and per-artifact SHA-256 identify the immutable release. No hot replacement of loaded jars.

## Load and evidence

An absolute monotonic scheduler offers requests independently of replies. Bounded round-robin FIFO queues feed 16, 32, or 64 synchronous, single-in-flight clients. Queue capacity is fixed at 64 per worker; request timeout 2 seconds; drain limit 30 seconds. The scheduler's deadline error limit is 20 ms. Retain late schedules and mark affected runs invalid as evidence of generator timing failure. Queue-full means client admission loss, never a server rejection. Retry a timeout using its identical command identity before advancing that producer; unresolved means unknown, never a failed trade.

Every arrival is retained, including queue drops and unresolved commands. Report planned-to-confirmed latency (including queueing), initial API RTT, queue delay, offered rate, confirmation rate **inside the arrival window**, drain-inclusive rate, backlog over time, client drops, business rejection, transport errors, initial unknown and final unresolved. Conditional latency distributions must be labeled; if any offered request is not accepted, the all-offered accepted p99 is unavailable. Final replay checks canonical bytes, every business result, asset conservation and replicated-outbox continuity.

Collect 1-second process CPU/RSS/IO, cgroup quota/throttling/memory, namespace UDP counters and private-interface counters on all three members. Separately identify the load process. Preserve raw CnC counters for role, term, commit/append/service/recording positions and errors. Counter samples are observational, non-atomic, and may reuse IDs; cumulative and gauge counters must not be conflated.

## Adaptive sequence and interpretation

1. Small cloud smoke, then 10–12 second screens at 50, 100, 200, 400, 800, 1,600 and 2,400 arrivals/s with 16 clients, stopping/refining if a bottleneck appears.
2. Repeat the suspected plateau with 32 and 64 clients. If throughput rises with clients, the previous plateau was a client-window limit. If the scheduler misses its deadlines, do not label it a backend ceiling.
3. Refine the interval, repeat both sides at least twice and extend feasible windows to 30 seconds (subject to 30,000 arrivals). Retain every failed or invalid run; any adaptation is recorded alongside the evidence.

An observed stable trial requires correctness and unchanged leader/term, all arrivals accepted, no unknown, an on-time scheduler, at least 95% of the offered rate confirmed within the arrival window, no persistent queue growth (last-half backlog growth no more than max(2, 1% of arrivals)), and drain no longer than max(100 ms, 1% of the window). These are declared finite-window observation thresholds, not a production SLA or a mathematical stability proof. Report p99 directly; do not invent a latency SLA to select a flattering capacity. State the highest repeatedly stable rate and first repeatedly unstable rate **for this configuration**. Identify load-generator saturation or untested intervals explicitly.

## Budget and recovery

Reuse the three existing Pods initially; their conservative combined quote is $1.56/hour. Before every trial, estimate project spend from the recorded launch times, reserve $2 for recovery, and refuse a new trial if the projected campaign would exceed the $20 total. This is a local guard, not a provider billing cap. Account charges for unrelated workloads are excluded. The user's retained-Pod reminder stays unchanged. Do not stop/delete Pods or volumes as part of this campaign. Restore the original application, with its original state and normal leader election, and verify HTTP/SQL projection readiness after measurement.

Sources: [pinned Aeron configuration](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModule.java), [pinned CnC reader](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-samples/src/main/java/io/aeron/samples/CncFileReader.java).
