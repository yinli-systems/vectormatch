#!/usr/bin/env python3
"""Opt-in Linux thread/socket attribution for explicit VectorMatch PID records.

Separate from capacity-telemetry.py; no attach, packet capture or system changes.
Use the same observer in every compared attribution run. This is observation,
not proof that a sampled hot thread or socket caused a latency change.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import sys
import time


_spec = importlib.util.spec_from_file_location("vectormatch_capacity_telemetry", Path(__file__).with_name("capacity-telemetry.py"))
common = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(common)

MAX_THREADS = 1024
MAX_FDS = 4096
MAX_UDP_ROWS = 65536
MAX_UDP_BYTES = 8 * 1024 * 1024
DETAIL_THREADS = 16
SOCKET_LINK = re.compile(r"socket:\[(\d+)\]")


def unavailable(exc):
    return {"value": None, **common.error_value(exc)}


def read_value(path, parser):
    try:
        return {"value": parser(Path(path).read_text())}
    except (OSError, ValueError, IndexError, KeyError, TypeError) as exc:
        return unavailable(exc)


def parse_thread_stat(text):
    values = common.parse_stat(text)
    left, right = text.index("("), text.rindex(")")
    tid = int(text[:left].strip())
    if tid < 1 or values["startTicks"] < 1:
        raise ValueError("Invalid thread identity")
    return {"tid": tid, "startTicks": values["startTicks"], "comm": text[left + 1:right],
            "state": values["state"], "userCpuTicks": values["userCpuTicks"],
            "systemCpuTicks": values["systemCpuTicks"]}


def parse_schedstat(text):
    values = text.split()
    if len(values) != 3:
        raise ValueError("Expected three schedstat counters")
    return dict(zip(("runtimeNs", "runqueueWaitNs", "timeslices"), map(common.nonnegative, values)))


def bounded_entries(directory, limit):
    result, truncated = [], False
    with os.scandir(directory) as entries:
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            if len(result) == limit:
                truncated = True
                break
            result.append(int(entry.name))
    return sorted(result), truncated


def owned_socket_inodes(base, max_fds):
    try:
        fds, truncated = bounded_entries(base / "fd", max_fds)
    except OSError as exc:
        return {}, {"status": "unavailable", "limit": max_fds, **unavailable(exc)}
    inodes, errors, failures = {}, [], 0
    for fd in fds:
        try:
            target = os.readlink(base / "fd" / str(fd))
            matched = SOCKET_LINK.fullmatch(target)
            if matched:
                inodes.setdefault(int(matched.group(1)), []).append(fd)
        except OSError as exc:
            failures += 1
            if len(errors) < 8:
                errors.append({"fd": fd, **common.error_value(exc)})
    return inodes, {"status": "partial" if truncated or failures else "ok", "limit": max_fds,
                    "scannedFds": len(fds), "truncated": truncated,
                    "readFailures": failures, "errors": errors, "ownedSocketInodes": len(inodes)}


def parse_bind(text, family):
    address, port = text.split(":")
    expected = 8 if family == "ipv4" else 32
    if len(address) != expected or not re.fullmatch(r"[0-9a-fA-F]+", address) or not re.fullmatch(r"[0-9a-fA-F]{4}", port):
        raise ValueError("Invalid local UDP bind")
    # proc renders each address word in native endianness.
    packed = b"".join(int(address[index:index + 8], 16).to_bytes(4, sys.byteorder)
                      for index in range(0, len(address), 8))
    return str(ipaddress.ip_address(packed)), int(port, 16)


def parse_owned_udp_row(line, owned, family):
    fields = line.split()
    # Only the inode field is inspected before ownership is established. Never
    # retain a non-owned row, peer endpoint, uid or kernel pointer.
    try:
        inode = int(fields[9])
    except (ValueError, IndexError):
        return None, "unattributable-row"
    if inode not in owned:
        return None, None
    if len(fields) < 13:
        raise ValueError("Truncated owned UDP row")
    local_address, local_port = parse_bind(fields[1], family)
    tx, rx = fields[4].split(":")
    return {"inode": inode, "fdNumbers": list(owned[inode]), "family": family,
            "localAddress": local_address, "localPort": local_port,
            "transmitQueueKernelBytes": common.nonnegative(int(tx, 16)),
            "receiveQueueKernelBytes": common.nonnegative(int(rx, 16)),
            "drops": common.nonnegative(fields[12])}, None


def udp_table(path, owned, family):
    if not owned:
        return {"status": "no-owned-socket-inodes", "sockets": [], "scannedRows": 0}
    matches, errors, rows, byte_count, malformed, truncated = [], [], 0, 0, 0, False
    try:
        with Path(path).open() as handle:
            header = handle.readline(4097)
            if "local_address" not in header or "inode" not in header:
                raise ValueError("Unexpected UDP table header")
            byte_count = len(header)
            while True:
                line = handle.readline(4097)
                if not line:
                    break
                byte_count += len(line)
                if rows == MAX_UDP_ROWS or byte_count > MAX_UDP_BYTES or len(line) > 4096:
                    truncated = True
                    break
                rows += 1
                try:
                    row, issue = parse_owned_udp_row(line, owned, family)
                    if issue:
                        malformed += 1
                    if row is not None:
                        matches.append(row)
                except (ValueError, IndexError, TypeError) as exc:
                    malformed += 1
                    if len(errors) < 8:
                        errors.append(common.error_value(exc))
    except (OSError, ValueError) as exc:
        return {"status": "unavailable", "sockets": None, **unavailable(exc)}
    return {"status": "partial" if truncated or malformed else "ok", "sockets": matches,
            "scannedRows": rows, "scanBytes": byte_count, "truncated": truncated,
            "unparsedRows": malformed, "errors": errors}


class Collector:
    def __init__(self, proc_root=Path("/proc"), max_threads=MAX_THREADS, max_fds=MAX_FDS):
        self.proc_root = Path(proc_root)
        self.max_threads, self.max_fds = max_threads, max_fds
        self.previous = {}

    def threads(self, base, process_key):
        try:
            tids, truncated = bounded_entries(base / "task", self.max_threads)
        except OSError as exc:
            return {"status": "unavailable", "sampled": None, **unavailable(exc)}, {}
        records, errors, current = [], [], {}
        for tid in tids:
            metric = read_value(base / "task" / str(tid) / "stat", parse_thread_stat)
            row = metric.get("value")
            if row is None or row["tid"] != tid:
                errors.append({"tid": tid, **{key: value for key, value in metric.items() if key != "value"}})
                continue
            observed = time.monotonic_ns()
            key = (*process_key, tid, row["startTicks"])
            ticks = row["userCpuTicks"] + row["systemCpuTicks"]
            previous = self.previous.get(key)
            delta = ticks - previous[0] if previous else None
            elapsed = observed - previous[1] if previous else None
            if delta is not None and (delta < 0 or elapsed <= 0):
                delta, elapsed = None, None
            row.update(observedMonotonicNs=observed, deltaCpuTicks=delta, elapsedSincePreviousNs=elapsed,
                       detailStatus="not-selected")
            current[key] = (ticks, observed)
            records.append(row)
        # All CPU counters are retained; only sixteen threads incur additional
        # wait-channel/scheduler reads. Names from stat can be kernel-truncated.
        ranked = sorted(records, key=lambda row: (
            row["deltaCpuTicks"] is not None,
            row["deltaCpuTicks"] if row["deltaCpuTicks"] is not None else row["userCpuTicks"] + row["systemCpuTicks"]), reverse=True)
        for row in ranked[:DETAIL_THREADS]:
            thread = base / "task" / str(row["tid"])
            details = {"schedstat": read_value(thread / "schedstat", parse_schedstat),
                       "wchan": read_value(thread / "wchan", lambda value: value.strip())}
            check = read_value(thread / "stat", parse_thread_stat)
            verified = check.get("value")
            if verified is None or (verified["tid"], verified["startTicks"]) != (row["tid"], row["startTicks"]):
                row["detailStatus"] = "thread-identity-lost-or-changed"
                row["detailError"] = {key: value for key, value in check.items() if key != "value"}
            else:
                row.update(details=details, detailStatus="identity-verified")
        return {"status": "partial" if truncated or errors else "ok", "limit": self.max_threads,
                "enumeratedThreads": len(tids), "sampledThreads": len(records), "truncated": truncated,
                "readFailures": len(errors), "errors": errors[:8], "sampled": records,
                "detailLimit": DETAIL_THREADS,
                "detailSelection": "top CPU tick delta where available; initial threads by cumulative CPU"}, current

    def process(self, record_path, role):
        started = time.monotonic_ns()
        result = {"recordPath": str(record_path)}
        try:
            expected = common.read_record(record_path)
        except (OSError, ValueError, TypeError) as exc:
            return {**result, "status": "record-unavailable", **unavailable(exc)}, {}
        result.update(expected)
        identity = {name: expected[name] for name in ("startTicks", "commandSha256")}
        try:
            if common.proc_identity(expected["pid"], self.proc_root) != identity:
                return {**result, "status": "identity-mismatch"}, {}
        except (OSError, ValueError, IndexError) as exc:
            return {**result, "status": "identity-unavailable", **unavailable(exc)}, {}
        base = self.proc_root / str(expected["pid"])
        key = (role, expected["pid"], expected["startTicks"], expected["commandSha256"])
        threads, previous = self.threads(base, key)
        owned, fd_scan = owned_socket_inodes(base, self.max_fds)
        udp = {family: ({"status": "ownership-scan-unavailable", "sockets": None}
                        if fd_scan["status"] == "unavailable" else udp_table(base / "net" / name, owned, family))
               for family, name in (("ipv4", "udp"), ("ipv6", "udp6"))}
        after_owned, after_scan = owned_socket_inodes(base, self.max_fds)
        for table in udp.values():
            if table.get("sockets") is None:
                continue
            if after_scan["status"] == "unavailable":
                table.update(status="ownership-recheck-unavailable", sockets=None)
                continue
            confirmed = []
            for socket in table["sockets"]:
                same_fds = sorted(set(socket["fdNumbers"]) & set(after_owned.get(socket["inode"], [])))
                if same_fds:
                    confirmed.append({**socket, "fdNumbers": same_fds, "ownershipConfirmedAfterRead": True})
            table["ownershipLostDuringRead"] = len(table["sockets"]) - len(confirmed)
            table["sockets"] = confirmed
            if table["ownershipLostDuringRead"]:
                table["status"] = "partial"
        try:
            if common.proc_identity(expected["pid"], self.proc_root) != identity:
                return {**result, "status": "identity-changed-during-read"}, {}
        except (OSError, ValueError, IndexError) as exc:
            return {**result, "status": "identity-lost-during-read", **unavailable(exc)}, {}
        return {**result, "status": "verified", "threads": threads, "fdScan": fd_scan, "fdScanAfter": after_scan,
                "udp": udp, "collectionElapsedNs": time.monotonic_ns() - started}, previous

    def sample(self, state_dir=None, load_pid_file=None, node_records=None):
        started, cpu_started = time.monotonic_ns(), time.process_time_ns()
        wall_started = datetime.now(timezone.utc).isoformat()
        if node_records:
            records = []
            for index, path in enumerate(node_records):
                parent = Path(path).parent.name
                role = parent if re.fullmatch(r"node-[012]", parent) else f"node-record-{index}"
                records.append((role, Path(path)))
            if len({role for role, path in records}) != len(records):
                raise ValueError("Duplicate node record roles")
        else:
            records = [(f"node-{index}", Path(state_dir) / f"node-{index}/process.json") for index in range(3)]
        if load_pid_file is not None:
            records.append(("load", Path(load_pid_file)))
        processes, previous = {}, {}
        for role, record in records:
            processes[role], state = self.process(record, role)
            previous.update(state)
        self.previous = previous
        return {"type": "sample", "wallTimeUtc": wall_started,
                "monotonicNs": started, "processes": processes,
                "collectionFinishedMonotonicNs": time.monotonic_ns(),
                "collectionElapsedNs": time.monotonic_ns() - started,
                "collectorCpuElapsedNs": time.process_time_ns() - cpu_started}


def system_metadata(proc_root=Path("/proc")):
    sysctl = Path(proc_root) / "sys"
    values = {f"net.core.{name}": read_value(sysctl / "net/core" / name, lambda text: common.nonnegative(text.strip()))
              for name in ("rmem_default", "rmem_max", "wmem_default", "wmem_max")}
    values.update({f"net.ipv4.{name}": read_value(sysctl / "net/ipv4" / name, lambda text: common.nonnegative(text.strip()))
                   for name in ("udp_rmem_min", "udp_wmem_min")})
    values["net.ipv4.udp_mem"] = read_value(sysctl / "net/ipv4/udp_mem", lambda text: [common.nonnegative(value) for value in text.split()])
    values["kernel.sched_schedstats"] = read_value(sysctl / "kernel/sched_schedstats", lambda text: common.nonnegative(text.strip()))
    return {"clockTicksPerSecond": os.sysconf("SC_CLK_TCK"), "pageSizeBytes": os.sysconf("SC_PAGE_SIZE"),
            "system": platform.system(), "kernel": platform.release(), "sysctls": values}


def stamp():
    return {"wallTimeUtc": datetime.now(timezone.utc).isoformat(), "monotonicNs": time.monotonic_ns()}


def run(args):
    stopped = {"signal": None}
    def stop(signum, frame):
        stopped["signal"] = signum
    handlers = {signum: signal.signal(signum, stop) for signum in (signal.SIGTERM, signal.SIGINT)}
    started, cpu_started, count = time.monotonic(), time.process_time_ns(), 0
    collector = Collector(max_threads=args.max_threads, max_fds=args.max_fds)
    try:
        with args.output.open("x", encoding="utf-8", buffering=1) as handle:
            def emit(value):
                handle.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
                handle.flush()
            emit({"type": "metadata", "schemaVersion": 1, **stamp(), "intervalSeconds": args.interval,
                  "durationSeconds": args.duration, "hardware": system_metadata(),
                  "maxThreads": args.max_threads, "maxFds": args.max_fds, "detailThreads": DETAIL_THREADS,
                  "scope": "Only explicit version=1 PID/startTicks/commandSha256 records; reverified before and after each process sample. "
                  "Missing delayed load identity is unavailable, never guessed. Thread CPU counters are cumulative USER_HZ ticks keyed by PID and TID startTicks; "
                  "comm is the kernel thread name and may be truncated. schedstat runtime/runqueue wait are nanoseconds, timeslices is a count; "
                  "zero schedstat or wchan=0 can mean disabled/restricted instrumentation, not proof of no waiting. "
                  "UDP namespace tables are streamed but only socket inodes found in verified owned PID fd symlinks are serialized; no peer endpoints, uid, "
                  "other-process rows, payload, environment or full command line. Queue fields are kernel-accounting bytes, not packets or exact payload bytes; "
                  "socket drops are cumulative and may wrap. Gauges and ownership joins are asynchronous and can miss transient queues or closing sockets. "
                  "Sysctl rmem/wmem defaults/max/min are bytes; udp_mem is pages. They do not establish a socket's effective SO_RCVBUF/SO_SNDBUF. "
                  "No attach, ptrace, TCP inspection, packet capture or configuration changes. Observer collection wall/CPU costs are reported. "
                  "Use the same observer in every compared run; finite observational samples alone do not prove causality."})
            next_sample = started
            while stopped["signal"] is None and time.monotonic() - started < args.duration:
                now = time.monotonic()
                if now < next_sample:
                    time.sleep(min(.1, next_sample - now, max(0, started + args.duration - now)))
                    continue
                row = collector.sample(args.state_dir, args.load_pid_file, getattr(args, "node_record", None))
                row.update(sequence=count, scheduledElapsedSeconds=next_sample - started)
                emit(row)
                count += 1
                next_sample += args.interval
                if next_sample < time.monotonic():
                    next_sample = started + (math.floor((time.monotonic() - started) / args.interval) + 1) * args.interval
            emit({"type": "complete", **stamp(), "samples": count, "elapsedSeconds": time.monotonic() - started,
                  "collectorCpuElapsedNs": time.process_time_ns() - cpu_started,
                  "reason": "signal" if stopped["signal"] is not None else "duration", "signal": stopped["signal"]})
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def bounded_int(value, maximum):
    parsed = int(value)
    if not 1 <= parsed <= maximum:
        raise argparse.ArgumentTypeError(f"Expected integer 1..{maximum}")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    identities = parser.add_mutually_exclusive_group(required=True)
    identities.add_argument("--state-dir", type=Path)
    identities.add_argument("--node-record", type=Path, action="append", help="Explicit node identity JSON (repeatable)")
    parser.add_argument("--load-record", "--load-pid-file", dest="load_pid_file", type=Path,
                        help="Explicit identity JSON; may appear after the observer starts")
    parser.add_argument("--output", required=True, type=Path, help="New JSONL path, never overwritten")
    parser.add_argument("--interval", default=1.0, type=lambda value: common.bounded_float(value, 1, 60))
    parser.add_argument("--duration", default=600.0, type=lambda value: common.bounded_float(value, .1, 3600))
    parser.add_argument("--max-threads", default=MAX_THREADS, type=lambda value: bounded_int(value, MAX_THREADS))
    parser.add_argument("--max-fds", default=MAX_FDS, type=lambda value: bounded_int(value, MAX_FDS))
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("This collector requires Linux /proc")
    if args.state_dir is not None and not args.state_dir.is_dir():
        parser.error("--state-dir must be an existing project state directory")
    run(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(json.dumps({"type": "fatal", **unavailable(exc)}), file=sys.stderr)
        raise SystemExit(1)
