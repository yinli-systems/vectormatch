# Measurement boundaries

## Current executable baseline

`CoreBenchmark` is a fixed-rate in-process experiment, not a network service capacity result. Every command is generated before timing. The loop records scheduled-to-complete latency, actual dispatch lag, and engine service time separately. It does not compensate a second time for coordinated omission.

The trace is 25% resting sell, 25% IOC buy against that maker, 25% resting buy and 25% valid cancellation. Every operation is expected to be accepted. Results include actual trade counts, an invariant check and deterministic replay state hash. It currently uses a shallow order book and is not representative of a deep, busy production market.

The first run was 60,000 commands at 20,000/s for three seconds on a developer Mac, while other builds were running. Its scheduled p99 was 203 microseconds, service p99 17 microseconds, and scheduling-lag p99 183 microseconds. These are initial observations, not stable capacity claims, and the three-second run is not a release benchmark. Re-run on isolated hardware with longer warmup, repeated trials, deeper books and varied sweep sizes before making comparisons.

## Local console

Server latency is cumulative service time for local journal `force(true)` and engine execution, or gateway-to-quorum commit plus mirror update in replicated mode. It excludes browser latency and gateway writer queue. Browser RTT is measured independently and includes browser, HTTP/network and server processing. Neither live telemetry series is a load-test result.

## Other executable experiments

- [HTTP arrival-rate generator](../bench/HTTP_LOAD.md): fixed arrivals for new orders, with dependent cancellations and explicit unsent/unknown accounting. It currently accepts only the local journaled backend and loopback URLs. Its lifecycle workload can have zero trades.
- [Replicated experiments](../cluster/BENCHMARKS.md): real three-process Aeron, sync level 2, single-client baseline and paired one/four-client closed-loop comparison. The paired comparison validates after timing, preserves per-command traces and reports the observed tail-latency regression alongside throughput improvement.
- `scripts/verify-replicated-workbench.py`: functional HTTP, idempotency/conflict/cancel, authoritative snapshot/mirror check and durable PostgreSQL cursor observation. It is not a load test.

`evidence/index.json` supplies recorded results to the console. Missing metrics are null, not invented zeros. Raw JSON, traces, histogram logs and limitations live beside the evidence index. Different measurement scopes must not be compared as if they measured the same path.

### Cloud workbench through an SSH tunnel

The workbench verifier accepts an optional third positional argument:

```sh
python3 scripts/verify-replicated-workbench.py \
  http://127.0.0.1:18001 reports/local/cloud-workbench deployment-manifest.json
```

Keep the HTTP URL loopback-bound and forward it to the authorized remote gateway
with SSH. The manifest must contain exactly these fields:

```json
{
  "scope": "Runpod 3 Pods private UDP; workbench reached through an SSH tunnel",
  "clusterMemberCount": 3,
  "clusterPrivateIps": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
  "physicalHostIsolationVerified": false,
  "gatewaySharesClusterMember": true,
  "postgresSharesClusterMember": true,
  "networkEvidencePath": "evidence/udp-pairs/index.json"
}
```

Use the real IPs, layout and evidence reference. These are caller-supplied
topology metadata, preserved with that provenance in the summary. The verifier
does not inspect provider placement, establish physical host independence, or
open the referenced UDP artifact. Its cloud `independentMachines` is `null` even
if the caller declares `physicalHostIsolationVerified: true`. It still checks
that the actual HTTP backend reports `CLUSTER_REPLICATED` and is writable, then
performs the same order, replay, balance and PostgreSQL observations. Without a
manifest it retains the original local single-host scope and limitations.

## Required release campaign

Separate core, local network, replicated durability and market fanout campaigns. Preserve planned/first-send/retry/reject/known-result/unknown counts; histogram sample sizes; per-second resource use; commit; exact JDK/dependencies; workload seed; durability flags; hardware and cost. At least three repeated stable trials and a separate failure timeline are required. Timeouts must be reconciled by the same business identity, never counted automatically as unexecuted.
