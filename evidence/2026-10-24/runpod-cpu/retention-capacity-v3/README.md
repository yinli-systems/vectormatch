# V3 continuous-arrival source: local functional pilot

Candidate: `4102446b333573efde2b33a0eb53a8177575bad5`, branch `codex/retention-capacity-v3`, based on maintenance candidate `475dcd7960251eccc3fd6c0e60d4026a1ad7da1d`. This directory preserves local validation; no cloud capacity run is represented here.

Each fresh three-JVM arm scheduled 6,400 arrivals at 500/s for 12.8 seconds, with W128 and a separate Q64 queue per worker. Maintenance pauses dispatch while the independent arrival clock continues. All 6,400 test orders were eventually accepted in each arm, with zero NOT_SENT, final UNKNOWN, business rejections or duplicate/out-of-range order IDs. Setup comprises three additional business commands and one seed order, excluded from arrival goodput. Each arm crossed three archive/event maintenance cycles, matched its physical-offer-order candidate reference, wrote matching snapshot hashes on all three replicas and stopped all owned node processes. These are two distinct lineages.

| Arm | Scheduler validity | All-arrival accepted p99 | Last known reply after window | Total source drain after window |
| --- | --- | ---: | ---: | ---: |
| Batch cap 1 | Invalid: five releases >20 ms late, maximum 26.335 ms | 22.353105125 s | 22.033167250 s | 23.308813375 s |
| Batch cap 4 | Valid under the registered 20 ms release-lateness check | 23.206070375 s | 22.877518416 s | 24.138843833 s |

Both arms completed only 239.765625 accepted orders/s inside the arrival window; eventual acceptance does not establish stable 500/s capacity. The substantial queueing and drain remain a performance problem. Cap 1 is an invalid timing sample, so these arms support no performance comparison or promotion. The reported percentiles include scheduled-arrival queueing and maintenance delays. There is no sustained capacity, zero-latency, independent-host, external-storage durability, persistent client recovery or 100M claim.

## Preserved evidence and independent audit

`validation/` is an exact byte/mode copy of all 38 frozen validation files, totalling 26,652,297 bytes. It retains both failed compilation attempts and their exact source ZIPs, the successful 24-test focused run, distribution preparation, the successful one-method native test containing both arms, and the complete stopped native archive. XML recounts are 24/24 and 1/1, with zero failures/errors/skips; this audit did not rerun tests.

The native archive contains 159 files, 26 directories and 2,489,645,465 logical bytes, compressed to 20,262,738 bytes. SHA-256: `f4e84b96d1757873e2902851a20ed2e937a736aa0a541266ceebd5d48f438c0c`. Independent streaming readback verified every complete file SHA/size/mode, every directory mode and exact path closure, including sparse zero bytes, without extracting the multi-GB tree. All 202 captured class ZIP entries match their manifests and corresponding runtime JAR class entries. All 119 archived source/docs files match candidate Git blobs exactly. The two native artifact inventories reconcile 328 loaded-artifact observations.

Exact pre-native artifact manifest SHA-256: `ec57923625e27966eed710b0e4b8a7b25867ba3bc8da22c0fbfc98af6e4375bb`. Native runtime fingerprint: `d5a52982151fc70bdb11ff305b45ac20b06661c731ec82fb9f707c066f61a378`; this actually loads cluster classes and the core JAR. The separately described distribution fingerprint is `e6243f4639af1cd35c3bbcb0b7ff0d10938320be8e2f1e0cb236ac9ef667dbb3`, with distribution manifest SHA-256 `8cab11ede5876515ff71047e74704d1601f3deea1d58cef2b199eed768bdd727`. `DirectBuffer` loads from Aeron-all; the separately inventoried Agrona JAR is not substituted into either fingerprint. These runtime identities are distinct and are both independently reproduced.

The four original review findings are addressed in the frozen source:

- `RetentionCapacityExperimentV3.java:86–90`: mandatory owner closure is independent of before/after receipt writes.
- `RetentionBatchOwnerV3.java:518` and `RetentionCapacityExperimentV3.java:233`: the owner captures final transport state before closing, and the tape validates accumulated leader/term events as well as current state.
- `RetentionBatchOwnerV3.java:462–463`: successful publication admission uses a fresh timestamp after the offer returns. It remains distinct from business acceptance.
- `RetentionCapacityPlanV3.java:125` and `RetentionBatchMaintenanceV3.java:97–98`: the prospective envelope includes 256 bytes per logical RPC timing row, with the same row maximum enforced when writing.

Run `python3 audit-local-evidence.py` from any directory to repeat the archive/artifact audit. It only reads evidence and writes its JSON report to stdout. `independent-audit.json` records the successful audit; `copy-receipt.json` binds the full copied inventory. The first audit attempt incorrectly assumed native `MatchingEngine` loaded from a class directory. Its source and assertion traceback are preserved in `audit-attempts/`; the corrected audit uses the observed core JAR layout and reconciles the raw native artifact inventories. No application source, compiled build output, test run, cloud resource or shared Git index was changed by this audit.

Root's separate independent CSV/timing analysis may be added alongside this preservation audit.
