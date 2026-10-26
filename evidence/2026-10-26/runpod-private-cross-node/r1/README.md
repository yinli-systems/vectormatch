# Native private-UDP cross-node evidence, 2026-10-26

Completed: three actual matching replica Pods, a separate load Pod, actual leader
JVM failure/rejoin/snapshot/cold continuation, six original capacity trials and four
single-factor tuning arms. All data is synthetic. All four active roles and the
provider-initialization-failed predecessor are stopped at $0/hour. Existing prepaid
CPU and unrelated workloads were preserved. Conservative cost: $2.062 of $3.

[Full report](../../../../docs/PRIVATE_CROSS_NODE_RESULTS.md) describes every scope
and limitation. The six original capacity arms all accepted their planned requests;
the separate tuning A1 lost three arrivals at client admission, so its all-offered
p99 is undefined. No unknown is silently counted as rejection. Ten trials contain
490,000 planned requests and 489,997 accepted. Both registered gates pass at 4,000/s;
8,000/s tails vary. The candidate is not promoted. No sustained capacity, physical
failure domain, continuous 100M lineage or funded venue readiness is claimed.

- `CAPACITY_REGISTRATION.json`, `TUNING_REGISTRATION.json`: original parameters/gates.
- `CURVE_PROGRESS.json`, `CURVE_COMPLETE.json`: original observer output, including
  its initial misclassification of the uncollected last run after SSH failure.
- `CAPACITY_8000_R2_RECOVERED.json`: original remote Java run completed successfully;
  recovery did not rerun workload or replace the original failed observation.
- `INDEPENDENT_AUDIT.json`: recomputed original rows/counts/p99/configuration for six
  capacity arms, plus exact auditor/reference source hashes.
- `TUNING_INDEPENDENT_AUDIT.json`: all four original A/B/A/B arms, raw-row hashes,
  paired decision, whole-lifetime CPU scope and private-shaper counter observations.
- `FAULT_EVENTS.jsonl`, `FAULT_VERIFIED.json`: actual faults and complete state/new
  trade checks. Functional client shares replica Pod 1; fault between writer phases.
- `PODS.json`, `STOPPED.json`, `STOPPED.jpg`, `FINAL_COST.json`: exact resources,
  stopped state, privacy-scoped screenshot and conservative quoted-rate estimate.
- `AUDITOR_LINUX_TESTS.json`, `TARGETED_TESTS.json`: seven new tests on actual Linux,
  seven locally plus 38 existing analyzer tests. No new full-suite/hosted-CI claim.
- `LATEST_HOSTED_CI.json`: checked commit and hosted job outcomes; both jobs have
  zero executed steps. This is not evidence of a code-test failure or a green run.
- `DELIVERY.json`: immutable private attachment IDs, sizes and complete SHA-256.
- `collection/`: all-member node inventories and local verification proofs.
- `CONTROLLER_MEMBERS.json`: exact controller attachment file inventory.
- `REPRODUCE.md`: authenticated private downloads and offline auditor commands.

The draft private release is `evidence-private-20261025`, release ID `423510304`.
Raw assets: `677650661`, `677650668`, `677650665`, `677650662`; controller/source
asset: `677682130`. Four raw archives total 110,845,335 bytes and 988 members;
the 4,987,604-byte controller attachment adds 242 members. Every uploaded byte was
fully authenticated-downloaded and every archived member was independently hashed.
These bulk attachments stay outside Git history. They exclude SSH private keys,
API keys, preflight HMAC keys and unrelated account/UI data. The cropped screenshot
contains only this round's five stopped instance records.
