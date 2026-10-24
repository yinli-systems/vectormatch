# Finite CPU idle comparison preparation

The stdlib-only local tool accepts explicit collection/root-review paths relative to its config. Python3.9+ is required. No remote commands, Java, Git, launch, signal, cleanup, original evidence modification or benchmark execution occur. An output is CREATE_NEW, including an error output.

Formal mode requires arms1/2/3/4, ordered1ms/100us/1ms/100us, each with completed collection, independent full outer/raw root review, matching ready release/controller, exact stopped proof, all native/raw audit closures and hashes. The four actual JARs must match the pinned release. Config and registration must be equal except requested park and fresh lineage/origin. Each node's seven actual factory creations and the owner's one creation are checked separately (22 total), without claiming measured sleep or private runner-thread assignment.

The CSV calculation separately reports all-arrival accepted-order p99, accepted conditional and completed-reply conditional distributions. All-arrival p99 is undefined if any planned arrival is absent, unknown, notSent or rejected. Successful comparison additionally requires zero such outcomes and valid scheduler timing; failure produces a retained error, never a smaller passing subset. Nearest-rank quantiles use ceil(p*N). Scheduled-to-dispatch, dispatch-to-successful-offer-return and successful-offer-return-to-reply are separate distributions; their quantiles must not be added.

Maintenance cycle wall time comes from actual cycle start/end receipts, including force/readback/ACK work. Read phase spans use first reservation-to-last coordinator-recorded end as an observed lower bound of lease lifetime. Overlapping logical-RPC elapsed sums are explicitly not wall time. Physical frame batch distributions are classified by disjoint arrival and maintenance correlations, not members>0 (maintenance index rows also use members=1).

CPU uses per-process adjacent complete interior 1Hz samples and matching PID/startTicks/argv identities. Each role has its actual covered monotonic intervals/duration, gaps, cumulative CPU seconds, covered mean occupied cores, RSS/thread maxima and kernel write deltas. Missing or reused identities remain unavailable, never fabricated zero. The parent entire observed span is separately reported and includes setup/drain/close. No uniform all-role CPU sum, quota normalization, pure fsync, exclusive CPU or unique cause is claimed. UTC-vs-monotonic consistency is checked coarsely (100ms threshold; observed residuals24.4/26.1µs in the first two arms), not claimed as exact sample calibration.

## Executed local validation

- guards-r1:10 pure tests passed.
- two-arm-diagnostic-r1:FAILED a draft frame discriminator. It treated every members>0 index as business, although maintenance has members=1. Exact source is retained in guards-r1/source.zip and its SHA matches that attempt's registration. Error JSON/stdout/stderr/receipt remain unchanged.
- guards-r2:11 tests passed after exact correlation-set classification and its regression.
- guards-r3:12 tests passed after adding strict nanosecond UTC parsing and clock-domain mismatch coverage.
- two-arm-diagnostic-r2:PASS;99 input files hashed and rechecked before publication. It is explicitly not a full ABAB result.

The successful two-arm diagnostic independently finds p99 899.508607ms vs562.917877ms, three-cycle maintenance wall1.988772353s vs1.292279377s, and identical arrival-window goodput479.765625/s. Both arms have6400 distinct accepted orders and no notSent/unknown/reject/late>20ms/warnings. These are finite observations, not sustained500/s capacity or significance claims.

## Later formal invocation

Use formal-config.template.json only after all four SUCCESS/root-review files exist and are closed. Review or create a new config with actual archived paths; do not rewrite frozen source or original proof. Example local invocation:

    python3 -B compare_idle.py --config /absolute/path/config.json --output /new/absolute/path/comparison.json

No formal comparison has been executed in this preparation. Qualified warnings and historical failed wrapper/native attempts remain original evidence. This tool does not reinterpret their gates.
