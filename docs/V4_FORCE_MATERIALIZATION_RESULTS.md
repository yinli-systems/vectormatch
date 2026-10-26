# File materialization: standalone force(true) screening

Both predeclared A/B/A/B screening pairs pass. Across all six matched writer comparisons,force p99 is11.80–21.23% lower with no worse per-thread workload duration. This is a standalone filesystem result,not an improvement in trading latency.

| Arm | Writer | Preparation | Force p99 ms | Force total s | Full work s | Setup ms |
|---|---:|---|---:|---:|---:|---:|
| C1 | 0 | sparse | 6.076041 | 10.455559 | 10.494863 | 1.628601 |
| C1 | 1 | sparse | 5.898713 | 10.257929 | 10.296901 | 1.253925 |
| C1 | 2 | sparse | 5.861303 | 10.358712 | 10.396649 | 1.168017 |
| D1 | 0 | materialized | 4.873395 | 8.808519 | 8.846110 | 34.173690 |
| D1 | 1 | materialized | 4.904144 | 8.938832 | 8.974872 | 39.498430 |
| D1 | 2 | materialized | 4.925774 | 8.859086 | 8.893460 | 38.906916 |
| C2 | 0 | sparse | 5.469778 | 9.955719 | 9.985767 | 1.767560 |
| C2 | 1 | sparse | 5.698015 | 9.958498 | 9.988372 | 1.212796 |
| C2 | 2 | sparse | 5.413758 | 9.869063 | 9.899767 | 1.147756 |
| D2 | 0 | materialized | 4.745766 | 8.707097 | 8.742679 | 28.274878 |
| D2 | 1 | materialized | 4.488539 | 8.525814 | 8.557439 | 35.331538 |
| D2 | 2 | materialized | 4.774975 | 8.728196 | 8.760134 | 31.775217 |

On the same prepaid CPU and overlay filesystem,each arm starts one new JVM with three threads and three128MiB files. Controls use RandomAccessFile.setLength;candidates write the complete file with zeroes. Each initialization force(true) and directory force completes before timing. Each writer then performs3000 consecutive4KiB writes,each followed by force(true),with identical deterministic payloads. No JFR,cluster,network or client window is involved. Setup allocation/warmup effects belong to the candidate;this does not isolate device firmware or physical-media latency.

All36000 raw force samples and corresponding write samples were independently recomputed from complete CSVs,including monotonic ordering,counts,totals,p50,p99 and maxima. The expected SHA-256 of each entire128MiB file was independently reconstructed in Python from the payload formula and zero tail;all12 Java full-byte readback results match. Ready-state stat records establish sparse versus fully allocated files. Every original member,mode,owner and directory was reviewed on CPU and after full local collection,then every published Git body was verified against the pushed private revision.

The prospective criterion requires at least10% lower force p99 for every writer and no worse full-work duration in both adjacent pairs. Both pairs pass. These are closed-loop,unpaced synthetic file operations with only two repeats per configuration;they establish no statistical confidence interval,healthy order latency,capacity gain,physical crash durability or production certification. The console remains120 runs/44 cohorts:these filesystem probes are not trading benchmarks.

Next implement explicit fresh-first-segment preparation with pending/completed admission markers,refusal of existing or partial state,and cold-restart validation without rewriting existing data. Qualify the actual Linux source/artifact,then compare native control/candidate with identical sync2 and complete order/recovery audits. No default changes until that separate native comparison passes.

[Prospective source,protocol,config,class and local qualification](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/prospective-r1/PROTOCOL.md). Full original packages: [qualification](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/qualification-original-r1/README.md), [C1](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/c1-original-r1/README.md), [D1](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/d1-original-r1/README.md), [C2](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/c2-original-r1/README.md), [D2](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/d2-original-r1/README.md). [Complete derivation and private push proofs](../evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/summary-r1/RESULT.json).
