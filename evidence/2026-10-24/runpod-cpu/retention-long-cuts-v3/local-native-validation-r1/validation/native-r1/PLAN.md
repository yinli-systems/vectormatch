# One local native long-cut attempt, not yet launched

Source bcf49c10b77a14708b53d3fc6c115a6a3b834408, exact installed JAR fingerprint6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8.
One fresh arm only: `idle-window8-long-cuts 42000`, property `vectormatch.retention.idleMaxParkNs=100000`.
33792 planned arrivals at500/s for67.584s; cap4/chunk6144/Fetch16/read8/leader0/term0/sync2.

`run_native.py --prepare` binds/probes the fifteen fixed UDP endpoints and releases them, checks clean source/JDK/JAR/actual Plan/owned-namespace/free space, and writes an exclusive preregistration. It starts no JVM.
Root reviews that registration and wrapper before the separate one-shot `--start-new` invocation. No fallback port, second attempt or second arm.
The wrapper uses one direct unreaped Popen handle for the Java parent; exact argv and supplementary PID/start/argv ps output are preserved. Nodes are launched by the frozen Java pilot and registered by Process.info startInstant/command/argv. Java clean stop rechecks all three and sends TERM only; no escalation.
The wrapper sends no signals. It records5s sampled owned st_blocks/paths/free space plus parent identity; the Java source independently enforces all unchanged budget/1Hz sample/raw/path bounds. A420s wrapper deadline preserves active identity/evidence and forbids rerun; it does not fabricate stopped state or archive active files.

The existing30s Java startup wait,120s Config maximum,90s task/drain, physical permits and all other limits remain unchanged. Free space must cover1GiB floor +757122377 prospective growth +891340105 closed-archive reserve.
Successful functional inspection requires all33792 original orders,12cycles, exact final counters, fixed leader/term, physical-order reference reconciliation and all three canonical checkpoint logs.
Actual idle factory evidence must contain7per node +1owner (22creations), configured100us maximum and actual child argv; it does not measure sleeps, active thread count or real-time guarantees.

Original strict node-log results remain distinct from the pinned pure narrow post-checkpoint follower EOS WARN classification. No other exception/error/log tail is accepted, no warning is removed, no signal-time causality is inferred.
Do not execute or relax the old<=8-phase raw auditor: this run needs a separately bound24-phase/12cycle/33792-row audit later.

Only after direct parent exit and all3owned nodes stopped, `capture_closed.py` streams the complete original namespace plus exact input JAR/source/proof copies into one gzip TAR. It verifies every full logical file SHA, bytes, modes, uid/gid, explicit directories/empty directories by streaming readback; it never fully extracts sparse native files. Raw failures and warnings stay in the archive. No SSH/cloud/PG/main edits are involved. Local CPU performance claims remain false, even if this source's scheduler happens to be valid.
