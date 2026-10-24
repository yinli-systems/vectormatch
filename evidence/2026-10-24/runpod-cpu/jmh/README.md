# CPU core JMH baseline and warmup sensitivity

Source `987f6526b8a0b3c3516ee668a239990cc79fbd8f`, Temurin21.0.13+9,3 forks,1 thread,2GiB fixed heap. CPU packaging smoke plus16-case default matrix and15-case fresh warmup100 matrix completed and independently rehashed. Every raw fork/iteration score was recounted and mean recomputed. See [registration](registration.json), [raw receipt](raw/receipt.json), [independent verification](independent-verification.json), and [measurement contract](../../../../docs/CORE_JMH.md).

Warmup sensitivity is substantial. These are sequential same-code configurations, **not code optimization gains**. Use the same explicitly disclosed100-iteration fresh warmup in subsequent comparisons; it remains finite and does not establish JIT steady state. At100iterations, matching means range0.620–7.711us/command within64-command batches depending on book and trade count; place0.481–0.614us; cancel0.497–0.787us. No per-order p99, sustained fresh-command throughput or replicated-platform capacity is inferred.

| Action | Initial levels | Trades/command | Warmup5 us | Warmup100 us |100/5 ratio |
|---|---:|---:|---:|---:|---:|
|MATCH|1|1|1.654158|0.758059|0.458|
|MATCH|1|10|3.460482|0.829775|0.240|
|MATCH|1|100|7.777376|4.350137|0.559|
|MATCH|100|1|1.632049|0.743584|0.456|
|MATCH|100|10|4.212285|0.895512|0.213|
|MATCH|100|100|7.492156|5.833351|0.779|
|MATCH|10000|1|0.585229|0.620155|1.060|
|MATCH|10000|10|1.571780|1.368037|0.870|
|MATCH|10000|100|7.677856|7.711453|1.004|
|PLACE|1|0|1.264704|0.480845|0.380|
|PLACE|100|0|1.494711|0.488065|0.327|
|PLACE|10000|0|0.627832|0.613679|0.977|
|CANCEL|1|0|0.955098|0.497186|0.521|
|CANCEL|100|0|1.356079|0.595656|0.439|
|CANCEL|10000|0|0.857246|0.787376|0.918|

Each fresh score pools30 normalized batch-mean observations (3forks ×10measurements), not1920 independent order timings. JMH error intervals and complete raw data remain in JSON. Setup/verification is outside the timer and can still affect JIT, caches and GC. No allocation profiler was used.

The separate dedup replay case scored84,402,292 cached replies/s. These64 previously accepted identities advance no business sequence and emit no new events. This figure is **not**84M new orders/s and does not satisfy any100M target.

Measured core code entries match the deployed source433 core byte-for-byte. Capacity on the same CPU host runs after this entire JMH job, never concurrently. No affinity or OS tuning was performed.
