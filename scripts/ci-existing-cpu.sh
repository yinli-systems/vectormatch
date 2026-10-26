#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ "$(id -u)" = 0 ]; then echo 'Run CI as a dedicated unprivileged user.' >&2; exit 1; fi
: "${VM_CI_PYTHON:?One-job runner must provide the pinned portable Python executable}"
"$VM_CI_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'
mkdir -p runtime/ci
java -version
node --version
gradle --version
"$VM_CI_PYTHON" scripts/bootstrap-postgres.py
# Allocate only a fresh, job-owned database. No shared database or background service.
VM_CI_PGDATA="$(mktemp -d "${RUNNER_TEMP:?}/vectormatch-pg.XXXXXXXX")"
VM_CI_PGPORT="$("$VM_CI_PYTHON" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
cleanup() {
  if [ -f "$VM_CI_PGDATA/postmaster.pid" ]; then
    .tools/postgres/bin/pg_ctl -D "$VM_CI_PGDATA" -m fast -w stop
  fi
}
trap cleanup EXIT
.tools/postgres/bin/initdb -D "$VM_CI_PGDATA" -U vectormatch -A trust --locale=C --encoding=UTF8
.tools/postgres/bin/pg_ctl -D "$VM_CI_PGDATA" -l "$VM_CI_PGDATA/server.log" \
  -o "-h 127.0.0.1 -p $VM_CI_PGPORT -c unix_socket_directories='' -c synchronous_commit=on -c fsync=on" -w start
export VM_TEST_PG_URL="jdbc:postgresql://127.0.0.1:$VM_CI_PGPORT/postgres"
export VM_TEST_PG_USER=vectormatch
export VM_TEST_PG_PASSWORD=local-ci-only
gradle --no-daemon --no-build-cache --rerun-tasks check 2>&1 | tee runtime/ci/gradle-check.log
"$VM_CI_PYTHON" -B scripts/verify_sealed_read_route.py --junit cluster/build/test-results/test/TEST-io.vectormatch.cluster.RetentionSealedThreeJvmV4Test.xml | tee runtime/ci/sealed-read-route-audit.json
gradle --no-daemon :cluster:failoverSmoke 2>&1 | tee runtime/ci/failover.log
"$VM_CI_PYTHON" -B -m unittest discover -s scripts/tests -v 2>&1 | tee runtime/ci/python-tests.log
bash -n scripts/run-replicated.sh deploy/cluster.sh deploy/postgres.sh scripts/ci-existing-cpu.sh
(cd web && npm ci && npm run build && npm run format:check) 2>&1 | tee runtime/ci/web.log
