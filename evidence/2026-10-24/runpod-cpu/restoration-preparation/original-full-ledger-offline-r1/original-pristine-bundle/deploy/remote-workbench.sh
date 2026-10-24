#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$HERE/remote_service.py" "${1:?Usage: remote-workbench.sh gateway|projector start|status|stop|init|once|db-status}" "${2:-status}"
