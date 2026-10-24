# CPU pilot measurement contract

This independent cohort is **SINGLE_HOST_THREE_JVM_LOOPBACK_UDP**: three node
JVMs and the load JVM share the user-provided CPU Pod `4il7v4518ccogj`, hostname
`ed6c0673f5cb`. It establishes no cross-host UDP capability or independent
failure domains. The allowed 32 logical CPUs represent 16 physical cores;
no CPU affinity, governor, kernel or quota setting is changed by this harness.

Node and load use the exact deployed source
`433f02bebe2f3109ec363291fa562d5c509c0723`. Deployment file hashes are checked
again before launching. The pilot fixes leader 0, loopback hosts, port 23000,
sync level 2, node/load maximum heaps 2g, 350k state profile, SHARED node driver,
explicit node max park 1ms, requested receive buffer 131072, MTU 1248, NAK delay
1000ns and retry ratio 100. The load fixes **10,000 arrivals/s ×350,000 arrivals**,
128 logical workers, one multiplexed session/shared MediaDriver, Q64 per worker
(total FIFO8192), request timeout 2s, drain30s and scheduler lateness limit20ms.
Its actual pending capacity must be explicitly recorded as128.

Measured state, Aeron files and archive writes live under
`/opt/vectormatch-cpu/runs/<unique-job-id>/` on container **overlayfs**. A preflight
requires3GiB free there and in the archive destination, all topology UDP ports
initially free, exact hostname, Linux pidfd support and matching release bytes.
The live run stops its exact owned load if overlay free space falls below512MiB.
`/workspace` is FUSE and is used only for the final complete archive/control
records, never as measured local NVMe. Sync2 is a software setting, not proof
of hardware fsync latency or provider durability.

## Registration and one durable execution

`capacity.py` imports and its default draft do not use the network. From the
repository root, first review and register the unique immutable plan:

```sh
python3 -B runtime/cloud/cpu-20261024/capacity.py --job-id cpu-pilot-10000-w128-r1
python3 -B runtime/cloud/cpu-20261024/capacity.py --register --job-id cpu-pilot-10000-w128-r1
```

The registered plan contains the complete fixed configuration, exact paths,
controller SHA, source433 tool bytes/SHA, deployment receipt and separate frozen
analysis identity `31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f`.
Only after root has checked deployment/space and authorized execution:

```sh
python3 -B runtime/cloud/cpu-20261024/capacity.py --execute \
  --plan evidence/2026-10-24/runpod-cpu/registrations/cpu-pilot-10000-w128-r1.json
```

The controller is detached with a new session and redirected stdin/stdout so it
survives SSH disconnects. Exclusive control/job directory creation and a durable
launch-attempt record reject reissues. If submission times out, query this same
job ID; never create a replacement workload or new order identities:

```sh
python3 -B runtime/cloud/cpu-20261024/capacity.py --status --job-id cpu-pilot-10000-w128-r1
```

No GPU history, four-round precondition or old checked128-trial assumption is
used. This harness accepts exactly this one pilot; any capacity matrix must be
separately registered. It performs no automatic cleanup/prune or business retry
outside the existing load generator's same-key resolution protocol.

## Validation and complete evidence

Every node and owned collector/load records PID, `/proc` startTicks, complete
actual argv and NUL-terminated argv SHA. The source433 supervisor performs
pidfd-bound ownership checks before stopping; a changed identity is a failure,
never an excuse to signal an unrelated process. Nodes stop in `finally`, including
after startup, timeout, config, canonical or UNKNOWN failures. The harness never
uses process-name kills, broad process-group kills or unconditional SIGKILL.
Python3.8 does not expose the native Python pidfd APIs. On this pinned Linux
x86_64 host only, the CPU controller supplies a documented in-memory syscall
adapter (`pidfd_open=434`, `pidfd_send_signal=424`) to the unchanged supervisor.
A self-pidfd signal0 probe checks actual kernel/seccomp support before workload
launch; failure stops preflight. The actual native/adapter path is recorded.
There is no numeric-PID `kill` fallback. The syscall numbers come from the
[official Linux x86_64 table](https://github.com/torvalds/linux/blob/v6.6/arch/x86/entry/syscalls/syscall_64.tbl).

Before load, the official ClusterTool must show members0/1/2 with leader0 and
one term. Three read-only CnC collectors retain pre-load through post-validation
samples; the original source433 leader checker requires complete files and
consistent roles/term/election evidence. One1Hz telemetry collector covers all
three nodes and load on the same host (`lo`), avoiding three duplicate host scans.
Collector CPU/IO overhead is part of this disclosed observer-on configuration.
Sampled CnC cannot exclude transitions wholly between observations.
After the load JVM exits, the controller waits at most5s for complete post-load
samples from all three CnC collectors and telemetry before stopping them. Missing
post samples fail the trial; timing strings remain raw, with microsecond-normalized
UTC comparisons for Python3.8 compatibility with Java nanosecond timestamps.

The original source433 configuration verifier is preserved byte-for-byte.
Its historical load argv builder hardcodes `/opt/vectormatch`, so this CPU
controller explicitly replaces **only that builder in memory** with the registered
CPU Java/release/evidence paths. All existing supervisor/node startup, idle-role,
NAK, profile, transport and prepared-byte checks still run. Adapter mapping/source
SHA and reconstructed load argv are retained. Zero checked runs, absent actual
pending capacity, or any unsupported schema fails closed rather than skipping
validation. The prepared snapshot must match the preregistered deterministic
350k SHA `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`.

Strict pilot pass requires full canonical validation, valid scheduler timing,
all350,000 confirmed accepted and exactly zero not-sent, business rejection,
server error, initial unknown, final unresolved and late-scheduler counts.
Missing values, booleans and missing artifacts do not mean zero. The raw engine
retains typed UNKNOWN outcomes; an incomplete canonical result remains a failure.

After exact owned stop, all job files—including failure artifacts, original CSV,
backlog, binary snapshots, node/Aeron state, logs, configs, PID identities,
load result and collector data—are retained in a complete gzip tar under
`/workspace/vectormatch-cpu-archives/`. Original arrivals also receive the frozen
verified gzip/manifest. Every archived file is checked byte-for-byte by SHA and
size, and the whole compressed archive receives a SHA. Original overlay state
is preserved; root may explicitly move it after reviewing verified export. A
failed stop prevents a misleading complete archive and preserves the live state.

Retrieve the completed archive and run the independently pinned local streaming
analysis once, without rerunning the workload:

```sh
python3 -B runtime/cloud/cpu-20261024/capacity.py --collect \
  --plan evidence/2026-10-24/runpod-cpu/registrations/cpu-pilot-10000-w128-r1.json
```

Collection refuses existing evidence directories, verifies archive SHA and each
extracted file, rejects unsafe/duplicate archive entries, and runs the exact31e4
source files with its pinned Python identity. The command, stdout/stderr, exit
code and identity are archived alongside structured summary/CSV. Source bytes or
runtime changes fail closed. Failed/incomplete trials are analyzed diagnostically;
missing results never become successful capacity observations.

This35s finite pilot tests correctness and baseline validity. It is not a
throughput ceiling, sustained-load guarantee, production p99 SLA or comparison
with the earlier GPU Pod measurements. A later fixed-config rate/concurrency
matrix needs its own immutable plan, space check, complete raw evidence and
explicit interpretation of finite-window goodput, conditional/all-offered p99,
backlog, rejection and UNKNOWN.
