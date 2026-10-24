#!/usr/bin/env python3
"""Fail-closed preflight for a *candidate* local NVMe ext4/XFS test directory.

This checks visible mount/block-device metadata and usable capacity. It cannot
attest physical placement or prove power-loss durability. Those require separate
provider/operator evidence and fault-injection experiments.
"""

import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys


FILESYSTEMS = frozenset(("ext4", "xfs"))
REMOTE_MODEL_HINTS = (
    "elastic block store", "amazon ebs", "persistent disk", "azure disk",
    "virtual disk", "network", "iscsi", "ceph", "rbd", "virtio",
)


def command_json(argv):
    """Use explicit columns; a failed/malformed probe must never mean PASS."""
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise ValueError("probe failed: " + argv[0] + " (exit " + str(result.returncode) + ")")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise ValueError("non-JSON probe response: " + argv[0]) from error
    if not isinstance(payload, dict):
        raise ValueError("invalid probe object: " + argv[0])
    return payload


def _not_rotational(value):
    return ((type(value) is bool and value is False)
            or (type(value) is int and value == 0) or value == "0")


def classify(mounts, devices, free_bytes, required_growth_bytes, minimum_reserve_bytes):
    """Pure conservative classifier; does not trust disk names or FS types alone."""
    failures = []
    mount = {}
    roots = mounts.get("filesystems") if isinstance(mounts, dict) else None
    if not isinstance(roots, list) or len(roots) != 1 or not isinstance(roots[0], dict):
        failures.append("findmnt must identify exactly one mount")
    else:
        mount = roots[0]

    filesystem = mount.get("fstype")
    source = mount.get("source")
    if filesystem not in FILESYSTEMS:
        failures.append("backing filesystem is not ext4 or XFS")
    options = mount.get("options")
    if not isinstance(options, str) or "rw" not in options.split(","):
        failures.append("mount is not confirmed read-write")
    if not isinstance(source, str) or not source.startswith("/dev/") or "[" in source or "]" in source:
        failures.append("source is not a direct, unambiguous /dev block device")

    nodes = devices.get("blockdevices") if isinstance(devices, dict) else None
    lookup = {}
    if not isinstance(nodes, list) or not nodes:
        failures.append("lsblk returned no flat block-device inventory")
    else:
        for item in nodes:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                failures.append("lsblk device inventory is malformed")
                break
            path = item.get("path")
            if isinstance(path, str) and path.startswith("/dev/"):
                lookup[path] = item
            lookup["/dev/" + item["name"]] = item

    leaf = lookup.get(source) if isinstance(source, str) else None
    if leaf is None:
        failures.append("mount source is missing from lsblk")
    elif leaf.get("type") not in ("part", "disk"):
        failures.append("mount is backed by a virtual/mapped device, not a direct NVMe partition")

    disk = leaf
    seen = set()
    for _ in range(8):
        if not isinstance(disk, dict):
            break
        name = disk.get("name")
        if not isinstance(name, str) or name in seen:
            failures.append("invalid or cyclic block-device ancestry")
            disk = None
            break
        seen.add(name)
        parent = disk.get("pkname")
        if not parent:
            break
        disk = lookup.get("/dev/" + str(parent))
    else:
        failures.append("block-device ancestry exceeds safety bound")
        disk = None

    identified_device = {}
    if not isinstance(disk, dict) or disk.get("type") != "disk":
        failures.append("physical NVMe parent disk is not identified")
    else:
        identified_device = {field: disk.get(field) for field in ("name", "path", "type", "tran", "rota", "model")}
        if disk.get("tran") != "nvme":
            failures.append("parent disk transport is not reported as NVMe")
        if not _not_rotational(disk.get("rota")):
            failures.append("parent disk is not confirmed non-rotational")
        model = disk.get("model")
        if not isinstance(model, str) or not model.strip():
            failures.append("parent disk model is unknown; cannot classify local vs remote")
        elif any(hint in model.casefold() for hint in REMOTE_MODEL_HINTS):
            failures.append("disk model suggests remote/virtualized backing")

    if type(free_bytes) is not int or free_bytes < 0:
        failures.append("free capacity is unknown")
    if type(required_growth_bytes) is not int or required_growth_bytes <= 0:
        failures.append("positive maximum allocated-growth budget is required")
    if type(minimum_reserve_bytes) is not int or minimum_reserve_bytes <= 0:
        failures.append("positive runtime free-space reserve is required")
    if (type(free_bytes) is int and type(required_growth_bytes) is int
            and type(minimum_reserve_bytes) is int and free_bytes < required_growth_bytes + minimum_reserve_bytes):
        failures.append("insufficient free bytes for growth budget plus runtime reserve")

    return {
        "schema": "vectormatch.local-nvme-candidate.v1",
        "mount": {field: mount.get(field) for field in ("target", "source", "fstype", "options")},
        "parentDevice": identified_device,
        "capacity": {"freeBytes": free_bytes, "maximumAllocatedGrowthBytes": required_growth_bytes,
                     "minimumFreeRuntimeBytes": minimum_reserve_bytes},
        "candidateForDiskBackedExperiment": not failures,
        "strictPhysicalDurabilityProven": False,
        "operatorAndProviderPhysicalLocalityAttestationRequired": True,
        "powerLossOrDeviceFlushProofRequired": True,
        "rejectionReasons": failures,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Existing experiment directory; no files are created")
    parser.add_argument("--required-growth-bytes", type=int, required=True)
    parser.add_argument("--minimum-reserve-bytes", type=int, required=True)
    args = parser.parse_args(argv)
    report = {"timestampUtc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "checkedPath": args.path, "strictPhysicalDurabilityProven": False}
    try:
        if sys.platform != "linux":
            raise ValueError("Linux block-device inspection is required")
        path = Path(args.path).resolve(strict=True)
        if not path.is_dir():
            raise ValueError("experiment path must be an existing directory")
        mounts = command_json(["findmnt", "--json", "--first-only", "--target", str(path),
                               "--output", "TARGET,SOURCE,FSTYPE,OPTIONS"])
        devices = command_json(["lsblk", "--json", "--list", "--output", "NAME,PATH,TYPE,PKNAME,TRAN,ROTA,MODEL"])
        report.update(classify(mounts, devices, shutil.disk_usage(path).free,
                               args.required_growth_bytes, args.minimum_reserve_bytes))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        report.update({"candidateForDiskBackedExperiment": False,
                       "rejectionReasons": [type(error).__name__ + ": " + str(error)]})
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["candidateForDiskBackedExperiment"] else 2


if __name__ == "__main__":
    sys.exit(main())
