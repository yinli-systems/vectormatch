# Extended finite-window fixture

The original fixed configuration is retained in runpod-capacity. Its 30,000-arrival bound prevented at least 10-second windows above 3,000/s. W32 at 3,000/s still accepted all commands, so that bound was a fixture limitation rather than a measured backend ceiling.

This independent profile raises outbox capacity to 262,144, fixes maker quantity at 180,000 and each of 64 buyers funding at 900,000,000, and permits at most 90,000 measured IOC orders. All other node settings, leader 0, private UDP, sync=2 and the arrival/latency/loss definitions remain fixed. The larger seed and release have their own identity and prepared snapshot digest. **Do not combine old and extended points into one configuration group.**

Before cloud runs, exercise the 90,000-command final state, conservation, outbox and snapshot restore outside the timed workload under a 1 GiB heap. Validation snapshot RPCs remain outside measurements; the extended validator has a wider timeout and separately records validation duration. No core matching rule is changed.

Screen at W64 with 800, 1600, 2400, 3200, 4800, 6400, 8000 and 9000 arrivals/s, adapting once overload appears. Arrival window is min(30 seconds, 90000/rate) with a 10-second minimum. Compare lower concurrency at the suspected edge, refine and repeat both sides at least twice. A client or generator limit must be identified as such, not presented as an unconstrained engine ceiling. Preserve every invalid/failing trial.
