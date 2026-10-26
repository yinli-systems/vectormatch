# V4 instrumented counter diagnostic

[Prospective protocol](V4_COUNTER_DIAGNOSTIC_PROTOCOL.md). Fixed artifact `dcfeeb81`, source `c6445604`, leader 0, sync2, CONTINUE, read-bank CLOSED, agent100us, owner1ms. One physical CPU host; three real loopback UDP JVMs plus a separately registered read-only observer.

All 80,000 scheduled IOC orders confirmed distinct ACCEPTED results; unknown/reject/notSent zero. Arrival-window goodput **3993.45/s**, global p99 **66.507884ms**, post-positive-offer p99 **13.884341ms**. Financial audit, physical-order replay, exact cuts, all three snapshots and all three cold restores passed. This finite instrumented point is not a baseline comparison or production SLA.

The observer recorded 314 complete three-driver samples, including 200 wholly inside the arrival window per original driver. Whole-window bracketing, original PID/file-key continuity and stable archive-counter identity passed. Maximum complete-sample duration 3.009066ms; maximum gap 102.341577ms. Zero skipped unstable counter records inside the window.

| Original member | In-window observed span | Archive total write-time increase | Archive bytes increase | Lifetime max write at last inside sample |
|---|---:|---:|---:|---:|
| 0 | 19.918391s | 16.080125s | 23,852,864 | 13.198029ms |
| 1 | 19.918197s | 16.425725s | 23,851,392 | 15.939067ms |
| 2 | 19.918146s | 16.434361s | 23,851,104 | 15.180436ms |

Each node independently accumulates its own write-path wall time; these values are not added across nodes. Zero observed NAK/retransmit increments, short sends, driver/cluster/container error increments and leadership-term changes. Leader sender-flow-control counter increased 114, so back-pressure did occur. Absence of retransmits does not independently measure network RTT or rule out every transport wait.

The timer in [pinned Aeron 1.53.3 RecordingWriter](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-archive/src/main/java/io/aeron/archive/RecordingWriter.java) spans recording writes and configured force calls. These observations therefore prioritize the durable write path; they do not isolate fsync duration or establish a causal decomposition of reply p99. A cumulative maximum is not a percentile. Sequential counter reads are not atomic.

The whole source recorded 54,272 distinct business-batch requests for 80,003 business commands including three setup commands: {'1': 44755, '4': 7541, '3': 1132, '2': 844}. Most batches contain one command despite a cap of four. This motivates a bounded coalescing-delay experiment while retaining sync2, the same batch cap, deadlines, credits, exact cuts and financial semantics. It is a hypothesis, not a measured improvement.

The observer consumed about 0.014 sampled CPU cores and at most 138MB sampled RSS over its recorded in-window process samples. Its actual activity and roughly 6MB counter JSONL are included in the original archive. Node CPU averages do not measure disk wait directly.

[Complete original raw asset and inventories](../evidence/2026-10-26/runpod-cpu/v4-latency-r1/counter-diagnostic-4000-x1-native-r1/README.md): private asset `676595091`, 65,984,830 bytes, SHA-256 `ae7efb4a7eb8589f0f86511ac496873e65123ab502065b4e90cee5bdaab89b60`. All 566 original files were verified after a complete authenticated download. [Analysis source, eight refusal/coverage tests and private proof](../evidence/2026-10-26/runpod-cpu/v4-latency-r1/counter-diagnostic-review-r1/README.md).
