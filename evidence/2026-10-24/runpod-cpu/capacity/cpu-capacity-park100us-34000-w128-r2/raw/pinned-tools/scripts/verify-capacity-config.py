#!/usr/bin/env python3
"""Verify recorded launch arguments before annotating comparable capacity runs."""
from pathlib import Path
import hashlib
import json
import re
import sys
import argparse
from datetime import datetime, timezone


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


NAK_FIXED_FIELDS = {"nakUnicastDelayNs", "clientNakUnicastDelayNs", "nakUnicastRetryDelayRatio"}
NAK_CLIENT_FIELDS = {"clientNakUnicastDelayNs", "clientNakUnicastRetryDelayRatio"}
TRANSPORT_FIELDS = {"clientTransportMode", "clientSessionCount"}
NODE_DATA_PATH_PROPERTY = "vectormatch.node.dataPathMaxParkNs"
NODE_DATA_PATH_ROLES = ("driver-shared", "driver-sender", "driver-receiver", "driver-conductor",
                        "driver-native-resource", "archive-shared", "consensus", "service")
UNKNOWN_GUARD = ("Confirmed-only replay skipped: {count} UNKNOWN_UNRESOLVED identities may already have executed; canonical validation is incomplete. "
                 "Preserve the original identities for same-key recovery; no core business mismatch is established.")


def failed_unknown_configuration_only(directory, enabled):
    """Opt in only to launch-configuration attestation; never manufacture a business result."""
    if not enabled or (directory / "result.json").exists():
        return False
    trial_path = directory / "trial.json"
    if not trial_path.exists():
        return None
    trial = json.loads(trial_path.read_text())
    if not isinstance(trial.get("completedAt"), str) or not trial["completedAt"]:
        return None  # Still in progress; do not annotate its mutable evidence.
    receipt = json.loads((directory / "receipt.json").read_text())
    failure = json.loads((directory / "failure.json").read_text())
    load = json.loads((directory / "load-result.json").read_text())
    count = load.get("unresolvedFinal")
    assert type(receipt.get("exitCode")) is int and receipt["exitCode"] != 0, "Failed UNKNOWN run requires nonzero terminal receipt"
    assert type(count) is int and count > 0, "Failed UNKNOWN run requires positive unresolved count"
    assert failure.get("passed") is False and failure.get("errorType") == "java.lang.IllegalStateException", "Unexpected failed-run type"
    assert failure.get("error") == UNKNOWN_GUARD.format(count=count), "Unexpected failed-run signature"
    assert failure.get("loadSummary") == load, "Failed-run load summaries differ"
    return True


def nak_settings(fixed):
    declared = NAK_FIXED_FIELDS.intersection(fixed)
    if not declared:
        return None
    assert declared == NAK_FIXED_FIELDS, "Incomplete explicit NAK configuration"
    for name in ("nakUnicastDelayNs", "clientNakUnicastDelayNs"):
        assert type(fixed[name]) is int and 1000 <= fixed[name] <= 1000000, "Invalid explicit NAK delay: " + name
    assert type(fixed["nakUnicastRetryDelayRatio"]) is int and fixed["nakUnicastRetryDelayRatio"] == 100, "NAK retry ratio must remain 100"
    return {name: fixed[name] for name in NAK_FIXED_FIELDS}


def transport_settings(fixed):
    declared = TRANSPORT_FIELDS.intersection(fixed)
    if not declared:
        return None
    assert declared == TRANSPORT_FIELDS, "Incomplete explicit client transport configuration"
    assert fixed["clientTransportMode"] in ("direct", "multiplexed"), "Invalid explicit client transport mode"
    count = fixed["clientSessionCount"]
    assert type(count) is int and 1 <= count <= 256, "Invalid explicit client session count"
    assert fixed["clientTransportMode"] != "multiplexed" or count == 1, "Multiplexed transport requires one physical session"
    return {name: fixed[name] for name in TRANSPORT_FIELDS}


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
    permitted_transport = ("-Dvectormatch.capacity.client.transport=direct",
                           "-Dvectormatch.capacity.client.transport=multiplexed")
    assert isinstance(extra, list), "Load-generator JVM arguments must be a list"
    settings = nak_settings(fixed or {})
    transport = transport_settings(fixed or {})
    nak_flag = "-Daeron.nak.unicast.delay=" + str(settings["clientNakUnicastDelayNs"]) if settings else None
    assert all(isinstance(value, str) and (value in permitted or value in permitted_transport or value == nak_flag) for value in extra), "Disallowed load-generator JVM argument"
    driver_flags = [value for value in extra if value in permitted]
    transport_flags = [value for value in extra if value in permitted_transport]
    assert len(driver_flags) <= 1 and len(transport_flags) <= 1 and len(extra) == len(set(extra)), "Disallowed duplicate/conflicting load-generator JVM argument"
    transport_runtime = TRANSPORT_FIELDS.intersection(configuration)
    if transport is None:
        assert not transport_flags, "Undeclared client transport JVM opt-in"
        if transport_runtime:
            assert transport_runtime == TRANSPORT_FIELDS, "Incomplete client transport mode/session runtime declaration"
            assert configuration["clientTransportMode"] == "direct", "Undeclared nondefault client transport"
            assert type(configuration["clientSessionCount"]) is int and configuration["clientSessionCount"] == trial["workers"], "Client physical session count differs"
        actual_transport = "direct"
    else:
        assert transport_flags == ["-Dvectormatch.capacity.client.transport=" + transport["clientTransportMode"]], "Client transport JVM flag differs or is missing"
        assert transport_runtime == TRANSPORT_FIELDS, "Incomplete client transport mode/session runtime declaration"
        actual_transport = transport["clientTransportMode"]
        assert configuration["clientTransportMode"] == actual_transport, "Client transport effective runtime differs"
        expected_sessions = trial["workers"] if actual_transport == "direct" else 1
        assert type(configuration["clientSessionCount"]) is int and configuration["clientSessionCount"] == transport["clientSessionCount"] == expected_sessions, "Client physical session count differs"
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
    expected_aeron = "one-independent-Aeron-per-client" if actual_transport == "direct" else "one-session-one-network-owner"
    assert configuration["clientAeronMode"] == expected_aeron, "Client Aeron ownership mode differs"
    if actual_transport == "multiplexed":
        assert type(trial["workers"]) is int and trial["workers"] in (128, 256) and mode == "shared" and driver_flags == [permitted[1]], "Multiplexed transport requires shared driver and 128 or 256 logical workers"
        # Historical 128-worker artifacts predate this runtime field; the new 256
        # path must attest its actual physical-client pending bound explicitly.
        if "clientPendingCapacity" in configuration or trial["workers"] == 256:
            assert type(configuration.get("clientPendingCapacity")) is int and configuration["clientPendingCapacity"] == trial["workers"], "Multiplexed pending capacity differs from logical workers"
        if "workers" in configuration or trial["workers"] == 256:
            assert type(configuration.get("workers")) is int and configuration["workers"] == trial["workers"], "Effective logical workers differ"
        if "maxServiceRequestsInFlight" in configuration or trial["workers"] == 256:
            assert type(configuration.get("maxServiceRequestsInFlight")) is int and configuration["maxServiceRequestsInFlight"] == trial["workers"], "Effective logical in-flight bound differs"
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


def node_data_path_max_park(fixed):
    value = fixed.get("nodeDataPathMaxParkNs")
    if "nodeDataPathMaxParkNs" not in fixed:
        assert not any(name.startswith("nodeDataPathIdle") for name in fixed), "Incomplete explicit node data-path policy"
        return None
    assert type(value) is int and 1000 <= value <= 1000000, "Invalid explicit node data-path max park"
    for name, expected in (("nodeDataPathIdlePolicyVersion", 1), ("nodeDataPathIdleAgentMaxYields", 20),
                           ("nodeDataPathIdleMinParkNs", 1000)):
        if name in fixed:
            assert type(fixed[name]) is int and fixed[name] == expected, "Conflicting node data-path declaration: " + name
    return value


def verify_node_data_path_jvm_arguments(arguments, fixed):
    maximum = node_data_path_max_park(fixed)
    actual = [arg for arg in arguments if isinstance(arg, str) and "vectormatch.node.dataPath" in arg]
    expected = [] if maximum is None else ["-D" + NODE_DATA_PATH_PROPERTY + "=" + str(maximum)]
    assert actual == expected, "Node data-path JVM property missing, differing, duplicate or hidden"
    if expected:
        assert "-cp" in arguments and arguments.index(expected[0]) < arguments.index("-cp"), "Node data-path property is not a JVM argument"


def verify_node_data_path_startup(fixed, startup, node=None):
    maximum = node_data_path_max_park(fixed)
    started = [line for line in startup.splitlines() if line.startswith("VECTOR_CLUSTER_STARTED ")]
    evidence = [line for line in startup.splitlines() if line.startswith("VECTOR_NODE_DATA_PATH_IDLE ")]
    if maximum is None:
        assert not evidence and all("nodeDataPath" not in line for line in started), "Undeclared node data-path runtime opt-in"
        return
    assert len(started) == 1, "Require one explicit node data-path startup"
    for name, value in (("nodeDataPathIdlePolicyVersion", "1"), ("nodeDataPathMaxParkNs", str(maximum)),
                        ("nodeDataPathIdleInstancesDistinct", "true")):
        assert re.findall(r"(?:^|\s)" + name + r"=([^\s]+)(?=\s|$)", started[0]) == [value], "Missing, duplicate or differing node data-path startup: " + name
    started_node = re.findall(r"(?:^|\s)node=([0-2])(?=\s|$)", started[0])
    assert len(started_node) == 1 and (node is None or started_node == [str(node)]), "Node data-path startup member differs"
    threading = driver_threading_argument(fixed) or fixed.get("driverThreading", "SHARED")
    verify_driver_threading_startup({**fixed, "driverThreadingArgument": threading}, startup)
    roles, instances = set(), set()
    for line in evidence:
        pairs = re.findall(r"(?:^|\s)([A-Za-z][A-Za-z0-9]*)=([^\s]+)", line)
        fields = dict(pairs)
        assert len(fields) == len(pairs) and set(fields) == {"node", "role", "instanceId", "runnerSelected", "strategyClass", "configuration"}, "Invalid or duplicate data-path instance fields"
        role = fields["role"]
        assert role in NODE_DATA_PATH_ROLES and fields["node"] == started_node[0], "Unexpected data-path role/member"
        instance = fields["instanceId"]
        assert re.fullmatch(r"[1-9][0-9]*", instance) and instance not in instances, "Repeated/invalid data-path instance identity"
        instances.add(instance); roles.add(role)
        yields = 5 if role.startswith("driver-") else 20
        runner_selected = (threading == "SHARED" if role == "driver-shared" else threading == "DEDICATED") if role.startswith("driver-") else True
        expected_configuration = ("BackoffIdleStrategy{alias=backoff,maxSpins=10,maxYields=" + str(yields)
                                  + ",minParkPeriodNs=1000,maxParkPeriodNs=" + str(maximum) + "}")
        assert fields["runnerSelected"] == str(runner_selected).lower(), "Data-path runner-selected/configured instance differs"
        assert fields["strategyClass"] == "org.agrona.concurrent.BackoffIdleStrategy" and fields["configuration"] == expected_configuration, "Data-path actual strategy configuration differs"
    assert roles == set(NODE_DATA_PATH_ROLES), "Missing data-path role instance evidence"


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
              "driverIdleMinParkNs": 1000, "driverIdleMaxParkNs": node_data_path_max_park(fixed) or 1000000}
    assert started, "Missing driver threading startup evidence"
    for name, value in fields.items():
        pattern = r"(?:^|\s)" + name + "=" + str(value) + r"(?=\s|$)"
        assert all(len(re.findall(pattern, line)) == 1 for line in started), "Missing or differing driver threading/idle startup evidence: " + name


def main(root, include_failed_unknown=False):
    campaign = json.loads((root / "campaign.json").read_text())
    deployment = json.loads((root / "deployment.json").read_text())
    fixed = {"outboxCapacity": 65536,
             "driverThreading": "SHARED", "archiveThreading": "SHARED",
             "idleStrategy": "BackoffIdleStrategy defaults",
             "socketSendBufferBytes": 131072, "socketReceiveBufferBytes": 131072,
             "aeronVersion": "1.53.3", **campaign["fixed"]}
    maximum_cluster_sessions(fixed)  # Validate without adding/changing historical fingerprint fields.
    nak_settings(fixed)  # Optional values enter the existing fixed-configuration fingerprint unchanged.
    transport_settings(fixed)  # Historical absence leaves the fixed fingerprint unchanged.
    data_path_maximum = node_data_path_max_park(fixed)
    if data_path_maximum is not None:
        fixed.update({"nodeDataPathIdlePolicyVersion": 1, "nodeDataPathIdleAgentMaxYields": 20,
                      "nodeDataPathIdleMinParkNs": 1000})
    receive_buffer = socket_receive_buffer_argument(fixed)
    if receive_buffer is not None:
        if "socketReceiveBufferBytes" in campaign["fixed"]:
            assert campaign["fixed"]["socketReceiveBufferBytes"] == receive_buffer, "Conflicting receive buffer declarations"
        fixed["socketReceiveBufferBytes"] = receive_buffer
    driver_threading = driver_threading_argument(fixed)
    if driver_threading is not None:
        expected = {"driverThreading": driver_threading, "driverIdleMaxSpins": 10, "driverIdleMaxYields": 5,
                    "driverIdleMinParkNs": 1000, "driverIdleMaxParkNs": data_path_maximum or 1000000}
        for name, value in expected.items():
            if name in campaign["fixed"]:
                assert campaign["fixed"][name] == value, "Conflicting driver threading/idle declaration: " + name
        fixed.update(expected)
    checked = []
    for directory in sorted((root / "runs").iterdir()):
        configuration_only = False
        if not (directory / "result.json").exists():
            configuration_only = failed_unknown_configuration_only(directory, include_failed_unknown)
            if configuration_only is not True:
                continue  # Historical default and in-progress runs must not be rewritten.
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
        if configuration_only:
            for name in ("failure.json", "load-result.json", "receipt.json", "configuration.json"):
                hashes[name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for node in range(3):
            path = directory / f"node{node}" / "process.json"
            record = json.loads(path.read_text())
            args = record["arguments"]
            assert "-Xmx" + fixed["nodeHeap"] in args
            assert "-Daeron.cluster.appointed.leader.id=0" in args
            verify_maximum_cluster_sessions(args, fixed)
            verify_nak_jvm_arguments(args, fixed)
            verify_node_data_path_jvm_arguments(args, fixed)
            assert args[args.index("-cp") + 1] == release + "/dist/cluster/lib/*"
            index = args.index("io.vectormatch.cluster.ClusterNodeMain")
            assert args[index + 1:] == node_arguments(trial, fixed, node, hosts)
            if fixed.get("stateProfile") or receive_buffer is not None or driver_threading is not None or nak_settings(fixed) is not None or data_path_maximum is not None:
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
                verify_node_data_path_startup(fixed, startup, node)
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
        verification_scope = ({"configurationOnly": True, "businessCorrectnessVerified": False,
                               "includeFailedUnknownOptIn": True,
                               "failedRunScope": "Only recorded configuration/argv/runtime/startup/prepared-byte evidence is verified. Original UNKNOWN outcomes and nonzero failure remain; no business correctness, capacity eligibility or result.json is created."}
                              if configuration_only else {})
        write(directory / "configuration-verification.json", {
            "passed": True, "verifiedAtUtc": datetime.now(timezone.utc).isoformat(),
            "recordedArgumentsVerified": True, "preparedSnapshotDigestVerified": True,
            "loadGeneratorArgumentsVerified": True,
            "rawSha256": hashes, **verification_scope,
            "scope": ("CONFIGURATION ONLY for a terminal unresolved-UNKNOWN failure; no business correctness or capacity validation. " if configuration_only else "") + ("Recorded supervisor arguments and deployment-transfer hash receipts; not a hardware, kernel fsync or independent provider durability attestation. Idle/socket settings are pinned source constants."
                      if receive_buffer is None else
                      "Recorded supervisor arguments, startup requested receive buffer, and deployment-transfer hash receipts; actual kernel effective SO_RCVBUF, hardware/fsync and provider durability are not attested. Other idle/socket settings are pinned source constants.")
                      + (" Explicit node data-path role factory instances and actual Backoff parameter strings are cross-checked; instance IDs are process-local evidence, not OS wakeup or CPU guarantees." if data_path_maximum is not None else "")})
        checked.append({"id": directory.name, "preparedSnapshotSha256": configuration["preparedSnapshotSha256"], **verification_scope})
    assert len({row["preparedSnapshotSha256"] for row in checked}) <= 1, "Initial logical state changed"
    write(root / "configuration-verification.json", {"passed": True, "runs": checked,
                                                    "preparedStateIdentical": True, "fixed": fixed})
    print("VERIFIED_CONFIGURATIONS", len(checked))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("evidence/2026-10-23/runpod-capacity"))
    parser.add_argument("--include-failed-unknown", action="store_true",
                        help="Verify configuration only for an exact terminal unresolved-UNKNOWN guard; preserve invalid business outcome")
    options = parser.parse_args()
    main(options.root, options.include_failed_unknown)
