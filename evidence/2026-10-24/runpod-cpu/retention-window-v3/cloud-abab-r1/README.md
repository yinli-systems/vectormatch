# CPU maintenance read-window ABAB

Increasing the bounded read window from 1 to 8 reduced all-arrival p99 by **84.62% and 83.98%** in two ordered comparisons. Complete maintenance wall time fell **83.45% and 82.80%**. Arrival-window confirmation goodput stayed unchanged.

| Arm | Read window | All-arrival p99 | Complete maintenance wall time | Confirmed inside 12.8s | Window goodput |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 | 1 | 5.032984288 s | 10.615118901 s | 6,141 / 6,400 | 479.765625/s |
| B1 | 8 | 0.774253656 s | 1.756311306 s | 6,141 / 6,400 | 479.765625/s |
| A2 | 1 | 5.055624496 s | 10.628120071 s | 6,141 / 6,400 | 479.765625/s |
| B2 | 8 | 0.810148792 s | 1.828364500 s | 6,141 / 6,400 | 479.765625/s |

Each arm eventually confirmed all 6,400 distinct planned orders. Each has zero notSent, rejected, UNKNOWN or invalid scheduler arrivals, 1,298 logical maintenance RPCs, three complete maintenance cycles, and six read phases. Original requests, callbacks, offer results, per-arrival CSV, archived prefixes, exported events, exact reference execution, all three snapshot logs, and complete stopped native files were checked. The wire-observed positive-offer-to-first-callback overlap reaches exactly 1/8. Retained read-bank credit bounds additionally rely on source enforcement and runtime attestations; consume timestamps are not independently logged.

The selected window is the experiment factor. Both arms use the same four JARs, profile, common eight-slot resource envelope, business batch cap 4, archive chunk 6144 bytes, event fetch 16, 128 workers, queue 64 per worker, appointed leader 0, MTU 1248, and Archive/catalog/consensus sync level 2. The code fingerprint is `b148bbd416beca0c63ec10a2921a7709f1e82e8f3263604c930d5d901367117b`; source is `0f7eb2e7f6409a81b9a816fdb3142941d1850013`. The release and full process arguments are preserved in each collection.

This uses one existing shared CPU host, three JVMs and loopback UDP. Each arm is a separate lineage scheduling 500 orders/s for 12.8 seconds, with two full command-prefix cuts and a trailing partial cut. All four lineages together are **not** one cumulative-order proof. The fixed order is A1/B1/A2/B2, with no randomization, confidence interval or host-exclusivity guarantee. The percentiles remain separate; they are never pooled. Neither unchanged window goodput nor outstanding replies at the exposure boundary proves sustained 500/s capacity or an instability threshold. Independent storage durability after Pod stop remains unproved.

In [round 1's independent raw analysis](round-1/root-raw-comparison/README.md), arrival-to-dispatch p99 falls from 5.025 to 0.766 seconds; post-positive-offer reply p99 is 16.73/11.18 milliseconds. The large delay is therefore observed before dispatch during serialized maintenance. Business frames increase from 4,245 to 5,873 because shorter queues fill fewer batches; all still bind to exactly 6,400 orders, with no extra successful physical admission or duplicate execution. RPC elapsed intervals overlap in window 8, so their sum is not a wall-time measurement. The table uses the complete cycle receipts.

[Machine-readable results](comparison/results-archived.json) retain exact per-arm metrics and input SHA-256 bindings. [The derivation](comparison/derive.py) reproduces them directly from this checked-in evidence, without a live machine or the ignored runtime directory:

```sh
python3 -B evidence/2026-10-24/runpod-cpu/retention-window-v3/cloud-abab-r1/comparison/derive.py \
  --evidence-root evidence/2026-10-24/runpod-cpu/retention-window-v3/cloud-abab-r1 \
  --output /tmp/vectormatch-window-abab-new.json
```

The output must be a new file. [The independent runtime-derived results](comparison/results.json) produce exactly the same metrics; both derivations and their source hashes are retained. [Round 1](round-1/CLOSED.json) and [round 2](round-2/CLOSED.json) retain full compressed outer/native payloads, selected raw files, source and strict native/raw audits, clean-stop identities, and independent root full-member byte/owner/mode/empty-directory reviews. Failed guard and root-review attempts remain archived. No private keys, original PostgreSQL data or API credentials are included.
