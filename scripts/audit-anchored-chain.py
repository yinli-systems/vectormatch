#!/usr/bin/env python3
"""Join verified raw-pack audit indexes without averaging segment percentiles.

This checks continuity and recomputes exact service-only quantiles from the sample
reader's lossless frequency tables. It does not replace native full business
replay or independently download/replay private raw assets.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("samples", Path(__file__).with_name("audit-anchored-samples.py"))
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)
require = samples.require


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(root, expected):
    require(1 <= expected <= 100_000_000, "expected cumulative target bound")
    root = Path(root)
    packs, inputs, assets = [], [], set()
    combined = collections.Counter()
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not (folder / "PRIVATE_ASSET_VERIFIED.json").exists():
            continue
        receipt = json.loads((folder / "PRIVATE_ASSET_VERIFIED.json").read_text())
        require(all(receipt.get(k) is True for k in ["allOriginalMembersVerified", "authenticatedFullDownloadVerified", "nativeRunsAndAuditsExited"]), "incomplete raw retention/replay receipt")
        require(receipt["assetId"] not in assets, "duplicate raw asset")
        assets.add(receipt["assetId"])
        index = json.loads((folder / "EXACT_SERVICE_SAMPLES.json").read_text())
        require(index["replicated"] is False and index["allArrivalLatencyProven"] is False, "wrong measurement scope")
        manifest = json.loads((folder / "MEMBER_MANIFEST.json").read_text())["files"]
        histogram = collections.Counter()
        with gzip.open(folder / "exact-service-frequency.csv.gz", "rt") as stream:
            reader = csv.DictReader(stream)
            require(reader.fieldnames == ["duration_ns", "count"], "frequency schema")
            for row in reader:
                duration, count = int(row["duration_ns"]), int(row["count"])
                require(duration >= 0 and count > 0 and duration not in histogram, "invalid/duplicate frequency row")
                histogram[duration] = count
                require(len(histogram) <= samples.MAX_DISTINCT_DURATIONS, "histogram bound")
        require(samples.quantiles(histogram) == index["freshOrderSamples"], "frequency/index quantiles differ")
        require(sum(p["samples"] for p in index["packs"]) == sum(histogram.values()), "cohort sample count differs")
        for p in index["packs"]:
            member = p["member"]
            require(member in manifest and member.endswith("/raw.pack"), "missing canonical pack member")
            packs.append(dict(p, packSha256=manifest[member]["sha256"], assetId=receipt["assetId"]))
        combined.update(histogram)
        require(len(combined) <= samples.MAX_DISTINCT_DURATIONS, "combined histogram bound")
        inputs.append({"cohort": folder.name, "assetId": receipt["assetId"], "assetSha256": receipt["sha256"],
                       "inputSha256": {name: sha(folder / name) for name in ["PRIVATE_ASSET_VERIFIED.json", "MEMBER_MANIFEST.json", "EXACT_SERVICE_SAMPLES.json", "exact-service-frequency.csv.gz"]}})
    require(packs, "no verified packs")
    packs.sort(key=lambda p: p["firstCommand"])
    previous = None
    for p in packs:
        require(p["lastCommand"] == p["acceptedTotal"] + 2, "absolute command/accepted mismatch")
        require(p["samples"] == p["lastCommand"] - max(3, p["firstCommand"]) + 1, "sample interval mismatch")
        if previous is None:
            require(p["firstCommand"] == 1 and p["parentPackSha256"] == "0" * 64, "missing genesis or reset lineage")
        else:
            require(p["lineage"] == previous["lineage"], "changed lineage")
            require(p["firstCommand"] == previous["lastCommand"] + 1, "command gap/duplicate")
            require(p["parentPackSha256"] == previous["packSha256"], "parent pack hash differs")
            require(p["initialSnapshotSha256"] == previous["finalSnapshotSha256"], "snapshot continuity differs")
            require(p["acceptedTotal"] > previous["acceptedTotal"], "cumulative target did not advance")
        previous = p
    require(previous["acceptedTotal"] == expected and sum(combined.values()) == expected, "requested cumulative target incomplete")
    return {"schema": "anchored-chain-index-audit-1", "lineage": packs[0]["lineage"], "acceptedTotal": expected,
            "rawPackCount": len(packs), "separateColdContinuationBoundaries": len(packs) - 1,
            "firstCommand": packs[0]["firstCommand"], "lastCommand": previous["lastCommand"],
            "lastPackSha256": previous["packSha256"], "finalSnapshotSha256": previous["finalSnapshotSha256"],
            "exactFreshOrderServiceNs": samples.quantiles(combined), "singleBusinessLineageIndexVerified": True,
            "replicated": False, "uninterruptedUptimeProven": False, "allArrivalLatencyProven": False,
            "auditScope": "hash/counter/snapshot continuity of full-raw-derived indexes; native business replay and full private asset download are recorded prerequisites, not repeated by this index auditor",
            "inputs": inputs}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.root, args.expected)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "inputs"}))
