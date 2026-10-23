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


def load_generator_jvm_arguments(trial, configuration):
    """Validate declared runtime mode against the allowlisted recorded JVM flag.

    Historical evidence predates runtime mode fields and is accepted only when
    all three fields and the new JVM flag are absent.
    """
    extra = trial.get("loadGeneratorJvmArguments", [])
    permitted = ("-Dvectormatch.capacity.client.driver=isolated",
                 "-Dvectormatch.capacity.client.driver=shared")
    assert isinstance(extra, list), "Load-generator JVM arguments must be a list"
    assert len(extra) <= 1 and all(value in permitted for value in extra), "Disallowed load-generator JVM argument"
    runtime_fields = {"clientDriverMode", "clientDriverCount", "clientAeronMode"}
    declared = runtime_fields.intersection(configuration)
    if not declared:
        assert not extra, "Missing runtime declaration for new client mode"
        return list(extra)
    assert declared == runtime_fields, "Incomplete client transport runtime declaration"
    mode = configuration["clientDriverMode"]
    assert mode in ("isolated", "shared"), "Unknown client driver mode"
    expected_mode = extra[0].split("=", 1)[1] if extra else "isolated"
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


def main(root):
    campaign = json.loads((root / "campaign.json").read_text())
    deployment = json.loads((root / "deployment.json").read_text())
    fixed = {"outboxCapacity": 65536,
             "driverThreading": "SHARED", "archiveThreading": "SHARED",
             "idleStrategy": "BackoffIdleStrategy defaults",
             "socketSendBufferBytes": 131072, "socketReceiveBufferBytes": 131072,
             "aeronVersion": "1.53.3", **campaign["fixed"]}
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
            assert "-Daeron.cluster.max.sessions=128" in args
            assert args[args.index("-cp") + 1] == release + "/dist/cluster/lib/*"
            index = args.index("io.vectormatch.cluster.ClusterNodeMain")
            node_arguments = [str(node), trial["state"], str(fixed["portBase"]),
                              str(fixed["syncLevel"]), str(fixed["outboxCapacity"]), hosts]
            if fixed.get("stateProfile"):
                node_arguments.append(fixed["stateProfile"])
            assert args[index + 1:] == node_arguments
            if fixed.get("stateProfile"):
                startup = (directory / f"node{node}" / "process.log").read_text()
                assert "profile=" + fixed["stateProfile"] in startup, "Missing state profile startup evidence"
                assert "outbox=" + str(fixed["outboxCapacity"]) in startup, "Outbox startup evidence differs"
                assert "checkpointMaxBytes=" + str(fixed["checkpointMaxBytes"]) in startup
                assert "maxRetainedOrders=" + str(fixed["maxRetainedOrders"]) in startup
                assert "resultCachePerProducer=" + str(fixed["resultCachePerProducer"]) in startup
                hashes[f"node{node}/process.log"] = hashlib.sha256(startup.encode()).hexdigest()
            hashes[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot = directory / "prepared-snapshot.bin"
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == configuration["preparedSnapshotSha256"]
        hashes[snapshot.name] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        extra_jvm_arguments = load_generator_jvm_arguments(trial, configuration)
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
            "scope": "Recorded supervisor arguments and deployment-transfer hash receipts; not a hardware, kernel fsync or independent provider durability attestation. Idle/socket settings are pinned source constants."})
        checked.append({"id": directory.name, "preparedSnapshotSha256": configuration["preparedSnapshotSha256"]})
    assert len({row["preparedSnapshotSha256"] for row in checked}) <= 1, "Initial logical state changed"
    write(root / "configuration-verification.json", {"passed": True, "runs": checked,
                                                    "preparedStateIdentical": True, "fixed": fixed})
    print("VERIFIED_CONFIGURATIONS", len(checked))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "evidence/2026-10-23/runpod-capacity"))
