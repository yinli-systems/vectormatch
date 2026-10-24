#!/usr/bin/env python3
"""Bounded, read-only Linux telemetry for explicit VectorMatch process records.

No process enumeration, environment reads, command output, or system changes.
Counters are cumulative: derive rates from monotonic timestamps, never wall time.
Container network/cgroup counters include other processes in that namespace/group.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import sys
import time


STATUS_BYTES = ("VmPeak", "VmSize", "VmHWM", "VmRSS", "RssAnon", "RssFile", "RssShmem")
STATUS_COUNTS = ("Threads", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches")
IO_FIELDS = ("rchar", "wchar", "syscr", "syscw", "read_bytes", "write_bytes", "cancelled_write_bytes")
NETWORK_FIELDS = ("bytes", "packets", "errs", "drop", "fifo", "frame", "compressed", "multicast",
                  "bytes", "packets", "errs", "drop", "fifo", "colls", "carrier", "compressed")


def error_value(exc):
    # Do not serialize input records or /proc command lines in exception messages.
    return {"error": type(exc).__name__, "errno": getattr(exc, "errno", None)}


def read_parsed(path, parser):
    try:
        return {"value": parser(Path(path).read_text())}
    except (OSError, ValueError, IndexError, KeyError, TypeError) as exc:
        return error_value(exc)


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise ValueError("Negative cumulative counter")
    return number


def parse_stat(text):
    # comm can contain spaces, ')' characters and newlines. The final ')' bounds it.
    close = text.rindex(")")
    if close < 2 or text[close + 1:close + 2] != " ":
        raise ValueError("Invalid proc stat")
    fields = text[close + 2:].split()
    if len(fields) < 22:
        raise ValueError("Truncated proc stat")
    return {"state": fields[0], "minorFaults": nonnegative(fields[7]),
            "majorFaults": nonnegative(fields[9]), "userCpuTicks": nonnegative(fields[11]),
            "systemCpuTicks": nonnegative(fields[12]), "threadCount": nonnegative(fields[17]),
            "startTicks": nonnegative(fields[19]), "virtualBytes": nonnegative(fields[20]),
            "residentPages": int(fields[21])}


def proc_identity(pid, proc_root=Path("/proc")):
    values = parse_stat((proc_root / str(pid) / "stat").read_text())
    command = (proc_root / str(pid) / "cmdline").read_bytes()
    if values["state"] in ("Z", "X", "x") or not command:
        raise ProcessLookupError("Process is not live")
    return {"startTicks": values["startTicks"], "commandSha256": hashlib.sha256(command).hexdigest()}


def read_record(path):
    record = json.loads(Path(path).read_text())
    if not isinstance(record, dict):
        raise ValueError("PID file must be an identity JSON object")
    if type(record.get("version")) is not int or record["version"] != 1 or type(record.get("pid")) is not int or record["pid"] < 2:
        raise ValueError("Invalid identity record version or PID")
    if type(record.get("startTicks")) is not int or record["startTicks"] <= 0:
        raise ValueError("Invalid process start time")
    if not isinstance(record.get("commandSha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["commandSha256"]):
        raise ValueError("Invalid command hash")
    return {name: record[name] for name in ("pid", "startTicks", "commandSha256")}


def parse_status(text):
    entries = dict(line.split(":", 1) for line in text.splitlines() if ":" in line)
    result = {}
    for name in STATUS_BYTES:
        if name in entries:
            parts = entries[name].split()
            if len(parts) != 2 or parts[1] != "kB":
                raise ValueError("Unexpected status memory unit")
            result[name + "Bytes"] = nonnegative(parts[0]) * 1024
    for name in STATUS_COUNTS:
        if name in entries:
            result[name] = nonnegative(entries[name].strip())
    if not result:
        raise ValueError("No recognized status metrics")
    return result


def parse_io(text):
    entries = dict(line.split(":", 1) for line in text.splitlines() if ":" in line)
    result = {name: nonnegative(entries[name].strip()) for name in IO_FIELDS if name in entries}
    if not result:
        raise ValueError("No recognized IO metrics")
    return result


def process_sample(path, proc_root=Path("/proc")):
    result = {"recordPath": str(path)}
    try:
        expected = read_record(path)
    except (OSError, ValueError, TypeError) as exc:
        return {**result, "status": "record-unavailable", **error_value(exc)}
    result.update(expected)
    identity = {name: expected[name] for name in ("startTicks", "commandSha256")}
    try:
        if proc_identity(expected["pid"], proc_root) != identity:
            return {**result, "status": "identity-mismatch"}
    except (OSError, ValueError, IndexError) as exc:
        return {**result, "status": "identity-unavailable", **error_value(exc)}
    base = proc_root / str(expected["pid"])
    metrics = {"stat": read_parsed(base / "stat", parse_stat),
               "status": read_parsed(base / "status", parse_status),
               "io": read_parsed(base / "io", parse_io)}
    try:
        # An exit/reuse between reads invalidates this sample's process metrics.
        if proc_identity(expected["pid"], proc_root) != identity:
            return {**result, "status": "identity-changed-during-read"}
    except (OSError, ValueError, IndexError) as exc:
        return {**result, "status": "identity-lost-during-read", **error_value(exc)}
    return {**result, "status": "verified", "metrics": metrics}


def unescape_mount(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def resolve_cgroup_leaf(membership, mountinfo):
    groups = [line.split(":", 2) for line in membership.splitlines()]
    v2 = [row[2] for row in groups if len(row) == 3 and row[0] == "0" and row[1] == ""]
    if len(v2) != 1:
        raise ValueError("Only a single mapped cgroup v2 membership is supported")
    member = PurePosixPath(v2[0])
    if not member.is_absolute() or ".." in member.parts:
        raise ValueError("Invalid cgroup membership")
    candidates = []
    for line in mountinfo.splitlines():
        before, separator, after = line.partition(" - ")
        left, right = before.split(), after.split()
        if not separator or len(left) < 6 or not right or right[0] != "cgroup2":
            continue
        root, mountpoint = (PurePosixPath(unescape_mount(left[index])) for index in (3, 4))
        if not root.is_absolute() or not mountpoint.is_absolute() or ".." in root.parts or ".." in mountpoint.parts:
            continue
        try:
            relative = member.relative_to(root)
        except ValueError:
            continue
        candidates.append((len(root.parts), str(mountpoint / relative), str(root), str(mountpoint)))
    if not candidates:
        raise ValueError("Membership is not mapped by a visible cgroup2 mount")
    _, directory, root, mountpoint = min(candidates)
    return {"directory": directory, "membership": str(member), "mountRoot": root, "mountPoint": mountpoint}


def parse_key_counters(text):
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] in result:
            raise ValueError("Invalid key counter file")
        result[parts[0]] = nonnegative(parts[1])
    if not result:
        raise ValueError("Empty key counter file")
    return result


def parse_cpu_max(text):
    quota, period = text.split()
    period = nonnegative(period)
    if period == 0:
        raise ValueError("Zero CPU quota period")
    maximum = None if quota == "max" else nonnegative(quota)
    return {"quotaMicros": maximum, "periodMicros": period,
            "quotaCpuUpperBound": None if maximum is None else maximum / period}


def resolve_cgroup_v1_leaves(membership, mountinfo):
    result = []
    for line in membership.splitlines():
        fields = line.split(":", 2)
        if len(fields) != 3 or not fields[1]:
            continue
        selected = set(fields[1].split(",")) & {"cpu", "cpuacct", "memory"}
        if not selected:
            continue
        member = PurePosixPath(fields[2])
        if not member.is_absolute() or ".." in member.parts:
            raise ValueError("Invalid cgroup membership")
        candidates = []
        for mount in mountinfo.splitlines():
            before, separator, after = mount.partition(" - ")
            left, right = before.split(), after.split()
            if not separator or len(left) < 6 or len(right) < 3 or right[0] != "cgroup":
                continue
            if not selected & set(right[2].split(",")):
                continue
            root, mountpoint = (PurePosixPath(unescape_mount(left[index])) for index in (3, 4))
            if not root.is_absolute() or not mountpoint.is_absolute() or ".." in root.parts or ".." in mountpoint.parts:
                continue
            try:
                relative = member.relative_to(root)
            except ValueError:
                continue
            candidates.append((len(root.parts), str(mountpoint / relative), str(root), str(mountpoint)))
        if not candidates:
            result.append({"controllers": sorted(selected), "status": "unmapped"})
            continue
        _, directory, root, mountpoint = min(candidates)
        result.append({"controllers": sorted(selected), "status": "mapped", "directory": directory,
                       "membership": str(member), "mountRoot": root, "mountPoint": mountpoint})
    if not result:
        raise ValueError("No supported cgroup v1 membership")
    return result


def cgroup_v1_sample(membership, mountinfo):
    groups = resolve_cgroup_v1_leaves(membership, mountinfo)
    for group in groups:
        if group["status"] != "mapped":
            continue
        parsers = {}
        if "cpu" in group["controllers"]:
            parsers.update({"cpu.stat": parse_key_counters, "cpu.cfs_quota_us": int,
                            "cpu.cfs_period_us": nonnegative})
        if "cpuacct" in group["controllers"]:
            parsers.update({"cpuacct.usage": nonnegative, "cpuacct.stat": parse_key_counters})
        if "memory" in group["controllers"]:
            parsers.update({"memory.usage_in_bytes": nonnegative, "memory.limit_in_bytes": nonnegative,
                            "memory.failcnt": nonnegative, "memory.oom_control": parse_key_counters})
        group["metrics"] = {name: read_parsed(Path(group["directory"]) / name, parser) for name, parser in parsers.items()}
    return {"status": "mapped-v1-leaves", "hierarchies": groups,
            "v2OnlyFiles": {"cpu.max": "unavailable-in-v1; see cpu.cfs_*_us",
                            "memory.current": "unavailable-in-v1; see memory.usage_in_bytes",
                            "memory.events": "unavailable-in-v1; see memory.failcnt/memory.oom_control"}}


def cgroup_sample(proc_root=Path("/proc")):
    try:
        membership = (proc_root / "self/cgroup").read_text()
        mountinfo = (proc_root / "self/mountinfo").read_text()
        # Hybrid hosts may expose an empty v2 hierarchy but active v1 CPU/memory.
        active_v1 = any(len(parts := line.split(":", 2)) == 3 and
                        set(parts[1].split(",")) & {"cpu", "cpuacct", "memory"}
                        for line in membership.splitlines())
        if active_v1:
            return cgroup_v1_sample(membership, mountinfo)
        leaf = resolve_cgroup_leaf(membership, mountinfo)
    except (OSError, ValueError, IndexError) as exc:
        return {"status": "unavailable", **error_value(exc)}
    directory = Path(leaf["directory"])
    parsers = {"cpu.stat": parse_key_counters, "cpu.max": parse_cpu_max,
               "memory.current": lambda value: nonnegative(value.strip()), "memory.events": parse_key_counters}
    return {"status": "mapped-v2-leaf", **leaf,
            "metrics": {name: read_parsed(directory / name, parser) for name, parser in parsers.items()}}


def parse_interface(text, interface):
    for line in text.splitlines():
        name, separator, values = line.partition(":")
        if separator and name.strip() == interface:
            fields = values.split()
            if len(fields) != 16:
                raise ValueError("Expected 16 interface counters")
            return {direction: {name: nonnegative(value) for name, value in zip(NETWORK_FIELDS[start:start + 8], fields[start:start + 8])}
                    for direction, start in (("receive", 0), ("transmit", 8))}
    raise KeyError("Selected interface unavailable")


def parse_udp(text):
    lines = [line.split() for line in text.splitlines() if line.startswith("Udp:")]
    if len(lines) != 2 or len(lines[0]) < 2 or len(lines[0]) != len(lines[1]):
        raise ValueError("Missing or malformed UDP MIB")
    if len(set(lines[0][1:])) != len(lines[0]) - 1:
        raise ValueError("Repeated UDP MIB counter")
    return {name: nonnegative(value) for name, value in zip(lines[0][1:], lines[1][1:])}


def timestamp():
    return {"wallTimeUtc": datetime.now(timezone.utc).isoformat(), "monotonicNs": time.monotonic_ns()}


def metadata():
    result = {"system": platform.system(), "kernel": platform.release(), "architecture": platform.machine(),
              "logicalCpuCount": os.cpu_count(), "clockTicksPerSecond": os.sysconf("SC_CLK_TCK"),
              "pageSizeBytes": os.sysconf("SC_PAGE_SIZE"),
              "clockMetadata": {name: vars(time.get_clock_info(name)) for name in ("time", "monotonic", "perf_counter")},
              "cpuModel": read_parsed("/proc/cpuinfo", lambda value: next((
                  line.split(":", 1)[1].strip() for line in value.splitlines() if line.startswith("model name") and ":" in line), None))}
    try:
        result["samplerAllowedCpuIds"] = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError) as exc:
        result["samplerAllowedCpuIds"] = error_value(exc)
    return result


def sample(state_dir, load_pid_file=None, interface="podnet1", proc_root=Path("/proc")):
    records = [(f"node-{index}", state_dir / f"node-{index}/process.json") for index in range(3)]
    if load_pid_file is not None:
        records.append(("load", load_pid_file))
    return {"type": "sample", **timestamp(),
            "processes": {name: process_sample(path, proc_root) for name, path in records},
            "cgroup": cgroup_sample(proc_root), "network": {
                "interface": interface,
                "device": read_parsed(proc_root / "net/dev", lambda text: parse_interface(text, interface)),
                "udp": read_parsed(proc_root / "net/snmp", parse_udp)}}


def bounded_float(value, low, high):
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise argparse.ArgumentTypeError(f"Expected finite number in {low}..{high}")
    return number


def run(args):
    stopped = {"signal": None}
    def stop(signum, _frame):
        stopped["signal"] = signum
    previous = {signum: signal.signal(signum, stop) for signum in (signal.SIGTERM, signal.SIGINT)}
    count, start = 0, time.monotonic()
    try:
        # Refuse evidence overwrite; flush each whole JSON line for interruption safety.
        with args.output.open("x", encoding="utf-8", buffering=1) as handle:
            def emit(value):
                handle.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
                handle.flush()
            emit({"type": "metadata", "schemaVersion": 1, **timestamp(), "intervalSeconds": args.interval,
                  "durationSeconds": args.duration, "hardware": metadata(),
                  "scope": "Only explicit node-0/1/2 identity records and optional load identity record. "
                           "cgroup counters describe the sampler's current visible v1/v2 leaves, not their hidden ancestors. "
                           "Network counters describe the sampler's network namespace, not individual processes. "
                           "Raw counters are cumulative; use monotonic deltas for rates. Null/errors are unavailable, not zero. "
                           "CPU ticks use clockTicksPerSecond; status *Bytes/io *_bytes/network bytes are bytes; "
                           "rchar/wchar are bytes; syscr/syscw are syscall counts; v2 cpu.stat *_usec are microseconds. "
                           "v1 cpu.stat throttled_time/burst_time and cpuacct.usage are nanoseconds; "
                           "v1 cpuacct.stat user/system are USER_HZ ticks. memory.failcnt is allocation failures, not OOM kills. "
                           "Wall clocks are not verified synchronized and do not establish one-way latency."})
            next_sample = start
            while stopped["signal"] is None and time.monotonic() - start < args.duration:
                now = time.monotonic()
                if now < next_sample:
                    time.sleep(min(.1, next_sample - now, max(0, start + args.duration - now)))
                    continue
                row = sample(args.state_dir, args.load_pid_file, args.interface)
                row["sequence"] = count
                row["scheduledElapsedSeconds"] = next_sample - start
                row["collectionFinishedMonotonicNs"] = time.monotonic_ns()
                emit(row)
                count += 1
                next_sample += args.interval
                # Do not generate a burst of backfilled samples when a read overruns.
                if next_sample < time.monotonic():
                    next_sample = start + (math.floor((time.monotonic() - start) / args.interval) + 1) * args.interval
            emit({"type": "complete", **timestamp(), "samples": count,
                  "elapsedSeconds": time.monotonic() - start,
                  "reason": "duration" if stopped["signal"] is None else "signal",
                  "signal": stopped["signal"]})
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New JSONL path; existing file is refused")
    parser.add_argument("--interval", default=1.0, type=lambda value: bounded_float(value, .05, 60))
    parser.add_argument("--duration", required=True, type=lambda value: bounded_float(value, .1, 86400))
    parser.add_argument("--load-pid-file", type=Path, help="Explicit version=1 PID/startTicks/commandSha256 identity JSON")
    parser.add_argument("--interface", default="podnet1")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("This read-only sampler requires Linux /proc and cgroup mounts")
    if not args.state_dir.is_dir():
        parser.error("--state-dir must be an existing project state directory")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", args.interface):
        parser.error("Invalid interface name")
    run(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(json.dumps({"type": "fatal", **error_value(exc)}), file=sys.stderr)
        raise SystemExit(1)
