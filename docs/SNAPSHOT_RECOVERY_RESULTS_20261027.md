# Snapshot transfer ABAB and restore to new VMs

The opt-in bounded snapshot pipeline completed a same-state **serial / window32 / serial / window32** comparison. Both pairs reduced transfer duration by about **11.1×**. The same restored cluster then replayed an original request without duplicate execution and settled one fresh synthetic IOC. All three temporary VMs and attached resources were deleted after full private evidence verification.

This is a large canonical-read and backup-restoration result. It does not establish a trading-latency distribution, sustained throughput, production RTO or a physical-media fault result. The [previous 120-second cold-read failure](PHYSICAL_SOAK_RESULTS_20261027.md) remains in the historical evidence.

## Frozen comparison

Three new Azure managed VMs in France Central occupied provider-reported fault domains 2, 1 and 0. Each had 2 vCPUs/8GiB RAM and a new Standard SSD managed data disk, with caching `None`. All original state files were restored from the previous experiment's private, fully verified role archives and checked before starting writers. VM IDs and boot IDs differ from the source machines. The canonical state, funding and request sequences were preserved.

Servers used the exact previous frozen JARs, sync level 2, the `capacity-190k-v1` state profile, 2GiB heaps and fixed leader 0. Only the explicitly supplied client patch added the pipeline and comparison/restore probes. All four arms used that same client artifact; A invoked the unchanged serial method, B selected window 32. The client shared replica 0's VM and CPU. It was not the earlier cross-region generator. JFR streaming was absent in both policies; process counters and GC logs were retained. The runtime registration precedes the first timed read.

| Arm | Read path | Snapshot bytes | Duration |
| --- | --- | ---: | ---: |
| A1 | Serial | 38,786,721 | 160.040437 s |
| B1 | Window 32 | 38,786,721 | 14.386827 s |
| A2 | Serial | 38,786,721 | 159.908798 s |
| B2 | Window 32 | 38,786,721 | 14.424431 s |

Every returned byte sequence was retained and identical. All four full snapshot SHA-256 values were `583ad6397fc61a84fd150cabdc16a52ccb3da53ffde91ff665a316e4b0ea60e5`. Business sequence stayed 180,295; leader stayed 0 before and after every arm. The two speedup ratios are 11.1241 and 11.0860. These are two finite pairs, not statistical confidence intervals or a general performance guarantee. Connection setup and writing the returned snapshot to the evidence file are outside each transfer duration. The default read API remains serial.

## Restored business continuation

The following probe used window 32, with no state reset between comparison and continuation:

1. Read the complete canonical snapshot and compare it with the original backed-up bytes.
2. Retry original index 180,127, receiving its cached command result 180,295, and verify a second full snapshot is unchanged.
3. Submit fresh index 180,128, confirm one accepted one-lot IOC trade at 10,000 ticks, then verify the complete post-trade canonical bytes and invariants.

The final command sequence was **180,296**, and the final snapshot SHA-256 was `564886f3e157b1b032cdcbf4717acb3fd3cdf7acb9d41883c9e22d1575bf17ee`. A separate Python audit reads the archived binary snapshot prefix and checks checksums, all account balances, unchanged system asset totals and the exact counter increments. Buyer 1,000,132 gains one base lot and spends 10,000 quote units; seller 1,000,001 releases one reserved base lot and gains the same quote amount. Every other account is unchanged. This prefix audit is independent arithmetic, not a second complete matching implementation; native full canonical comparison covers the complete state.

The single fresh RPC took 17.680 ms. One RPC is not a p99 measurement. Provisioning and comparison took place before the fresh trade, so no recovery RTO is claimed. The test proves restored business continuation on new VMs/disks from the archived source state. It does not inject a physical media failure or establish power-loss flush guarantees.

## Reproduction and evidence

[The thin evidence index](../evidence/2026-10-27/azure-restore-r2/) contains all four comparison results, native recovery proof, independent account audit, source/class hashes, input-archive relationships, provider fault domains and cleanup verification. Complete node archives are private release assets 679740788, 679740786 and 679740812; the control/source archive is 679741542. Each asset was fully downloaded with authentication and checked against its SHA-256 and member manifest.

`SnapshotReadComparison NEW_DIRECTORY PORT_BASE EXPECTED_SNAPSHOT` performs the four read-only arms. `ColdRestoreProbe` accepts the explicit `-Dvectormatch.snapshot.read.window=32` selection while preserving its original serial default. Run `scripts/audit-snapshot-recovery.py ARCHIVE_FOLDER --expected-before-sha256 SHA256 --output NEW_REPORT` against the original private archive folder to reproduce the independent read/settlement audit. Five negative/positive parser tests cover checksums, altered asset totals, duplicate accounts, negative balances and unsupported versions. The pipeline's six transport tests and one actual three-JVM UDP regression also passed.

Resource-group deletion was confirmed at **2026-10-26 22:56:48 UTC**, before the registered 23:45 provider stop deadline. The student spending limit remained on; the incremental plan capped credit at $1 and cash authorization at $0. No final invoice amount is asserted. The prepaid Runpod CPU and its running continuity campaign were unaffected.
