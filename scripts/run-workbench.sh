#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/env.sh
if [ ! -f web/dist/index.html ]; then (cd web && npm ci && npm run build); fi
./gradlew :server:installDist --console=plain
exec server/build/install/server/bin/server

