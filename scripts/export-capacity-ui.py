#!/usr/bin/env python3
"""Export every measured point from one configuration campaign to the evidence UI."""
import argparse
from pathlib import Path
import json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--index", type=Path)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    rows = summary["trials"]
    fingerprints = {row["comparisonFingerprintSha256"] for row in rows if row["measurementValid"]}
    if len(fingerprints) > 1:
        raise ValueError("Choose one fixed configuration campaign for one UI curve")
    points = []
    for row in sorted(rows, key=lambda r: (r["targetArrivalRatePerSecond"] or 0, r["workers"] or 0, r["id"])):
        derived = row["derived"]
        points.append({"id": row["id"], "rate": row["targetArrivalRatePerSecond"], "workers": row["workers"],
                       "goodput": derived["arrivalWindowGoodputPerSecond"],
                       "p99Millis": derived["latency"]["conditionalAccepted"]["p99Millis"],
                       "queueDrops": derived["clientQueueFullNotSent"], "clientNotSent": derived["clientNotSent"],
                       "rejected": derived["businessRejected"], "serverErrors": derived["serverErrors"],
                       "unknown": derived["unknownAtInitialDeadline"], "unresolved": derived["unknownUnresolved"],
                       "allOfferedAcceptedP99Millis": derived["allOfferedAcceptedP99Millis"],
                       "peakBacklog": row["backlog"]["peakObservedOutstanding"],
                       "valid": row["measurementValid"], "stable": row["observedStableWindow"],
                       "windowSeconds": row["arrivalWindowSeconds"]})
    capacity = {"title": "Three-node capacity under load", "updatedAt": summary.get("generatedAt"),
                "scope": "Fixed leader 0 · private UDP · sync=2 · 1 GiB/member. Load generation shares member 2. Finite windows with bounded client queues; p99 includes scheduling and queueing and is conditional on accepted confirmation. All recorded trials are retained.",
                "reportPath": "docs/CAPACITY_RESULTS.md", "points": points}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(capacity, indent=2) + "\n")
    if args.index:
        index = json.loads(args.index.read_text())
        if not isinstance(index.get("runs"), list):
            raise ValueError("Existing evidence index must contain its historical runs")
        index["capacity"] = capacity
        args.index.write_text(json.dumps(index, indent=2) + "\n")
    print("EXPORTED_CAPACITY_POINTS", len(points))


if __name__ == "__main__":
    main()
