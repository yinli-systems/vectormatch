#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/.tools/postgres/bin"
DATA="$ROOT/runtime/postgres18"
PORT="${VM_PG_PORT:-55432}"
mkdir -p "$ROOT/runtime"
if [ ! -x "$BIN/pg_ctl" ]; then echo 'Run python3 scripts/bootstrap-postgres.py first.' >&2; exit 1; fi
case "${1:-status}" in
  start)
    if [ ! -f "$DATA/PG_VERSION" ]; then "$BIN/initdb" -D "$DATA" -U vectormatch -A trust --locale=C --encoding=UTF8; fi
    if "$BIN/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then echo 'PostgreSQL already running'; exit 0; fi
    "$BIN/pg_ctl" -D "$DATA" -l "$ROOT/runtime/postgres18.log" -o "-h 127.0.0.1 -p $PORT -c unix_socket_directories='' -c synchronous_commit=on -c fsync=on" -w start
    ;;
  stop) "$BIN/pg_ctl" -D "$DATA" -m fast -w stop ;;
  status) "$BIN/pg_ctl" -D "$DATA" status ;;
  *) echo 'Usage: deploy/postgres.sh start|stop|status' >&2; exit 2 ;;
esac
