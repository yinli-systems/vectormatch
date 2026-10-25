# Exact-cut V4 stage diagnosis

Read-only derivation of all20 original privately verified point archives, unchanged artifact65c41d519ea7. Every request timestamp is checked in chronological order. These are distinct per-stage distributions; percentiles cannot be added or subtracted.

| Rate | Arm | Accepted/planned | Arrival → dispatch p99 ms | Submit → first physical call p99 ms | First call → positive return p99 ms | Positive return → reply p99 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1000 | C1 | 20000/20000 | 193.028 | 0.903 | 0.150 | 12.122 |
| 1000 | C2 | 20000/20000 | 193.324 | 1.150 | 0.179 | 12.028 |
| 1000 | D1 | 20000/20000 | 64.960 | 0.670 | 0.178 | 11.927 |
| 1000 | D2 | 20000/20000 | 64.593 | 0.419 | 0.163 | 11.919 |
| 2000 | C1 | 40000/40000 | 195.415 | 1.146 | 0.169 | 12.420 |
| 2000 | C2 | 40000/40000 | 191.025 | 0.914 | 0.164 | 11.925 |
| 2000 | D1 | 40000/40000 | 68.415 | 0.713 | 0.172 | 12.466 |
| 2000 | D2 | 40000/40000 | 69.013 | 0.927 | 0.164 | 12.783 |
| 4000 | C1 | 80000/80000 | 193.386 | 1.257 | 0.160 | 16.047 |
| 4000 | C2 | 80000/80000 | 207.578 | 1.350 | 0.163 | 12.629 |
| 4000 | D1 | 80000/80000 | 115.720 | 2.705 | 0.185 | 20.616 |
| 4000 | D2 | 80000/80000 | 79.903 | 1.535 | 0.156 | 14.127 |
| 500 | C1 | 10000/10000 | 178.916 | 0.547 | 0.174 | 11.998 |
| 500 | C2 | 10000/10000 | 173.306 | 1.793 | 0.178 | 11.835 |
| 500 | D1 | 10000/10000 | 57.439 | 0.413 | 0.180 | 11.586 |
| 500 | D2 | 10000/10000 | 58.686 | 0.343 | 0.178 | 11.893 |
| 6000 | C1 | 113280/120000 | 1546.253 | 1.391 | 0.170 | 13.996 |
| 6000 | C2 | 113105/120000 | 1536.601 | 1.240 | 0.176 | 14.035 |
| 6000 | D1 | 120000/120000 | 789.036 | 1.236 | 0.163 | 14.485 |
| 6000 | D2 | 120000/120000 | 682.518 | 1.399 | 0.164 | 14.027 |

At6000/s the PAUSE stage percentiles condition on accepted orders; their global all-arrival p99 remains undefined because originals were unsent. The short first-physical-call-to-positive-return interval measures local publication admission, not a remote network RTT. Its low tail does not prove that the network is fast or exclude replication/service/client observation costs after offer. Negative offer-code totals include maintenance and control operations. Aggregate process CPU cannot prove or exclude single-thread saturation.

The observed high-rate wait before dispatch and the earlier recorded maintenance-phase overlap motivate dispatcher work. Before changing read-bank ownership, the new [owner-poll A/B/A/B](OWNER_POLL_PROTOCOL_V4.md) isolates an already qualified, explicit owner-only setting. Both controls use CONTINUE, all node arguments remain identical, and actual constructed-owner settings must match the registration. No outcome is presumed.

[Full stage distributions, original private archive SHA/asset references and all analysis sources](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/owner-poll-r1/admission-r1/README.md). The first streaming-reader compatibility failure is retained alongside the corrected derivation.
