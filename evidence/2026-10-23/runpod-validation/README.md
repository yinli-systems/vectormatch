# Local regression validation, 2026-10-23

These are macOS local unit and integration results for the recorded source manifest, including the pending bounded ClusterClient bootstrap fix. They are not Linux cloud performance or physical-machine availability evidence. Existing local live services were not restarted.

`gradle-check.log` records a fresh `check --rerun-tasks` with the existing local PostgreSQL database and explicit `vectormatch` role. `junit/` preserves each module's raw JUnit XML, and `test-summary.json` counts tests, skips, failures, and errors. Python verification is recorded separately in `scripts-tests.log` (19 tests) and `deploy-tests.log` (13 tests). Seven shell files passed `bash -n` (`bash-syntax.log` is empty on success).

The new three-process bootstrap test uses sync level 2 and MTU 1248. It kills the original leader, immediately creates a fresh client, replays a confirmed identity, submits a new cancellation, and compares the canonical state hash while the killed process remains down. It also verifies one shared 20-second all-members-unavailable budget and interrupt-preserving resource cleanup. These are local process-failure tests. No benchmark was rerun. The cluster JUnit system-out records the original raw node-log directory.

`bootstrap-node-logs/` preserves the two new bootstrap-regression runs' raw node logs and result lines (one focused run and one fresh full-check run). Binary archive/state directories are not copied.
