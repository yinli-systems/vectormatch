# Preserved startup rejection, no capacity workload

This exact registered job was submitted once. It failed before any JVM/node or load launch: the frozen remote launcher requires three distinct IPv4 addresses and rejects the registered repeated127.0.0.1 loopback topology. `workloadLaunched=false`; all owned processes are stopped. This is a CPU harness compatibility failure, not a matching correctness failure or a capacity point.

The complete17-file original job archive was downloaded, byte/SHA-verified and safely extracted. [Completion](completion.json), [raw node0 startup receipt](raw/node0-start.json), [full original manifest](raw/full-state-manifest.json), [typed invalid analysis](analysis/summary.json) and independent analysis invocation are retained. The unchanged analyzer returns an invalid observation with missing load metrics; those null metrics are not fabricated zeros. A corrected launcher adapter must use another registered ID and preserve this job.
