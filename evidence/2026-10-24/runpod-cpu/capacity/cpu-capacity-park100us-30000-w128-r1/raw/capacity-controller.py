#!/usr/bin/env python3
"""CPU fixed-node100us finite capacity curve; local draft/register, explicit one-point execution only."""
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
    "nodeDataPathMaxParkNs": 100000, "nodeDataPathIdlePolicyVersion": 1,
    "nodeDataPathIdleAgentMaxYields": 20, "nodeDataPathIdleMinParkNs": 1000,
    "driverIdleMaxSpins": 10, "driverIdleMaxYields": 5, "driverIdleMinParkNs": 1000,
    "driverIdleMaxParkNs": 100000, "nakUnicastDelayNs": 1000,
    "clientNakUnicastDelayNs": 1000, "nakUnicastRetryDelayRatio": 100,
    "clientTransportMode": "multiplexed", "clientSessionCount": 1,
    "idleStrategy": "Explicit node driver(10,5,1000,100000); archive/consensus/service(10,20,1000,100000)",
}
ZERO_COUNTS = ("clientNotSentCommands", "businessRejectedCommands", "serverErrors",
               "unknownAtInitialDeadline", "unresolvedFinal", "schedulerLatenessAboveLimitCount")
BASE_V2_SHA256 = "89a5517c0fbe7998512208554630b3a34286ee3524bad27e226a75dedbaadd98"
PILOT_ID = "cpu-pilot-10000-w128-r2"
BASE_MATRIX_SHA256 = "99f093d87c9aa342b9bbc6c1f558faa1e4385786754e7413142beab15ab2d824"
BASELINE_IDS = ("cpu-capacity-13000-w128-r1", "cpu-capacity-13000-w128-r2")
BASE_IDLE_SHA256 = "2a9b9d64137c192ca19f26d5717278e07795a54fbf703371f9fd11f199831300"
BASE_IDLE_MATRIX_ID = "cpu-node-idle-18000-w128-abab-433-r1"
MATRIX_ID = "cpu-node-park100us-capacity-433-r1"
MATRIX_PHASE = "cpu-single-host-fixed-node-100us-capacity-curve"
LOOPBACK_DECLARATION = "VECTOR_CPU_LOOPBACK_SCOPE"
LOOPBACK_HOSTS = "127.0.0.1,127.0.0.1,127.0.0.1"
VARIABLE_FIXED_FIELDS = ("nodeDataPathMaxParkNs", "driverIdleMaxParkNs", "idleStrategy")
NODE_IDLE_ROLES = ("driver-shared", "driver-sender", "driver-receiver", "driver-conductor",
                   "driver-native-resource", "archive-shared", "consensus", "service")


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
    require(isinstance(value, str) and re.fullmatch(r"cpu-capacity-[a-z0-9][a-z0-9-]{0,70}", value),
            "Use a unique cpu-capacity-... identifier, without paths")
    return value


def matrix_tasks():
    return [{"id": "cpu-capacity-park100us-" + str(rate) + "-w128-r" + str(repetition),
             "stage": "R" + str(repetition) + "-" + str(rate), "group": "park100us",
             "rate": rate, "arrivals": 350000, "workers": 128, "phase": MATRIX_PHASE,
             "repetition": repetition, "nodeMaxParkNs": 100000}
            for repetition in (1, 2) for rate in (22000, 26000, 30000, 34000)]


def fixed_for_task(task):
    require(task == task_for_id(task["id"]), "Unregistered idle task")
    maximum = task["nodeMaxParkNs"]
    return {**FIXED, "nodeDataPathMaxParkNs": maximum, "driverIdleMaxParkNs": maximum,
            "idleStrategy": "Explicit node driver(10,5,1000," + str(maximum)
                            + "); archive/consensus/service(10,20,1000," + str(maximum) + ")"}


def common_fixed():
    return dict(FIXED)


def idle_declaration(task):
    return {"scope": "FIXED_NODE_100US_CAPACITY_CURVE", "nodeMaxParkNs": task["nodeMaxParkNs"],
            "changedFixedFields": list(VARIABLE_FIXED_FIELDS), "nodeEnvironmentName": "VECTOR_DATA_PATH_MAX_PARK_NS",
            "nodeJvmProperty": "vectormatch.node.dataPathMaxParkNs", "roleClasses": list(NODE_IDLE_ROLES),
            "clientNodePolicyEnvironmentHeldAtOriginalNs": 1000000,
            "unchanged": "Source433 node/load artifacts, node spins/yields/minPark, all client driver/scheduler/NAK, leader0, sync2, heap2g, W128/Q64, MTU1248, profile/prepared state; node maxPark stays100us for all eight points; only arrival rate/repetition varies."}


def task_for_id(ident):
    matches = [task for task in matrix_tasks() if task["id"] == ident]
    require(len(matches) == 1, "Only the eight preregistered fixed100us curve point IDs are supported")
    return matches[0]


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
    require(plan.get("baseIdleControllerSha256") == BASE_IDLE_SHA256, "Frozen idle source identity differs")
    validate_idle_prerequisite_declaration(plan.get("nodeIdlePrerequisite", {}))
    require(plan.get("controllerVersion") == 5 and plan.get("baseControllerSha256") == BASE_V2_SHA256
            and plan.get("baseMatrixControllerSha256") == BASE_MATRIX_SHA256,
            "Explicit curve controller/frozen idle, matrix and v2 source identity required")
    require(plan.get("schemaVersion") == 1 and plan.get("scope") == SCOPE, "CPU scope/schema differs")
    require(plan.get("hostname") == HOSTNAME and plan.get("podId") == POD, "CPU target differs")
    require(plan.get("sourceRevision") == REVISION and plan.get("fixed") == fixed_for_task(task_for_id(ident)), "Point source/fixed idle configuration differs")
    require(plan.get("task") == task_for_id(ident), "Node-only idle task/configuration differs")
    require(plan.get("nodeIdleVariant") == idle_declaration(plan["task"]), "Node-only idle declaration differs")
    require(isinstance(plan.get("pilotPrerequisite"), dict) and plan["pilotPrerequisite"].get("jobId") == PILOT_ID,
            "Exact10k r2 pilot and paired13k baseline prerequisite required")
    validate_prerequisite_declaration(plan["pilotPrerequisite"])
    require(plan.get("paths") == {key: str(value) for key, value in paths(ident).items()}, "Owned path mapping differs")
    require(plan.get("expectedPreparedSnapshotSha256") == PREPARED_SHA, "Prepared canonical baseline differs")
    require(plan.get("minimumOverlayFreeBytes") == 3 * 1024**3 and plan.get("minimumLiveFreeBytes") == 512 * 1024**2,
            "Storage safety bounds differ")
    require(plan.get("archiveCompressionLevel") == 1, "Matrix archive compression setting differs")
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


def draft_plan(ident, repository=REPO, prerequisite=None, idle_prior=None):
    ident = job_id(ident)
    task = task_for_id(ident)
    require(sha(BASE / "capacity_idle.py") == BASE_IDLE_SHA256, "Frozen idle controller changed")
    require(sha(BASE / "capacity_v2.py") == BASE_V2_SHA256, "Frozen v2 source changed")
    require(sha(BASE / "capacity_matrix.py") == BASE_MATRIX_SHA256, "Frozen matrix source changed")
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
    plan = {"schemaVersion": 1, "controllerVersion": 5, "baseControllerSha256": BASE_V2_SHA256,
            "baseMatrixControllerSha256": BASE_MATRIX_SHA256,
            "baseIdleControllerSha256": BASE_IDLE_SHA256,
            "nodeIdlePrerequisite": idle_prior if idle_prior is not None else {"ready": False},
            "jobId": ident, "registeredAtUtc": now(), "scope": SCOPE,
            "hostname": HOSTNAME, "podId": POD, "sourceRevision": REVISION,
            "task": task, "pilotPrerequisite": prerequisite if prerequisite is not None else {"jobId": PILOT_ID, "ready": False},
            "fixed": fixed_for_task(task), "paths": {key: str(value) for key, value in paths(ident).items()},
            "minimumOverlayFreeBytes": 3 * 1024**3, "minimumLiveFreeBytes": 512 * 1024**2,
            "expectedPreparedSnapshotSha256": PREPARED_SHA, "deployment": deployment,
            "deploymentReceiptSha256": sha(repository / "evidence/2026-10-24/runpod-cpu/deployment.json"),
            "controllerSha256": sha(__file__), "tools": sources, "analysisIdentity": identity,
            "launcherAdapter": launcher_adapter_identity(deployment),
            "nodeIdleVariant": idle_declaration(task),
            "trialGateScope": "Canonical/timing/configuration/owned-stop/complete archive required. Queue-full/drain-not-sent overload is allowed, initial/final UNKNOWN or invalid evidence stops the matrix. Local31e4 analysis must pass before the next point.",
            "archiveCompressionLevel": 1,
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
                "VECTOR_NAK_UNICAST_DELAY_NS": "1000", "VECTOR_DATA_PATH_MAX_PARK_NS": str(plan["fixed"]["nodeDataPathMaxParkNs"]),
                "VECTOR_STATE_DIR": plan["paths"]["state"]})
    return env


def client_environment(plan, environment):
    """Keep the load process environment at the frozen matrix's original value.

    This is a node-only namespace; no new client idle property is introduced.
    In particular B's node100us setting must not leak into the load JVM.
    """
    require(environment.get("VECTOR_DATA_PATH_MAX_PARK_NS") == str(plan["fixed"]["nodeDataPathMaxParkNs"]),
            "Node environment does not match point registration")
    return {**environment, "VECTOR_DATA_PATH_MAX_PARK_NS": "1000000"}


def actual_idle_check(plan, verifier, trial):
    fixed = fixed_for_task(plan["task"])
    require(plan["fixed"] == fixed, "Point fixed idle mapping changed")
    require(read(trial / "trial.json").get("fixedNodeConfiguration") == fixed, "Normalized trial idle mapping differs")
    require(not any("vectormatch.node.dataPath" in value for value in load_arguments(plan)),
            "Node-only idle JVM property leaked to load generator")
    nodes = []
    for node in range(3):
        process_path = trial / ("node" + str(node)) / "process.json"
        startup_path = trial / ("node" + str(node)) / "process.log"
        process = read(process_path)
        startup = startup_path.read_text()
        # Original pinned433 verifier checks every actual instance and every
        # driver/startup field, including false runnerSelected driver instances.
        verifier.verify_node_data_path_jvm_arguments(process["arguments"], fixed)
        verifier.verify_node_data_path_startup(fixed, startup, node)
        instances = [dict(re.findall(r"(?:^|\s)([A-Za-z][A-Za-z0-9]*)=([^\s]+)", line))
                     for line in startup.splitlines() if line.startswith("VECTOR_NODE_DATA_PATH_IDLE ")]
        require(set(row["role"] for row in instances) == set(NODE_IDLE_ROLES), "Incomplete actual eight role classes")
        expected_counts = {role: (2 if role in ('archive-shared', 'consensus', 'service') else 1) for role in NODE_IDLE_ROLES}
        require(len(instances) == 11 and len({row['instanceId'] for row in instances}) == 11
                and {role: sum(row['role'] == role for row in instances) for role in NODE_IDLE_ROLES} == expected_counts,
                'Expected exactly11 distinct actual instances across8 role classes')
        nodes.append({"node": node, "processSha256": sha(process_path), "startupSha256": sha(startup_path),
                      "actualIdleInstances": instances, "roleClassCount": 8, "distinctInstanceCount": len(instances)})
    return {"passed": True, "nodeMaxParkNs": plan["task"]["nodeMaxParkNs"], "nodes": nodes,
            "fixed": fixed, "nodeIdleVariant": plan["nodeIdleVariant"],
            "scope": "Pinned433 validation of all actual distinct node idle instances across eight role classes. Supplier roles may construct multiple instances; class count is not instance count. No client scheduler/driver tuning."}


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
    pilot = plan.get("pilotPrerequisite", {})
    require(pilot.get("ready") is True, "Complete strict r2 pilot/local analysis prerequisite is missing; no launch")
    remote_pilot = read(CONTROL_BASE / PILOT_ID / "completion.json")
    require(value_sha(remote_pilot) == pilot.get("completionContentSha256")
            and remote_pilot.get("strictPilotPassed") is True and remote_pilot.get("archiveComplete") is True
            and remote_pilot.get("allOwnedProcessesStopped") is True, "Remote r2 pilot completion differs or is incomplete")
    require(sha(remote_pilot["archive"]["path"]) == pilot.get("archiveSha256"), "Remote complete pilot archive changed")
    verify_remote_13000_baselines(pilot)
    verify_remote_idle_prerequisite(plan["nodeIdlePrerequisite"])
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


def matrix_trial_check(result, load, configuration):
    errors = []
    for field in ("passed", "measurementValid", "canonicalSnapshotBytesVerified", "fixedLeaderVerified"):
        if result.get(field) is not True:
            errors.append("result." + field)
    if result.get("leaderChanged") is not False or load.get("generatorTimingInvalid") is not False:
        errors.append("leader-or-generator-invalid")
    if type(load.get("scheduledArrivals")) is not int or load["scheduledArrivals"] != 350000:
        errors.append("load.scheduledArrivals")
    if type(load.get("confirmedAcceptedCommands")) is not int or not 0 <= load["confirmedAcceptedCommands"] <= 350000:
        errors.append("load.confirmedAcceptedCommands")
    for field in ZERO_COUNTS:
        if type(load.get(field)) is not int or not 0 <= load[field] <= 350000:
            errors.append("load." + field)
    for field in ("unknownAtInitialDeadline", "unresolvedFinal", "schedulerLatenessAboveLimitCount"):
        if load.get(field) != 0:
            errors.append("matrix-continuation-forbidden." + field)
    terminal = ("confirmedAcceptedCommands", "businessRejectedCommands", "serverErrors", "clientNotSentCommands", "unresolvedFinal")
    if all(type(load.get(field)) is int for field in terminal) and sum(load[field] for field in terminal) != 350000:
        errors.append("terminal-outcome-count-conservation")
    for name, expected in (("workers", 128), ("maxServiceRequestsInFlight", 128), ("clientPendingCapacity", 128),
                           ("clientDriverCount", 1), ("clientSessionCount", 1)):
        if type(configuration.get(name)) is not int or configuration[name] != expected:
            errors.append("configuration." + name)
    for name, expected in (("clientTransportMode", "multiplexed"), ("clientDriverMode", "shared"),
                           ("clientAeronMode", "one-session-one-network-owner"), ("preparedSnapshotSha256", PREPARED_SHA)):
        if configuration.get(name) != expected:
            errors.append("configuration." + name)
    return {"passed": not errors, "errors": errors, "scope": "Finite matrix trial continuation gate. Canonical overload allowed; no initial/final UNKNOWN, invalid timing or incomplete outcomes. Local31e4 analysis remains mandatory before a next point."}


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
    require(configuration.get("ratePerSecond") == plan["task"]["rate"]
            and configuration.get("scheduledArrivals") == plan["task"]["arrivals"] == 350000,
            "Actual capacity point arrival rate/count differs from registration")
    save_new(trial / "cpu-configuration-adapter.json", {
        "passed": True, "verifierSha256": sha(tools_root / "scripts/verify-capacity-config.py"),
        "controllerSha256": plan["controllerSha256"], "mapping": plan["configurationAdapter"],
        "loadArguments": expected_arguments, "pendingCapacityVerified": 128,
        "targetArrivalRateVerified": plan["task"]["rate"],
        "configurationVerificationSha256": sha(trial / "configuration-verification.json")})
    save_new(trial / "node-idle-variant-verification.json", actual_idle_check(plan, verifier, trial))


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
    with tarfile.open(partial, "x:gz", compresslevel=1) as stream:
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
               "matrixTrialPassed": False, "workloadLaunched": False}
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
        save_new(p["evidence"] / "campaign.json", {"scope": SCOPE, "fixed": plan["fixed"], "planSha256": plan["planSha256"]})
        save_new(p["evidence"] / "deployment.json", plan["deployment"])
        trial = {**plan["task"], "state": str(p["state"]), "release": str(RELEASE),
                 "profile": plan["fixed"]["capacityProfile"], "queuePerWorker": 64, "scope": SCOPE,
                 "sourceRevision": REVISION, "deploymentRevision": REVISION,
                 "deploymentBundleSha256": plan["deployment"]["bundleSha256"], "fixedNodeConfiguration": plan["fixed"],
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
        child = spawn_owned(svc, load_arguments(plan), load_record, watch / "load.log", client_environment(plan, env))
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
            receipt["matrixTrialPassed"] = False
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
                require(load.get("targetArrivalRatePerSecond") == plan["task"]["rate"], "Raw load-summary rate differs from registered point")
                assessment = matrix_trial_check(result, load, configuration)
                save_new(p["trial"] / "matrix-trial-check.json", assessment)
                require(receipt.get("loadExitCode") == 0 and assessment["passed"], "Matrix point is UNKNOWN/nonvalid; keep failure and typed outcomes")
                receipt["matrixTrialPassed"] = True
            except BaseException as failure:
                receipt["matrixTrialPassed"] = False
                receipt["validationError"] = {"type": type(failure).__name__, "error": str(failure), "traceback": traceback.format_exc()}
        try:
            raw_load = read(p["trial"] / "load-result.json") if (p["trial"] / "load-result.json").exists() else {}
        except (OSError, ValueError) as failure:
            raw_load = {}
            receipt["rawLoadReadError"] = str(failure)
            receipt["matrixTrialPassed"] = False
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
    return 0 if receipt["matrixTrialPassed"] and archive_receipt["archiveComplete"] and receipt["allOwnedProcessesStopped"] else 1


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
    # One binary SSH stream, followed by the same whole-archive and every-file
    # checks. Transfer cannot issue a workload and timeout never resubmits a job.
    with archive.open("xb") as output:
        transferred = subprocess.run([*remote.sshargs(), "cat -- " + shlex.quote(info["path"])],
                                     stdout=output, stderr=subprocess.PIPE, timeout=600)
    require(transferred.returncode == 0, "Archive transport failed; retain partial export and query SAME job: " + transferred.stderr.decode(errors="replace"))
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
    print(json.dumps({"jobId": plan["jobId"], "matrixTrialPassed": completion["matrixTrialPassed"],
                      "measurementValid": summary["trials"][0]["measurementValid"], "local": str(local), "scope": SCOPE}))
    return {"directory": str(local), "completion": completion, "summary": summary}


def strict_10000_prerequisite(repository=REPO, required=False):
    """Require complete r2 canonical/owned/archive/local31e4 closure before execution."""
    prefix = repository / "evidence/2026-10-24/runpod-cpu"
    local = prefix / "capacity" / PILOT_ID
    pilot_plan_path = prefix / "registrations" / (PILOT_ID + ".json")
    paths_to_read = [pilot_plan_path, local / "completion.json", local / "postprocess.json", local / "analysis/summary.json",
                     local / (PILOT_ID + ".tar.gz"), local / "raw/full-state-manifest.json"]
    trial = local / "raw/evidence/runs" / PILOT_ID
    paths_to_read += [trial / name for name in ("result.json", "load-result.json", "strict-pilot-check.json",
                                               "configuration-verification.json", "fixed-leader-check.json", "configuration.json")]
    missing = [str(path.relative_to(repository)) for path in paths_to_read if not path.is_file()]
    if missing:
        require(not required, "Strict r2 pilot archive/local analysis is not complete: " + json.dumps(missing))
        return {"jobId": PILOT_ID, "ready": False, "missing": missing}
    original = read(pilot_plan_path)
    completion = read(local / "completion.json")
    require(original.get("controllerSha256") == BASE_V2_SHA256 and original.get("controllerVersion") == 2,
            "Strict r2 pilot must use the frozen v2 controller")
    require(original.get("planSha256") == plan_identity(original) == completion.get("planSha256"), "Pilot registered/completed plan differs")
    require(completion.get("strictPilotPassed") is True and completion.get("archiveComplete") is True
            and completion.get("allOwnedProcessesStopped") is True and completion.get("loadExitCode") == 0,
            "Pilot canonical/cleanup/archive did not completely pass")
    require(sha(local / (PILOT_ID + ".tar.gz")) == completion["archive"]["sha256"], "Complete local pilot archive SHA differs")
    manifest_path = local / "raw/full-state-manifest.json"
    require(sha(manifest_path) == completion["archive"]["fullStateManifestSha256"], "Pilot full-state manifest SHA differs")
    manifest = read(manifest_path)
    require(isinstance(manifest.get("files"), dict) and manifest["files"], "Pilot full-state manifest missing")
    for name, expected in manifest["files"].items():
        path = PurePosixPath(name)
        require(not path.is_absolute() and ".." not in path.parts, "Unsafe pilot manifest path")
        actual = local / "raw" / name
        require(sha(actual) == expected["sha256"] and actual.stat().st_size == expected["bytes"], "Pilot raw/state manifest no longer closes: " + name)
    raw = read(trial / "result.json")
    load = read(trial / "load-result.json")
    require(all(raw.get(name) is True for name in ("passed", "measurementValid", "canonicalSnapshotBytesVerified", "fixedLeaderVerified"))
            and raw.get("leaderChanged") is False and load.get("generatorTimingInvalid") is False,
            "Pilot business/canonical/timing evidence is incomplete")
    require(load.get("scheduledArrivals") == load.get("confirmedAcceptedCommands") == 350000,
            "Pilot did not confirm all350k commands")
    require(all(type(load.get(name)) is int and load[name] == 0 for name in ZERO_COUNTS), "Pilot contains drops/rejections/errors/UNKNOWN/late scheduling")
    for name in ("strict-pilot-check.json", "configuration-verification.json", "fixed-leader-check.json"):
        require(read(trial / name).get("passed") is True, "Pilot prerequisite failed: " + name)
    configuration = read(trial / "configuration.json")
    require(configuration.get("preparedSnapshotSha256") == PREPARED_SHA and configuration.get("clientPendingCapacity") == 128,
            "Pilot prepared state/pending window differs")
    summary = read(local / "analysis/summary.json")
    require(len(summary.get("trials", [])) == 1 and summary["trials"][0].get("measurementValid") is True,
            "Independent local31e4 pilot analysis is not valid")
    for name, expected in summary["trials"][0].get("inputSha256", {}).items():
        require(sha(trial / name) == expected, "Pilot independent-analysis raw input SHA changed")
    post = read(local / "postprocess.json")
    require(post.get("exitCode") == 0 and post.get("analysisIdentitySha256") == ANALYSIS_ID,
            "Pilot independent analysis source/runtime receipt missing")
    inputs = {str(path.relative_to(repository)): sha(path) for path in paths_to_read}
    return {"jobId": PILOT_ID, "ready": True, "planSha256": original["planSha256"],
            "completionContentSha256": value_sha(completion), "archiveSha256": completion["archive"]["sha256"],
            "analysisIdentitySha256": ANALYSIS_ID, "inputs": inputs,
            "scope": "Complete frozenv2 strict350k pilot, canonical/raw/state manifest, exact owned stop, full archive SHA and independently valid local31e4 analysis."}


def historical_baseline_fixed():
    """Historical13k used explicit1ms; current100us policy must never rewrite it."""
    return {**FIXED, 'nodeDataPathMaxParkNs': 1000000, 'driverIdleMaxParkNs': 1000000,
            'idleStrategy': 'Explicit node driver(10,5,1000,1000000); archive/consensus/service(10,20,1000,1000000)'}


def baseline_13000_prerequisite(ident, repository=REPO, required=False):
    """Close original successful13k native evidence without reclassifying matrix points."""
    require(ident in BASELINE_IDS, "Only the two original13k baseline identities are eligible")
    prefix = repository / "evidence/2026-10-24/runpod-cpu"
    local = prefix / "capacity" / ident
    original_plan_path = prefix / "matrices/cpu-capacity-staircase-433-r1/trial-plans" / (ident + ".json")
    trial = local / "raw/evidence/runs" / ident
    inputs = [original_plan_path, local / "raw/plan.json", local / "completion.json", local / "postprocess.json",
              local / "analysis/summary.json", local / (ident + ".tar.gz"), local / "raw/full-state-manifest.json"]
    inputs += [trial / name for name in ("result.json", "load-result.json", "matrix-trial-check.json",
                                         "configuration-verification.json", "fixed-leader-check.json", "configuration.json")]
    missing = [str(path.relative_to(repository)) for path in inputs if not path.is_file()]
    if missing:
        require(not required, "Complete13k native/export/analysis prerequisite missing: " + json.dumps(missing))
        return {"jobId": ident, "ready": False, "missing": missing}
    original = read(original_plan_path)
    completion = read(local / "completion.json")
    require(original == read(local / "raw/plan.json"), "Archived13k plan differs from original registration")
    require(original.get("controllerSha256") == BASE_MATRIX_SHA256 and original.get("controllerVersion") == 3
            and original.get("sourceRevision") == REVISION and original.get("fixed") == historical_baseline_fixed(),
            "13k baseline source/controller/fixed policy differs")
    task = original.get("task", {})
    require(task.get("id") == ident and task.get("rate") == 13000
            and task.get("arrivals") == 350000 and task.get("workers") == 128,
            "13k baseline task differs")
    require(original.get("planSha256") == plan_identity(original) == completion.get("planSha256"),
            "13k completed registration identity differs")
    require(completion.get("matrixTrialPassed") is True and completion.get("allOwnedProcessesStopped") is True
            and completion.get("archiveComplete") is True and completion.get("arrivalArchivePassed") is True
            and completion.get("loadExitCode") == 0, "13k canonical/owned/archive evidence incomplete")
    require(sha(local / (ident + ".tar.gz")) == completion["archive"]["sha256"], "13k full native archive SHA differs")
    manifest_path = local / "raw/full-state-manifest.json"
    require(sha(manifest_path) == completion["archive"]["fullStateManifestSha256"], "13k full-state manifest differs")
    manifest = read(manifest_path)
    require(isinstance(manifest.get("files"), dict) and manifest["files"], "13k full native manifest empty")
    for name, expected in manifest["files"].items():
        path = PurePosixPath(name)
        require(not path.is_absolute() and ".." not in path.parts, "Unsafe13k manifest path")
        actual = local / "raw" / name
        require(sha(actual) == expected["sha256"] and actual.stat().st_size == expected["bytes"],
                "13k raw/native bytes no longer close: " + name)
    raw, load = read(trial / "result.json"), read(trial / "load-result.json")
    require(all(raw.get(name) is True for name in ("passed", "measurementValid", "canonicalSnapshotBytesVerified", "fixedLeaderVerified"))
            and raw.get("leaderChanged") is False and load.get("generatorTimingInvalid") is False,
            "13k canonical/leader/timing invalid")
    require(load.get("targetArrivalRatePerSecond") == 13000
            and load.get("scheduledArrivals") == load.get("confirmedAcceptedCommands") == 350000,
            "13k baseline must accept all350k offered commands")
    require(all(type(load.get(name)) is int and load[name] == 0 for name in ZERO_COUNTS),
            "13k baseline contains not-sent/reject/error/UNKNOWN/late scheduling")
    for name in ("matrix-trial-check.json", "configuration-verification.json", "fixed-leader-check.json"):
        require(read(trial / name).get("passed") is True, "13k validation failed: " + name)
    configuration = read(trial / "configuration.json")
    require(configuration.get("preparedSnapshotSha256") == PREPARED_SHA
            and configuration.get("clientPendingCapacity") == configuration.get("workers") == 128
            and configuration.get("ratePerSecond") == 13000,
            "13k prepared state/actual pending window/rate differs")
    summary = read(local / "analysis/summary.json")
    require(len(summary.get("trials", [])) == 1 and summary["trials"][0].get("measurementValid") is True,
            "13k independent31e4 analysis invalid")
    analysis_inputs = summary["trials"][0].get("inputSha256")
    require(isinstance(analysis_inputs, dict) and analysis_inputs, "13k analysis input hashes absent")
    for name, expected in analysis_inputs.items():
        require(sha(trial / name) == expected, "13k independently analyzed input changed: " + name)
    post = read(local / "postprocess.json")
    require(post.get("exitCode") == 0 and post.get("analysisIdentitySha256") == ANALYSIS_ID,
            "13k independent analyzer identity/exit missing")
    return {"jobId": ident, "ready": True, "sourceRevision": REVISION, "controllerSha256": BASE_MATRIX_SHA256,
            "planSha256": original["planSha256"], "completionContentSha256": value_sha(completion),
            "archiveSha256": completion["archive"]["sha256"],
            "fullStateManifestSha256": completion["archive"]["fullStateManifestSha256"],
            "inputs": {str(path.relative_to(repository)): sha(path) for path in inputs},
            "scope": "Original13k finite-window observation additionally satisfies all350k/zero not-sent/reject/error/UNKNOWN/late strict counts, full canonical/native manifest/archive and valid31e4. This adds an idle-experiment prerequisite; original matrix classifications remain unchanged."}


def validate_prerequisite_declaration(prior):
    require(prior.get("jobId") == PILOT_ID and type(prior.get("ready")) is bool,
            "10k pilot prerequisite declaration missing")
    if prior["ready"]:
        rows = prior.get("baselines13000", [])
        require([row.get("jobId") for row in rows] == list(BASELINE_IDS), "Both original13k baselines required in fixed order")
        for row in rows:
            require(row.get("ready") is True and row.get("sourceRevision") == REVISION
                    and row.get("controllerSha256") == BASE_MATRIX_SHA256, "13k prerequisite source/closure differs")
            for name in ("completionContentSha256", "archiveSha256"):
                require(re.fullmatch(r"[a-f0-9]{64}", row.get(name, "")), "13k prerequisite SHA absent")
    return prior


def pilot_prerequisite(repository=REPO, required=False):
    strict = strict_10000_prerequisite(repository, required)
    baselines = [baseline_13000_prerequisite(ident, repository, required) for ident in BASELINE_IDS]
    prior = {**strict, "ready": strict.get("ready") is True and all(row.get("ready") is True for row in baselines),
             "baselines13000": baselines,
             "idlePrerequisiteScope": "Complete original10k strictv2 plus both original13k strict-count finite-window raw/canonical/native/full-export/local31e4 closures; no dependence on invalid18kr2 or unlaunched matrix point6."}
    return validate_prerequisite_declaration(prior)


def verify_remote_13000_baselines(prior):
    validate_prerequisite_declaration(prior)
    require(prior.get("ready") is True, "Strict13k native/export closure not ready")
    for baseline in prior["baselines13000"]:
        completion = read(CONTROL_BASE / baseline["jobId"] / "completion.json")
        require(value_sha(completion) == baseline["completionContentSha256"]
                and completion.get("matrixTrialPassed") is True and completion.get("archiveComplete") is True
                and completion.get("allOwnedProcessesStopped") is True and completion.get("loadExitCode") == 0,
                "Remote13k completion changed or incomplete")
        require(sha(completion["archive"]["path"]) == baseline["archiveSha256"], "Remote13k full archive changed")


def validate_idle_prerequisite_declaration(prior):
    require(type(prior) is dict and type(prior.get('ready')) is bool, 'Idle prerequisite readiness missing')
    if not prior['ready']:
        return prior
    require(prior.get('matrixId') == BASE_IDLE_MATRIX_ID and prior.get('controllerSha256') == BASE_IDLE_SHA256,
            'Exact completed idle A/B/A/B source required')
    for key in ('comparisonSha256', 'matrixPlanFileSha256', 'matrixPlanSha256', 'summarizerSha256'):
        require(re.fullmatch(r'[a-f0-9]{64}', prior.get(key, '')), 'Idle prerequisite SHA missing: ' + key)
    points = prior.get('points', [])
    require([p.get('stage') for p in points] == ['A1', 'B1', 'A2', 'B2'], 'All four idle attempts required in order')
    for point in points:
        stage = point['stage']
        require(point.get('jobId') == 'cpu-capacity-idle-' + stage.lower() + '-18000-w128-r1'
                and point.get('valid') is True and point.get('actualInstanceCountPerNode') == [11, 11, 11],
                'Idle validity/actual33instance closure differs')
        if stage.startswith('B'):
            require(point.get('finiteStable') is True, 'Both100us B repeats must be finite stable')
        for key in ('completionContentSha256', 'archiveSha256', 'analysisSha256', 'pointSha256', 'receiptSha256', 'idleProofSha256'):
            require(re.fullmatch(r'[a-f0-9]{64}', point.get(key, '')), 'Idle point SHA missing: ' + key)
    return prior


def idle_prerequisite(repository=REPO, required=False):
    """Revalidate immutable four-point native/export/31e4/actual-instance closure locally."""
    prefix = repository / 'evidence/2026-10-24/runpod-cpu'
    plan_path = prefix / 'registrations' / (BASE_IDLE_MATRIX_ID + '.json')
    comparison_path = prefix / 'node-idle-abab/comparison/comparison.json'
    if not plan_path.is_file() or not comparison_path.is_file():
        require(not required, 'Complete four-point idle comparison missing; no launch')
        return {'ready': False}
    require(sha(BASE / 'capacity_idle.py') == BASE_IDLE_SHA256, 'Frozen idle prerequisite controller changed')
    original = import_file('fixed_idle_prerequisite', BASE / 'capacity_idle.py')
    plan = original.validate_matrix(read(plan_path))
    destination = prefix / 'matrices' / BASE_IDLE_MATRIX_ID
    points = original.completed_prefix(destination, plan, 4)
    comparison = read(comparison_path)
    summarizer = BASE / 'summarize-idle-abab.py'
    require(comparison.get('passed') is True and comparison.get('matrixId') == BASE_IDLE_MATRIX_ID
            and comparison.get('matrixPlanSha256') == plan['matrixPlanSha256']
            and comparison.get('sourceSha256') == sha(summarizer), 'Idle comparison source/plan binding differs')
    require(len(comparison.get('rows', [])) == 4, 'Idle comparison must retain all four rows')
    rows = []
    for point, child, observed in zip(points, plan['trialPlans'], comparison['rows']):
        local = Path(point['analysisDirectory']); ident = child['jobId']; stage = child['task']['stage']
        receipt_path = destination / 'point-executions' / ident / 'receipt.json'
        receipt = read(receipt_path)
        require(receipt.get('passed') is True and receipt.get('point') == point, 'Idle per-point execution receipt differs')
        summary_path = local / 'analysis/summary.json'
        trial = read(summary_path)['trials'][0]
        verifier_path = local / 'raw/pinned-tools/scripts/verify-capacity-config.py'
        require(sha(verifier_path) == child['tools']['scripts/verify-capacity-config.py']['sha256'], 'Idle pinned verifier changed')
        verifier = import_file('idle_prerequisite_verifier_' + stage, verifier_path)
        proof = original.actual_idle_check(child, verifier, local / 'raw/evidence/runs' / ident)
        counts = [node['distinctInstanceCount'] for node in proof['nodes']]
        require(observed.get('jobId') == ident and observed.get('stage') == stage
                and observed.get('valid') == trial['measurementValid'] is True
                and observed.get('finiteStable') == trial['observedStableWindow']
                and observed.get('analysisSha256') == sha(summary_path)
                and observed.get('completeArchiveSha256') == point['completion']['archive']['sha256']
                and observed.get('idleInstanceVerification') == proof, 'Idle comparison/raw proof differs')
        rows.append({'stage': stage, 'jobId': ident, 'valid': True, 'finiteStable': trial['observedStableWindow'],
                     'actualInstanceCountPerNode': counts, 'completionContentSha256': value_sha(point['completion']),
                     'archiveSha256': point['completion']['archive']['sha256'], 'analysisSha256': sha(summary_path),
                     'pointSha256': sha(destination / 'points' / (ident + '.json')), 'receiptSha256': sha(receipt_path),
                     'idleProofSha256': value_sha(proof)})
    return validate_idle_prerequisite_declaration({'ready': True, 'matrixId': BASE_IDLE_MATRIX_ID,
        'controllerSha256': BASE_IDLE_SHA256, 'comparisonSha256': sha(comparison_path),
        'matrixPlanFileSha256': sha(plan_path), 'matrixPlanSha256': plan['matrixPlanSha256'],
        'summarizerSha256': sha(summarizer), 'points': rows,
        'scope': 'All4 actual idle attempts retained/canonical/valid/owned-stopped/native-archived/local31e4. Both100us B points finite stable18k. Not a sustained capacity ceiling or cross-host proof.'})


def verify_remote_idle_prerequisite(prior):
    validate_idle_prerequisite_declaration(prior)
    require(prior['ready'], 'Complete idle prerequisite missing; no launch')
    for point in prior['points']:
        completion = read(CONTROL_BASE / point['jobId'] / 'completion.json')
        require(value_sha(completion) == point['completionContentSha256']
                and completion.get('allOwnedProcessesStopped') is True and completion.get('archiveComplete') is True
                and completion.get('matrixTrialPassed') is True and completion.get('loadExitCode') == 0,
                'Remote idle terminal/cleanup/archive receipt differs')
        require(completion['archive']['path'] == str(ARCHIVE_BASE / (point['jobId'] + '.tar.gz'))
                and sha(completion['archive']['path']) == point['archiveSha256'], 'Remote complete idle archive differs')


def matrix_identity(plan):
    return value_sha({key: value for key, value in plan.items() if key != "matrixPlanSha256"})


def draft_matrix(repository=REPO, prerequisite=None, idle_prior=None):
    prior = pilot_prerequisite(repository) if prerequisite is None else prerequisite
    idle = idle_prerequisite(repository) if idle_prior is None else idle_prior
    validate_idle_prerequisite_declaration(idle)
    trials = [draft_plan(task['id'], repository, prior, idle) for task in matrix_tasks()]
    plan = {'schemaVersion': 3, 'role': 'cpu-fixed-node100us-capacity-curve', 'matrixId': MATRIX_ID,
            'scope': SCOPE, 'sourceRevision': REVISION, 'controllerSha256': sha(__file__),
            'baseControllerSha256': BASE_V2_SHA256, 'baseMatrixControllerSha256': BASE_MATRIX_SHA256,
            'baseIdleControllerSha256': BASE_IDLE_SHA256, 'registeredAtUtc': now(),
            'fixedAcrossPoints': common_fixed(), 'variableFixedFields': [], 'order': matrix_tasks(),
            'trialPlans': trials, 'pilotPrerequisite': prior, 'nodeIdlePrerequisite': idle,
            'analysisIdentitySha256': ANALYSIS_ID, 'archiveCompressionLevel': 1,
            'minimumOverlayFreeBytesBeforeEveryPoint': 3 * 1024**3,
            'executionPolicy': 'Explicit single-point exactID only; two ascending22/26/30/34k repetitions,350k fresh arrivals each,W128/Q64,node100us,client unchanged. Valid overload allowed; any UNKNOWN/invalid/incomplete cleanup/export blocks all later points. Retain every attempted point. No retry/reissue/automatic prune.',
            'scopeLimit': 'Single CPU host/three JVMs/loopback UDP, finite10.29–15.91s windows. No infinite/sustained ceiling, real-time guarantee, or cross-host fault-isolation claim.'}
    plan['matrixPlanSha256'] = matrix_identity(plan)
    return validate_matrix(plan)


def validate_matrix(plan):
    require(plan.get('schemaVersion') == 3 and plan.get('role') == 'cpu-fixed-node100us-capacity-curve'
            and plan.get('matrixId') == MATRIX_ID and plan.get('scope') == SCOPE, 'Curve role/scope/ID differs')
    require(plan.get('sourceRevision') == REVISION and plan.get('fixedAcrossPoints') == common_fixed()
            and plan.get('controllerSha256') == sha(__file__) and plan.get('baseControllerSha256') == BASE_V2_SHA256
            and plan.get('baseMatrixControllerSha256') == BASE_MATRIX_SHA256
            and plan.get('baseIdleControllerSha256') == BASE_IDLE_SHA256, 'Curve source/fixed/controller identity differs')
    require(plan.get('order') == matrix_tasks() and len(plan.get('trialPlans', [])) == 8, 'Exact eight-point ascending repetitions required')
    require(plan.get('variableFixedFields') == [], 'Node/client configuration must stay fixed across curve')
    require(plan.get('analysisIdentitySha256') == ANALYSIS_ID and plan.get('archiveCompressionLevel') == 1
            and plan.get('minimumOverlayFreeBytesBeforeEveryPoint') == 3 * 1024**3, 'Curve analysis/archive/space policy differs')
    validate_idle_prerequisite_declaration(plan.get('nodeIdlePrerequisite', {}))
    require(plan.get('matrixPlanSha256') == matrix_identity(plan), 'Curve registered SHA differs')
    for expected, child in zip(matrix_tasks(), plan['trialPlans']):
        validate_plan(child)
        require(child['task'] == expected and child['pilotPrerequisite'] == plan['pilotPrerequisite']
                and child['nodeIdlePrerequisite'] == plan['nodeIdlePrerequisite'], 'Curve point/prerequisite differs')
    return plan


def wait_completion(plan, timeout=2400):
    remote = remote_module()
    deadline = time.monotonic() + timeout
    completion_path = Path(plan["paths"]["control"]) / "completion.json"
    while True:
        code = "from pathlib import Path\np=Path(" + repr(str(completion_path)) + ")\nprint(p.read_text() if p.exists() else 'null')\n"
        response = remote.run("python3 -B -", input=code, timeout=30)
        require(response.returncode == 0, "Status transport failed; query the SAME job; no further point may launch")
        receipt = json.loads(response.stdout)
        if receipt is not None:
            require(receipt.get("planSha256") == plan["planSha256"], "Completed point plan SHA differs")
            return receipt
        require(time.monotonic() < deadline, "Point still pending; query the SAME job and never reissue")
        time.sleep(2)


def overlay_space():
    code = "import json,platform,shutil\nprint(json.dumps({'hostname':platform.node(),'freeBytes':shutil.disk_usage('/opt/vectormatch-cpu').free}))\n"
    response = remote_module().run("python3 -B -", input=code, timeout=30)
    require(response.returncode == 0, "Cannot verify post-point overlay space; stop before another launch")
    result = json.loads(response.stdout)
    require(result.get("hostname") == HOSTNAME and type(result.get("freeBytes")) is int, "Overlay space identity invalid")
    return {**result, "checkedAtUtc": now(), "minimumBeforeNextPoint": 3 * 1024**3,
            "nextPointEligible": result["freeBytes"] >= 3 * 1024**3}


def continuation_check(completion, summary):
    errors = []
    for name in ("matrixTrialPassed", "allOwnedProcessesStopped", "archiveComplete"):
        if completion.get(name) is not True:
            errors.append("completion." + name)
    if completion.get("loadExitCode") != 0:
        errors.append("completion.loadExitCode")
    trials = summary.get("trials", [])
    if len(trials) != 1 or trials[0].get("measurementValid") is not True:
        errors.append("independent-analysis.measurementValid")
    else:
        derived = trials[0].get("derived", {})
        for name in ("unknownAtInitialDeadline", "unknownUnresolved"):
            if type(derived.get(name)) is not int or derived[name] != 0:
                errors.append("independent-analysis." + name)
    return {"passed": not errors, "errors": errors, "overloadAllowed": True}


def execute_matrix(plan_path):
    raise ValueError("Batch execution disabled: use --execute-point EXACT_POINT_ID for one sequential point; manual verified prune is separate")


def completed_prefix(destination, plan, count):
    """Only an already valid/exported identical prefix can authorize continuation."""
    result = []
    for child in plan["trialPlans"][:count]:
        point = read(destination / "points" / (child["jobId"] + ".json"))
        require(point.get("id") == child["jobId"] and point.get("task") == child["task"], "Previous point identity changed")
        completion = point["completion"]
        require(completion.get("planSha256") == child["planSha256"], "Previous completed plan differs")
        local = Path(point["analysisDirectory"])
        require(sha(local / "analysis/summary.json") == point["analysisSummarySha256"], "Previous independent analysis changed")
        summary = read(local / "analysis/summary.json")
        require(continuation_check(completion, summary)["passed"] and point.get("continuation", {}).get("passed") is True,
                "Cannot continue past UNKNOWN/invalid/failed prior point")
        require(sha(local / (child["jobId"] + ".tar.gz")) == completion["archive"]["sha256"]
                and sha(local / "raw/full-state-manifest.json") == completion["archive"]["fullStateManifestSha256"],
                "Previous full native archive/manifest changed or missing")
        post = read(local / "postprocess.json")
        require(post.get("exitCode") == 0 and post.get("analysisIdentitySha256") == ANALYSIS_ID,
                "Previous pinned31e4 analysis receipt missing")
        inputs = summary["trials"][0].get("inputSha256")
        require(isinstance(inputs, dict) and inputs, "Previous analysis input SHA closure missing")
        for name, expected in inputs.items():
            require(sha(local / "raw/evidence/runs" / child["jobId"] / name) == expected,
                    "Previous independently analyzed raw input changed")
        result.append(point)
    return result


def execute_registered_point(plan_path, stage):
    """Explicit per-point continuation, allowing manual archive-verified prune between points.

    A failed/ambiguous launch is never resumed. No completed identity is reissued;
    no automatic state deletion occurs. The original batch stop receipt remains.
    """
    plan = validate_matrix(read(plan_path))
    require(plan["pilotPrerequisite"].get("ready") is True, "Complete strict10k/13k prerequisites required")
    require(pilot_prerequisite(required=True) == plan["pilotPrerequisite"], "Original prerequisite evidence changed")
    require(idle_prerequisite(required=True) == plan["nodeIdlePrerequisite"], "Complete idle A/B/A/B prerequisite changed")
    stages = [child["jobId"] for child in plan["trialPlans"]]
    require(stage in stages, "Choose an exact registered curve point ID")
    index = stages.index(stage); child = plan["trialPlans"][index]
    destination = REPO / "evidence/2026-10-24/runpod-cpu/matrices" / MATRIX_ID
    if destination.exists():
        require(read(destination / "plan.json") == plan, "Continuation registration changed")
    else:
        destination.mkdir(parents=True, exist_ok=False)
        save_new(destination / "plan.json", plan)
        for item in plan["trialPlans"]:
            save_new(destination / "trial-plans" / (item["jobId"] + ".json"), item)
    for item in plan["trialPlans"]:
        require(read(destination / "trial-plans" / (item["jobId"] + ".json")) == item, "Recorded point plan changed")
    completed_prefix(destination, plan, index)
    old_batch = destination / "matrix-summary.json"
    if old_batch.exists():
        attempted = [point["id"] for point in read(old_batch).get("points", [])]
        require(child["jobId"] not in attempted, "Batch already attempted this identity; query same job, no reissue")
    attempt = destination / "point-executions" / child["jobId"]
    require(not attempt.exists() and not (destination / "points" / (child["jobId"] + ".json")).exists(),
            "Point already attempted/completed; query the same job, never reissue")
    for later in plan["trialPlans"][index + 1:]:
        require(not (destination / "point-executions" / later["jobId"]).exists(), "Out-of-order future point was already attempted")
    before = overlay_space()
    require(before["nextPointEligible"], "Overlay below3GiB; manual verified archive/prune required before any launch")
    attempt.mkdir(parents=True, exist_ok=False)
    save_new(attempt / "attempted.json", {"jobId": child["jobId"], "planSha256": child["planSha256"],
                                         "matrixPlanSha256": plan["matrixPlanSha256"], "startedAtUtc": now(), "spaceBefore": before})
    point = {"id": child["jobId"], "task": child["task"], "spaceBefore": before, "startedAtUtc": now()}
    receipt = {"stage": stage, "jobId": child["jobId"], "passed": False, "automaticPrunePerformed": False}
    try:
        child_path = destination / "trial-plans" / (child["jobId"] + ".json")
        execute(child_path)
        completion = wait_completion(child); point["completion"] = completion
        require(completion.get("archiveComplete") is True and completion.get("allOwnedProcessesStopped") is True,
                "No continuation after incomplete owned stop/archive")
        collected = collect(child_path)
        summary = collected["summary"]
        checked = continuation_check(completion, summary)
        point.update(analysisDirectory=collected["directory"],
                     analysisSummarySha256=sha(Path(collected["directory"]) / "analysis/summary.json"),
                     continuation=checked, analysisTrial=summary["trials"][0] if len(summary.get("trials", [])) == 1 else None,
                     spaceAfter=overlay_space(), completedAtUtc=now())
        save_new(destination / "points" / (child["jobId"] + ".json"), point)
        require(checked["passed"], "Point UNKNOWN/invalid; subsequent stages permanently blocked by this evidence")
        receipt["passed"] = True
    except BaseException as failure:
        receipt.update(errorType=type(failure).__name__, error=str(failure), traceback=traceback.format_exc())
    finally:
        receipt.update(completedAtUtc=now(), point=point)
        save_new(attempt / "receipt.json", receipt)
        print(json.dumps(receipt))
    return 0 if receipt["passed"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument('--register', action='store_true')
    commands.add_argument('--execute-point', metavar='EXACT_POINT_ID')
    commands.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    commands.add_argument('--status', action='store_true')
    commands.add_argument('--collect', action='store_true')
    parser.add_argument('--job-id', help='Only query an already registered point')
    parser.add_argument('--plan', type=Path)
    args = parser.parse_args(argv)
    if args.execute_point:
        require(args.plan is not None and args.job_id is None, '--execute-point needs --plan and its exact point ID')
        return execute_registered_point(args.plan, args.execute_point)
    if args.worker or args.collect:
        require(args.plan is not None and args.job_id is None, 'Explicit registered point --plan required')
        return worker(args.plan) if args.worker else (collect(args.plan) and 0)
    if args.status:
        task_for_id(job_id(args.job_id))
        return status(args.job_id)
    require(args.job_id is None, 'Curve IDs are fixed in registration')
    plan = draft_matrix()
    if args.register:
        require(plan['pilotPrerequisite'].get('ready') is True and plan['nodeIdlePrerequisite'].get('ready') is True,
                'Complete strict pilot/13k plus four idle attempts and both stable B repeats required')
        target = args.plan or REPO / 'evidence/2026-10-24/runpod-cpu/registrations' / (MATRIX_ID + '.json')
        save_new(target, plan)
        print(json.dumps({'registered': str(target), 'matrixPlanSha256': plan['matrixPlanSha256'], 'scope': SCOPE, 'networkUsed': False}))
    else:
        print(json.dumps({key: value for key, value in plan.items() if key != 'trialPlans'}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
