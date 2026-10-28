# Pod autopilot

Unattended replicated-path pipeline for a single RunPod CPU pod. Three cluster replicas and the load source
run on one host over loopback, so nothing here is a physical failure-domain claim.

`autopilot.py` runs these stages, each in a fresh write-once root under `/opt/vectormatch-b/experiments`:

1. **sync0 sweep** (`sweep.py`): one physical core per node with 100 µs park (baseline); two cores with 100 µs
   or 1 µs park; and two cores with busy spin (`dataPathMaxParkNs=0` on the nodes, `driverMaxParkNs=0` on the
   source, which then gets two cores) — at 1000, 8000 and 20000 orders/s. Exploratory; every case is audited and recorded, none is selected.
2. **Pick**: lowest p99 at 8000/s among configurations whose 8000/s case passed every gate (else 1000/s,
   else the one-core 100 µs baseline).
3. **sync0 ABAB** (`campaign.py`): baseline vs pick at 8000/s under the registered selection rule. The ladders
   use the pick only if it is selected; otherwise they use the baseline.
4. **sync0 ladder** (`ladder.py`): 1K → 50K orders/s. sync0 is Aeron Cluster's default durability (majority
   replication, no per-write force), the closest match to published vendor round-trip benchmarks.
5. **Durable ladder**: consensus and catalog sync2, recording data sync1, initialized segments; 1K → 12K/s.
6. **Summary**: `SUMMARY.md` / `SUMMARY.json` after every stage, marking which rungs meet the production target
   (p99 ≤ 5 ms and p99.9 ≤ 20 ms) as well as the registered 25 ms gates.

`autopilot.py STAGING abab:A:B` skips stages 1–2: it confirms configuration B against A by ABAB and runs the
ladders on the winner.

Ladder rule: the first rung that fails its gates stops escalation and is repeated once. Rungs whose stage audit
refuses the stream (for example orders the source could not send) are still recorded from `samples.csv`.

## Files

| File | Role |
|---|---|
| `autopilot.py` | Orchestrator; CPU layout from `VM_LAYOUT`: `one` and `two` (four sets each: three nodes, then source) and `spinSource` (the busy-spin source's cores) |
| `campaign.py` | Launch, audit and ABAB selection controller; per-case `cpuSets`, `jvmExtra`, `sync` and `auditMode` |
| `sweep.py`, `ladder.py` | Sweep and ladder runners on top of `campaign.py` |
| `setup_b.py` | Creates a campaign root from a verified runtime (`VM_RUNTIME`, `VM_CPUSETS`) |
| `patch_runtime.py` | Derives a runtime whose cluster jar differs only by classes compiled from given sources |
| `pin_threads.py` | Thread-level CPU isolation while a case runs (cases with `pinThreads`); tested by `scripts/tests/test_pod_thread_pinning.py` |
| `fsync_floor.py` | 4 KiB append + `fdatasync`/`fsync` latency on the pod's root filesystem |

## Thread pinning

Busy-spinning agents are preempted whenever another thread of their JVM (JIT, JFR, Aeron client conductor,
VM housekeeping) is scheduled onto the same CPU, which costs a scheduler slice of a few milliseconds and
shows up as the p99 tail. With `pinThreads` the controller runs `pin_threads.py` from the moment the nodes are
ready until the case stops. Every 0.5 s it gives each data-path agent (node: media driver, archive,
consensus, service; source: media driver, response loop, arrival clock) its own CPU, lets GC workers use the
JVM's whole set, and confines every other thread to the housekeeping CPUs. Agent CPUs are sticky and handed
out in thread-creation order; the launcher's primordial thread is never an agent; an agent with no free CPU
is confined to housekeeping and reported. Every decision goes to `thread-pinning.jsonl` in the case
directory, and a summary goes to `<case>-THREAD_PINNING.json`.

## Running on a fresh pod

The runtime is the hash-verified replicated-path-probe candidate (`CANDIDATE.json`) plus Aeron 1.53.3 and
Agrona 2.6.1 from Maven Central, run on Temurin 21.0.13+9. On the pod:

1. Install the JDK under `/root/tools/jdk-21.0.13+9` and check `bin/java` against `javaBinarySha256`.
2. Restore the candidate runtime to `/opt/vectormatch-b/runtime` and verify every file hash.
3. `patch_runtime.py runtime runtime-r3 ... PendingReplies.java MatchingClusteredService.java`, then
   `patch_runtime.py runtime-r3 runtime-r4 ... ReplicatedPathProbeNode.java`, then
   `patch_runtime.py runtime-r4 runtime-r5 ... ClusterNodeMain.java ClusterClient.java ReplicatedPathProbe.java`
   (sources from this branch; the autopilot runs `runtime-r5`).
4. Map the pod's cpuset to complete physical cores (both hyperthreads), preferring same-L3 pairs per node, then:

```bash
VM_LAYOUT='{"one": [[67,163],[15,111],[22,118],[78,174]], "two": [[67,71,163,167],[15,31,111,127],[22,61,118,157],[78,174]], "spinSource": [78,95,174,191]}' \
  setsid nohup python3 autopilot.py "$PWD" run > autopilot.out 2>&1 < /dev/null &
```

Progress is appended to `experiments/autopilot-<stamp>/AUTOPILOT.log`; each stage root keeps its own
`PROGRESS.log`, per-case audits and raw evidence.
