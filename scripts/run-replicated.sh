#!/usr/bin/env bash
# A local, three-process demo, with the projector supervised by this foreground process.
set -euo pipefail
cd "$(dirname "$0")/.."
# Acquire the per-repository lock before build/bootstrap or any Aeron driver can be touched.
# The descriptor survives exec and stays held by supervised descendants after an abrupt parent exit.
launcher_lock="$PWD/runtime/replicated-launcher.lock"
if [ "${VM_REPLICATED_LOCK_PID:-}" != "$$" ]; then
    exec python3 scripts/launcher-lock.py "$launcher_lock" bash "$PWD/scripts/run-replicated.sh" "$@"
fi
python3 scripts/launcher-lock.py --validate "${VM_REPLICATED_LOCK_FD:?Missing inherited launcher lock}" "$launcher_lock"
source scripts/env.sh
: "${VM_CLUSTER_ID:?Set VM_CLUSTER_ID to the stable lineage for this cluster/database pair}"
: "${VM_PG_URL:=jdbc:postgresql://127.0.0.1:55432/postgres}"
: "${VM_PG_USER:=vectormatch}"
: "${VM_CLUSTER_PORT_BASE:=19000}"
: "${VM_PROJECTOR_DRIVER:=runtime/projector-driver}"
export VM_CLUSTER_ID VM_PG_URL VM_PG_USER VM_CLUSTER_PORT_BASE VM_PROJECTOR_DRIVER
if [ ! -f web/dist/index.html ]; then
    (cd web && python3 ../scripts/launcher-lock.py --without-lock "$VM_REPLICATED_LOCK_FD" npm ci &&
        python3 ../scripts/launcher-lock.py --without-lock "$VM_REPLICATED_LOCK_FD" npm run build)
fi
python3 scripts/launcher-lock.py --without-lock "$VM_REPLICATED_LOCK_FD" \
    ./gradlew :cluster:installDist :projector:installDist :server:installDist --console=plain
# A supplied external database is never initialized or stopped by this launcher.
if [ "$VM_PG_URL" = 'jdbc:postgresql://127.0.0.1:55432/postgres' ]; then
    python3 scripts/launcher-lock.py --without-lock "$VM_REPLICATED_LOCK_FD" bash deploy/postgres.sh start
fi
VECTOR_PORT_BASE="$VM_CLUSTER_PORT_BASE" python3 scripts/launcher-lock.py --without-lock "$VM_REPLICATED_LOCK_FD" bash deploy/cluster.sh start
projector/build/install/projector/bin/projector init
projector/build/install/projector/bin/projector watch &
projector_pid=$!
gateway_pid=''
cleanup() {
    trap - EXIT INT TERM
    [ -z "$gateway_pid" ] || kill -TERM "$gateway_pid" 2>/dev/null || true
    kill -TERM "$projector_pid" 2>/dev/null || true
    wait "$projector_pid" 2>/dev/null || true
    [ -z "$gateway_pid" ] || wait "$gateway_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
JAVA_OPTS="${JAVA_OPTS:-} -Dvm.backend=cluster -Dvm.port=${VM_PORT:-8001} -Dvm.runtime=${VM_GATEWAY_RUNTIME:-runtime/workbench-cluster} -Dvm.cluster.portBase=$VM_CLUSTER_PORT_BASE" \
    server/build/install/server/bin/server &
gateway_pid=$!
printf 'Gateway and projector supervised; persistent cluster and PostgreSQL remain running after exit.\n'
while kill -0 "$gateway_pid" 2>/dev/null && kill -0 "$projector_pid" 2>/dev/null; do sleep 1; done
if ! kill -0 "$projector_pid" 2>/dev/null; then
    echo 'Projector exited; stopping the gateway. Inspect projector diagnostics before restarting.' >&2
    exit 1
fi
wait "$gateway_pid"
