# Client-order index startup sizing experiment

Registered after the16 isolation/collector arms and before any sizing performance point. The paired250K ZGC maxima align exactly with client-index threshold786433; see [diagnostic evidence](PROCESS_ISOLATION_RESULTS.md).

The candidate adds an explicit nonnegative expected-retained-orders hint, bounded by the existing retention limit. Existing constructors retain default sizing. A positive hint uses Java21 HashMap.newHashMap(expected); its table is allocated by setup orders before the arrival origin. No keys, terminal orders, cached results, ledger state, fills, snapshots or dedup semantics are removed. The hint is an allocation choice and is not serialized as business state. Memory footprint and startup cost may increase; the heap ceiling is unchanged. This candidate is opt-in, not a new production default.

After the ongoing three-replica endurance and cold-restore experiment fully closes, qualify12Java tests on the existing CPU (including snapshot byte identity, duplicate safety, retention-capacity rejection and an actual child JVM receiving the hint), then3Python independent financial-auditor tests and two1000/s functional runs. Run100K and250K each in A1/B1/A2/B2 order for5seconds, seed73439. A uses lazy sizing; B requests count+1025 retained entries. Both use independent source/controller G1 and business Generational ZGC, same8CPU affinity,1GiB source heap,1–3GiB business heap,8192credits,64batch ceiling and same loopback TCP code. One immutable candidate serves both arms.

Report all planned/sent/replied/accepted/rejected/not-sent/unknown counters, full-stream p50/p99/p99.9 only if every original is accepted, exact backlog peaks, source timing, business-local call durations, GC and CPU. Both matched pairs must remove missing acceptances and pass timing/goodput gates to establish a repeatable finite capacity improvement. Failed arms stay archived. Five-second improvement never proves30minute250K/s endurance or replicated capacity.

Raw assets are privately archived and downloaded in full for SHA verification before closed duplicate retirement. Never overlap native benchmark groups. Keep the prepaid CPU running and stop only owned test processes.

## Local reproduction

Build `:bench:comparisonInstallDist` with Java21, then run each point with a fresh output path:

```sh
scripts/run-process-isolation.sh ISOLATED GEN_ZGC false 250000 5 73439 /tmp/vm-sizing-a1
python3 scripts/audit-process-isolation.py /tmp/vm-sizing-a1 --output /tmp/vm-sizing-a1-audit.json
scripts/run-process-isolation.sh ISOLATED GEN_ZGC true 250000 5 73439 /tmp/vm-sizing-b1
python3 scripts/audit-process-isolation.py /tmp/vm-sizing-b1 --output /tmp/vm-sizing-b1-audit.json
```

Repeat A then B with new a2/b2 directories. Set the same `VM_COMPARE_CPUSET` on Linux for all arms. The launcher removes inherited JVM option variables and fixes the source heap/collector; the actual business child flags and original outputs remain recorded. The frozen remote campaign additionally captures process CPU/IO, executable hashes and authenticated raw-archive receipts.
