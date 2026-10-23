#!/usr/bin/env python3
"""Export every point in one fixed-configuration group; optionally upsert a UI cohort."""
import argparse
from pathlib import Path
import json
import math
import re


def make_capacity(summary, cohort_id=None, title=None, scope=None, report_path=None):
    rows = summary["trials"]
    fingerprints = {row.get("comparisonFingerprintSha256") for row in rows if row.get("comparisonFingerprintSha256")}
    if len(fingerprints) > 1:
        raise ValueError("Choose one fixed configuration campaign for one UI curve, including invalid trials")
    if any(row.get("measurementValid") and not row.get("comparisonFingerprintSha256") for row in rows):
        raise ValueError("Valid trials require a fixed configuration fingerprint")
    points = []
    for row in sorted(rows, key=lambda r: (r["targetArrivalRatePerSecond"] or 0, r["workers"] or 0, r["id"])):
        derived = row["derived"]
        window = row["arrivalWindowSeconds"]
        sufficient_window = type(window) in (int, float) and math.isfinite(window) and window >= 10
        points.append({"id": row["id"], "rate": row["targetArrivalRatePerSecond"], "workers": row["workers"],
                       "goodput": derived["arrivalWindowGoodputPerSecond"],
                       "p99Millis": derived["latency"]["conditionalAccepted"]["p99Millis"],
                       "queueDrops": derived["clientQueueFullNotSent"], "clientNotSent": derived["clientNotSent"],
                       "rejected": derived["businessRejected"], "serverErrors": derived["serverErrors"],
                       "unknown": derived["unknownAtInitialDeadline"], "unresolved": derived["unknownUnresolved"],
                       "allOfferedAcceptedP99Millis": derived["allOfferedAcceptedP99Millis"],
                       "drainSeconds": derived.get("drainSeconds"), "classification": row.get("classification"),
                       "peakBacklog": row["backlog"]["peakObservedOutstanding"],
                       "valid": row["measurementValid"], "stable": bool(row["observedStableWindow"] and sufficient_window),
                       "windowSeconds": window})
    capacity = {"title": title or "Three-node capacity under load", "updatedAt": summary.get("generatedAt"),
                "scope": scope or "Fixed leader 0 · private UDP · sync=2 · 1 GiB/member. Load generation shares member 2. Finite windows with bounded client queues; p99 includes scheduling and queueing and is conditional on accepted confirmation. All recorded trials are retained within this fixed configuration group.",
                "reportPath": report_path or "docs/CAPACITY_RESULTS.md", "points": points}
    if cohort_id:
        capacity["id"] = cohort_id
    if fingerprints:
        capacity["configurationFingerprint"] = next(iter(fingerprints))
    return capacity


def update_index(index, capacity, cohort_id=None):
    if not isinstance(index.get("runs"), list):
        raise ValueError("Existing evidence index must contain its historical runs")
    if cohort_id:
        cohorts = index.get("capacityCohorts", [])
        if not isinstance(cohorts, list) or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) for item in cohorts):
            raise ValueError("Existing capacityCohorts must be an array of objects with IDs")
        ids = [item["id"] for item in cohorts]
        if len(ids) != len(set(ids)):
            raise ValueError("Existing capacityCohorts contains duplicate IDs")
        if cohort_id in ids:
            cohorts[ids.index(cohort_id)] = capacity
        else:
            cohorts.append(capacity)
        index["capacityCohorts"] = cohorts
    # Legacy clients still receive one whole configuration group, never a merged curve.
    index["capacity"] = capacity
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--cohort-id", help="Append or replace this fixed-configuration group in index.capacityCohorts")
    parser.add_argument("--title")
    parser.add_argument("--scope")
    parser.add_argument("--report-path")
    args = parser.parse_args(argv)
    if args.cohort_id and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.cohort_id):
        parser.error("--cohort-id must contain 1..80 letters, digits, dots, underscores or hyphens")
    summary = json.loads(args.summary.read_text())
    capacity = make_capacity(summary, args.cohort_id, args.title, args.scope, args.report_path)
    index = update_index(json.loads(args.index.read_text()), capacity, args.cohort_id) if args.index else None
    encoded_capacity = json.dumps(capacity, indent=2, allow_nan=False) + "\n"
    encoded_index = json.dumps(index, indent=2, allow_nan=False) + "\n" if index is not None else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded_capacity)
    if args.index:
        args.index.write_text(encoded_index)
    print("EXPORTED_CAPACITY_POINTS", len(capacity["points"]), "COHORT", args.cohort_id or "legacy")


if __name__ == "__main__":
    main()
