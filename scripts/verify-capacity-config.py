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
            assert args[index + 1:] == [str(node), trial["state"], str(fixed["portBase"]),
                                        str(fixed["syncLevel"]), str(fixed["outboxCapacity"]), hosts]
            hashes[str(path.relative_to(directory))] = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot = directory / "prepared-snapshot.bin"
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == configuration["preparedSnapshotSha256"]
        hashes[snapshot.name] = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        trial.update({"deploymentRevision": deployment["revision"],
                      "deploymentBundleSha256": deployment["bundleSha256"],
                      "fixedNodeConfiguration": fixed})
        write(directory / "trial.json", trial)
        write(directory / "configuration-verification.json", {
            "passed": True, "verifiedAtUtc": datetime.now(timezone.utc).isoformat(),
            "recordedArgumentsVerified": True, "preparedSnapshotDigestVerified": True,
            "rawSha256": hashes,
            "scope": "Recorded supervisor arguments and deployment-transfer hash receipts; not a hardware, kernel fsync or independent provider durability attestation. Idle/socket settings are pinned source constants."})
        checked.append({"id": directory.name, "preparedSnapshotSha256": configuration["preparedSnapshotSha256"]})
    assert len({row["preparedSnapshotSha256"] for row in checked}) <= 1, "Initial logical state changed"
    write(root / "configuration-verification.json", {"passed": True, "runs": checked,
                                                    "preparedStateIdentical": True, "fixed": fixed})
    print("VERIFIED_CONFIGURATIONS", len(checked))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "evidence/2026-10-23/runpod-capacity"))
