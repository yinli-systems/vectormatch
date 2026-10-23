# Cloud testing: first campaign, USD 20 ceiling

The initial approved cloud testing budget is **USD 20 total**. No instances have been purchased by this project. Record the actual hourly quote, storage charges, start/stop times and exported evidence. Run a short campaign, then terminate unused resources after preserving evidence; stopped persistent disks can still incur charges. A benchmark process stopping does not stop a provider's billing.

The selected next campaign is now a real multi-host UDP lab: **3 × Hetzner CCX23 + 1 × CCX13**, with private networking and a spread placement group. The [exact rental and SSH handoff guide](HETZNER_LAB.md) supersedes the initial single-machine suggestion below. Its 12-hour estimate is USD 6.8724 before tax; 24 hours is USD 13.7448. Current account quota and stock must be confirmed in the provider console before purchase.

## First machine

Target Linux x86-64 or ARM64, 8–16 effective vCPU, 16–32 GiB available RAM, and roughly 100 GB of SSD. Prefer 16 vCPU / 32 GiB when the quote fits the budget. SSH, Python 3, outbound dependency downloads and loopback UDP must work. GPU performance has no role in these workloads. CPU isolation, storage sync latency and throttling matter more than the advertised host core count.

Use a provisional **USD 8 first-session allowance**, keep USD 12 for reruns or another host, and calculate maximum runtime from the actual compute plus storage quote. This is a spending plan, not a quoted price. Set a provider-side expiration or billing alert if available; do not assume the benchmark scripts enforce billing limits.

After connecting, transfer only the repository source at a recorded commit. Use an existing authorized SSH/deploy key for a private clone or a source archive. Do not copy GitHub tokens, local environment files, runtime databases, or unrelated workspace files.

```sh
python3 scripts/bootstrap.py
source scripts/env.sh
python3 scripts/cloud-preflight.py reports/local/linux-preflight.json
./gradlew check :bench:installDist
bench/build/install/bench/bin/bench 20000 30 reports/local/linux-core-20k
./gradlew :cluster:failoverSmoke
./gradlew :cluster:replicatedBenchmark
```

Run these sequentially. The first `check` skips real PostgreSQL integration unless `VM_TEST_PG_URL` is configured; label that explicitly or start the repository's PostgreSQL test instance first. Repeat stable benchmark trials after warmup, preserving every result rather than selecting the fastest trial. The replicated task launches three JVMs on one host and remains a process-recovery/loopback experiment.

PostgreSQL's server and `initdb` require an unprivileged OS user. A container whose SSH login is root needs a dedicated unprivileged execution user or an external test database before running the local PostgreSQL launcher. Do not treat a skipped database suite as verification.

`cloud-preflight.py` records affinity and cgroup limits, not just `os.cpu_count()`, plus JVM, commit/dirty state, filesystem and a small synchronous-write probe. Inspect `cpu.max` and `cpu.stat` for quota and throttling. The probe does not establish disk durability under power loss.

## Runpod constraints verified on 2026-10-23

- [Public port exposure](https://docs.runpod.io/pods/configuration/expose-ports): TCP and HTTP; UDP exposure is unsupported. The HTTP proxy adds intermediaries and is unsuitable as an invisible part of a low-latency transport benchmark.
- [Global networking](https://docs.runpod.io/pods/networking): documented as NVIDIA GPU Pods only, with a 100 Mbps inter-Pod network. The documentation does not establish Aeron UDP compatibility or suitable physical failure separation for this project.
- [Billing](https://docs.runpod.io/pods/pricing): storage can continue billing on stopped Pods; preserve evidence before deleting ephemeral storage.

A single CPU Pod can be useful for core benchmarks, three-process loopback tests (after validating loopback UDP), or HTTP load generation. Do not rent three CPU Pods assuming they form the private UDP network required by the current Aeron transport. The configured A40 SSH target returned connection refused during the initial read-only capability check; no remote benchmark has run there.

## Later independent-machine experiment

Use three Linux hosts with private bidirectional UDP, low and measured same-region RTT, and explicitly separate failure domains, plus a fourth load-generator host if budget permits. The current launcher binds all Aeron endpoints to loopback: a real host topology, bind/advertised addresses, access control and reachable MTU must be implemented and tested before deployment. Adding a larger CPU instance alone does not provide machine fault tolerance.

Measure warmup and steady state separately, fixed-arrival offered load and useful confirmed work, p50/p99/p99.9, unknown outcomes, queue depth, CPU throttling, RSS, GC, sync latency and network use. Retain an independent leader-kill timeline and verify final balances, order state, event continuity and replay hashes. Claim a capacity only after repeated trials remain correct and stable at that arrival rate.
