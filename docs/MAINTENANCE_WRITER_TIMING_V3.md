# Maintenance writer phase timing

This instrumentation measures the existing V3 path before an optimization is selected. It changes no verification, copy ownership, force call, acknowledgement ordering, admission limit or file-count budget. It is a new application artifact and must not be mixed into the earlier capacity cohort. No performance improvement is claimed.

The completed same-artifact boundary repeats show7500/s p99=263.32ms and8000/s p99=580.14ms. The earlier phase decomposition leaves about4.07/4.16s per run outside measured source-RPC unions and payload write/force/readback phases. That residual is not isolated CPU time. Source-RPC durations also combine queueing, service, transport and evidence consumption. See [the full boundary results](CAPACITY_BOUNDARY_REPEATS_V3.md).

Each completed cycle now adds `writerTimingSchema=1` to its existing verification record. It records `coordinatorArchiveVerificationNs` around the coordinator's canonical archive verification. Archive and event writer results each expose the following monotonic durations from the same JVM:

| Phase | Boundary |
| --- | --- |
| Copy | The defensive caller-buffer clone before admission to the writer queue |
| QueueWait | From the stamp immediately before queue admission until the writer begins validation; excludes the clone |
| Prevalidation | Canonical archive verification or exact event-frame verification before creating a payload file |
| InputHash | SHA-256 of the immutable copied input |
| Write | Opening the new payload file and writing all bytes; retains the prior metric definition |
| Force | The payload `FileChannel.force(true)` call |
| Readback | Closing the payload, post-force test hook, bounded full readback, SHA comparison and canonical verification; retains the prior definition |
| ReceiptWrite | Constructing, opening and writing the existing bounded success receipt |
| ReceiptForce | The receipt's own `force(true)` call |
| Elapsed | From writer prevalidation start until the receipt has been forced and closed |

Copy and queue waiting are outside writer elapsed. The seven measured serial phases inside elapsed must sum to no more than elapsed; free-space checks, path construction, close operations and timing overhead account for the remainder. Durations include scheduling pauses and GC. Neither force duration nor readback is a measurement of physical device latency or a power-loss durability guarantee.

The per-payload receipt keeps its existing fields and <=1024-byte bound. Its own final force duration cannot be included in the same already-forced receipt. That duration is available only in the completed writer ticket and is exported through the existing cycle record after both destructive ACKs. Ticket success still requires the payload and receipt force/close to finish. Missing cycle timing after a failure is not permission to infer success, reissue fresh identities or delete raw evidence.

The next experiment must qualify the new sources/JARs, retain both native/raw inputs and compare the instrumented control with a proposed optimization at identical settings. Any avoided validation must first prove immutable bytes and exact profile/lineage/range/ACK binding while retaining full canonical forced-file readback. Continuous retention, cross-host isolation and the millisecond trading target remain separate pending gates.
