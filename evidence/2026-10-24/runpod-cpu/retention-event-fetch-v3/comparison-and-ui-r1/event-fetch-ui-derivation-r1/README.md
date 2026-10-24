The frozen event-fetch UI exporter executed exactly once against the root-pinned
completed four-arm comparison and actual full archive/private push receipts. It
exited successfully and wrote a fresh derived index and derivation receipt.

The derived index contains 25 records. The previous 21 run objects and every
capacity/other index field remain equal to the complete preserved before-index.
The new event-page16/32/16/32 p99 values are
550.774389/449.890003/562.453877/422.691382 milliseconds. All four reported
goodputs are 499.9556107954545/s. These values exactly match the actual final root
comparison. Maintenance wall totals, actual logical RPC counts, sampled backlog
and failure counters remain in each record's context.

This scope retains the frozen exporter copy, complete before-index, actual root
manifest copy, exact command registration, input hashes and metadata before/after,
actual stdout/stderr, execution outcome, derived index, exporter receipt, and
separate presentation readback. All explicitly read inputs stayed unchanged.

The live `evidence/index.json`, main scripts and UI were not modified. No SSH,
Git, test, JVM, benchmark or business audit ran. Root can separately inspect and
apply the resulting index, then validate HTTP/browser rendering. Four independent
fresh lineages remain separate observations; fixed 500/s maintenance observations
do not establish a throughput ceiling or hard-real-time behavior.
