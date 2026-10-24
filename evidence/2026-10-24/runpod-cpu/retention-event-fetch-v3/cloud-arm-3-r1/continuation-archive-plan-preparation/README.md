# Explicit closed-scope plan augmentation only

The unchanged R2 `build_plan.py` creates a fresh arm 3 or 4 plan after the actual raw root-review receipt closes. Its immediate-prior pair, freeze/upload and their execution scopes, private readback and archive root-review must already exist. Every actual current close attempt and the complete original collection remain present without exclusions. The R2 archive implementation and all scan/copy limits stay unchanged.

`augment_plan.py` then takes the actual builder plan SHA and only adds explicitly named closed directories to a new plan. It copies no evidence, scans no markers, runs no tests or business auditors, uses no network or Git, and never overwrites either plan or source. Its own body/freeze and the original builder plan/registration become pinned source singles in the resulting archive.

For arm 3, root requested three new full scopes: `event-git-interruption-recovery-r1`, `event-cloud-archive-root-review-preparation-r3`, and `event-cloud-arm-2-archive-root-review-execution-r1`. The actual arm 2 archive root-review itself is already the builder's `prior-archive-root-review`; do not replace it or create a duplicate. Snapshot only once these scopes and all builder-required prior 2 scopes actually close. The interruption recovery includes only the actual recovery receipt and saved empty lock, never the Git index contents.

For arm 4, select its actual closed immediate-prior archive-root-review execution and the same closed R3 verifier preparation explicitly. Add any further root-requested closed comparison/execution scopes by additional `--scope name=/absolute/source` arguments after they actually exist. No future scope is pre-snapshotted or invented. Earlier archived source-generation fields and failures remain unchanged.

Execute the unchanged R2 `archive.py --config /absolute/augmented/COPY_PLAN.json --config-sha256 ACTUAL_SHA` only after root selects the actual raw root-review SHA and authorizes that exact closed arm copy. Preserve the external attempt registration/completion; the independent archive verifier and private push are root work.
