#!/usr/bin/env python3
"""Verify recorded launch arguments before annotating comparable capacity runs."""
from pathlib import Path
import hashlib
import json
import re
import sys
from datetime import datetime, timezone


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


NAK_FIXED_FIELDS = {"nakUnicastDelayNs", "clientNakUnicastDelayNs", "nakUnicastRetryDelayRatio"}
NAK_CLIENT_FIELDS = {"clientNakUnicastDelayNs", "clientNakUnicastRetryDelayRatio"}


def nak_settings(fixed):
    declared = NAK_FIXED_FIELDS.intersection(fixed)
    if not declared:
        return None
    assert declared == NAK_FIXED_FIELDS, "Incomplete explicit NAK configuration"
    for name in ("nakUnicastDelayNs", "clientNakUnicastDelayNs"):
        assert type(fixed[name]) is int and 1000 <= fixed[name] <= 1000000, "Invalid explicit NAK delay: " + name
    assert type(fixed["nakUnicastRetryDelayRatio"]) is int and fixed["nakUnicastRetryDelayRatio"] == 100, "NAK retry ratio must remain 100"
    return {name: fixed[name] for name in NAK_FIXED_FIELDS}


def verify_nak_jvm_arguments(arguments, fixed, client=False):
    settings = nak_settings(fixed)
    actual = [arg for arg in arguments if isinstance(arg, str) and "aeron.nak" in arg]
    expected = [] if settings is None else ["-Daeron.nak.unicast.delay=" + str(
        settings["clientNakUnicastDelayNs" if client else "nakUnicastDelayNs"])]
    assert actual == expected, "NAK JVM property missing, differing, duplicate or hidden"
    if expected and "-cp" in arguments:
        assert arguments.index(expected[0]) < arguments.index("-cp"), "NAK property is not a JVM argument"


def verify_nak_startup(fixed, startup):
    settings = nak_settings(fixed)
    if settings is None:
        return
    started = [line for line in startup.splitlines() if line.startswith("VECTOR_CLUSTER_STARTED ")]
    assert started, "Missing NAK startup evidence"
    for name in ("nakUnicastDelayNs", "nakUnicastRetryDelayRatio"):
        pattern = r"(?:^|\s)" + name + r"=([^\s]+)(?=\s|$)"
        assert all(re.findall(pattern, line) == [str(settings[name])] for line in started), "Missing, duplicate or differing NAK startup evidence: " + name


def load_generator_jvm_arguments(trial, configuration, fixed=None):
    """Validate declared runtime mode against the allowlisted recorded JVM flag.

    Historical evidence predates runtime mode fields and is accepted only when
    all three fields and the new JVM flag are absent.
    """
    extra = trial.get("loadGeneratorJvmArguments", [])
    permitted = ("-Dvectormatch.capacity.client.driver=isolated",
                 "-Dvectormatch.capacity.client.driver=shared")
    assert isinstance(extra, list), "Load-generator JVM arguments must be a list"
    settings = nak_settings(fixed or {})
    nak_flag = "-Daeron.nak.unicast.delay=" + str(settings["clientNakUnicastDelayNs"]) if settings else None
    assert all(isinstance(value, str) and (value in permitted or value == nak_flag) for value in extra), "Disallowed load-generator JVM argument"
    driver_flags = [value for value in extra if value in permitted]
    assert len(driver_flags) <= 1 and len(extra) == len(set(extra)), "Disallowed duplicate load-generator JVM argument"
    verify_nak_jvm_arguments(extra, fixed or {}, client=True)
    nak_runtime = NAK_CLIENT_FIELDS.intersection(configuration)
    if settings is None:
        if nak_runtime:
            assert nak_runtime == NAK_CLIENT_FIELDS, "Incomplete client NAK runtime declaration"
            assert type(configuration["clientNakUnicastDelayNs"]) is int and configuration["clientNakUnicastDelayNs"] == 1000, "Undeclared nondefault client NAK runtime configuration"
            assert type(configuration["clientNakUnicastRetryDelayRatio"]) is int and configuration["clientNakUnicastRetryDelayRatio"] == 100, "Undeclared nondefault client NAK runtime configuration"
    else:
        assert nak_runtime == NAK_CLIENT_FIELDS, "Incomplete client NAK runtime declaration"
        assert type(configuration["clientNakUnicastDelayNs"]) is int and configuration["clientNakUnicastDelayNs"] == settings["clientNakUnicastDelayNs"], "Client NAK delay differs from effective runtime"
        assert type(configuration["clientNakUnicastRetryDelayRatio"]) is int and configuration["clientNakUnicastRetryDelayRatio"] == 100, "Client NAK retry ratio differs from effective runtime"
    runtime_fields = {"clientDriverMode", "clientDriverCount", "clientAeronMode"}
    declared = runtime_fields.intersection(configuration)
    if not declared:
        assert not extra, "Missing runtime declaration for new client mode"
        return list(extra)
    assert declared == runtime_fields, "Incomplete client transport runtime declaration"
    mode = configuration["clientDriverMode"]
    assert mode in ("isolated", "shared"), "Unknown client driver mode"
    expected_mode = driver_flags[0].split("=", 1)[1] if driver_flags else "isolated"
    assert mode == expected_mode, "Declared client driver mode differs from actual JVM argument"
    count = configuration["clientDriverCount"]
    assert type(count) is int and count == (1 if mode == "shared" else trial["workers"]), "Client driver count differs"
    assert configuration["clientAeronMode"] == "one-independent-Aeron-per-client", "Client Aeron ownership mode differs"
    return list(extra)


def load_generator_arguments(trial, release, extra_jvm_arguments):
    """Reconstruct the exact launched argv, including explicit default flags."""
    load_release = trial.get("loadGeneratorRelease", release)
    arguments = ["/opt/vectormatch/tools/jdk/bin/java",
                 "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED",
                 "--add-opens=java.base/java.util.zip=ALL-UNNAMED", *extra_jvm_arguments, "-Xmx2g", "-cp",
                 load_release + "/dist/cluster/lib/*",
                 "io.vectormatch.cluster.RemoteCapacityExperiment",
                 "/opt/vectormatch/evidence/capacity-" + trial["id"], "23000",
                 str(trial["rate"]), str(trial["arrivals"]), str(trial["workers"]),
                 "64", "2000", "30000", "0", "20"]
    if trial.get("profile", "").startswith("extended-"):
        arguments.append(trial["profile"])
    return arguments


def command_sha256(arguments):
    """Match the supervisor's NUL-terminated argv digest, preserving boundaries."""
    return hashlib.sha256(b"".join(value.encode() + b"\0" for value in arguments)).hexdigest()


def socket_receive_buffer_argument(fixed):
    """Return an explicitly requested node value; never infer effective SO_RCVBUF."""
    if "socketReceiveBufferArgumentBytes" not in fixed:
        return None
    value = fixed["socketReceiveBufferArgumentBytes"]
    assert type(value) is int and 65536 <= value <= 4194304, "Invalid explicit node receive buffer bytes"
    return value


def driver_threading_argument(fixed):
    if "driverThreadingArgument" not in fixed:
        return None
    value = fixed["driverThreadingArgument"]
    assert value in ("SHARED", "DEDICATED"), "Invalid explicit node driver threading"
    return value


def maximum_cluster_sessions(fixed):
    value = fixed.get("maxClusterSessions", 128)
    assert type(value) is int and value in (128, 256), "Invalid fixed max cluster sessions"
    return value


def verify_maximum_cluster_sessions(arguments, fixed):
    expected = "-Daeron.cluster.max.sessions=" + str(maximum_cluster_sessions(fixed))
    actual = [value for value in arguments if value == "-Daeron.cluster.max.sessions"
              or value.startswith("-Daeron.cluster.max.sessions=")]
    assert actual == [expected], "Node max cluster sessions JVM argument differs or is repeated"


def node_arguments(trial, fixed, node, hosts):
    arguments = [str(node), trial["state"], str(fixed["portBase"]),
                 str(fixed["syncLevel"]), str(fixed["outboxCapacity"]), hosts]
    receive_buffer = socket_receive_buffer_argument(fixed)
    driver_threading = driver_threading_argument(fixed)
    if fixed.get("stateProfile") or receive_buffer is not None or driver_threading is not None:
        arguments.append(fixed.get("stateProfile") or "default")
    if receive_buffer is not None or driver_threading is not None:
        arguments.append(str(131072 if receive_buffer is None else receive_buffer))
    if driver_threading is not None:
        arguments.append(driver_threading)
    return arguments


def verify_requested_receive_buffer_startup(fixed, startup):
    expected = socket_receive_buffer_argument(fixed)
    if expected is None:
        return
    started = [line for line in startup.splitlines() if line.startswith("VECTOR_CLUSTER_STARTED ")]
    values = [value for line in started for value in
              re.findall(r"(?:^|\s)requestedSocketReceiveBufferBytes=([0-9]+)(?=\s|$)", line)]
    assert values and set(values) == {str(expected)}, "Missing or differing requested receive buffer startup evidence"


def verify_driver_threading_startup(fixed, startup):
    expected = driver_threading_argument(fixed)
    if expected is None:
        return
    started = [line for line in startup.splitlines() if line.startswith("VECTOR_CLUSTER_STARTED ")]
    fields = {"driverThreading": expected, "driverIdleMaxSpins": 10, "driverIdleMaxYields": 5,
              "driverIdleMinParkNs": 1000, "driverIdleMaxParkNs": 1000000}
    assert started, "Missing driver threading startup evidence"
    for name, value in fields.items():
        pattern = r"(?:^|\s)" + name + "=" + str(value) + r"(?=\s|$)"
        assert all(len(re.findall(pattern, line)) == 1 for line in started), "Missing or differing driver threading/idle startup evidence: " + name


def main(root):
    campaign = json.loads((root / "campaign.json").read_text())
    deployment = json.loads((root / "deployment.json").read_text())
    fixed = {"outboxCapacity": 65536,
             "driverThreading": "SHARED", "archiveThreading": "SHARED",
             "idleStrategy": "BackoffIdleStrategy defaults",
             "socketSendBufferBytes": 131072, "socketReceiveBufferBytes": 131072,
             "aeronVersion": "1.53.3", **campaign["fixed"]}
    maximum_cluster_sessions(fixed)  # Validate without adding/changing historical fingerprint fields.
    nak_settings(fixed)  # Optional values enter the existing fixed-configuration fingerprint unchanged.
    receive_buffer = socket_receive_buffer_argument(fixed)
    if receive_buffer is not None:
        if "socketReceiveBufferBytes" in campaign["fixed"]:
            assert campaign["fixed"]["socketReceiveBufferBytes"] == receive_buffer, "Conflicting receive buffer declarations"
        fixed["socketReceiveBufferBytes"] = receive_buffer
    driver_threading = driver_threading_argument(fixed)
    if driver_threading is not None:
        expected = {"driverThreading": driver_threading, "driverIdleMaxSpins": 10, "driverIdleMaxYields": 5,
                    "driverIdleMinParkNs": 1000, "driverIdleMaxParkNs": 1000000}
        for name, value in expected.items():
            if name in campaign["fixed"]:
                assert campaign["fixed"][name] == value, "Conflicting driver threading/idle declaration: " + name
        fixed.update(expected)
    checked = []
    for directory in sorted((root / "runs").iterdir()):
        if not (directory / "result.json").exists():
            continue  # An in-progress run must not be rewritten.
        trial = json.loads((directory / "trial.json").read_text())
        configuration = json.loads((directory / "configuration.json").read_text())
        release = trial["release"]
        assert re.fullmatch(r"[a-f0-9]{40}", release.rsplit("/", 1)[1]), release
        assert release == deployment["root"]
        assert configuration["aeronMtuLength"] == fixed["aeronMtuLength"]
        assert configuration["expectedLeader"] == fixed["leader"]
        assert configuration["queueCapacityPerWorker"] == fixed["queuePerWorker"]
        if "declaredOutboxCapacity" in configuration:
            assert configuration["declaredOutboxCapacity"] == fixed["outboxCapacity"]
        if "capacityProfile" in fixed:
            assert configuration["profile"] == fixed["capacityProfile"]
        if fixed.get("stateProfile"):
            assert configuration["expectedStateProfile"] == fixed["stateProfile"]
            assert configuration["fullCheckpointMaximumBytes"] == fixed["checkpointMaxBytes"]
            assert configuration["expectedCoreLimits"] == {
                "maxAccounts": 10000, "maxProducers": 10000,
                "maxRetainedOrders": fixed["maxRetainedOrders"], "maxCachedResults": 100000}
        for name in ("requestTimeoutMs", "drainTimeoutMs", "schedulerLatenessLimitMs", "portBase"):
            assert configuration[name] == fixed[name], name
        hosts = ",".join(configuration["memberHosts"])
        hashes = {}
        for node in range(3):
            path = directory / f"node{node}" / "process.json"
            record = json.loads(path.read_text())
            args = record["arguments"]
            assert "-Xmx" + fixed["nodeHeap"] in args
            assert "-Daeron.cluster.appointed.leader.id=0" in args
            verify_maximum_cluster_sessions(args, fixed)
            verify_nak_jvm_arguments(args, fixed)
            assert args[args.index("-cp") + 1] == release + "/dist/cluster/lib/*"
            index = args.index("io.vectormatch.cluster.ClusterNodeMain")
            assert args[index + 1:] == node_arguments(trial, fixed, node, hosts)
            if fixed.get("stateProfile") or receive_buffer is not None or driver_threading is not None or nak_settings(fixed) is not None:
                startup = (directory / f"node{node}" / "process.log").read_text()
                if fixed.get("stateProfile"):
                    assert "profile=" + fixed["stateProfile"] in startup, "Missing state profile startup evidence"
                    assert "outbox=" + str(fixed["outboxCapacity"]) in startup, "Outbox startup evidence differs"
                    assert "checkpointMaxBytes=" + str(fixed["checkpointMaxBytes"]) in startup
                    assert "maxRetainedOrders=" + str(fixed["maxRetainedOrders"]) in startup
                    assert "resultCachePerProducer=" + str(fixed["resultCachePerProducer"]) in startup
                verify_requested_receive_buffer_startup(fixed, startup)
                if driver_threading is not None:
                    verify_requested_receive_buffer_startup(
                        {**fixed, "socketReceiveBufferArgumentBytes": 131072 if receive_buffer is None else receive_buffer}, startup)
                verify_driver_threading_startup(fixed, startup)
                verify_nak_startup(fixed, startup)
                hashes[f"node{node}/process.log"] = hashlib.sha256(startup.encode()).hexdigest()
            hashes[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot = directory / "prepared-snapshot.bin"
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == configuration["preparedSnapshotSha256"]
        hashes[snapshot.name] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        extra_jvm_arguments = load_generator_jvm_arguments(trial, configuration, fixed)
        load_arguments = load_generator_arguments(trial, release, extra_jvm_arguments)
        load_record = json.loads((directory / "load-process.json").read_text())
        command_digest = command_sha256(load_arguments)
        assert load_record["commandSha256"] == command_digest, "Load-generator arguments differ"
        hashes["load-process.json"] = hashlib.sha256((directory / "load-process.json").read_bytes()).hexdigest()
        trial.update({"deploymentRevision": deployment["revision"],
                      "deploymentBundleSha256": deployment["bundleSha256"],
                      "fixedNodeConfiguration": fixed})
        write(directory / "trial.json", trial)
        write(directory / "configuration-verification.json", {
            "passed": True, "verifiedAtUtc": datetime.now(timezone.utc).isoformat(),
            "recordedArgumentsVerified": True, "preparedSnapshotDigestVerified": True,
            "loadGeneratorArgumentsVerified": True,
            "rawSha256": hashes,
            "scope": ("Recorded supervisor arguments and deployment-transfer hash receipts; not a hardware, kernel fsync or independent provider durability attestation. Idle/socket settings are pinned source constants."
                      if receive_buffer is None else
                      "Recorded supervisor arguments, startup requested receive buffer, and deployment-transfer hash receipts; actual kernel effective SO_RCVBUF, hardware/fsync and provider durability are not attested. Other idle/socket settings are pinned source constants.")})
        checked.append({"id": directory.name, "preparedSnapshotSha256": configuration["preparedSnapshotSha256"]})
    assert len({row["preparedSnapshotSha256"] for row in checked}) <= 1, "Initial logical state changed"
    write(root / "configuration-verification.json", {"passed": True, "runs": checked,
                                                    "preparedStateIdentical": True, "fixed": fixed})
    print("VERIFIED_CONFIGURATIONS", len(checked))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "evidence/2026-10-23/runpod-capacity"))
