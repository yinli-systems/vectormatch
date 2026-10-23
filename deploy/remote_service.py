#!/usr/bin/env python3
"""Small Linux process supervisor for transferred installDist bundles; no systemd needed.

PID ownership requires the same /proc start time and byte-for-byte command line.
No environment values, database credentials, or arbitrary commands enter PID records.
"""
from __future__ import annotations

import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OPENS = ["--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED",
         "--add-opens=java.base/java.util.zip=ALL-UNNAMED"]
MAINS = {"node": "io.vectormatch.cluster.ClusterNodeMain",
         "gateway": "io.vectormatch.server.WorkbenchServer",
         "projector": "io.vectormatch.projector.ProjectorMain"}


def positive_int(name: str, default: int, low: int, high: int) -> int:
    value = int(os.environ.get(name, default))
    if value < low or value > high:
        raise ValueError(f"{name} must be {low}..{high}")
    return value


def proc_identity(pid: int) -> dict | None:
    """None means gone/zombie; access and malformed-record errors fail closed."""
    try:
        # comm may contain spaces and parentheses, so split after its final ')'.
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rindex(")") + 2:].split()
        if fields[0] == "Z":
            return None
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
        if not command:
            return None
        return {"startTicks": int(fields[19]),
                "commandSha256": hashlib.sha256(command).hexdigest()}
    except (FileNotFoundError, ProcessLookupError):
        return None


def record_state(path: Path) -> tuple[str, dict | None]:
    if not path.exists():
        return "stopped", None
    record = json.loads(path.read_text())
    pid = record.get("pid")
    if type(pid) is not int or pid < 2 or record.get("version") != 1:
        raise ValueError(f"Invalid PID record: {path}")
    current = proc_identity(pid)
    if current is None:
        return "stopped", record
    if any(current[key] != record.get(key) for key in current):
        return "identity-mismatch", record
    return "running", record


@contextmanager
def locked(path: Path):
    with path.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


def write_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def distribution(component: str) -> Path:
    explicit = os.environ.get("VECTOR_DIST_ROOT")
    path = (Path(explicit).expanduser() / component if explicit else
            ROOT / "dist" / component)
    if not explicit and not (path / "lib").is_dir():
        path = ROOT / component / "build" / "install" / component
    path = path.resolve()
    if not (path / "lib").is_dir() or not any((path / "lib").glob("*.jar")):
        raise ValueError(f"Missing installDist jars: {path}/lib")
    return path


def java() -> str:
    executable = os.environ.get("VECTOR_JAVA")
    if not executable and os.environ.get("JAVA_HOME"):
        executable = str(Path(os.environ["JAVA_HOME"]) / "bin/java")
    executable = executable or shutil.which("java")
    if not executable or not os.access(executable, os.X_OK):
        raise ValueError("Java 21 is required; set JAVA_HOME or VECTOR_JAVA")
    return str(Path(executable).resolve())


def network_environment(role: str) -> dict[str, str]:
    environment = dict(os.environ)
    value = environment.get("VECTOR_CLUSTER_HOSTS", "")
    hosts = value.split(",")
    if len(hosts) != 3:
        raise ValueError("Set VECTOR_CLUSTER_HOSTS to three directly routed IPv4 addresses")
    for host in hosts:
        if ipaddress.ip_address(host).version != 4:
            raise ValueError("VECTOR_CLUSTER_HOSTS must use IPv4 addresses")
    if len(set(hosts)) != 3:
        raise ValueError("Remote cluster members must have three distinct IPv4 addresses")
    mtu = positive_int("VECTOR_AERON_MTU_LENGTH", 1248, 64, 65504)
    if mtu % 32:
        raise ValueError("VECTOR_AERON_MTU_LENGTH must be aligned to 32 bytes")
    environment["VECTOR_AERON_MTU_LENGTH"] = str(mtu)
    if role != "node":
        egress = environment.get("VECTOR_CLIENT_EGRESS_HOST", "")
        if not egress or ipaddress.ip_address(egress).version != 4:
            raise ValueError("Set VECTOR_CLIENT_EGRESS_HOST to this client's reachable private IPv4")
    return environment


def command(role: str, node: int | None, state: Path, action: str) -> tuple[list[str], dict[str, str]]:
    component = {"node": "cluster", "gateway": "server", "projector": "projector"}[role]
    dist = distribution(component)
    environment = network_environment(role) if action not in ("init", "db-status") else dict(os.environ)
    heap = os.environ.get("VECTOR_MAX_HEAP", "1g" if role == "node" else "512m")
    if not re.fullmatch(r"[1-9][0-9]*[mMgG]", heap):
        raise ValueError("VECTOR_MAX_HEAP must be a positive Java heap size such as 512m or 1g")
    args = [java(), *OPENS, f"-Xmx{heap}", f"-Dvm.process.identity={state}"]
    port = positive_int("VECTOR_PORT_BASE", 19000, 1024, 65000)
    if role == "gateway":
        args += ["-Dvm.backend=cluster", f"-Dvm.runtime={state / 'workbench'}",
                 f"-Dvm.web={Path(os.environ.get('VECTOR_WEB_DIR', ROOT / 'web/dist')).resolve()}",
                 f"-Dvm.port={positive_int('VM_HTTP_PORT', 8000, 1024, 65535)}",
                 f"-Dvm.cluster.portBase={port}"]
    args += ["-cp", str(dist / "lib/*"), MAINS[role]]
    if role == "node":
        sync = positive_int("VECTOR_SYNC_LEVEL", 2, 0, 2)
        if sync not in (0, 2):
            raise ValueError("VECTOR_SYNC_LEVEL must be 0 or 2")
        args += [str(node), str(state.parent), str(port), str(sync),
                 str(positive_int("VECTOR_OUTBOX_CAPACITY", 65536, 1, 1000000)),
                 environment["VECTOR_CLUSTER_HOSTS"]]
    if role == "projector":
        if not environment.get("VM_PG_URL") or not environment.get("VM_CLUSTER_ID"):
            raise ValueError("Set VM_PG_URL and stable VM_CLUSTER_ID; credentials belong in environment")
        environment.setdefault("VM_PROJECTOR_DRIVER", str(state / "driver"))
        environment["VM_CLUSTER_PORT_BASE"] = str(port)
        args += [{"start": "watch", "db-status": "status"}.get(action, action)]
    return args, environment


def start(role: str, node: int | None, state: Path, record_path: Path):
    status, existing = record_state(record_path)
    if status == "identity-mismatch":
        raise ValueError(f"PID identity changed; refusing to replace or signal PID {existing['pid']}")
    args, environment = command(role, node, state, "start")
    expected = hashlib.sha256(b"\0".join(os.fsencode(arg) for arg in args) + b"\0").hexdigest()
    if status == "running":
        if existing["commandSha256"] != expected:
            raise ValueError("Process already running with different arguments; stop it explicitly first")
        print(f"{state.name} already running pid={existing['pid']}")
        return
    log_path = state / "process.log"
    with log_path.open("ab", buffering=0) as log:
        child = subprocess.Popen(args, cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        current = proc_identity(child.pid)
        if current is None or current["commandSha256"] != expected:
            raise RuntimeError(f"Process identity was not established; inspect {log_path}")
        record = {"version": 1, "pid": child.pid, **current, "role": role,
                  "createdAt": datetime.now(timezone.utc).isoformat(),
                  "arguments": args, "log": str(log_path)}
        write_json(record_path, record)
    except BaseException:
        # Popen still owns this exact newly created process; no PID-file inference.
        child.terminate()
        child.wait(timeout=10)
        raise
    time.sleep(0.3)
    if child.poll() is not None:
        raise RuntimeError(f"{role} exited with code {child.returncode}; inspect {log_path}")
    print(f"{state.name} launched pid={child.pid}; log={log_path}; launch is not readiness")


def stop(state: Path, record_path: Path):
    status, record = record_state(record_path)
    if status == "stopped":
        print(f"{state.name} stopped")
        return
    if status != "running":
        raise ValueError("PID identity mismatch; refusing to signal an unrelated process")
    # pidfd binds the signal to the verified process even if its numeric PID is reused.
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise ValueError("Python/Linux pidfd support is required for safe stop")
    try:
        descriptor = os.pidfd_open(record["pid"])
    except ProcessLookupError:
        print(f"{state.name} stopped")
        return
    try:
        if record_state(record_path)[0] != "running":
            raise ValueError("Process identity changed during stop; no signal sent")
        try:
            signal.pidfd_send_signal(descriptor, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if record_state(record_path)[0] != "running":
                print(f"{state.name} stopped; persistent state preserved")
                return
            time.sleep(0.1)
        raise RuntimeError("Graceful stop timed out; inspect logs. No SIGKILL was sent")
    finally:
        os.close(descriptor)


def main():
    if sys.platform != "linux":
        raise ValueError("Remote launcher requires Linux /proc; use deploy/cluster.sh locally")
    if len(sys.argv) not in (3, 4):
        raise ValueError("Usage: remote_service.py node|gateway|projector ACTION [NODE_ID]")
    role, action = sys.argv[1:3]
    if role not in MAINS:
        raise ValueError("Role must be node, gateway, or projector")
    node = int(sys.argv[3]) if role == "node" and len(sys.argv) == 4 else None
    if role == "node" and node not in (0, 1, 2):
        raise ValueError("Node ID must be 0, 1, or 2")
    allowed = {"start", "status", "stop"}
    if role == "node":
        allowed.add("snapshot")
    if role == "projector":
        allowed.update(("init", "once", "db-status"))
    if action not in allowed:
        raise ValueError(f"Unsupported {role} action: {action}")
    state_root = Path(os.environ.get("VECTOR_STATE_DIR", ROOT / "runtime/remote")).expanduser().resolve()
    state = state_root / (f"node-{node}" if role == "node" else role)
    state.mkdir(parents=True, exist_ok=True)
    record_path = state / "process.json"
    with locked(state / "process.lock"):
        if action == "status":
            status, record = record_state(record_path)
            print(f"{state.name} {status}" + (f" pid={record['pid']}" if record else ""))
            return 0 if status != "identity-mismatch" else 1
        if action == "stop":
            stop(state, record_path)
        elif action == "start":
            start(role, node, state, record_path)
        elif action == "snapshot":
            status, _ = record_state(record_path)
            if status != "running":
                raise ValueError("Node must be running; snapshot only succeeds on the leader")
            dist = distribution("cluster")
            return subprocess.run([java(), *OPENS, "-cp", str(dist / "lib/*"),
                                   "io.aeron.cluster.ClusterTool", str(state / "cluster"),
                                   "snapshot"], cwd=ROOT, check=False).returncode
        else:
            if action == "once" and record_state(record_path)[0] == "running":
                raise ValueError("Stop this projector before running once with the same driver directory")
            args, environment = command(role, node, state, action)
            return subprocess.run(args, cwd=ROOT, env=environment, check=False).returncode
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"remote launcher: {error}", file=sys.stderr)
        sys.exit(1)
