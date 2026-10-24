# Frozen PG-only probe review r1

Reviewed the frozen controller `0a12ad7dd7aed6866c58e6c0fd46e068b82721144872584880965d7cfb13d9f8` and Java inspector `73b7c1cb9725265681f7041d9a27e68a6adb61168a0ea4ce2f3af84c3d88b82f`. No blocking defect found for one bounded PG-only probe, with the limits below. This was local source review only: no SSH, cloud action, PostgreSQL startup, SQL connection or change to the frozen inputs. The existing 33 offline guards and Java payload self-tests remain the earlier local results, not fresh cloud recovery proof.

## Main postmaster and process titles

The exact [official PostgreSQL18.6 archive](https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2), SHA `555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f`, was inspected directly. Entry SHA, exact line ranges and all backend `init_ps_display` occurrences are in `review-r1.json`.

`src/backend/utils/misc/ps_status.c:55–56` selects Linux argv overwriting, but its `init_ps_display` at281–282 returns for `!IsUnderPostmaster`. `globals.c:120` initializes this flag false; `miscinit.c:98` sets it true only while initializing a postmaster child. The complete postmaster.c has no `init_ps_display` call; all actual backend callers found are child initialization paths. main.c:93–104 saves argv before these operations. This supports keeping the main postmaster's exact original argv guard; child titles must not be confused with the owned main PID. Setting update_process_title off is not a universal child-title invariant: child initialization forces its first update (ps_status.c328–334).

This source inference does not certify that the separately pinned Zonky binary is an unpatched official build. Root must independently observe its actual SHA/version and the live main PID/startTicks/argv SHA. Normal shutdown keeps exact identity checks and pidfd-directed SIGINT. A changed identity produces explicit failure/cleanup-unconfirmed, never a false stop receipt or numeric PID fallback. A future narrowly scoped cleanup revision could use the already-held main pidfd; it is not implemented here.

## SQL and locale review

The inspector uses the original e1db typed Event and the same sorted Jackson mapper as PostgresEventStore. It reencodes JSONB into the original serializer form before checking stored payload SHA; text spacing/order are not used as the original SHA. Indexed columns, every event/market sequence, target cursor, event/trade counts and public-view extrema are cross-checked inside one read-only repeatable-read transaction. Existing schema is read only; no PostgresEventStore initializer, DDL, source ACK or projector is invoked. This is PG internal ledger consistency, not reconciliation to a recovered Aeron canonical source.

The actual database locale/provider/stored+actual version and installed version mismatches are captured. pg_locale_libc.c:658–720 deliberately returns no version for C/C.* or POSIX. A stored NULL version is therefore not automatically an error, but the inspector's NULL allowance also must not be described as full locale/library compatibility proof. The conservative all-installed mismatch guard may stop on unused collations; that alone does not establish damaged trading indexes, and no REFRESH/reindex is performed to hide warnings. dbcommands.c:2776–2807 defines the database actual-version lookup used by the query.

The server command pins fsync, synchronous_commit and full_page_writes on; the current SQL inspector reads back the first two plus control system ID. It does not independently verify WAL replay, recovery state, every page checksum or full_page_writes through SQL. Those claims remain unproved. Adding pg_is_in_recovery=false/readback is a possible small later revision, not part of this frozen attempt.

## Execution and evidence limits

Root supplies a separate owned75-second JVM timeout. Java's60-second check runs only during event iteration and does not impose a hard total limit on metadata or an empty ledger. The PG controller has a180-second observation deadline plus30-second clean-stop wait, contingent on the controller remaining alive; it does not promise survival cleanup after SIGKILL/OOM or a kernel-stuck shutdown. Actual execution must preserve unconfirmed cleanup as failure.

PostgreSQL may legitimately modify cloned control/WAL/stat/hint-bit/postmaster.opts files even with read-only application SQL. The original full-byte preflight belongs before the first startup. After shutdown capture a new inventory/diff and independently verify clean pg_controldata with the same system ID, including critical-file SHA before/after the read-only control inspection; do not require the running-derived clone to still equal every original backup byte. Preserve all original backups, original stopped baseline, partial logs and raw SQL evidence. No automatic retry, initdb, fresh empty database, cluster-ID change or cursor override.
