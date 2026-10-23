# Extended 90k capacity cohort — 2026-10-23

For this **64-client plus three-member replicated matching path**, **7,600 offered commands/s met the declared finite-window stability criteria twice; 8,000/s did not, twice**. Each boundary trial offered 90,000 commands from the same prepared state and fixed deployment. This brackets the observed transition for this client/window configuration between tested rates of 7,600 and 8,000/s. It does not establish a backend-only ceiling, a production SLA, or stability at every untested rate in that interval.

At 7,600/s, in-window goodput was **7,595.9467/s** and **7,594.8489/s**, with all-offered p99 **52.768010 ms** and **95.828644 ms**. Both accepted every arrival, with no unknowns. At 8,000/s, the first trial admitted 890 fewer commands and reached accepted-response p99 **576.183419 ms**; its all-offered accepted p99 is unavailable. The repeat accepted every command, but p99 was **407.244710 ms** and drain was **455.311 ms**, exceeding the **112.5 ms** finite-window drain limit.

All **11** trials passed correctness, source/configuration, scheduler-timing, and fixed-leader validation; **9** met the stability criteria. The cohort contains **864,000 offered arrivals**, **863,110 confirmed accepted commands**, zero business rejections, zero server errors, zero initial unknowns, and zero final unresolved results. Every accepted measured command produced one one-lot trade. Setup and warm-up are excluded from these totals. Final canonical state, asset arithmetic, outbox continuity, and leader/term checks passed even for the two nonstable load windows.

## All observations

All rows use **64 workers**, each with one synchronous in-flight command and a FIFO capacity of 64. Window goodput counts accepted confirmations before the planned arrival-window end; drain confirmations are excluded. p99 starts at the planned arrival, including scheduler and FIFO delay, transport, replication, matching, and any retries. Values below are rounded; [CSV](analysis/capacity.csv), [analysis JSON](analysis/summary.json), and [raw run directories](runs/) retain full precision.

| Run | Window s | Offered /s | Arrivals | Window goodput /s | All-offered p99 ms | Accepted p99 ms | Client not sent | Rejects | Unknown initial/final | Peak queue | Drain ms | Observed window |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| [x-screen-0800-w64](runs/x-screen-0800-w64/) | 30.000000 | 800 | 24,000 | 799.8333 | 10.363532 | 10.363532 | 0 | 0 | 0/0 | 1 | 8.591 | Stable |
| [x-screen-1600-w64](runs/x-screen-1600-w64/) | 30.000000 | 1,600 | 48,000 | 1,599.6667 | 10.325786 | 10.325786 | 0 | 0 | 0/0 | 1 | 13.385 | Stable |
| [x-screen-2400-w64](runs/x-screen-2400-w64/) | 30.000000 | 2,400 | 72,000 | 2,399.4000 | 11.324929 | 11.324929 | 0 | 0 | 0/0 | 1 | 4.766 | Stable |
| [x-screen-3200-w64](runs/x-screen-3200-w64/) | 28.125000 | 3,200 | 90,000 | 3,199.2533 | 12.498877 | 12.498877 | 0 | 0 | 0/0 | 1 | 9.410 | Stable |
| [x-screen-4800-w64](runs/x-screen-4800-w64/) | 18.750000 | 4,800 | 90,000 | 4,797.7067 | 16.658462 | 16.658462 | 0 | 0 | 0/0 | 1 | 10.143 | Stable |
| [x-screen-6400-w64](runs/x-screen-6400-w64/) | 14.062500 | 6,400 | 90,000 | 6,396.5867 | 24.602679 | 24.602679 | 0 | 0 | 0/0 | 40 | 11.425 | Stable |
| [x-refine-7200-w64](runs/x-refine-7200-w64/) | 12.500000 | 7,200 | 90,000 | 7,195.3600 | 35.897360 | 35.897360 | 0 | 0 | 0/0 | 55 | 6.040 | Stable |
| [x-refine-7600-w64](runs/x-refine-7600-w64/) | 11.842105 | 7,600 | 90,000 | 7,595.9467 | 52.768010 | 52.768010 | 0 | 0 | 0/0 | 153 | 7.856 | Stable |
| [x-confirm-7600-w64-r2](runs/x-confirm-7600-w64-r2/) | 11.842105 | 7,600 | 90,000 | 7,594.8489 | 95.828644 | 95.828644 | 0 | 0 | 0/0 | 357 | 14.081 | Stable |
| [x-screen-8000-w64](runs/x-screen-8000-w64/) | 11.250000 | 8,000 | 90,000 | 7,555.6444 | — | 576.183419 | 890 | 0 | 0/0 | 4,004 | 556.494 | Nonstable |
| [x-confirm-8000-w64-r2](runs/x-confirm-8000-w64-r2/) | 11.250000 | 8,000 | 90,000 | 7,830.1333 | 407.244710 | 407.244710 | 0 | 0 | 0/0 | 1,914 | 455.311 | Nonstable |

Client-not-sent counts are admission loss, not server rejection. “—” means the all-offered accepted percentile cannot be computed, not zero latency. Accepted-response p99 is conditional on accepted responses. Peak queue is the observed sum of worker FIFO depths, excluding in-flight commands. The latency plot also uses conditional accepted-response p99; inspect loss and all-offered-finite columns alongside it.

![Extended-cohort capacity observations](analysis/capacity.png)

[SVG](analysis/capacity.svg) · [Full CSV](analysis/capacity.csv) · [All validation/stability checks](analysis/summary.json) · [Telemetry analysis](analysis/telemetry-summary.json)

## Why the repeated boundary is comparable

The phases `extended-screen`, `extended-refine`, and `extended-confirm` record adaptive provenance. The analysis intentionally preserves phase groups. For the repeated-boundary statement above, the two 7,600/s trials have the same 90,000 arrivals and 11.842105263-second window; the two 8,000/s trials have the same 90,000 arrivals and 11.25-second window. All four share the same source, load artifact, fixed settings, prepared-state hash, worker count, queue size, and comparison fingerprint. Their different phase labels do not change those inputs.

The first 8,000/s trial failed all-arrival acceptance, the 95% in-window goodput rule, drain, and second-half backlog-growth checks. The repeat's in-window goodput fraction and backlog-growth threshold passed; **its drain check alone failed**. Its fitted second-half outstanding growth was 742.853 commands, below the 900-command tolerance, while its measured drain remained 455.311 ms. Thus zero losses in that repeat does not make it a stable window.

The declared rule requires at least 10 seconds, all offered commands accepted, no initial/final unknowns, at least 95% of offered rate confirmed inside the window, drain at most `max(100 ms, 1% of window)`, and second-half fitted outstanding growth at most `max(2 commands, 1% of arrivals)`, in addition to all validation checks. These finite-window thresholds allow small positive backlog drift. No p99 SLA was imposed to select capacity. The two 7,600/s p99 results differ substantially; report both, rather than choosing the faster repeat.

## Fixed source, state, and deployment

The [campaign](campaign.json), [deployment receipt](deployment.json), [configuration verification](configuration-verification.json), and [registered protocol](../../../docs/CAPACITY_CAMPAIGN.md) provide the recorded setup. This cohort's node and load code used one common immutable deployment:

| Identity | Value |
|---|---|
| Node and load-generator revision | `8b4bea3f37d623cd08f7c26ea4b5f6506fc3c5bd` |
| Node and load-generator release | `/opt/vectormatch/releases/8b4bea3f37d623cd08f7c26ea4b5f6506fc3c5bd` |
| Deployment archive SHA-256 | `f6dbda4354c000edb3b3250ab4867ddd005c9875758055cb2280972102a45034` |
| Prepared core snapshot SHA-256, all 11 trials | `bcd308591d3aef73744f7516977061afc170135ea773fd1bfcd182a57eaf7915` |
| Comparison fingerprint | `0642493bfc21f2eb3d23856c5f5ba1bdce48ee9db19141ab525598dbd805ccdc` |

Fixed settings were Aeron 1.53.3, Java 21.0.13, sync level 2, UDP MTU 1248 over private interface MTU 1300, port base 23000, node heap 1 GiB, load heap 2 GiB, SHARED driver/archive threading, default BackoffIdleStrategy, 131,072-byte UDP send/receive buffers, 128 maximum cluster sessions, outbox capacity 262,144, request timeout 2 seconds, drain allowance 30 seconds, and scheduler-lateness invalidation threshold 20 ms. Aeron's **test-only** appointed-leader setting selected member 0. Every trial's official pre/post members view and recorded CnC samples verified member 0 as leader, the other members as followers, ACTIVE module state, and unchanged leadership term **0**.

Each run used fresh isolated trial state. Preparation always funded 64 buyers with 900,000,000 quote units each, funded a seller with 180,000 base lots, placed one GTC ask at 10,000 ticks, and completed 100 warm-up one-lot IOC buys. Measured commands were independent one-lot IOC buys against that maker. Preparation did not scale with actual trial length, and its canonical SHA remained identical. The 90,000-arrival maximum retains at most 90,101 orders and 180,267 events including setup/warm-up, below the 100,000-order and 262,144-event bounds. No projector acknowledged the trial outbox; the original application's HTTP gateway, projector, and PostgreSQL were paused during measurements.

The generator offered arrivals on absolute monotonic deadlines, independently of replies, to round-robin bounded worker queues. Each worker still had one in-flight request, so service concurrency remained finite. The generator shared **member 2's Pod**. The three existing EU-RO-1 Pods had visible CPU-quota upper bounds of 5.1, 10.2, and 23.8 CPU equivalents for members 0, 1, and 2 respectively; see the [recorded topology](../runpod-network/summary.json). These are shared-container upper bounds, not dedicated-core guarantees. Physical anti-affinity is unverified, and ephemeral container disks plus sync level 2 do not establish host power-loss durability. No additional Pods were created; the project's total-budget guard remained $20.

## Scope and follow-up separation

This is a boundary for the observed **client, bounded queues, and replicated matching path together**. One-second process/cgroup/network telemetry and CnC counter observations are retained per node. Those counters are non-atomic; namespace and cgroup counters include shared activity. The response distribution and plateau do not uniquely identify CPU, disk, networking, batching, or client-window causes. A 64-client window can still be limiting, so these results must not be labeled the backend's intrinsic maximum.

Planned-arrival latency and window/drain durations use `System.nanoTime()` in one generator JVM. UTC timestamps locate evidence; clock synchronization and one-way latency are not claimed. API execute-start does not measure first wire offer. CnC sampling cannot exclude every between-sample transition; unchanged terms and official pre/post member output strengthen the sampled evidence. The final deterministic replay uses the same MatchingEngine implementation, supplemented by balance/order/event arithmetic; it is not an independent matching algorithm. Correctness after drain does not imply load-window stability.

Higher-rate windows are shorter because of the fixed 90,000-arrival bound. Only the 7,600/s and 8,000/s boundary points have two repetitions here; there is no long-run or statistical-confidence guarantee. The baseline and extended profiles have different seed funding, outbox capacity, prepared hashes, and deployment identities, so their points must remain separate curves. The [128-client follow-up](../runpod-capacity-128/) retains node deployment 8b4 but uses a separate load-generator artifact. Its new 64/128 controls require their own comparison group; do not silently merge them into this cohort.

## Recompute the archived cohort

From the repository root:

```sh
python3 -B scripts/analyze-capacity.py \
  --runs-dir evidence/2026-10-23/runpod-capacity-extended/runs \
  --output-dir /tmp/vectormatch-extended-recomputed \
  --campaign evidence/2026-10-23/runpod-capacity-extended/campaign.json \
  --plot
```

To reproduce a load point, first create separate fresh three-member state using the immutable deployment and exact settings above. Preserve per-node launch arguments, source/transfer receipts, official pre/post member output, CnC samples, telemetry, and all raw arrivals. On the generator host with Java 21 and the private topology configured, the first 7,600/s load invocation was equivalent to:

```sh
export VECTOR_CLUSTER_HOSTS=10.0.212.169,10.1.60.60,10.1.81.207
export VECTOR_CLIENT_EGRESS_HOST=10.1.81.207
export VECTOR_AERON_MTU_LENGTH=1248
VM_RELEASE=/opt/vectormatch/releases/8b4bea3f37d623cd08f7c26ea4b5f6506fc3c5bd
java --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED \
  --add-opens=java.base/java.util.zip=ALL-UNNAMED -Xmx2g \
  -cp "$VM_RELEASE/dist/cluster/lib/*" \
  io.vectormatch.cluster.RemoteCapacityExperiment \
  /opt/vectormatch/evidence/FRESH-EXTENDED-TRIAL \
  23000 7600 90000 64 64 2000 30000 0 20 extended-90k
```

The CLI does not provision or verify the node launch configuration by itself. Use fresh state and evidence paths, run the fixed-leader/configuration checks, and keep failed/invalid attempts before comparing any new point with this cohort.
