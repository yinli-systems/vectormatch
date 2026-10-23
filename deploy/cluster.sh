#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/env.sh"
STATE="${VECTOR_STATE_DIR:-$ROOT/runtime/cluster}"
PORT_BASE="${VECTOR_PORT_BASE:-19000}"
SYNC="${VECTOR_SYNC_LEVEL:-2}"
OUTBOX_CAPACITY="${VECTOR_OUTBOX_CAPACITY:-65536}"
DIST="$ROOT/cluster/build/install/cluster"
JAVA="${JAVA_HOME:+$JAVA_HOME/bin/}java"
VM_OPENS=(--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED --add-opens=java.base/java.util.zip=ALL-UNNAMED)

mkdir -p "$STATE"
STATE="$(cd "$STATE" && pwd)"

owned_pid() {
    local node="$1" pid command
    [ -f "$STATE/node-$node.pid" ] || return 1
    read -r pid < "$STATE/node-$node.pid"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    command="$(ps -p "$pid" -o command=)"
    [[ "$command" == *"io.vectormatch.cluster.ClusterNodeMain $node $STATE $PORT_BASE"* ]] || return 1
    printf '%s' "$pid"
}

require_dist() {
    if [ ! -d "$DIST/lib" ]; then
        printf 'Build the cluster first: ./gradlew :cluster:installDist\n' >&2
        exit 1
    fi
}

case "${1:-status}" in
    start)
        require_dist
        for node in 0 1 2; do
            if pid="$(owned_pid "$node")"; then
                printf 'node=%s already running pid=%s\n' "$node" "$pid"
                continue
            fi
            pid="$(python3 - "$STATE/node-$node.log" "$JAVA" "${VM_OPENS[@]}" -cp "$DIST/lib/*" \
                io.vectormatch.cluster.ClusterNodeMain "$node" "$STATE" "$PORT_BASE" "$SYNC" "$OUTBOX_CAPACITY" <<'PY'
import subprocess, sys
with open(sys.argv[1], 'ab', buffering=0) as log:
    child = subprocess.Popen(sys.argv[2:], stdin=subprocess.DEVNULL, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
print(child.pid)
PY
)"
            printf '%s\n' "$pid" > "$STATE/node-$node.pid"
            printf 'node=%s started pid=%s sync=%s log=%s\n' "$node" "$pid" "$SYNC" "$STATE/node-$node.log"
        done
        ;;
    status)
        for node in 0 1 2; do
            if pid="$(owned_pid "$node")"; then
                printf 'node=%s running pid=%s\n' "$node" "$pid"
            else
                printf 'node=%s stopped\n' "$node"
            fi
        done
        ;;
    stop)
        for node in 0 1 2; do
            if pid="$(owned_pid "$node")"; then
                kill -TERM "$pid"
                printf 'node=%s shutdown requested pid=%s\n' "$node" "$pid"
            fi
        done
        ;;
    snapshot)
        require_dist
        leader=''
        for node in 0 1 2; do
            owned_pid "$node" > /dev/null || continue
            if "$JAVA" "${VM_OPENS[@]}" -cp "$DIST/lib/*" io.aeron.cluster.ClusterTool \
                    "$STATE/node-$node/cluster" is-leader > /dev/null 2>&1; then
                leader="$node"
                break
            fi
        done
        if [ -z "$leader" ]; then
            printf 'No live leader found; inspect %s/node-*.log\n' "$STATE" >&2
            exit 1
        fi
        "$JAVA" "${VM_OPENS[@]}" -cp "$DIST/lib/*" io.aeron.cluster.ClusterTool \
            "$STATE/node-$leader/cluster" snapshot
        ;;
    *) printf 'Usage: deploy/cluster.sh {start|status|snapshot|stop}\n' >&2; exit 2 ;;
esac
