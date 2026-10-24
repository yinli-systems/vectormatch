# Finite-window classification and periodic backlog

A read-only reanalysis of the frozen chunk A/B/A/B inputs changes the interpretation boundary, not the recorded metrics or historical classifications. All21 inputs were SHA-bound and rechecked unchanged. No new benchmark, Java, SSH, SQL or business operation ran.

Both6144-byte treatments recover between their first two full maintenance cuts. B1 has4 released-but-unconfirmed orders at each cut start; B2 has3 at each. After the first maintenance ends, the minimum between-cut outstanding count is2 in both treatments. First-cycle pauses are4.979/4.921seconds. This supports periodic recovery during the observed short exposure; it does not establish long-run stability. The3072 controls begin their second full cut with259 still unconfirmed, after the12.8-second arrival window has ended.

The historical `VALID_FINITE_OVERLOAD` label remains in the frozen comparison. It describes a finite window with low within-window goodput and seconds of p99/drain. **It must not be read as proof that500offered orders/s causes unbounded steady-state queue growth.** The12.8-second window covers only two full3072-command cuts and one final partial cut. Its placement relative to maintenance affects within-window goodput. The original all-arrival p99 values and all6400 terminal outcomes remain unchanged.

`releasedMinusConfirmed` is independently computed as the number of actual arrival offsets at or before t minus the number of full accepted reply completions at or before t. It includes any queued/inflight work; it is not an independent reconstruction of the owner queue component. Raw1Hz sampled queue high water can miss the exact interval-boundary outstanding count.

The separate read-window1/8 comparison keeps its original6400-order configuration for a clean factor comparison. A later preregistered capacity run needs at least10full maintenance cycles, repeated measurements of outstanding work at equivalent cut boundaries, backlog slope uncertainty and a stated latency SLO. Recovery between two cuts is insufficient to promote a stable capacity; trailing replies at a finite window boundary are insufficient to locate a unique instability threshold.

See `result.json` for all four exact timelines and21 input hashes. `executed-source.py` is the actual arithmetic source. No frozen source result, raw arrival CSV or earlier proof was edited.
