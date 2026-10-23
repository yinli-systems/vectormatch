#!/usr/bin/env python3
"""One-shot read-only ss probe; archive only verified project-owned UDP sockets.

No packet capture, process attach, socket mutation, sysctl changes, or raw ss
output is saved. ss can internally fall back to /proc; this is not netlink-only.
Run outside the capacity window, identically in both compared configurations.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import time
from datetime import datetime, timezone


ROLES = {"archive": 1, "ingress": 2, "consensus": 3, "log": 4, "catchup": 5}
MAX_FDS = 4096
MAX_STDOUT = 262144
MAX_STDERR = 16384
TIMEOUT_SECONDS = 3
CGROUP2_WARNING = b"Failed to find cgroup2 mount\n"


def ss_diagnostics(stderr, exit_code):
    """Allow only the exact observed non-socket cgroup metadata warning."""
    lines = stderr.splitlines(keepends=True)
    if exit_code != 0 or any(line != CGROUP2_WARNING for line in lines):
        raise ValueError("ss-error-or-diagnostic")
    return {"diagnosticCodes": ["SS_CGROUP2_MOUNT_METADATA_WARNING"] if lines else [],
            "diagnosticLineCount": len(lines)}


def identity(pid):
    text = Path(f"/proc/{pid}/stat").read_text()
    fields = text[text.rindex(")") + 2:].split()
    if fields[0] == "Z":
        raise ValueError("process-not-live")
    return {"startTicks": int(fields[19]),
            "commandSha256": hashlib.sha256(Path(f"/proc/{pid}/cmdline").read_bytes()).hexdigest()}


def sockets(pid):
    result = {}
    # Enumerate this explicit process only; never use ss -p or global /proc walks.
    with os.scandir(f"/proc/{pid}/fd") as entries:
        count = 0
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            count += 1
            if count > MAX_FDS:
                raise ValueError("fd-scan-limit")
            try:
                target = os.readlink(entry.path)
            except FileNotFoundError:
                continue  # Closed sockets are removed again by the second join.
            match = re.fullmatch(r"socket:\[(\d+)\]", target)
            if match:
                result.setdefault(int(match[1]), set()).add(int(entry.name))
    return result


def bounded_ss(arguments):
    """Capture bounded bytes only in RAM; raw stderr is never serialized."""
    process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    output, diagnostic = bytearray(), bytearray()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("ss-deadline")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 16384)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.data == "stdout":
                        if len(output) + len(chunk) > MAX_STDOUT:
                            raise ValueError("ss-stdout-limit")
                        output.extend(chunk)
                    else:
                        if len(diagnostic) + len(chunk) > MAX_STDERR:
                            raise ValueError("ss-stderr-limit")
                        diagnostic.extend(chunk)
        code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        safe_diagnostics = ss_diagnostics(bytes(diagnostic), code)
        return output.decode("utf-8", errors="strict"), safe_diagnostics
    finally:
        if process.poll() is None:
            process.terminate()  # Only this probe's own ss child, never the node.
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.5)
        process.stdout.close()
        process.stderr.close()


def parse_owned(text, before, after, ports, bind_address):
    result = []
    for line in text.splitlines():
        matches = re.findall(r"(?:^|\s)ino:([0-9]+)(?=\s|$)", line)
        if len(matches) != 1:
            raise ValueError("ss-missing-or-ambiguous-inode")
        inode = int(matches[0])
        fds = before.get(inode, set()) & after.get(inode, set())
        if not fds:
            continue
        fields = line.split()
        if fields and fields[0] in ("udp", "udp4"):
            fields = fields[1:]
        if len(fields) < 5:
            raise ValueError("ss-owned-row-format")
        state, receive_queue, send_queue, local, peer = fields[:5]
        # The planned ingress/log receivers are unconnected. Reject surprises;
        # do not retain the peer address in either success or error evidence.
        if peer not in ("0.0.0.0:*", "0.0.0.0:0", "*:*"):
            raise ValueError("ss-owned-unexpected-peer")
        address, port_text = local.rsplit(":", 1)
        port = int(port_text)
        if address != bind_address or port not in ports:
            raise ValueError("ss-owned-unexpected-bind")
        groups = re.findall(r"skmem:\(([^)]+)\)", line)
        if len(groups) != 1:
            raise ValueError("ss-owned-memory-unavailable")
        memory = {}
        for item in groups[0].split(","):
            match = re.fullmatch(r"(rb|tb|bl|r|t|f|w|o|d)([0-9]+)", item)
            if not match or match[1] in memory:
                raise ValueError("ss-owned-memory-format")
            memory[match[1]] = int(match[2])
        if not memory.get("rb") or not memory.get("tb"):
            raise ValueError("ss-owned-buffer-limits-unavailable")
        if not receive_queue.isdecimal() or not send_queue.isdecimal():
            raise ValueError("ss-owned-queue-format")
        result.append({"inode": inode, "fdNumbers": sorted(fds), "role": ports[port],
                       "localAddress": address, "localPort": port, "state": state,
                       "receiveBufferKernelBytes": memory["rb"], "sendBufferKernelBytes": memory["tb"],
                       "receiveQueueKernelBytes": int(receive_queue), "sendQueueKernelBytes": int(send_queue),
                       "receiveAllocatedKernelBytes": memory.get("r"), "socketDrops": memory.get("d")})
    if len({row["inode"] for row in result}) != len(result):
        raise ValueError("ss-duplicate-owned-inode")
    return sorted(result, key=lambda row: (row["localPort"], row["inode"]))


def probe(options):
    record = json.loads(options.node_record.read_text())
    pid = record.get("pid")
    if (record.get("version") != 1 or type(pid) is not int or pid < 2
            or type(record.get("startTicks")) is not int or record["startTicks"] < 1
            or not re.fullmatch(r"[a-f0-9]{64}", record.get("commandSha256", ""))):
        raise ValueError("invalid-process-record")
    expected = {key: record[key] for key in ("startTicks", "commandSha256")}
    if identity(pid) != expected:
        raise ValueError("process-identity-mismatch-before")
    if os.readlink(f"/proc/{pid}/ns/net") != os.readlink("/proc/self/ns/net"):
        raise ValueError("different-network-namespace")
    before = sockets(pid)
    ports = {options.port_base + 100 * options.node + ROLES[role]: role for role in options.roles}
    expression = "( " + " or ".join("sport = :" + str(port) for port in sorted(ports)) + " )"
    executable = shutil.which("ss", path="/usr/sbin:/usr/bin:/sbin:/bin")
    if executable is None:
        raise ValueError("ss-unavailable")
    argv = [executable, "-4", "-u", "-a", "-n", "-m", "-e", "-H", "-O", expression]
    text, diagnostic = bounded_ss(argv)
    after = sockets(pid)
    if identity(pid) != expected:
        raise ValueError("process-identity-mismatch-after")
    rows = parse_owned(text, before, after, ports, options.bind_address)
    for role in options.required_roles:
        if len([row for row in rows if row["role"] == role]) != 1:
            raise ValueError("required-owned-role-missing-or-ambiguous")
    return {"passed": True, "pid": pid, **expected, **diagnostic, "ssBinary": executable,
            "filteredPorts": sorted(ports), "sockets": rows, "node": options.node}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-record", type=Path, required=True)
    parser.add_argument("--node", type=int, choices=(0, 1, 2), required=True)
    parser.add_argument("--port-base", type=int, default=23000)
    parser.add_argument("--bind-address", required=True)
    parser.add_argument("--roles", default="ingress,log")
    parser.add_argument("--required-roles", default="ingress")
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    options.roles = options.roles.split(",")
    options.required_roles = options.required_roles.split(",")
    if (not 1024 <= options.port_base <= 65330 or not options.roles
            or len(set(options.roles)) != len(options.roles)
            or any(role not in ROLES for role in options.roles)
            or not options.required_roles or not set(options.required_roles) <= set(options.roles)
            or ipaddress.ip_address(options.bind_address).version != 4):
        parser.error("Invalid explicit topology or role bounds")
    # Exclusive creation prevents replacing any existing observation.
    fd = os.open(options.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    started = time.monotonic_ns()
    try:
        result = probe(options)
    except Exception as error:
        allowed = {"process-not-live", "fd-scan-limit", "ss-deadline", "ss-stdout-limit", "ss-stderr-limit",
                   "ss-error-or-diagnostic", "ss-missing-or-ambiguous-inode", "ss-owned-row-format",
                   "ss-owned-unexpected-peer", "ss-owned-unexpected-bind", "ss-owned-memory-unavailable",
                   "ss-owned-memory-format", "ss-owned-buffer-limits-unavailable", "ss-owned-queue-format",
                   "ss-duplicate-owned-inode", "invalid-process-record", "process-identity-mismatch-before",
                   "process-identity-mismatch-after", "different-network-namespace", "ss-unavailable",
                   "required-owned-role-missing-or-ambiguous"}
        message = str(error)
        result = {"passed": False, "errorType": type(error).__name__,
                  "error": message if message in allowed else "probe-unavailable-or-malformed"}
    result.update(schemaVersion=1, observedAtUtc=datetime.now(timezone.utc).isoformat(),
                  elapsedNs=time.monotonic_ns() - started,
                  scope="Read-only port-filtered ss; ss may internally use namespace /proc fallback. Only sockets owned by the explicit verified node PID and stable FD/inode before/after are retained. rb/tb are Linux kernel memory limits, often doubled relative to requested SO_RCVBUF/SO_SNDBUF; not exact payload capacity. No peer, raw ss output, stderr, uid, cookie, environment, capture, attach or mutation is archived.")
    with os.fdopen(fd, "w") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
