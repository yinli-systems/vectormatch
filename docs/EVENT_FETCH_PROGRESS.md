# Event Fetch16/32 candidate

The candidate on `codex/event-fetch-page-v3`, source commit `d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8`, adds an explicit V3 event page of16 or32. It remains a candidate; default page16 and owner1ms remain unchanged on main. Both arms must run the same new installed JARs, including their UTF8 validation cost.

| Evidence | Actual result | Qualification |
|---|---|---|
| Final local Java tests |47 distinct tests,0 failures/errors/skips |Includes the initial4 codec tests; not51 tests |
| Local installed-JAR metadata |PASS |One compiler/helper attempt; no application/native session |
| Linux installed-JAR metadata |PASS |One actual metadata JVM; observed full argv/start/executable, normal exit and a separate strict PID-absence check |
| Strict LONG raw-parser guards |42 PASS |Synthetic codec/phase/configuration checks; no actual new native raw audit yet |
| Native16/32 comparison |Pending |No measured throughput, p99 or improvement claim |

Actual local and Linux fingerprint: `87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa`. Seven observed classes use three distinct JAR origins; all four distribution-JAR bodies are preserved. Both actual Plans admit33792 arrivals@500/s over67.584s with cap4/chunk6144/read8 and the same185514924B raw/757122377B allocated-growth budgets. The prospective selected event-RPC upper bound is4225 for page16 and2113 for page32. Actual runtime RPC counts remain unmeasured.

The maximum tested32-event reply with128-byte UTF8 details is6763 application bytes,6795 including the Aeron header, within the existing complete-message envelope. The strict parser requires every full request to use the selected page and permits the exact final partial page. It binds complete event prefixes, physical callbacks,13 CSV columns, earliest owner reply, four possible offers, eight read credits,24 ordered phases, force-before-ACK and UNKNOWN outcomes. The CPU scheduler gate remains strict by default. The retained synthetic binary fixtures are clearly labelled and do not substitute for JVM-captured wire evidence.

The planned comparison is16/32/16/32 on the existing one-host CPU Pod, fixed leader0, sync2, ports42000, owner1ms and server/driver100us. Its first page16 arm must establish this new artifact's native functional qualification through full raw/canonical/three-snapshot verification before page32 can proceed. Previous2358 artifact native results cannot qualify87a7. Each later arm requires the preceding full collection/root/private-push gate. This remains one host with loopback UDP, not three independent machines or a connection-scale test.

The previous owner-poll ABAB produced opposite pair directions: p99+0.44% and−5.71%, with unchanged finite-window goodput. It did not establish a repeatable benefit; owner1ms remains the control. See [the full owner-poll results](OWNER_POLL_RESULTS.md).

The post-metadata cloud free-space observation was2115571712B,505161B below the unchanged2116076873B single-arm reserve. No new arm was launched on that observation. Archive/restore-verified retirement of already closed synthetic native copies is a separate step; original application and PostgreSQL data remain protected. The current CPU resource uses the user's existing free/prepaid quota; no new resource was created.

Raw sources, both local guard attempts, the actual local/Linux metadata executions and independent reviews are in [metadata-and-parser-r1](../evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/metadata-and-parser-r1/README.md). The47 tests and installed JARs are in [local-unit-validation-r1](../evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/local-unit-validation-r1/README.md). No100M cumulative orders,100M orders/s,100M connections, hard-real-time or zero-latency result is claimed here.
