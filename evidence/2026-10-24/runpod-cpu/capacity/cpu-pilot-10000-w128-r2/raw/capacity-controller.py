#!/usr/bin/env python3
"""CPU pilot v2: explicit in-process loopback launcher adapter; r1 stays frozen."""
from __future__ import annotations

import argparse
import base64
import ctypes
import datetime as dt
import hashlib
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
REVISION = "433f02bebe2f3109ec363291fa562d5c509c0723"
SCOPE = "SINGLE_HOST_THREE_JVM_LOOPBACK_UDP"
HOSTNAME = "ed6c0673f5cb"
POD = "4il7v4518ccogj"
REMOTE_BASE = Path("/opt/vectormatch-cpu")
RELEASE = REMOTE_BASE / "releases" / REVISION
JAVA = REMOTE_BASE / "tools/jdk/bin/java"
CONTROL_BASE = Path("/workspace/vectormatch-cpu-control")
ARCHIVE_BASE = Path("/workspace/vectormatch-cpu-archives")
ANALYSIS_ID = "31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f"
PREPARED_SHA = "2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4"
OPENS = ["--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED",
         "--add-opens=java.base/java.util.zip=ALL-UNNAMED"]
LOAD_FLAGS = ["-Dvectormatch.capacity.client.driver=shared", "-Daeron.nak.unicast.delay=1000",
              "-Dvectormatch.capacity.client.transport=multiplexed"]
TOOLS = ("scripts/verify-capacity-config.py", "scripts/check-capacity-leader.py",
         "scripts/archive-capacity-arrivals.py", "scripts/capacity-telemetry.py")
FIXED = {
    "scope": SCOPE, "portBase": 23000, "leader": 0, "syncLevel": 2,
    "nodeHeap": "2g", "loadHeap": "2g", "queuePerWorker": 64,
    "requestTimeoutMs": 2000, "drainTimeoutMs": 30000, "schedulerLatenessLimitMs": 20,
    "capacityProfile": "extended-350k-256", "stateProfile": "capacity-350k-v1",
    "outboxCapacity": 800000, "maxRetainedOrders": 360000, "resultCachePerProducer": 1024,
    "checkpointMaxBytes": 536870912, "maxClusterSessions": 256, "aeronMtuLength": 1248,
    "socketReceiveBufferArgumentBytes": 131072, "socketReceiveBufferBytes": 131072,
    "socketSendBufferBytes": 131072, "driverThreadingArgument": "SHARED", "driverThreading": "SHARED",
    "archiveThreading": "SHARED", "aeronVersion": "1.53.3",
    "nodeDataPathMaxParkNs": 1000000, "nodeDataPathIdlePolicyVersion": 1,
    "nodeDataPathIdleAgentMaxYields": 20, "nodeDataPathIdleMinParkNs": 1000,
    "driverIdleMaxSpins": 10, "driverIdleMaxYields": 5, "driverIdleMinParkNs": 1000,
    "driverIdleMaxParkNs": 1000000, "nakUnicastDelayNs": 1000,
    "clientNakUnicastDelayNs": 1000, "nakUnicastRetryDelayRatio": 100,
    "clientTransportMode": "multiplexed", "clientSessionCount": 1,
    "idleStrategy": "Explicit node driver(10,5,1000,1000000); archive/consensus/service(10,20,1000,1000000)",
}
ZERO_COUNTS = ("clientNotSentCommands", "businessRejectedCommands", "serverErrors",
               "unknownAtInitialDeadline", "unresolvedFinal", "schedulerLatenessAboveLimitCount")
LOOPBACK_DECLARATION = "VECTOR_CPU_LOOPBACK_SCOPE"
LOOPBACK_HOSTS = "127.0.0.1,127.0.0.1,127.0.0.1"


def cpu_loopback_network_environment(role):
    """Only the explicitly declared CPU single-host node topology is supported."""
    environment = dict(os.environ)
    require(role == "node", "CPU loopback adapter supports node launch only")
    require(environment.get(LOOPBACK_DECLARATION) == SCOPE, "CPU loopback adapter requires its explicit scope declaration")
    require(environment.get("VECTOR_CLUSTER_HOSTS") == LOOPBACK_HOSTS, "CPU loopback adapter requires exactly three literal127.0.0.1 addresses")
    require(environment.get("VECTOR_CLIENT_EGRESS_HOST") == "127.0.0.1", "CPU loopback adapter requires literal127.0.0.1 egress")
    require(environment.get("VECTOR_AERON_MTU_LENGTH") == "1248", "CPU loopback adapter requires explicit canonical MTU1248")
    require("VECTOR_CLIENT_EGRESS_PORT" not in environment, "CPU loopback adapter does not permit a hidden fixed egress port")
    return environment


def launcher_adapter_identity(deployment):
    source = inspect.getsource(cpu_loopback_network_environment)
    return {"schemaVersion": 1, "name": "cpu-single-host-loopback-network-v2",
            "adapterSourceSha256": hashlib.sha256(source.encode()).hexdigest(),
            "controllerSourceSha256": sha(__file__),
            "originalSupervisorSourceSha256": deployment["filesVerified"]["deploy/remote_service.py"],
            "mapping": {"replacedFunction": "network_environment", "replacement": "cpu_loopback_network_environment",
                        "scopeDeclarationName": LOOPBACK_DECLARATION, "scopeDeclarationValue": SCOPE,
                        "role": "node", "clusterHosts": LOOPBACK_HOSTS, "clientEgressHost": "127.0.0.1",
                        "aeronMtuLength": "1248", "clientEgressPort": "absent", "launch": "in-process original supervisor.start",
                        "preserved": ["start", "stop", "command", "configuration_fingerprint", "proc_identity", "await_process_identity", "locked"],
                        "originalRemoteTopologyScope": "Three distinct IPv4 remains unchanged in original supervisor; this separate CPU adapter permits only explicit loopback."}}


def install_launcher_adapter(plan, svc):
    expected = launcher_adapter_identity(plan["deployment"])
    require(plan.get("launcherAdapter") == expected, "Registered CPU loopback adapter identity/mapping differs")
    require(sha(svc.__file__) == expected["originalSupervisorSourceSha256"], "Original supervisor source bytes differ")
    require(svc.network_environment is not cpu_loopback_network_environment, "Loopback adapter already installed unexpectedly")
    preserved = {name: getattr(svc, name) for name in expected["mapping"]["preserved"]}
    svc.network_environment = cpu_loopback_network_environment
    require(all(getattr(svc, name) is value for name, value in preserved.items()), "A non-network supervisor function changed")
    return {"passed": True, **expected, "preservedFunctionObjectsVerified": True,
            "originalSupervisorSourceChanged": False, "installedAtUtc": now()}


def start_cpu_node(svc, node, state_root, environment):
    """Invoke original start/lock/argv/fingerprint in this adapter-bearing process."""
    require(type(node) is int and node in (0, 1, 2), "CPU node ID must be0/1/2")
    require(svc.network_environment is cpu_loopback_network_environment, "Explicit in-process loopback adapter is not installed")
    original_environment = dict(os.environ)
    output, error = io.StringIO(), io.StringIO()
    result = {"node": node, "invocation": "original supervisor.start in CPU controller process",
              "subprocessLauncherUsed": False, "startedAtUtc": now()}
    try:
        os.environ.clear()
        os.environ.update(environment)
        cpu_loopback_network_environment("node")  # Fail before state/child mutation.
        state = Path(state_root) / ("node-" + str(node))
        state.mkdir(parents=True, exist_ok=True)
        with redirect_stdout(output), redirect_stderr(error), svc.locked(state / "process.lock"):
            svc.start("node", node, state, state / "process.json")
        result["exitCode"] = 0
    except BaseException as failure:
        result.update(exitCode=1, errorType=type(failure).__name__, error=str(failure), traceback=traceback.format_exc())
    finally:
        os.environ.clear()
        os.environ.update(original_environment)
        result.update(stdout=output.getvalue(), stderr=error.getvalue(), completedAtUtc=now())
    return result


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Regular file required: " + str(path))
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


def value_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def job_id(value):
    require(isinstance(value, str) and re.fullmatch(r"cpu-pilot-[a-z0-9][a-z0-9-]{0,70}", value),
            "Use a unique cpu-pilot-... identifier, without paths")
    return value


def paths(ident):
    ident = job_id(ident)
    root = REMOTE_BASE / "runs" / ident
    return {"root": root, "state": root / "state", "evidence": root / "evidence",
            "trial": root / "evidence/runs" / ident, "control": CONTROL_BASE / ident,
            "archive": ARCHIVE_BASE / (ident + ".tar.gz")}


def plan_identity(plan):
    return value_sha({key: value for key, value in plan.items() if key != "planSha256"})


def validate_plan(plan, verify_controller=True):
    ident = job_id(plan.get("jobId"))
    require(ident != "cpu-pilot-10000-w128-r1", "Frozen failed r1 job cannot be reused")
    require(plan.get("controllerVersion") == 2, "Explicit CPU loopback controller version2 required")
    require(plan.get("schemaVersion") == 1 and plan.get("scope") == SCOPE, "CPU scope/schema differs")
    require(plan.get("hostname") == HOSTNAME and plan.get("podId") == POD, "CPU target differs")
    require(plan.get("sourceRevision") == REVISION and plan.get("fixed") == FIXED, "Pilot source/fixed configuration differs")
    require(plan.get("task") == {"id": ident, "rate": 10000, "arrivals": 350000, "workers": 128,
                                "phase": "cpu-single-host-strict350k-pilot", "repetition": 1}, "Only the fixed strict pilot is registered")
    require(plan.get("paths") == {key: str(value) for key, value in paths(ident).items()}, "Owned path mapping differs")
    require(plan.get("expectedPreparedSnapshotSha256") == PREPARED_SHA, "Prepared canonical baseline differs")
    require(plan.get("minimumOverlayFreeBytes") == 3 * 1024**3 and plan.get("minimumLiveFreeBytes") == 512 * 1024**2,
            "Storage safety bounds differ")
    require(plan.get("planSha256") == plan_identity(plan), "Registered plan identity differs")
    require(plan.get("analysisIdentity", {}).get("analysisIdentitySha256") == ANALYSIS_ID, "Analysis identity differs")
    analysis = plan["analysisIdentity"]
    require(value_sha({key: value for key, value in analysis.items() if key != "analysisIdentitySha256"}) == ANALYSIS_ID,
            "Analysis identity contents differ")
    require(set(plan.get("tools", {})) == set(TOOLS), "Incomplete/unexpected pinned controller tools")
    for name, row in plan["tools"].items():
        require(set(row) == {"source", "sha256", "revision"} and row["revision"] == REVISION,
                "Pinned tool source declaration differs: " + name)
        require(hashlib.sha256(row["source"].encode()).hexdigest() == row["sha256"], "Pinned source bytes differ: " + name)
    deployment = plan.get("deployment", {})
    require(deployment.get("passed") is True and deployment.get("revision") == REVISION
            and deployment.get("root") == str(RELEASE), "CPU deployment not verified")
    require(re.fullmatch(r"[a-f0-9]{64}", deployment.get("bundleSha256", "")), "Deployment bundle SHA required")
    require(set(deployment.get("filesVerified", {})).issuperset({"deploy/remote_service.py", "dist/cluster/lib/cluster-0.1.0-SNAPSHOT.jar",
                                                               "dist/cluster/lib/core-0.1.0-SNAPSHOT.jar"}), "Incomplete deployment file hashes")
    require(plan.get("launcherAdapter") == launcher_adapter_identity(deployment), "CPU loopback adapter declaration/source SHA differs")
    if verify_controller:
        require(plan.get("controllerSha256") == sha(__file__), "Registered capacity controller changed")
    return plan


def draft_plan(ident, repository=REPO):
    ident = job_id(ident)
    deployment = read(repository / "evidence/2026-10-24/runpod-cpu/deployment.json")
    identity_path = repository / "runtime/cloud/optimization-20261024/pipeline-capacity/postprocessor-identity.json"
    identity = read(identity_path)
    for name, expected in identity["files"].items():
        require(sha(Path(identity["root"]) / name) == expected, "Pinned analysis source changed: " + name)
    for name in ("sourceArchive", "validationReceipt"):
        require(sha(identity[name]["path"]) == identity[name]["sha256"], "Pinned analysis provenance changed: " + name)
    sources = {}
    for name in TOOLS:
        p = subprocess.run(["git", "show", REVISION + ":" + name], cwd=repository, capture_output=True, timeout=15)
        require(p.returncode == 0, "Cannot read exact committed tool: " + name)
        source = p.stdout.decode("utf-8")
        sources[name] = {"source": source, "sha256": hashlib.sha256(p.stdout).hexdigest(), "revision": REVISION}
    plan = {"schemaVersion": 1, "controllerVersion": 2, "jobId": ident, "registeredAtUtc": now(), "scope": SCOPE,
            "hostname": HOSTNAME, "podId": POD, "sourceRevision": REVISION,
            "task": {"id": ident, "rate": 10000, "arrivals": 350000, "workers": 128,
                     "phase": "cpu-single-host-strict350k-pilot", "repetition": 1},
            "fixed": dict(FIXED), "paths": {key: str(value) for key, value in paths(ident).items()},
            "minimumOverlayFreeBytes": 3 * 1024**3, "minimumLiveFreeBytes": 512 * 1024**2,
            "expectedPreparedSnapshotSha256": PREPARED_SHA, "deployment": deployment,
            "deploymentReceiptSha256": sha(repository / "evidence/2026-10-24/runpod-cpu/deployment.json"),
            "controllerSha256": sha(__file__), "tools": sources, "analysisIdentity": identity,
            "launcherAdapter": launcher_adapter_identity(deployment),
            "priorInvalidAttempt": {"jobId": "cpu-pilot-10000-w128-r1", "scope": "Original remote supervisor rejected repeated loopback addresses before Java node/load launch. Retained separately, never rewritten or reclassified."},
            "storageScope": "All measured Aeron/archive/state files on container overlayfs under /opt; /workspace FUSE is archive destination only. No NVMe or provider durability claim.",
            "recoveryPolicy": "One job ID, one launch, no automatic reissue/retry/prune. Query the same job after a transport timeout; retain all failures and UNKNOWN identities.",
            "configurationAdapter": "Pinned verifier unchanged. Replace only load_generator_arguments in memory with the registered CPU Java/release/evidence paths; retain all node/startup/transport/prepared checks, and require actual pendingCapacity=workers."}
    plan["planSha256"] = plan_identity(plan)
    return validate_plan(plan)


def load_arguments(plan):
    task = plan["task"]
    return [str(JAVA), *OPENS, *LOAD_FLAGS, "-Xmx2g", "-cp", str(RELEASE / "dist/cluster/lib/*"),
            "io.vectormatch.cluster.RemoteCapacityExperiment", plan["paths"]["trial"], "23000",
            str(task["rate"]), str(task["arrivals"]), str(task["workers"]), "64", "2000", "30000", "0", "20",
            "extended-350k-256"]


def clean_environment(plan):
    env = dict(os.environ)
    for name in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
        require(not env.get(name), "Hidden JVM options refused: " + name)
    for name in list(env):
        if name.startswith("VECTOR_"):
            del env[name]
    env.update({"JAVA_HOME": str(JAVA.parent.parent), "VECTOR_CLUSTER_HOSTS": "127.0.0.1,127.0.0.1,127.0.0.1",
                LOOPBACK_DECLARATION: SCOPE,
                "VECTOR_CLIENT_EGRESS_HOST": "127.0.0.1", "VECTOR_AERON_MTU_LENGTH": "1248",
                "VECTOR_SYNC_LEVEL": "2", "VECTOR_PORT_BASE": "23000", "VECTOR_DIST_ROOT": str(RELEASE / "dist"),
                "VECTOR_APPOINTED_LEADER_ID": "0", "VECTOR_MAX_CLUSTER_SESSIONS": "256", "VECTOR_MAX_HEAP": "2g",
                "VECTOR_OUTBOX_CAPACITY": "800000", "VECTOR_STATE_PROFILE": "capacity-350k-v1",
                "VECTOR_SOCKET_RECEIVE_BUFFER_BYTES": "131072", "VECTOR_DRIVER_THREADING_MODE": "SHARED",
                "VECTOR_NAK_UNICAST_DELAY_NS": "1000", "VECTOR_DATA_PATH_MAX_PARK_NS": "1000000",
                "VECTOR_STATE_DIR": plan["paths"]["state"]})
    return env


def mount_for(path, text=None):
    target = str(Path(path).resolve())
    matches = []
    for line in (Path("/proc/self/mountinfo").read_text() if text is None else text).splitlines():
        before, after = line.split(" - ", 1)
        mount = before.split()[4].replace("\\040", " ")
        if target == mount or target.startswith(mount.rstrip("/") + "/"):
            matches.append({"mount": mount, "filesystem": after.split()[0], "source": after.split()[1]})
    require(matches, "Cannot establish state filesystem")
    return max(matches, key=lambda row: len(row["mount"]))


def enable_pidfd():
    """Expose Linux pidfd on Python3.8 without changing the frozen supervisor.

    Linux x86_64 syscall table: pidfd_send_signal=424, pidfd_open=434.
    https://github.com/torvalds/linux/blob/v6.6/arch/x86/entry/syscalls/syscall_64.tbl
    This explicit process-local compatibility mapping never falls back to kill(pid).
    """
    native = callable(getattr(os, "pidfd_open", None)) and callable(getattr(signal, "pidfd_send_signal", None))
    if not native:
        require(platform.system() == "Linux" and platform.machine() == "x86_64", "Python3.8 pidfd adapter supports only Linux x86_64")
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        def syscall(number, *arguments):
            result = libc.syscall(ctypes.c_long(number), *arguments)
            if result < 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            return int(result)
        def pidfd_open(pid, flags=0):
            require(type(pid) is int and pid > 1 and flags == 0, "Invalid pidfd_open arguments")
            descriptor = syscall(434, ctypes.c_int(pid), ctypes.c_uint(0))
            os.set_inheritable(descriptor, False)
            return descriptor
        def pidfd_send_signal(descriptor, signum, siginfo=None, flags=0):
            require(type(descriptor) is int and descriptor >= 0 and siginfo is None and flags == 0,
                    "Unsupported pidfd_send_signal arguments")
            syscall(424, ctypes.c_int(descriptor), ctypes.c_int(int(signum)), ctypes.c_void_p(), ctypes.c_uint(0))
        if not callable(getattr(os, "pidfd_open", None)):
            os.pidfd_open = pidfd_open
        if not callable(getattr(signal, "pidfd_send_signal", None)):
            signal.pidfd_send_signal = pidfd_send_signal
    # A self pidfd with signal0 verifies kernel/seccomp support without sending a signal.
    descriptor = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(descriptor, 0)
    finally:
        os.close(descriptor)
    return {"mode": "python-native" if native else "linux-x86_64-syscall-python38",
            "selfPidfdSignalZeroProbePassed": True, "supervisorSourceChanged": False,
            "mapping": {"pidfd_open": 434, "pidfd_send_signal": 424} if not native else None,
            "source": "https://github.com/torvalds/linux/blob/v6.6/arch/x86/entry/syscalls/syscall_64.tbl"}


def preflight(plan):
    require(platform.system() == "Linux" and platform.node() == HOSTNAME, "Wrong OS/host; no workload launched")
    require(sys.version_info >= (3, 8), "CPU controller requires Python >=3.8")
    pidfd = enable_pidfd()
    require(mount_for(REMOTE_BASE)["filesystem"] == "overlay", "Measurement state must be on the declared overlayfs, never FUSE")
    require(shutil.disk_usage(REMOTE_BASE).free >= plan["minimumOverlayFreeBytes"], "Insufficient overlay space for complete350k state/raw evidence")
    require(shutil.disk_usage("/workspace").free >= plan["minimumOverlayFreeBytes"], "Insufficient archive destination space")
    actual_files = {}
    for name, expected in plan["deployment"]["filesVerified"].items():
        actual_files[name] = sha(RELEASE / name)
        require(actual_files[name] == expected, "Deployed artifact bytes changed: " + name)
    # Refuse every occupied topology port, not merely the first node's ingress.
    sockets = []
    try:
        for node in range(3):
            for offset in range(1, 6):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append(sock)
                sock.bind(("127.0.0.1", 23000 + node * 100 + offset))
    finally:
        for sock in sockets:
            sock.close()
    return {"timestamp": now(), "hostname": platform.node(), "python": sys.version,
            "allowedCpuIds": sorted(os.sched_getaffinity(0)), "overlay": mount_for(REMOTE_BASE),
            "archiveFilesystem": mount_for("/workspace"), "overlayFreeBytes": shutil.disk_usage(REMOTE_BASE).free,
            "artifactFileSha256": actual_files, "topologyPortsInitiallyFree": True,
            "scope": SCOPE, "pidfdCompatibility": pidfd, "cpuAffinityChanged": False, "osTuningPerformed": False}


def strict_pilot(result, load, configuration):
    errors = []
    for field in ("passed", "measurementValid", "canonicalSnapshotBytesVerified", "fixedLeaderVerified"):
        if result.get(field) is not True:
            errors.append("result." + field)
    if result.get("leaderChanged") is not False or load.get("generatorTimingInvalid") is not False:
        errors.append("leader-or-generator-invalid")
    for field in ("scheduledArrivals", "confirmedAcceptedCommands"):
        if type(load.get(field)) is not int or load[field] != 350000:
            errors.append("load." + field)
    for field in ZERO_COUNTS:
        if type(load.get(field)) is not int or load[field] != 0:
            errors.append("load." + field)
    for name, expected in (("workers", 128), ("maxServiceRequestsInFlight", 128), ("clientPendingCapacity", 128),
                           ("clientDriverCount", 1), ("clientSessionCount", 1)):
        if type(configuration.get(name)) is not int or configuration[name] != expected:
            errors.append("configuration." + name)
    for name, expected in (("clientTransportMode", "multiplexed"), ("clientDriverMode", "shared"),
                           ("clientAeronMode", "one-session-one-network-owner"), ("preparedSnapshotSha256", PREPARED_SHA)):
        if configuration.get(name) != expected:
            errors.append("configuration." + name)
    return {"passed": not errors, "errors": errors, "scope": "Strict finite pilot eligibility, not a sustained capacity ceiling"}


def copy_node_records(plan):
    trial = Path(plan["paths"]["trial"])
    for node in range(3):
        source = Path(plan["paths"]["state"]) / ("node-" + str(node))
        target = trial / ("node" + str(node))
        target.mkdir(exist_ok=True)
        for name in ("process.json", "process.log"):
            if (source / name).exists():
                shutil.copy2(source / name, target / name)


def merge_watch(plan):
    """Java owns exclusive creation of its output directory; observers stage elsewhere."""
    p = paths(plan["jobId"])
    p["trial"].mkdir(parents=True, exist_ok=True)
    for source in sorted((p["root"] / "watch").iterdir()):
        require(source.is_file() and not source.is_symlink(), "Unexpected watch entry")
        target = p["trial"] / source.name
        if target.exists():
            if source.name == "trial.json":
                # The unchanged verifier adds normalized fixed/deployment fields
                # to this derived trial; the registered original remains in watch.
                continue
            require(sha(target) == sha(source), "Refusing to replace existing Java evidence: " + source.name)
        else:
            shutil.copy2(source, target)


def checked_record(svc, record, arguments=None):
    current = svc.proc_identity(record["pid"])
    require(current is not None and all(current[name] == record.get(name) for name in current), "Owned PID/startTicks/argv identity changed")
    actual = Path("/proc") / str(record["pid"]) / "cmdline"
    argv = actual.read_bytes().split(b"\0")[:-1]
    argv = [os.fsdecode(value) for value in argv]
    expected = record.get("arguments") if arguments is None else arguments
    require(argv == expected, "Actual /proc arguments differ from registered launch")
    return {**record, "actualArguments": argv, "actualCommandSha256": current["commandSha256"], "verifiedAtUtc": now()}


def spawn_owned(svc, arguments, record_path, log_path, env):
    require(not record_path.exists(), "Refusing duplicate owned child")
    with log_path.open("xb") as log:
        child = subprocess.Popen(arguments, cwd=REMOTE_BASE, env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        expected = hashlib.sha256(b"".join(os.fsencode(arg) + b"\0" for arg in arguments)).hexdigest()
        identity = svc.await_process_identity(child, expected, log_path)
        record = {"version": 1, "pid": child.pid, **identity, "arguments": arguments, "createdAtUtc": now()}
        save_new(record_path, checked_record(svc, record))
        return child
    except BaseException:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=15)
        raise


def stop_owned(svc, record_path):
    if not record_path.exists():
        return {"record": str(record_path), "launched": False, "stopped": True}
    status, record = svc.record_state(record_path)
    require(status != "identity-mismatch", "Cannot stop reused/changed PID: " + str(record_path))
    if status == "running":
        svc.stop(record_path.parent, record_path)
    final, _ = svc.record_state(record_path)
    require(final == "stopped", "Owned process still live after stop")
    return {"record": str(record_path), "pid": record["pid"], "startTicks": record["startTicks"],
            "commandSha256": record["commandSha256"], "stopped": True, "checkedAtUtc": now()}


def run_command(arguments, env=None, timeout=60):
    p = subprocess.run(arguments, env=env, capture_output=True, text=True, timeout=timeout)
    return {"arguments": arguments, "exitCode": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
            "completedAtUtc": now()}


def members(plan, env):
    return run_command([str(JAVA), *OPENS, "-Xmx128m", "-cp", str(RELEASE / "dist/cluster/lib/*"),
                        "io.aeron.cluster.ClusterTool", str(Path(plan["paths"]["state"]) / "node-0/cluster"), "list-members"], env, 25)


def cpu_configuration_check(plan, tools_root):
    trial = Path(plan["paths"]["trial"])
    verifier = import_file("cpu_fixed_configuration", tools_root / "scripts/verify-capacity-config.py")
    expected_arguments = load_arguments(plan)
    def adapted_arguments(recorded_trial, release, extra):
        require(recorded_trial["id"] == plan["jobId"] and release == str(RELEASE)
                and extra == LOAD_FLAGS, "Unexpected verifier CPU adapter inputs")
        return list(expected_arguments)
    verifier.load_generator_arguments = adapted_arguments
    verifier.main(Path(plan["paths"]["evidence"]), include_failed_unknown=True)
    result = read(Path(plan["paths"]["evidence"]) / "configuration-verification.json")
    require(len(result.get("runs", [])) == 1 and result["runs"][0]["id"] == plan["jobId"],
            "Pinned configuration verifier did not attest the CPU trial; incompatible/missing schema")
    configuration = read(trial / "configuration.json")
    require(configuration.get("clientPendingCapacity") == configuration.get("workers") == 128,
            "Actual multiplexed pending capacity not independently recorded as workers")
    save_new(trial / "cpu-configuration-adapter.json", {
        "passed": True, "verifierSha256": sha(tools_root / "scripts/verify-capacity-config.py"),
        "controllerSha256": plan["controllerSha256"], "mapping": plan["configurationAdapter"],
        "loadArguments": expected_arguments, "pendingCapacityVerified": 128,
        "configurationVerificationSha256": sha(trial / "configuration-verification.json")})


def utc_datetime(value):
    """Python3.8 accepts microseconds; retain original Java nanosecond strings in evidence."""
    require(isinstance(value, str), "Missing observer UTC timestamp")
    normalized = re.sub(r"(\.\d{6})\d+(?=Z$|[+-]\d{2}:\d{2}$)", r"\1", value).replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    require(parsed.tzinfo is not None, "Observer timestamp must include UTC offset")
    return parsed


def latest_complete_sample(path, kind_field, timestamp_field):
    path = Path(path)
    if not path.exists():
        return None
    # An observer may be in its next write. Only complete newline-terminated
    # records participate; malformed complete records remain real failures.
    lines = path.read_text().splitlines(keepends=True)
    for line in reversed(lines):
        if not line.endswith("\n"):
            continue
        row = json.loads(line)
        if row.get(kind_field) == "sample":
            value = row.get(timestamp_field)
            utc_datetime(value)
            return value
    return None


def wait_post_samples(watch, load_completed, timeout=5, clock=None, sleep=None):
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    deadline = clock() + timeout
    targets = [("node" + str(node), Path(watch) / ("node" + str(node) + "-counters.jsonl"), "kind", "timestamp")
               for node in range(3)]
    targets.append(("telemetry", Path(watch) / "telemetry.jsonl", "type", "wallTimeUtc"))
    while True:
        observations = {name: latest_complete_sample(path, kind, timestamp) for name, path, kind, timestamp in targets}
        if all(value is not None and utc_datetime(value) >= utc_datetime(load_completed) for value in observations.values()):
            return {"passed": True, "loadCompletedAtUtc": load_completed, "postSampleWallTimes": observations,
                    "maximumWaitSeconds": timeout, "timestampComparisonPrecision": "microseconds; original timestamp strings retained"}
        require(clock() < deadline, "No complete post-load sample from every CnC and telemetry collector within5s: " + json.dumps(observations))
        sleep(.1)


def counter_identity_check(plan, load_started, load_completed):
    p = paths(plan["jobId"])
    rows = []
    for node in range(3):
        records = [json.loads(line) for line in (p["trial"] / ("node" + str(node) + "-counters.jsonl")).read_text().splitlines()]
        metadata = [row for row in records if row.get("kind") == "metadata"]
        samples = [row for row in records if row.get("kind") == "sample"]
        actual = read(p["trial"] / ("node" + str(node) + "-actual-process.json"))
        require(len(metadata) == 1 and samples, "Incomplete counter identity evidence")
        require(metadata[0].get("driverPidFromCnc") == actual["pid"]
                and metadata[0].get("driverDirectory") == str(p["state"] / ("node-" + str(node)) / "driver"),
                "CnC source is not the recorded owned node")
        require(utc_datetime(samples[0]["timestamp"]) <= utc_datetime(load_started)
                and utc_datetime(samples[-1]["timestamp"]) >= utc_datetime(load_completed), "CnC observation does not enclose the complete load/validation process")
        rows.append({"node": node, "driverPidFromCnc": actual["pid"], "firstSample": samples[0]["timestamp"],
                     "lastSample": samples[-1]["timestamp"], "samples": len(samples)})
    save_new(p["trial"] / "cpu-counter-identity.json", {"passed": True, "loadStartedAtUtc": load_started,
                                                          "loadCompletedAtUtc": load_completed, "nodes": rows})


def archive_all(root, archive):
    """Verify every regular owned file inside the gzip archive; never remove original evidence."""
    root, archive = Path(root), Path(archive)
    require(not archive.exists() and not archive.with_suffix(archive.suffix + ".partial").exists(), "Refusing existing archive")
    files = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Owned evidence symlinks cannot be archived implicitly: " + str(path))
        if path.is_file():
            files[path.relative_to(root).as_posix()] = {"bytes": path.stat().st_size, "sha256": sha(path)}
        else:
            require(path.is_dir(), "Special file in owned evidence")
    save_new(root / "full-state-manifest.json", {"files": files, "scope": "All regular job files before this manifest; no live processes or symlinks. Original overlay state retained, no prune."})
    files["full-state-manifest.json"] = {"bytes": (root / "full-state-manifest.json").stat().st_size,
                                         "sha256": sha(root / "full-state-manifest.json")}
    archive.parent.mkdir(parents=True, exist_ok=True)
    partial = archive.with_suffix(archive.suffix + ".partial")
    with tarfile.open(partial, "x:gz") as stream:
        for name in files:
            stream.add(root / name, arcname=name, recursive=False)
    with tarfile.open(partial, "r:gz") as stream:
        seen = set()
        for member in stream:
            require(member.isfile() and member.name in files and member.name not in seen, "Archive entry set differs")
            seen.add(member.name)
            h = hashlib.sha256()
            handle = stream.extractfile(member)
            while block := handle.read(1024 * 1024):
                h.update(block)
            require(h.hexdigest() == files[member.name]["sha256"] and member.size == files[member.name]["bytes"], "Archive bytes differ")
        require(seen == set(files), "Archive incomplete")
    partial.rename(archive)
    return {"path": str(archive), "bytes": archive.stat().st_size, "sha256": sha(archive),
            "files": len(files), "fullStateManifestSha256": files["full-state-manifest.json"]["sha256"],
            "verifiedAllEntries": True, "originalOverlayStatePreserved": True}


def worker(plan_path):
    plan = validate_plan(read(plan_path))
    p = paths(plan["jobId"])
    require(Path(plan_path).resolve() == p["control"] / "plan.json", "Worker requires its registered control path")
    p["root"].mkdir(parents=True, exist_ok=False)  # The durable anti-reissue guard.
    p["evidence"].mkdir(parents=True)
    p["state"].mkdir()
    watch = p["root"] / "watch"
    watch.mkdir()
    save_new(p["root"] / "plan.json", plan)
    shutil.copy2(__file__, p["root"] / "capacity-controller.py")
    receipt = {"jobId": plan["jobId"], "scope": SCOPE, "planSha256": plan["planSha256"], "startedAtUtc": now(),
               "strictPilotPassed": False, "workloadLaunched": False}
    owned = []
    svc = None
    cleanup = []
    interruption = {"signal": None, "cleaning": False}
    def interrupted(signum, _frame):
        interruption["signal"] = signum
        if not interruption["cleaning"]:
            raise RuntimeError("Controller interrupted; preserving owned cleanup and raw evidence")
    previous_signals = {signum: signal.signal(signum, interrupted) for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        save_new(p["root"] / "preflight.json", preflight(plan))
        tools_root = p["root"] / "pinned-tools"
        for name, entry in plan["tools"].items():
            path = tools_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x") as out:
                out.write(entry["source"])
            require(sha(path) == entry["sha256"], "Pinned tool transfer differs")
        svc = import_file("cpu_owned_service", RELEASE / "deploy/remote_service.py")
        save_new(p["root"] / "launcher-adapter-verification.json", install_launcher_adapter(plan, svc))
        env = clean_environment(plan)
        save_new(p["evidence"] / "campaign.json", {"scope": SCOPE, "fixed": FIXED, "planSha256": plan["planSha256"]})
        save_new(p["evidence"] / "deployment.json", plan["deployment"])
        trial = {**plan["task"], "state": str(p["state"]), "release": str(RELEASE),
                 "profile": FIXED["capacityProfile"], "queuePerWorker": 64, "scope": SCOPE,
                 "sourceRevision": REVISION, "deploymentRevision": REVISION,
                 "deploymentBundleSha256": plan["deployment"]["bundleSha256"], "fixedNodeConfiguration": FIXED,
                 "loadGeneratorRevision": REVISION, "loadGeneratorRelease": str(RELEASE),
                 "loadGeneratorBundleSha256": plan["deployment"]["bundleSha256"],
                 "loadGeneratorJvmArguments": LOAD_FLAGS, "startedAt": now()}
        save_new(watch / "trial.json", trial)
        for node in range(3):
            record = p["state"] / ("node-" + str(node)) / "process.json"
            owned.append(record)
            started = start_cpu_node(svc, node, p["state"], env)
            save_new(p["root"] / ("node" + str(node) + "-start.json"), started)
            require(started["exitCode"] == 0, "Node launch failed; preserve original logs")
            save_new(watch / ("node" + str(node) + "-actual-process.json"), checked_record(svc, read(record)))
        checker = import_file("cpu_fixed_leader", tools_root / "scripts/check-capacity-leader.py")
        deadline = time.monotonic() + 90
        attempts = p["root"] / "readiness.jsonl"
        while True:
            observation = members(plan, env)
            with attempts.open("a") as out:
                out.write(json.dumps(observation) + "\n")
            probe = p["root"] / "members-probe.json"
            probe.write_text(json.dumps(observation))
            errors = []
            if checker.members(probe, errors) is not None:
                save_new(watch / "pre-members.json", observation)
                break
            require(time.monotonic() < deadline, "Three official member views did not become ready with leader0")
            time.sleep(1)
        for node in range(3):
            args = [str(JAVA), *OPENS, "-Xmx128m", "-cp", str(RELEASE / "dist/cluster/lib/*"),
                    "io.vectormatch.cluster.CapacityCounters", str(p["state"] / ("node-" + str(node)) / "driver"),
                    str(watch / ("node" + str(node) + "-counters.jsonl")), "2400", "1000"]
            record = watch / ("node" + str(node) + "-counters-process.json")
            owned.append(record)
            spawn_owned(svc, args, record, p["root"] / ("node" + str(node) + "-counters.log"), env)
        telemetry = [sys.executable, "-B", str(tools_root / "scripts/capacity-telemetry.py"),
                     "--state-dir", str(p["state"]), "--output", str(watch / "telemetry.jsonl"),
                     "--load-pid-file", str(watch / "load-process.json"), "--interface", "lo",
                     "--interval", "1", "--duration", "2400"]
        record = watch / "telemetry-process.json"
        owned.append(record)
        spawn_owned(svc, telemetry, record, p["root"] / "telemetry.log", env)
        deadline = time.monotonic() + 30
        while True:
            ready = True
            for node in range(3):
                path = watch / ("node" + str(node) + "-counters.jsonl")
                ready = ready and path.exists() and path.read_text().count('"kind":"sample"') >= 2
            if ready:
                break
            require(time.monotonic() < deadline, "CnC observers did not collect pre-load samples")
            time.sleep(.2)
        require(not p["trial"].exists(), "Java must exclusively create the original output directory")
        load_record = watch / "load-process.json"
        owned.append(load_record)
        receipt["workloadLaunched"] = True
        receipt["loadStartedAtUtc"] = now()
        # Conservatively mark a launch attempt before a possible exec/identity failure.
        child = spawn_owned(svc, load_arguments(plan), load_record, watch / "load.log", env)
        deadline = time.monotonic() + 1800
        while child.poll() is None:
            require(time.monotonic() < deadline, "Load validation timed out; no new identities may be issued")
            require(shutil.disk_usage(REMOTE_BASE).free >= plan["minimumLiveFreeBytes"], "Overlay storage safety boundary reached")
            time.sleep(1)
        save_new(watch / "receipt.json", {"exitCode": child.returncode, "completedAt": now(), "loadConfirmedStopped": True})
        receipt["loadCompletedAtUtc"] = now()
        trial["completedAt"] = receipt["loadCompletedAtUtc"]
        (watch / "trial.json").write_text(json.dumps(trial, indent=2) + "\n")
        receipt["loadExitCode"] = child.returncode
        save_new(watch / "post-members.json", members(plan, env))
        save_new(watch / "post-load-observer-coverage.json", wait_post_samples(watch, receipt["loadCompletedAtUtc"]))
        # Stop read-only collectors before reading complete JSONL, while nodes remain available.
        for record in owned[3:-1]:
            cleanup.append(stop_owned(svc, record))
        merge_watch(plan)
        leader = checker.check_trial(p["trial"])
        save_new(p["trial"] / "fixed-leader-check.json", leader)
        require(leader["passed"], "Fixed leader/term check failed")
        counter_identity_check(plan, receipt["loadStartedAtUtc"], receipt["loadCompletedAtUtc"])
        receipt["loadAndLeaderComplete"] = True
    except BaseException as failure:
        receipt.update(errorType=type(failure).__name__, error=str(failure), traceback=traceback.format_exc())
    finally:
        interruption["cleaning"] = True
        receipt["controllerSignal"] = interruption["signal"]
        if svc is not None:
            for record in reversed(owned):
                try:
                    cleanup.append(stop_owned(svc, record))
                except BaseException as failure:
                    cleanup.append({"record": str(record), "stopped": False, "errorType": type(failure).__name__, "error": str(failure)})
            try:
                merge_watch(plan)
                copy_node_records(plan)
            except BaseException as failure:
                receipt["nodeExportError"] = str(failure)
        receipt["allOwnedProcessesStopped"] = all(row.get("stopped") is True for row in cleanup)
        if owned and not cleanup:
            receipt["allOwnedProcessesStopped"] = False
        if not receipt["allOwnedProcessesStopped"] or receipt.get("nodeExportError"):
            receipt["strictPilotPassed"] = False
        elif receipt.get("loadAndLeaderComplete"):
            # Verify final immutable log bytes after graceful node shutdown. A
            # pre-stop log hash would otherwise be invalidated by shutdown output.
            try:
                cpu_configuration_check(plan, p["root"] / "pinned-tools")
                configuration = read(p["trial"] / "configuration.json")
                require(sha(p["trial"] / "prepared-snapshot.bin") == configuration["preparedSnapshotSha256"] == PREPARED_SHA,
                        "Prepared canonical snapshot differs from registered bytes")
                result = read(p["trial"] / "result.json") if (p["trial"] / "result.json").exists() else {}
                load = read(p["trial"] / "load-result.json") if (p["trial"] / "load-result.json").exists() else {}
                assessment = strict_pilot(result, load, configuration)
                save_new(p["trial"] / "strict-pilot-check.json", assessment)
                require(receipt.get("loadExitCode") == 0 and assessment["passed"], "Strict pilot did not pass; keep failure and typed outcomes")
                receipt["strictPilotPassed"] = True
            except BaseException as failure:
                receipt["strictPilotPassed"] = False
                receipt["validationError"] = {"type": type(failure).__name__, "error": str(failure), "traceback": traceback.format_exc()}
        try:
            raw_load = read(p["trial"] / "load-result.json") if (p["trial"] / "load-result.json").exists() else {}
        except (OSError, ValueError) as failure:
            raw_load = {}
            receipt["rawLoadReadError"] = str(failure)
            receipt["strictPilotPassed"] = False
        save_new(p["root"] / "failure-evidence-status.json", {
            "scope": SCOPE, "workloadLaunched": receipt["workloadLaunched"],
            "outcomeSetStatus": ("NOT_LAUNCHED" if not receipt["workloadLaunched"] else
                                 "RAW_TERMINAL_OUTCOMES_RETAINED" if (p["trial"] / "arrivals.csv").exists() else
                                 "UNKNOWN_OUTCOME_SET_UNAVAILABLE_NO_REISSUE"),
            "unknownAtInitialDeadline": raw_load.get("unknownAtInitialDeadline"),
            "unresolvedFinal": raw_load.get("unresolvedFinal"),
            "retainedArtifacts": {name: (p["trial"] / name).is_file() for name in (
                "arrivals.csv", "backlog.csv", "configuration.json", "load-result.json", "result.json", "failure.json")},
            "note": "Missing outcome counts remain null; a controller/space/timeout abort cannot fabricate CSV rows or prove no business execution."})
        save_new(p["root"] / "all-owned-processes-stopped.json", {"passed": receipt["allOwnedProcessesStopped"], "records": cleanup})
        receipt["completedAtUtc"] = now()
        save_new(p["root"] / "receipt.json", receipt)
        archive_receipt = {"jobId": plan["jobId"], "scope": SCOPE, "planSha256": plan["planSha256"], **receipt,
                           "archiveComplete": False}
        try:
            require(receipt["allOwnedProcessesStopped"], "Archive withheld while owned processes remain live; original state retained")
            csv_path = p["trial"] / "arrivals.csv"
            if csv_path.exists() and (p["root"] / "pinned-tools/scripts/archive-capacity-arrivals.py").exists():
                try:
                    archive_tool = import_file("cpu_arrival_archive", p["root"] / "pinned-tools/scripts/archive-capacity-arrivals.py")
                    archive_tool.archive(p["trial"], sha(csv_path))
                    archive_receipt["arrivalArchivePassed"] = True
                except BaseException as failure:
                    archive_receipt["arrivalArchivePassed"] = False
                    archive_receipt["arrivalArchiveError"] = {"type": type(failure).__name__, "error": str(failure)}
                    save_new(p["root"] / "arrival-archive-error.json", archive_receipt["arrivalArchiveError"])
                    # Full original CSV/state export is still mandatory on failure.
            archive_receipt["archive"] = archive_all(p["root"], p["archive"])
            archive_receipt["archiveComplete"] = True
        except BaseException as failure:
            archive_receipt["archiveError"] = {"type": type(failure).__name__, "error": str(failure), "traceback": traceback.format_exc()}
        save_new(p["control"] / "completion.json", archive_receipt)
        print(json.dumps(archive_receipt), flush=True)
        for signum, previous in previous_signals.items():
            signal.signal(signum, previous)
    return 0 if receipt["strictPilotPassed"] and archive_receipt["archiveComplete"] and receipt["allOwnedProcessesStopped"] else 1


def remote_module():
    return import_file("cpu_capacity_remote", BASE / "remote.py")


def execute(plan_path):
    plan = validate_plan(read(plan_path))
    remote = remote_module()
    control = Path(plan["paths"]["control"])
    code = "from pathlib import Path\np=Path(" + repr(str(control)) + ")\np.mkdir(parents=True,exist_ok=False)\nprint(p)\n"
    created = remote.run("python3 -B -", input=code, timeout=30)
    require(created.returncode == 0, "Control job already exists or create failed. Query the SAME job; never resubmit: " + created.stderr)
    for local, target in ((Path(__file__), control / "capacity.py"), (Path(plan_path), control / "plan.json")):
        transferred = remote.upload(local, str(target))
        require(transferred.returncode == 0, "Controller transfer failed; query the SAME job, do not recreate")
    launch = """import hashlib,json,os,pathlib,subprocess,time
root=pathlib.Path(CONTROL)
plan=json.loads((root/'plan.json').read_text())
assert hashlib.sha256((root/'capacity.py').read_bytes()).hexdigest()==plan['controllerSha256']
with (root/'launch-attempt.json').open('x') as out:json.dump({'jobId':plan['jobId'],'planSha256':plan['planSha256']},out)
args=['python3','-B',str(root/'capacity.py'),'--worker','--plan',str(root/'plan.json')]
with (root/'controller.log').open('xb') as log:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 raw=pathlib.Path('/proc')/str(child.pid)/'stat'
 ticks=int(raw.read_text().rsplit(')',1)[1].split()[19])
 expected=hashlib.sha256(b''.join(os.fsencode(arg)+bytes([0]) for arg in args)).hexdigest()
 record={'jobId':plan['jobId'],'pid':child.pid,'startTicks':ticks,'arguments':args,'commandSha256':expected,'commandSha256Scope':'Expected argv; status verifies actual /proc bytes.','planSha256':plan['planSha256'],'scope':plan['scope']}
 with (root/'launch.json').open('x') as out:json.dump(record,out)
 print(json.dumps(record))
"""
    started = remote.run("python3 -B -", input="CONTROL=" + repr(str(control)) + "\n" + launch, timeout=30)
    require(started.returncode == 0, "Launch response incomplete; query SAME job. " + started.stderr)
    print(started.stdout)


def status(ident):
    p = paths(ident)
    code = """import hashlib,json,pathlib
root=pathlib.Path(CONTROL)
out={'jobId':JOB,'controlExists':root.is_dir()}
for name in ('launch-attempt.json','launch.json','completion.json'):
 path=root/name
 if path.exists():out[name]=json.loads(path.read_text())
launch=out.get('launch.json')
if launch:
 try:
  stat=(pathlib.Path('/proc')/str(launch['pid'])/'stat').read_text().rsplit(')',1)[1].split()
  actual=(pathlib.Path('/proc')/str(launch['pid'])/'cmdline').read_bytes()
  out['controllerIdentityAlive']=stat[0]!='Z' and int(stat[19])==launch['startTicks'] and hashlib.sha256(actual).hexdigest()==launch['commandSha256']
 except FileNotFoundError:out['controllerIdentityAlive']=False
print(json.dumps(out))
"""
    answer = remote_module().run("python3 -B -", input="CONTROL=" + repr(str(p["control"])) + "\nJOB=" + repr(ident) + "\n" + code, timeout=30)
    require(answer.returncode == 0, "Status query failed; do not reissue workload")
    print(answer.stdout)


def safe_extract(archive, target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as stream:
        seen = set()
        for member in stream:
            path = PurePosixPath(member.name)
            require(member.isfile() and not path.is_absolute() and ".." not in path.parts
                    and member.name not in seen, "Unsafe/duplicate archive member")
            seen.add(member.name)
            destination = target.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as output, stream.extractfile(member) as source:
                shutil.copyfileobj(source, output, 1024 * 1024)
    manifest = read(target / "full-state-manifest.json")
    require(seen == set(manifest["files"]) | {"full-state-manifest.json"}, "Full archive file closure differs")
    for name, identity in manifest["files"].items():
        require(sha(target / name) == identity["sha256"] and (target / name).stat().st_size == identity["bytes"], "Extracted raw state hash differs")


def collect(plan_path):
    plan = validate_plan(read(plan_path))
    remote = remote_module()
    p = paths(plan["jobId"])
    command = "python3 -B -"
    lookup = remote.run(command, input="from pathlib import Path\np=Path(" + repr(str(p["control"] / "completion.json")) + ")\nprint(p.read_text())\n", timeout=30)
    require(lookup.returncode == 0, "Job not complete; query SAME job without reissuing")
    completion = json.loads(lookup.stdout)
    require(completion.get("planSha256") == plan["planSha256"] and completion.get("archiveComplete") is True,
            "Complete same-plan archive required")
    info = completion["archive"]
    require(info["path"] == str(p["archive"]), "Unexpected remote archive path")
    local = REPO / "evidence/2026-10-24/runpod-cpu/capacity" / plan["jobId"]
    local.mkdir(parents=True, exist_ok=False)
    archive = local / (plan["jobId"] + ".tar.gz")
    require(shutil.disk_usage(local).free > info["bytes"] + 3 * 1024**3, "Insufficient local space for complete raw/state export")
    # Bounded text-only transport through remote.run; a timeout never restarts a load job.
    with archive.open("xb") as output:
        for offset in range(0, info["bytes"], 4 * 1024**2):
            code = "import base64\nwith open(" + repr(info["path"]) + ",'rb') as f:\n f.seek(" + str(offset) + ")\n print(base64.b64encode(f.read(" + str(min(4 * 1024**2, info["bytes"] - offset)) + ")).decode())\n"
            response = remote.run(command, input=code, timeout=45)
            require(response.returncode == 0, "Archive transport failed; retain partial export and query SAME job")
            output.write(base64.b64decode(response.stdout.strip(), validate=True))
    require(archive.stat().st_size == info["bytes"] and sha(archive) == info["sha256"], "Downloaded archive SHA differs")
    save_new(local / "completion.json", completion)
    extracted = local / "raw"
    safe_extract(archive, extracted)
    identity = plan["analysisIdentity"]
    for name, expected in identity["files"].items():
        require(sha(Path(identity["root"]) / name) == expected, "Independent analysis source changed")
    for name in ("sourceArchive", "validationReceipt"):
        require(sha(identity[name]["path"]) == identity[name]["sha256"], "Independent analysis provenance changed")
    python = identity["python"]
    require(sha(python["resolvedExecutable"]) == python["binarySha256"], "Pinned analysis Python changed")
    analysis = local / "analysis"
    require(not analysis.exists(), "Refusing analysis evidence overwrite")
    arguments = [python["executable"], "-I", "-B", str(Path(identity["root"]) / identity["entryPoint"]),
                 "--runs-dir", str(extracted / "evidence/runs"), "--output-dir", str(analysis),
                 "--campaign", str(extracted / "evidence/campaign.json")]
    result = run_command(arguments, timeout=120)
    save_new(local / "postprocess.json", {**result, "analysisIdentitySha256": ANALYSIS_ID,
                                         "analysisIdentity": identity, "scope": SCOPE})
    require(result["exitCode"] == 0, "Pinned independent analysis failed; raw evidence retained")
    summary = read(analysis / "summary.json")
    require(len(summary["trials"]) == 1, "Unexpected analysis trial set")
    print(json.dumps({"jobId": plan["jobId"], "strictPilotPassed": completion["strictPilotPassed"],
                      "measurementValid": summary["trials"][0]["measurementValid"], "local": str(local), "scope": SCOPE}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument("--register", action="store_true")
    commands.add_argument("--execute", action="store_true")
    commands.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    commands.add_argument("--status", action="store_true")
    commands.add_argument("--collect", action="store_true")
    parser.add_argument("--job-id", default="cpu-pilot-10000-w128-r2")
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args(argv)
    if args.worker or args.execute or args.collect:
        require(args.plan is not None, "An explicit registered --plan is required")
        return worker(args.plan) if args.worker else execute(args.plan) if args.execute else collect(args.plan)
    if args.status:
        return status(job_id(args.job_id))
    plan = draft_plan(args.job_id)
    if args.register:
        target = args.plan or REPO / "evidence/2026-10-24/runpod-cpu/registrations" / (args.job_id + ".json")
        save_new(target, plan)
        print(json.dumps({"registered": str(target), "planSha256": plan["planSha256"], "scope": SCOPE, "networkUsed": False}))
    else:
        print(json.dumps({key: value for key, value in plan.items() if key not in ("tools", "analysisIdentity", "deployment")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
