#!/usr/bin/env python3
"""Summarize cross-phase repeats of identical finite capacity-trial inputs.

Usage: summarize-capacity-repeats.py SUMMARY_JSON OUTPUT_JSON
This complements the analyzer's phase groups; it never rewrites those groups.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re


STABLE = "OBSERVED_STABLE_WINDOW"
NONSTABLE = "OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT"
METRICS = {
    "clientNotSentTotal": "clientNotSent",
    "queueFullNotSentTotal": "clientQueueFullNotSent",
    "initialUnknownTotal": "unknownAtInitialDeadline",
    "unresolvedUnknownTotal": "unknownUnresolved",
    "businessRejectedTotal": "businessRejected",
    "serverErrorsTotal": "serverErrors",
    "confirmedAcceptedTotal": "confirmedAccepted",
}


def numeric(value, positive=False, integer=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if value < 0 or positive and value <= 0 or integer and int(value) != value:
        return None
    return int(value) if integer else float(value)


def inputs(row):
    return {
        "comparisonFingerprintSha256": row.get("comparisonFingerprintSha256"),
        "workers": numeric(row.get("workers"), positive=True, integer=True),
        "queueCapacityPerWorker": numeric(row.get("queueCapacityPerWorker"), positive=True, integer=True),
        "targetArrivalRatePerSecond": numeric(row.get("targetArrivalRatePerSecond"), positive=True),
        "scheduledArrivals": numeric(row.get("scheduledArrivals"), positive=True, integer=True),
        "arrivalWindowSeconds": numeric(row.get("arrivalWindowSeconds"), positive=True),
    }


def trial_record(row, minimum_window):
    identity = inputs(row)
    complete = all(value is not None for value in identity.values())
    enough_window = identity["arrivalWindowSeconds"] is not None and identity["arrivalWindowSeconds"] >= minimum_window
    valid = row.get("measurementValid") is True
    stable = valid and complete and enough_window and row.get("classification") == STABLE and row.get("observedStableWindow") is True
    nonstable = valid and complete and enough_window and row.get("classification") == NONSTABLE and row.get("observedStableWindow") is False
    derived = row.get("derived") or {}
    conditional = ((derived.get("latency") or {}).get("conditionalAccepted") or {}).get("p99Millis")
    return {
        "id": row["id"], "phase": row.get("phase"), "repetition": row.get("repetition"),
        "classification": row.get("classification"), "measurementValid": row.get("measurementValid"),
        "observedStableWindow": row.get("observedStableWindow"), "inputsComplete": complete,
        "minimumWindowObserved": enough_window, "eligibleStable": stable, "eligibleNonstable": nonstable,
        "conditionalAcceptedP99Millis": numeric(conditional),
        "allOfferedAcceptedP99Millis": numeric(derived.get("allOfferedAcceptedP99Millis")),
        "counters": {key: numeric(derived.get(source), integer=True) for key, source in METRICS.items()},
    }


def aggregate_metrics(records):
    totals, missing = {}, {}
    for key in METRICS:
        values = [record["counters"][key] for record in records]
        missing[key] = [record["id"] for record in records if record["counters"][key] is None]
        totals[key] = sum(values) if all(value is not None for value in values) else None
    latencies = [record["conditionalAcceptedP99Millis"] for record in records if record["conditionalAcceptedP99Millis"] is not None]
    return {
        **totals, "missingCounterTrialIds": {key: value for key, value in missing.items() if value},
        "conditionalAcceptedP99MillisRange": {
            "minimum": min(latencies) if latencies else None,
            "maximum": max(latencies) if latencies else None,
            "reportedTrials": len(latencies),
            "missingTrialIds": [record["id"] for record in records if record["conditionalAcceptedP99Millis"] is None],
        },
        "allOfferedAcceptedP99UnavailableTrialIds": [record["id"] for record in records if record["allOfferedAcceptedP99Millis"] is None],
    }


def summarize(summary, input_sha256):
    rows = summary.get("trials")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Input summary must contain a trials array")
    identifiers = [row.get("id") for row in rows]
    if any(not isinstance(value, str) or not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("Every trial must have a distinct nonempty ID")
    fingerprints = [row.get("comparisonFingerprintSha256") for row in rows]
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value) for value in fingerprints):
        raise ValueError("Every trial, including invalid observations, requires a configuration fingerprint")
    fingerprints = {value.lower() for value in fingerprints}
    if len(fingerprints) > 1:
        raise ValueError("Mixed configuration fingerprints require separate cohort summaries")
    minimum_window = numeric((summary.get("criteria") or {}).get("minArrivalWindowSeconds", 10))
    if minimum_window is None:
        raise ValueError("Invalid minimum arrival window in analyzer criteria")
    grouped = defaultdict(list)
    group_inputs = {}
    for row in rows:
        identity = inputs(row)
        identity["comparisonFingerprintSha256"] = identity["comparisonFingerprintSha256"].lower()
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(encoded.encode()).hexdigest()
        grouped[key].append(trial_record(row, minimum_window))
        group_inputs[key] = identity
    groups, records = [], []
    for key in sorted(grouped):
        entries = grouped[key]
        records.extend(entries)
        stable = sum(record["eligibleStable"] for record in entries)
        nonstable = sum(record["eligibleNonstable"] for record in entries)
        if len(entries) < 2:
            verdict = "INSUFFICIENT_REPETITIONS"
        elif stable == len(entries):
            verdict = "REPEATEDLY_STABLE_WINDOW"
        elif nonstable == len(entries):
            verdict = "REPEATEDLY_NONSTABLE_WINDOW"
        elif stable and nonstable:
            verdict = "MIXED"
        else:
            verdict = "INCONCLUSIVE"
        groups.append({"groupId": key, "inputs": group_inputs[key], "trialCount": len(entries),
                       "trialIds": [record["id"] for record in entries],
                       "phases": sorted({str(record["phase"]) for record in entries}),
                       "classifications": dict(sorted(Counter(str(record["classification"]) for record in entries).items())),
                       "eligibleStableTrials": stable, "eligibleNonstableTrials": nonstable,
                       "otherOrInvalidTrials": len(entries) - stable - nonstable,
                       "repeatVerdict": verdict, "trials": entries, **aggregate_metrics(entries)})
    groups.sort(key=lambda group: tuple((group["inputs"][name] is None, group["inputs"][name] or 0)
                                       for name in ("targetArrivalRatePerSecond", "workers", "queueCapacityPerWorker", "scheduledArrivals", "arrivalWindowSeconds")))
    stable_groups = [group for group in groups if group["repeatVerdict"] == "REPEATEDLY_STABLE_WINDOW"]
    nonstable_groups = [group for group in groups if group["repeatVerdict"] == "REPEATEDLY_NONSTABLE_WINDOW"]
    highest = max((group["inputs"]["targetArrivalRatePerSecond"] for group in stable_groups), default=None)
    lowest = min((group["inputs"]["targetArrivalRatePerSecond"] for group in nonstable_groups), default=None)
    return {
        "schemaVersion": 1, "test": "capacity-cross-phase-repeat-summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(), "inputSummarySha256": input_sha256,
        "configurationFingerprintSha256": next(iter(fingerprints), None),
        "minimumRepeats": 2, "minimumArrivalWindowSeconds": minimum_window,
        "trialCount": len(rows), "groupCount": len(groups), "groups": groups,
        "highestRepeatedlyStableRate": highest, "lowestRepeatedlyNonstableRate": lowest,
        "highestRepeatedlyStableGroupIds": [group["groupId"] for group in stable_groups if group["inputs"]["targetArrivalRatePerSecond"] == highest],
        "lowestRepeatedlyNonstableGroupIds": [group["groupId"] for group in nonstable_groups if group["inputs"]["targetArrivalRatePerSecond"] == lowest],
        "mixedRates": sorted({group["inputs"]["targetArrivalRatePerSecond"] for group in groups if group["repeatVerdict"] == "MIXED"}),
        "mixedGroupIds": [group["groupId"] for group in groups if group["repeatVerdict"] == "MIXED"],
        "totalsAcrossAllTrials": aggregate_metrics(records),
        "scope": "Cross-phase repeats are grouped by exact configuration fingerprint, worker count, per-worker queue, target rate, scheduled arrivals and arrival-window duration. "
                 "At least two observations and agreement of every retained trial in a group are required for a repeated stable/nonstable verdict. Invalid or insufficient observations are retained and cannot establish repeated capacity. "
                 "Stable/nonstable classifications and minimum-window criteria come from the source analyzer. A conditional p99 range is a range of per-trial percentiles, not a pooled percentile; it excludes unconfirmed commands. Missing counters remain null. "
                 "Rate extrema refer to the listed matching-input groups; compare their worker/window contexts. No monotonicity, sustained capacity, precise ceiling, production SLA, bare matching-engine limit or HTTP/fanout capacity is inferred from these finite client + bounded queue + replicated-path observations.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args(argv)
    if args.summary_json.resolve() == args.output_json.resolve():
        parser.error("Output must not overwrite the source summary")
    source = args.summary_json.read_bytes()
    summary = json.loads(source)
    if not isinstance(summary, dict):
        raise ValueError("Input summary must be a JSON object")
    json.dumps(summary, allow_nan=False)
    result = summarize(summary, hashlib.sha256(source).hexdigest())
    result["inputSummaryPath"] = str(args.summary_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_json)
    print(json.dumps({"output": str(args.output_json), "trials": result["trialCount"],
                      "highestRepeatedlyStableRate": result["highestRepeatedlyStableRate"],
                      "lowestRepeatedlyNonstableRate": result["lowestRepeatedlyNonstableRate"], "mixedRates": result["mixedRates"]}))


if __name__ == "__main__":
    main()
