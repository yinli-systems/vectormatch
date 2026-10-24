# Event-fetch ABAB presentation preparation

This scope contains source preparation only. No exporter, benchmark, business auditor,
SSH, JVM, Git mutation, or live index update is executed by this preparation.

The existing `web/src/Evidence.tsx` card and drawer already support all necessary
fields. Keep that renderer unchanged. Append four distinct `cpu-event-fetch-*`
records to the evidence ledger after all four observations and the root comparison
are closed and privately pushed. Keep the existing 21 run objects and all capacity
objects unchanged. The event-fetch experiment is not a capacity curve.

Each card identifies event page 16 or 32 and A1/B1/A2/B2. Show window goodput and
scheduled-arrival-to-reply p99 from actual strict raw evidence. The drawer records
the actual 12-cycle maintenance wall total, logical FetchEvents and total logical
maintenance RPC counts, sampled backlog and every failure counter. Never sum
overlapping per-RPC elapsed times as wall time.

All four runs must execute source `d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8`,
release `0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59`,
four-anchor code fingerprint
`87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa`.
Page order is 16/32/16/32; owner maximum requested park is fixed at 1ms, driver
at 100us, read window at 8, batch cap at 4 and archive chunk at 6144 bytes.

The exporter requires a SHA-pinned root manifest with schemaVersion 1,
scope `ROOT_VERIFIED_EVENT_FETCH_ABAB_UI_INPUTS`, passed true:

```json
{
  "schemaVersion": 1,
  "scope": "ROOT_VERIFIED_EVENT_FETCH_ABAB_UI_INPUTS",
  "passed": true,
  "comparison": {"path": "ACTUAL_FINAL_COMPARISON_PATH", "sha256": "ACTUAL_SHA"},
  "comparisonRootReview": {"path": "ACTUAL_FINAL_ROOT_REVIEW_PATH", "sha256": "ACTUAL_SHA"},
  "arms": [
    {
      "arm": 1,
      "archivePath": "evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-1-r1",
      "closedSha256": "ACTUAL_SHA",
      "inventorySha256": "ACTUAL_SHA",
      "archiveRootReview": {"path": "ACTUAL_PATH", "sha256": "ACTUAL_SHA"},
      "collectionGate": {"path": "ACTUAL_PATH", "sha256": "ACTUAL_SHA"},
      "privatePush": {"path": "ACTUAL_PATH", "sha256": "ACTUAL_SHA"},
      "privateGitReadback": {"path": "ACTUAL_PATH", "sha256": "ACTUAL_SHA"}
    }
  ]
}
```

The example is a contract, not a populated receipt. The real `arms` array must
contain all four ordered arms and actual hashes. Root comparison review must have
passed true, allFourArmsReviewed true and comparisonSha256 equal to the actual
four-observation COMPARISON.json. Each arm must have an actual full archive review,
private push receipt and actual full Git blob readback receipt. Arms 1 through 3
also bind their real next-arm collection gates. Arm 4 must omit `collectionGate`:
there is no next-arm gate to manufacture. Its actual finalized collection,
strict raw/root review, full archive review and private push/readback directly
qualify the final presentation input. Existing receipt schemas are reused and
exact archive/collection/raw/source hashes are reconciled. Receipt path pins may
use absolute paths; `archivePath` uses the real repository-relative evidence path
that is already recorded by the private push receipt.
The exporter reads only selected reviewed JSON inputs; it relays prior full-archive
proof rather than claiming to run another raw/native audit.

Run only after those receipts exist, with fresh output and receipt paths. It writes
a derived index copy rather than modifying the live index. Root can inspect that
copy, copy the approved result to `evidence/index.json`, verify the local passive
HTTP/browser presentation, and archive the exporter, input proof manifest,
before/after index, derivation receipt, browser observations and final report.

No unit tests are added for this reversible presentation update. Before use,
perform syntax inspection; then verify the one actual export result against all
four real observations. Preserve any failed derivation output and diagnose it
separately. Do not synthesize fixtures as benchmark evidence.
