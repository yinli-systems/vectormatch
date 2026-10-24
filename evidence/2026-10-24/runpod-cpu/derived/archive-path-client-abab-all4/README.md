# Complete client ABAB Archive timing diagnosis

All4registered trials and all3nodes are included. This extends the preserved provisional first-pair observation without replacing it. Every derived CPU summary and its raw input SHA was rechecked.

|Stage|Node0 write-path/wall|Node1|Node2|
|---|---:|---:|---:|
|A1|98.63%|94.89%|94.59%|
|B1|99.38%|95.80%|95.82%|
|A2|98.93%|95.64%|95.54%|
|B2|99.19%|95.94%|96.40%|

All tracked diagnostic counter deltas are zero in these sampled identities/windows. This does not establish absence of ephemeral or unobserved counter loss. The counter times copy/checksum/write/force plus descheduling;it is not a purefsync histogram,aCPU utilization measure or unique storage saturation proof. Source semantics are tied to [Aeron1.53.3](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-archive/src/main/java/io/aeron/archive/RecordingWriter.java) and [actual pinnedJAR bytecode](../archive-path-client-abab-prefix2/actual-pinned-jar-javap.log).

The next experiment uses separate synthetic files and force(true),with one JVM and1/3writer threads. Its I/O distributions must be kept separate from transaction latency.
