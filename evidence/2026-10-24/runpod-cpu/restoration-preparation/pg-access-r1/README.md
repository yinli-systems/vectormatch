# Original PostgreSQL clone: actual access preparation

The frozen access-only controller passed all 27 offline guards on the actual Ubuntu20/Python3.8 CPU host. Actual read-only preflight verified all 990 original PG files, 27 directories and 1,071 pinned original binary entries. It then created only the dedicated `vectormatch-pg` UID/GID963 identity, with no home or login shell.

Exactly five registered root-owned parent directories received execute-only access for UID963. Root ownership and other-user permissions remain restricted. No PGDATA ACL was added. Only the verified PGDATA tree changed ownership to963:963: 1,017 entries, with the root directory last. All 61,616,789 PG file bytes and original modes were rechecked afterward. Final effective-user access passed, and the original system identifier7699920832388303129 and clean `shut down` state were verified again. No PostgreSQL server, SQL connection, cluster node, gateway or projector started in this phase.

## Preserved partial failure

ACL attempt r1 completed and verified the first four grants, then failed its fifth-target mtime equality check before invoking the fifth grant. Its own intent and receipt files, stored inside that fifth JOB directory, had changed the directory mtime. Raw failure and all four successful per-target receipts remain unchanged under `acl-partial-state-r1/`.

The separate r2 action first verified all four existing postconditions without repeating any grant, repeated full PG byte/access preflight, and granted only the previously unattempted JOB execute ACL. Its control receipts live outside JOB so they do not invalidate its mtime comparison. This is a distinct recorded action, not a silent retry of r1.

`completion.json`, `final-readback.stdout.json`, and `final-cloud-receipts/` close the phase. Original immutable backups and all original cluster native files are retained. Database startup may change the physical clone internally; any later startup/SQL outcome belongs to a separate phase. This access preparation provides no recovery, application or performance result.
