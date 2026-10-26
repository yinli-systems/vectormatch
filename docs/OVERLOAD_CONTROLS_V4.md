# Prospective 7k/8k overload controls

This registers two additional **finite overload diagnostics**, not an escalation of the passed-capacity claim. The exact-cut campaign's 6k/s failures remain failures. The anchored in-process endurance runner is a separate path and cannot qualify this replicated experiment.

The input parser now recognises explicit 7,000 and 8,000/s requests so the planner can produce their full bounds. **Both remain refused by the default resource profile.** The window remains 20 seconds. All codec-derived raw/writer/journal/file/RPC bounds, the 2.5GiB allocation ceiling and the 1GiB runtime free floor remain enforced. No refusal can be reclassified as a measured latency result.

The first qualification incorrectly expected the higher points to fit; its two failed tests and source are preserved. Actual 7k planning requires 2,771,546,418 bytes of allocated growth and 3,845,288,242 initial free bytes, exceeding the original growth cap. The 8k point additionally exceeds the 2GiB raw bound. Tests now verify the required refusal and equal bounds for both policies. A separately named storage profile is now qualified for these finite controls; it does not remove the actual free-space admission requirement or establish a performance result.

Prospective order on a quiet, unchanged CPU host is 7k PAUSE A1, CONTINUE B1, PAUSE A2, CONTINUE B2; then the same four arms at 8k. This explicitly tests overload after the previous capacity failure. Freeze one artifact, leader 0, sync 2, three 256MiB JVMs, base port 22000, batch 4, exact cut 1536, read-window 32, page 32, archive chunk 6144, original idle/owner policies and durability fences. No endurance, compilation, audit or unrelated load may overlap measurement. Every arm uses fresh state and a separate evidence directory; the arms are not one continuous lineage.

Preserve every planned arrival, queue/dispatch/pending interval, negative offer, rejection, not-sent and observed/final unknown. Report scheduled-arrival latency and in-window goodput. With any missing planned acceptance, all-arrival accepted p99 is undefined; conditional latency must be labelled. Both A/B pairs must improve without worse goodput or post-offer tails to support a performance claim. A mixed direction or failure is published unchanged.

Before running, qualify both policies on the new artifact and verify the original native/raw audit, replay and three-node cold-restore gates. Retain complete raw evidence privately and verify it before retiring stopped state. If current disk cannot admit a point, record the refusal and free only independently verified, fully archived experiment data. Do not lower the guard.

After finite diagnostics, a 30–60 minute replicated experiment still needs a continuous, replicated maintenance-journal anchor and bounded streaming source/evidence integration. Repeating 20-second fresh states does not satisfy it. This document supplies no measured 7k/8k or sustained result.

## Explicit finite overload storage profile

`-Dvectormatch.v4.capacity.resource.profile=overload-4g-v1` permits only the unsealed 7k/8k controls. The default remains `standard-v1`; unknown values, lower-rate combinations and sealed-read combinations are rejected. This changes the experiment's storage ceiling, not the business/state profile, arrival clock, deadlines, journal bounds or execution policy. It admits a maximum 3GiB raw envelope and 4GiB allocated-growth envelope; the exact calculated limit is still enforced at runtime and the 1GiB free floor is unchanged.

| Planned rate | Exact raw bound | Exact allocated growth | Required initial free bytes |
| --- | ---: | ---: | ---: |
| 7,000/s | 2,078,479,731 | 2,771,546,418 | 3,845,288,242 |
| 8,000/s | 2,368,347,117 | 3,082,525,261 | 4,156,267,085 |

PAUSE and CONTINUE calculate identical bounds. Tests cover default refusal, explicit profile admission, strict configuration selection, the forbidden combinations, initial free-space refusal and runtime enforcement of both exact allocated growth and the free floor. No cloud arm has been run on this new profile yet. A disk shortfall must stop launch; only independently verified stopped experiment artifacts may be retired to make space. The ongoing 100M native lineage must close before any other CPU measurement starts.
