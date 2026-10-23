#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/remote_service.py" node "${1:-status}" "${2:?Usage: remote-node.sh start|status|stop|snapshot NODE_ID}"
