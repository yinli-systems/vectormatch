#!/usr/bin/env bash
# Start an autopilot run once the one currently running has exited, so two runs never share the CPUs.
# Usage: queue.sh RUNNING_PID STAGING_DIR MODE   (VM_LAYOUT must be exported)
set -u
running=$1 staging=$2 mode=$3
while kill -0 "$running" 2>/dev/null; do sleep 20; done
# Give the previous run's JVMs time to exit; the controller refuses to start while any are alive.
for _ in $(seq 1 30); do pgrep -x java >/dev/null || break; sleep 10; done
cd "$staging" && exec python3 "$staging/autopilot.py" "$staging" "$mode"
