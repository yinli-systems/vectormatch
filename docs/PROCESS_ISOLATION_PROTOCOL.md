# Process isolation and collector experiment

This is a new, preregistered VectorMatch-only protocol. It does not silently replace the [earlier common-subset results](COMMON_ENGINE_COMPARISON_RESULTS.md). That experiment placed the absolute source and business in one JVM; its 250k arms missed 17,420 arrivals and its 100k first arm violated the 20ms source-lateness gate.

## Controlled intervention

Both placements run two JVMs with the same loopback TCP framing, source code, pre-generated GTC/IOC/cancel corpus, 8,192-total-outstanding credits, request/reply batch ceiling64, TCP_NODELAY, requested64KiB socket buffers and unchanged MatchingEngine business logic. Each source uses a dedicated absolute scheduler and a separate nonblocking IO thread. The scheduler does not wait for network progress, a credit, or a reply: a full credit window records the original NOT_SENT and advances the original clock.

COLOCATED starts both source threads in the business JVM. ISOLATED starts those same threads in the controller JVM. The controller exists in both cases and waits when COLOCATED. Both JVMs preallocate and retain the identical primitive source-evidence arrays, including the unused copy, to avoid changing business initial evidence-array footprint. This controls one process-placement change, not a claim that operating-system scheduling costs or collector implementations are identical.

Source/controller: fixed G1,1GiB initial/max heap. Business:1GiB initial/3GiB maximum heap. Both have ActiveProcessorCount=8 and inherit the same eight allowed CPU IDs, frozen before native work; no other benchmark, build, compression or replay overlaps arrivals. This is the existing shared Runpod CPU, not exclusive hardware. No new paid resource is needed.

All plan→reply and completed-client-write→reply intervals use the **source JVM clock only**. A worker duration is worker-end minus worker-start on the worker clock; it is never subtracted from source timestamps to invent a network interval. Every source result must match an actual worker original, independently replayed fill history, complete final balances and open orders. Separate quantiles are not additive.

The TCP protocol deliberately differs from the earlier in-JVM queue boundary; compare only matched points within this protocol. Both placements use identical TCP behavior. [SocketChannel's specified partial/nonblocking reads and writes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html) are handled explicitly. Request identity is the immutable corpus index; partial writes never count as completed publications.

## Ordered campaign

1. Actual Linux execution of all nine targeted Java tests, including two real JVMs, plus the existing three independent Python business-auditor tests.
2. Three functional native qualifications: COLOCATED/G1, ISOLATED/G1, ISOLATED/GEN_ZGC, each1,000/s for one second. Run complete source/worker/Python business verification. These are not performance evidence.
3. **Placement ABAB:** for each100,000 and250,000/s, five seconds at seed73439: A1 COLOCATED/G1, B1 ISOLATED/G1, A2 COLOCATED/G1, B2 ISOLATED/G1.
4. **Collector ABAB:** for each same rate, same five-second plan and same isolated source: A1 G1, B1 GEN_ZGC, A2 G1, B2 GEN_ZGC. Only the business collector changes; the source/controller stays G1. Use the same candidate binary throughout.

GEN_ZGC means Java21 `-XX:+UseZGC -XX:+ZGenerational`, as specified by the [JDK21 collector documentation](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html). Low pause-time descriptions are motivation, not a guarantee or a result. Heap and CPU limits are not increased to improve a score. No business-index, deduplication or financial-state semantics change is included in this campaign.

Every phase retains all originals. Wrong business outcome, unknown original, process loss, missing raw data or failed full replay stops the campaign. A finite overload/timing failure remains a measured failure and may continue to the next registered diagnostic point. A collector/placement improvement requires both matched pairs to agree, no new missing acceptances/unknowns, valid source scheduling and no worse accepted in-window goodput. If an entire accepted distribution does not exist, it cannot be scored using only successes. This five-second screen does not establish sustained capacity or promote production defaults.

## Evidence and instrumentation

Preserve every plan/source/write/reply timestamp, source status, worker original, worker-local duration, all trades, final accounts/book, process identities, complete GC/safepoint logs, process CPU/memory/IO telemetry, argv, exact JAR/class/source hashes and separate JVM resource receipts. Counters for source-queued, credit-outstanding and completed-write-awaiting-reply high-water values update at each event, rather than a once-per-second sampler that misses short bursts. The counters do not infer unseen kernel/server queue sizes. Resource windows are explicitly labelled; receipt serialization and state capture must not be presented as isolated per-order CPU cost.

Finite acceptance remains: every planned command accepted, no unknown/not-sent/rejection, at least99% replies before the original five-second deadline, and no source release more than20ms late. This contains no millisecond latency SLA. Report p50/p99/p99.9, accepted goodput, all missing/error counters, exact defined source high-waters, GC and CPU. Full business replay uses the unchanged independent Java flat model and Python price-level/FIFO model. The new Python audit additionally binds source replies to worker results, verifies process placement/collector/closure and checks within-worker durations without assuming a common nanoTime epoch.

Original archives go to the authorized private repository as draft attachments with member hashes and complete authenticated download verification. Git retains thin results, sources and indexes. Any collection retry resumes the same stopped original and same asset; it does not rerun or replace a failed benchmark. Stop only owned test process groups, leaving the existing CPU available.

## Replicated sustained follow-up

After the finite isolation/collector campaign closes, run three separate Aeron JVM replicas plus an independent load process on this same CPU. This is a same-host UDP cluster, not independent physical fault domains. The existing separately admitted30–60minute `RemoteSoakExperiment` uses a190k-total-command profile; a30minute100/s run fits that profile and measures continued replicated operation, not100k/s or250k/s capacity. Preserve all minute windows, source timing, disk-sync/GC/CPU telemetry, canonical financial replay, snapshots and cold restore. Do not lift finite bounds or sum reset lineages to fake a higher-rate endurance result. The anchored V4 streaming integration remains required for a high-rate30–60minute V4 capacity claim.
