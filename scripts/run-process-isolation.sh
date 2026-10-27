#!/usr/bin/env bash
# Build :bench:comparisonInstallDist first. New originals only; no remote provisioning.
set -euo pipefail
if [[ $# -ne 7 ]]; then
  printf '%s\n' 'Usage: run-process-isolation.sh COLOCATED|ISOLATED G1|GEN_ZGC false|true RATE SECONDS SEED NEW_OUTPUT' \
    'Third argument enables an explicit client-index startup sizing hint.' \
    'Optional: JAVA_HOME and VM_COMPARE_CPUSET (Linux taskset CPU list).' \
    'Five-second finite TCP experiments do not establish replicated or sustained capacity.' >&2
  exit 2
fi
[[ "$1" == COLOCATED || "$1" == ISOLATED ]] || exit 2
[[ "$2" == G1 || "$2" == GEN_ZGC ]] || exit 2
[[ "$3" == false || "$3" == true ]] || exit 2
for isolated_number in "$4" "$5" "$6"; do [[ "$isolated_number" =~ ^[0-9]+$ ]] || exit 2; done
isolated_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
isolated_java="${JAVA_HOME:+$JAVA_HOME/bin/}java"
isolated_output="$7"
isolated_lib="$isolated_root/bench/build/install/common-comparison/lib"
[[ -d "$isolated_lib" ]] || { printf '%s\n' 'Build :bench:comparisonInstallDist first.' >&2; exit 2; }
[[ "$isolated_output" != *:* && "$isolated_output" != *$'\n'* ]] || { printf '%s\n' 'Output cannot contain Java GC-log separators.' >&2; exit 2; }
[[ ! -e "$isolated_output" && ! -e "$isolated_output.controller-gc.log" ]] || { printf '%s\n' 'Refusing to overwrite original evidence.' >&2; exit 2; }
mkdir -p "$(dirname "$isolated_output")"
isolated_prefix=(env -u JAVA_TOOL_OPTIONS -u JDK_JAVA_OPTIONS -u _JAVA_OPTIONS)
if [[ -n "${VM_COMPARE_CPUSET:-}" ]]; then
  command -v taskset >/dev/null || { printf '%s\n' 'VM_COMPARE_CPUSET requires taskset.' >&2; exit 2; }
  isolated_prefix+=(taskset -c "$VM_COMPARE_CPUSET")
fi
exec "${isolated_prefix[@]}" "$isolated_java" -Xms1g -Xmx1g -XX:ActiveProcessorCount=8 -XX:+UseG1GC \
  "-Dvectormatch.comparison.presizeClientIds=$3" \
  "-Xlog:gc*,safepoint:file=$isolated_output.controller-gc.log:time,uptime,level,tags" \
  -cp "$isolated_lib/*" io.vectormatch.bench.comparison.ProcessIsolationComparison \
  "$1" "$2" "$4" "$5" "$6" "$7" 3
