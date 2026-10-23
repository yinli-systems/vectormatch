#!/usr/bin/env python3
"""Record effective CPU/memory/storage limits without reading credentials or user files."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import importlib.util

_cgroup_spec = importlib.util.spec_from_file_location("cgroup_limits", Path(__file__).with_name("cgroup-limits.py"))
_cgroup_module = importlib.util.module_from_spec(_cgroup_spec)
_cgroup_spec.loader.exec_module(_cgroup_module)


def command(args):
    try:
        environment = os.environ.copy()
        if args[:2] == ["java", "-version"]:
            # The JVM echoes these variables, which can contain secret -D properties.
            for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
                environment.pop(key, None)
        result = subprocess.run(args, capture_output=True, text=True, timeout=10, env=environment)
        return {"exitCode": result.returncode, "output": (result.stdout + result.stderr).strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": type(error).__name__}


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/local/preflight.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    affinity_error = None
    try:
        affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    except OSError as error:
        affinity, affinity_error = None, type(error).__name__
    disk = shutil.disk_usage(output.parent)
    report = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "system": platform.system(), "release": platform.release(), "arch": platform.machine(),
        "logicalCpuCount": os.cpu_count(), "allowedCpuIds": affinity,
        "affinityReadError": affinity_error,
        "cgroups": _cgroup_module.collect(affinity=affinity),
        "diskBytes": {"total": disk.total, "free": disk.free},
        "java": command(["java", "-version"]),
        "gitCommit": command(["git", "rev-parse", "HEAD"]),
        "gitDirty": command(["git", "status", "--porcelain"]),
    }
    if platform.system() == "Linux":
        report["cpu"] = command(["lscpu", "--json"])
        report["memory"] = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                            for line in (read("/proc/meminfo") or "").splitlines()
                            if line.startswith(("MemTotal:", "MemAvailable:", "SwapTotal:"))}
        report["filesystem"] = command(["findmnt", "-T", str(output.parent), "-n", "-o", "FSTYPE,OPTIONS"])
    elif platform.system() == "Darwin":
        report["cpu"] = command(["sysctl", "-n", "machdep.cpu.brand_string"])
        report["physicalMemoryBytes"] = command(["sysctl", "-n", "hw.memsize"])
    # Small synchronous-write probe in the output filesystem; not a disk capacity benchmark.
    samples = []
    with tempfile.TemporaryFile(dir=output.parent) as probe:
        for _ in range(32):
            started = time.perf_counter_ns()
            probe.write(b"x" * 4096)
            probe.flush()
            os.fsync(probe.fileno())
            samples.append((time.perf_counter_ns() - started) / 1e6)
    samples.sort()
    report["syncProbe"] = {
        "scope": "32 sequential 4KiB buffered writes + flush + fsync, one temporary file; OS/device semantics apply",
        "samples": 32, "p50Millis": samples[15], "p99Millis": samples[-1],
        "notDiskCapacityOrPowerLossProof": True,
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Preflight saved: {output}")


if __name__ == "__main__":
    main()
