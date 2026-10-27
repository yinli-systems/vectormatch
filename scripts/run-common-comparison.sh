#!/usr/bin/env bash
# Finite common-subset API experiment. Build :bench:comparisonInstallDist first.
set -euo pipefail
if [[ $# -ne 5 ]]; then
  printf '%s\n' 'Usage: run-common-comparison.sh VECTOR|EXCHANGE RATE SECONDS SEED NEW_OUTPUT' \
    'Optional: JAVA_HOME and VM_COMPARE_CPUSET (Linux taskset CPU list).' \
    'This is an in-process API experiment, not a replicated or sustained SLA.' >&2
  exit 2
fi
comparison_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
comparison_java="${JAVA_HOME:+$JAVA_HOME/bin/}java"
comparison_output="$5"
comparison_lib="$comparison_root/bench/build/install/common-comparison/lib"
[[ -d "$comparison_lib" ]] || { printf '%s\n' 'Build :bench:comparisonInstallDist first.' >&2; exit 2; }
[[ ! -e "$comparison_output" && ! -e "$comparison_output.gc.log" ]] || { printf '%s\n' 'Refusing to overwrite original evidence.' >&2; exit 2; }
mkdir -p "$(dirname "$comparison_output")"
comparison_prefix=(env -u JAVA_TOOL_OPTIONS -u JDK_JAVA_OPTIONS -u _JAVA_OPTIONS)
if [[ -n "${VM_COMPARE_CPUSET:-}" ]]; then
  command -v taskset >/dev/null || { printf '%s\n' 'VM_COMPARE_CPUSET requires taskset.' >&2; exit 2; }
  comparison_prefix+=(taskset -c "$VM_COMPARE_CPUSET")
fi
exec "${comparison_prefix[@]}" "$comparison_java" -Xms1g -Xmx3g -XX:ActiveProcessorCount=8 -XX:+UseG1GC \
  --add-opens=java.base/java.lang.reflect=ALL-UNNAMED \
  --add-opens=java.base/java.lang=ALL-UNNAMED \
  --add-opens=java.base/java.nio=ALL-UNNAMED \
  --add-exports=java.base/jdk.internal.ref=ALL-UNNAMED \
  --add-exports=java.base/sun.nio.ch=ALL-UNNAMED \
  --add-opens=java.base/java.io=ALL-UNNAMED \
  --add-opens=java.base/java.util=ALL-UNNAMED \
  "-Xlog:gc*:file=$comparison_output.gc.log:time,uptime,level,tags" \
  -cp "$comparison_lib/*" io.vectormatch.bench.comparison.CommonComparison "$@"
