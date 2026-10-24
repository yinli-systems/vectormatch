# Second PostgreSQL-only probe: internal ledger audit passed

The new r2 lifecycle uses the exact stopped post-r1 physical baseline (989 files), keeps the original immutable backups, and writes into a new JOB. Its four documented changes are the baseline SHA/count, JOB path, and omission of the unnecessary empty external_pid_file override. The inspector switches PgJDBC to transaction read-only mode and retains every previous assertion; it also reads back full_page_writes and pg_is_in_recovery. No original evidence was replaced.

Before startup, the existing CPU passed all33 Python guards,23 Java API/setting guards and payload self-tests (2 valid/6 rejected). The r1 default=off settings sample remains rejected. Both actual session default and active transaction were then verified read-only; isolation was repeatable read, fsync/synchronous_commit/full_page_writes were on, recovery was false, and actual version/path/system identity matched the original PostgreSQL18.6 clone.

The fixed existing lineage `runpod-cloud-20261023-01` contains:

| Quantity | Actual verified value |
|---|---:|
| Events / event cursor | 6214 |
| Public market events / market cursor | 6194 |
| Trades | 1551 |
| Committed projection batches | 535 |
| Source last-event frontier recorded in PG | 6214 |

Every event's original sorted-Jackson payload SHA, JSONB semantic content, indexed event/type/market fields, contiguous sequence and trade count passed. Public-view range is1–6194. Recorded database collation versions match their actual versions and no installed version mismatch was reported; NULL version cases retain the limitations documented in r1 review. This is not a universal library/locale or WAL/page-integrity certification.

Root independently streamed the full13,483,845-byte raw archive:1,052 complete files and36 directories matched exact SHA/bytes/mode/owner/closure. It then independently parsed all6,214 raw rows and reproduced ledger digest `5a438910c3c1c7af02dd9e494754341cd03664cf315eaec68d56824e69a24226`. The SQL result, rows, process identities, actual settings, source/classes/dependencies, PG physical clone and before/after differences are retained. PostgreSQL and the inspector stopped, and pg_controldata confirmed the same system identifier7699920832388303129 and clean shutdown. PG internal physical writes are expected and separately inventoried.

## Tail-replay gate

The latest original Aeron checkpoint contains6106 events,108 fewer than the actual PG ledger. It is a checkpoint, not the final source tip. The previously compiled r1 leader probe's fixed6106/hash assertion must therefore not be used to certify the final recovered source. No such online probe or original node has run yet. A new probe must observe the replayed canonical source, require its correct final frontiers, and independently decode new snapshots from all three replicas. Old checkpoint evidence stays immutable.

This proves PG internal ledger consistency and controlled startup/clean shutdown. It does not yet prove Aeron tail replay, source-to-PG full historical cryptographic correspondence, three current replica states, gateway/HTTP/WebSocket recovery, cloud capacity or any100M target.
