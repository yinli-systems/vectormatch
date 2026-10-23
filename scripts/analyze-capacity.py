#!/usr/bin/env python3
"""Recompute finite-window capacity evidence without dropping failed trials.

Consumes RemoteCapacityExperiment's result/load-result, arrivals and backlog CSV,
plus the campaign's trial.json and fixed-leader-check.json. No live access.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile


DEFAULT_CRITERIA = {
    "minArrivalWindowSeconds": 10.0,
    "minArrivalWindowGoodputFraction": .95,
    "maxDrainSecondsFloor": .1,
    "maxDrainWindowFraction": .01,
    "maxBacklogGrowthCommandsFloor": 2.0,
    "maxBacklogGrowthArrivalFraction": .01,
    "requireFixedLeaderTermEvidence": True,
    "latencyTargetP99Millis": None,
}
OUTCOMES = {"CONFIRMED_ACCEPTED", "BUSINESS_REJECTED", "SERVER_ERROR", "INVALID_REPLY",
            "CLIENT_QUEUE_FULL_NOT_SENT", "DRAIN_NOT_SENT", "WORKER_BLOCKED_UNKNOWN_NOT_SENT", "UNKNOWN_UNRESOLVED"}
COMPARISON_KEYS = ("memberHosts", "aeronMtuLength", "clientEgressHost", "loadGeneratorUsesMemberAddress", "javaVersion",
                   "workload", "loadModel", "requestTimeoutMs", "drainTimeoutMs", "schedulerLatenessLimitMs",
                   "expectedLeader", "portBase", "warmupCommands", "seededBuyerAccounts", "seededMakerQuantity",
                   "seededQuotePerBuyer", "priceTicks", "quantityLotsPerMeasuredCommand")
RAW_KEYS = ("scheduledArrivals", "targetArrivalRatePerSecond", "workers", "queueCapacityPerWorker",
            "arrivalWindowSeconds", "completionWindowSeconds", "confirmedAcceptedCommands", "businessRejectedCommands",
            "serverErrors", "clientNotSentCommands", "clientQueueFullNotSent", "drainNotSent", "workerBlockedUnknownNotSent",
            "unknownAtInitialDeadline", "resolvedAfterInitialUnknown", "unresolvedFinal", "confirmedWithinArrivalWindow",
            "confirmedWithinArrivalWindowPerSecond", "confirmedIncludingDrainPerSecond", "drainSeconds",
            "schedulerLatenessAboveLimitCount", "generatorTimingInvalid", "executeStartAfterPlannedDeadlineCount",
            "executeStartDeadlineLimitMs", "allOfferedAcceptedP99Microseconds", "scheduledToConfirmedMicroseconds",
            "acceptedScheduledToConfirmedMicroseconds", "executeInitialAttemptMicroseconds", "queueDelayMicroseconds",
            "schedulerLatenessMicroseconds", "transportCountersByWorker", "passed", "measurementValid", "fixedLeaderVerified",
            "leaderChanged", "canonicalSnapshotBytesVerified", "stateHashVerified", "invariantsVerified", "assetConservationVerified")


def nearest_rank(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def distribution_ns(values):
    values = sorted(values)
    return {"count": len(values), "minMillis": values[0] / 1e6 if values else None,
            **{name + "Millis": nearest_rank(values, fraction) / 1e6 if values else None
               for name, fraction in (("p50", .5), ("p95", .95), ("p99", .99), ("p999", .999))},
            "maxMillis": values[-1] / 1e6 if values else None}


def reject_constant(value):
    raise ValueError("Nonfinite JSON numeric constant")


def read_json(path):
    value = json.loads(path.read_text(), parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    json.dumps(value, allow_nan=False)  # Also reject exponent overflow such as 1e999.
    return value


def load_json(directory, name, errors, sources, optional=False):
    path = directory / name
    if not path.exists() and optional:
        return None
    try:
        value = read_json(path)
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return value
    except (OSError, ValueError) as exc:
        errors.append({"file": name, "error": type(exc).__name__})
        return None


def load_csv(directory, name, errors, sources):
    path = directory / name
    try:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("Missing or repeated CSV header")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError("CSV row/header length mismatch")
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return rows
    except (OSError, ValueError, csv.Error) as exc:
        errors.append({"file": name, "error": type(exc).__name__})
        return []


def number(value, integer=False):
    if value is None or value == "":
        return None
    if type(value) is bool:
        raise ValueError("Boolean is not a numeric metric")
    result = int(value) if integer else float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite numeric field")
    return result


def truth(value):
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise ValueError("Expected boolean field")


def analyze_arrivals(rows, scheduled, window_seconds):
    outcomes = Counter()
    latency = {name: [] for name in ("conditionalReply", "conditionalAccepted", "initialExecute", "queue", "scheduler")}
    accepted_within, initial_unknown, resolved_unknown, invalid = 0, 0, 0, []
    confirmation_offsets = []
    indices = []
    for index, row in enumerate(rows):
        try:
            arrival_index = number(row["index"], True)
            if arrival_index is None or arrival_index < 0:
                raise ValueError("Invalid arrival index")
            indices.append(arrival_index)
            outcome = row["outcome"]
            outcomes[outcome] += 1
            if outcome not in OUTCOMES:
                invalid.append({"row": index, "issue": "nonterminal-or-unrecognized-outcome", "outcome": outcome})
            confirmed = number(row["confirmed_offset_ns"], True)
            scheduled_to_confirmed = number(row["scheduled_to_confirmed_ns"], True)
            if confirmed is not None:
                if scheduled_to_confirmed is None or scheduled_to_confirmed < 0:
                    raise ValueError("Missing or negative returned-response latency")
                planned = number(row.get("planned_offset_ns"), True)
                if planned is not None and confirmed - planned != scheduled_to_confirmed:
                    raise ValueError("Latency differs from confirmation minus planned offset")
                latency["conditionalReply"].append(scheduled_to_confirmed)
                if outcome == "CONFIRMED_ACCEPTED":
                    latency["conditionalAccepted"].append(scheduled_to_confirmed)
                    confirmation_offsets.append(confirmed)
                    if window_seconds is not None and confirmed <= window_seconds * 1e9:
                        accepted_within += 1
            elif outcome in ("CONFIRMED_ACCEPTED", "BUSINESS_REJECTED", "SERVER_ERROR", "INVALID_REPLY"):
                raise ValueError("Returned outcome lacks confirmation timestamp")
            for key, column in (("initialExecute", "initial_execute_rtt_ns"), ("queue", "queue_delay_ns"), ("scheduler", "scheduler_lateness_ns")):
                value = number(row.get(column), True)
                if value is not None:
                    if value < 0:
                        raise ValueError("Negative latency")
                    latency[key].append(value)
            if truth(row["unknown_at_initial_deadline"]):
                initial_unknown += 1
                if confirmed is not None:
                    resolved_unknown += 1
        except (ValueError, KeyError, TypeError) as exc:
            invalid.append({"row": index, "issue": type(exc).__name__})
    if len(set(indices)) != len(indices) or sorted(indices) != list(range(len(rows))):
        invalid.append({"issue": "arrival-indices-must-be-unique-and-contiguous"})
    if scheduled is not None and len(rows) != scheduled:
        invalid.append({"issue": "arrival-row-count-differs-from-scheduled", "expected": scheduled, "actual": len(rows)})
    accepted = outcomes["CONFIRMED_ACCEPTED"]
    all_finite = bool(rows) and not invalid and len(latency["conditionalAccepted"]) == len(rows) == scheduled
    completion_seconds = max([window_seconds or 0] + [value / 1e9 for value in confirmation_offsets])
    result = {"rows": len(rows), "outcomes": dict(sorted(outcomes.items())), "confirmedAccepted": accepted,
              "businessRejected": outcomes["BUSINESS_REJECTED"], "serverErrors": outcomes["SERVER_ERROR"] + outcomes["INVALID_REPLY"],
              "clientQueueFullNotSent": outcomes["CLIENT_QUEUE_FULL_NOT_SENT"], "drainNotSent": outcomes["DRAIN_NOT_SENT"],
              "workerBlockedUnknownNotSent": outcomes["WORKER_BLOCKED_UNKNOWN_NOT_SENT"],
              "clientNotSent": sum(outcomes[name] for name in ("CLIENT_QUEUE_FULL_NOT_SENT", "DRAIN_NOT_SENT", "WORKER_BLOCKED_UNKNOWN_NOT_SENT")),
              "unknownAtInitialDeadline": initial_unknown, "resolvedAfterInitialUnknown": resolved_unknown,
              "unknownUnresolved": outcomes["UNKNOWN_UNRESOLVED"], "confirmedWithinArrivalWindow": accepted_within,
              "arrivalWindowGoodputPerSecond": accepted_within / window_seconds if window_seconds and window_seconds > 0 else None,
              "completionWindowSeconds": completion_seconds,
              "confirmedIncludingDrainPerSecond": accepted / completion_seconds if completion_seconds > 0 else None,
              "drainSeconds": max(0, completion_seconds - window_seconds) if window_seconds is not None else None,
              "allOfferedAcceptedFinite": all_finite,
              "allOfferedAcceptedP99Millis": distribution_ns(latency["conditionalAccepted"])["p99Millis"] if all_finite else None,
              "latency": {name: distribution_ns(values) for name, values in latency.items()}, "validationIssues": invalid}
    return result


def analyze_backlog(rows, window_seconds):
    points, issues = [], []
    for index, row in enumerate(rows):
        try:
            offset = number(row["offset_ns"], True) / 1e9
            queue = number(row["queue_depth"], True)
            inflight = number(row["in_flight"], True)
            if queue < 0 or inflight < 0:
                raise ValueError("Negative queue/inflight gauge")
            points.append((offset, queue + inflight, queue, inflight))
        except (TypeError, KeyError, ValueError):
            issues.append({"row": index, "issue": "invalid-backlog-row"})
    if any(right[0] < left[0] for left, right in zip(points, points[1:])):
        issues.append({"issue": "nonmonotonic-backlog-offset"})
    selected = [point for point in points if window_seconds is not None and window_seconds / 2 <= point[0] <= window_seconds]
    trend = growth = endpoint_growth = None
    span = 0
    if len(selected) >= 2:
        xs, ys = [p[0] for p in selected], [p[1] for p in selected]
        mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
        denominator = sum((x - mean_x) ** 2 for x in xs)
        if denominator > 0:
            trend = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator
            span = xs[-1] - xs[0]
            growth = max(0, trend * span)
            endpoint_growth = ys[-1] - ys[0]
    return {"samples": len(points), "secondHalfWindowSamples": len(selected), "secondHalfSpanSeconds": span,
            "secondHalfOutstandingTrendCommandsPerSecond": trend, "secondHalfFittedGrowthCommands": growth,
            "secondHalfEndpointGrowthCommands": endpoint_growth,
            "peakQueueDepth": max((point[2] for point in points), default=None),
            "peakInFlight": max((point[3] for point in points), default=None),
            "peakObservedOutstanding": max((point[1] for point in points), default=None),
            "validationIssues": issues, "scope": "Non-atomic queue_depth + in_flight observations; not exact queue conservation. "
            "Growth is positive OLS trend times observed span in the second half of the arrival window; drain samples excluded."}


def leader_evidence_valid(value):
    if value is None or value.get("passed") is not True:
        return False
    if value.get("preTerm") is None or value.get("postTerm") != value.get("preTerm"):
        return False
    terms = value.get("observedTerms")
    return isinstance(terms, list) and bool(terms) and all(term == value["preTerm"] for term in terms)


def comparison_identity(configuration, trial):
    """Check declared identities before grouping; does not attest binaries or node settings."""
    issues = []
    release = trial.get("release", configuration.get("release"))
    revisions = []
    for source in (trial, configuration):
        for key in ("sourceRevision", "revision", "appRevision", "deploymentRevision", "codeRevision"):
            value = source.get(key)
            if value is None:
                continue
            values = list(value.values()) if isinstance(value, dict) else [value]
            if not values or any(not isinstance(item, str) or not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", item) for item in values):
                issues.append(f"invalid {key}: expected full source commit hash")
            else:
                revisions.extend(item.lower() for item in values)
    release_revision = None
    if release is not None:
        if not isinstance(release, str) or not release:
            issues.append("release must be a nonempty string")
        else:
            basename = Path(release).name
            if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", basename):
                release_revision = basename.lower()
                revisions.append(release_revision)
    distinct_revisions = sorted(set(revisions))
    if not distinct_revisions:
        issues.append("source revision missing; a full commit hash or commit-named release is required")
    elif len(distinct_revisions) != 1:
        issues.append("source revision declarations disagree")

    def declared(name, predicate, expectation):
        values = [source[name] for source in (trial, configuration) if name in source]
        if not values:
            issues.append(f"{name} missing; {expectation}")
            return None
        value = values[0]
        if not predicate(value):
            issues.append(f"invalid {name}; {expectation}")
        if any(other != value for other in values[1:]):
            issues.append(f"{name} declarations disagree")
        return value

    sha256 = lambda value: isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None
    bundle = declared("deploymentBundleSha256", sha256, "a deployment archive SHA-256 is required")
    prepared = declared("preparedSnapshotSha256", sha256, "a prepared-state SHA-256 is required")
    fixed = declared("fixedNodeConfiguration", lambda value: isinstance(value, dict) and bool(value),
                     "a nonempty common node-configuration object is required")
    identity = {"sourceRevision": distinct_revisions[0] if len(distinct_revisions) == 1 else None,
                "release": release, "deploymentBundleSha256": bundle.lower() if isinstance(bundle, str) else bundle,
                "preparedSnapshotSha256": prepared.lower() if isinstance(prepared, str) else prepared,
                "fixedNodeConfiguration": fixed}
    return identity, issues


def analyze_trial(directory, criteria=None):
    criteria = {**DEFAULT_CRITERIA, **(criteria or {})}
    errors, sources = [], {}
    configuration = load_json(directory, "configuration.json", errors, sources, optional=True) or {}
    trial = load_json(directory, "trial.json", errors, sources, optional=True) or {}
    fixed_leader = load_json(directory, "fixed-leader-check.json", errors, sources, optional=True)
    failure_present = (directory / "failure.json").exists()
    failure = load_json(directory, "failure.json", errors, sources, optional=True)
    result = load_json(directory, "result.json", errors, sources, optional=True)
    load_result = load_json(directory, "load-result.json", errors, sources, optional=True)
    source_name = "result.json" if result is not None else "load-result.json" if load_result is not None else None
    raw = result if result is not None else load_result or {}
    arrivals = load_csv(directory, "arrivals.csv", errors, sources)
    backlog = load_csv(directory, "backlog.csv", errors, sources)
    def field(*keys):
        for source in (raw, configuration, trial):
            for key in keys:
                if key in source:
                    return source[key]
        return None
    try:
        scheduled = number(field("scheduledArrivals", "arrivals"), True)
        rate = number(field("targetArrivalRatePerSecond", "ratePerSecond", "rate"))
        window = number(field("arrivalWindowSeconds", "windowSeconds"))
        if window is None and rate and scheduled is not None:
            window = scheduled / rate
        if scheduled is None or scheduled <= 0 or rate is None or rate <= 0 or window is None or window <= 0:
            raise ValueError("Missing positive offered count/rate/window")
    except (ValueError, TypeError):
        scheduled = rate = window = None
        errors.append({"file": source_name, "error": "invalid-or-missing-offered-count-rate-window"})
    derived = analyze_arrivals(arrivals, scheduled, window)
    queue = analyze_backlog(backlog, window)
    identity, identity_issues = comparison_identity(configuration, trial)
    consistency = []
    for key, value in (("confirmedAcceptedCommands", derived["confirmedAccepted"]), ("businessRejectedCommands", derived["businessRejected"]),
                       ("serverErrors", derived["serverErrors"]), ("clientNotSentCommands", derived["clientNotSent"]),
                       ("unknownAtInitialDeadline", derived["unknownAtInitialDeadline"]), ("unresolvedFinal", derived["unknownUnresolved"]),
                       ("confirmedWithinArrivalWindow", derived["confirmedWithinArrivalWindow"])):
        if key in raw and raw[key] != value:
            consistency.append({"field": key, "reported": raw[key], "recomputed": value})
    validation_checks = {
        "finalResultPresent": result is not None,
        "noFailureArtifact": not failure_present,
        "resultPassed": raw.get("passed") is True,
        "measurementValid": raw.get("measurementValid") is True,
        "canonicalSnapshotBytesVerified": raw.get("canonicalSnapshotBytesVerified") is True,
        "fixedLeaderVerified": raw.get("fixedLeaderVerified") is True and raw.get("leaderChanged") is False,
        "fixedLeaderTermEvidence": leader_evidence_valid(fixed_leader) if criteria["requireFixedLeaderTermEvidence"] else True,
        "schedulerTimingValid": raw.get("generatorTimingInvalid") is False and raw.get("schedulerLatenessAboveLimitCount") == 0,
        "inputsReadable": not errors,
        "arrivalRecordsValid": not derived["validationIssues"],
        "backlogRecordsValid": not queue["validationIssues"],
        "reportedCountsMatchRawCsv": not consistency,
        "configurationIdentityVerified": not identity_issues,
    }
    drain_limit = max(criteria["maxDrainSecondsFloor"], (window or 0) * criteria["maxDrainWindowFraction"])
    growth_limit = max(criteria["maxBacklogGrowthCommandsFloor"], (scheduled or 0) * criteria["maxBacklogGrowthArrivalFraction"])
    goodput_fraction = derived["arrivalWindowGoodputPerSecond"] / rate if rate and derived["arrivalWindowGoodputPerSecond"] is not None else None
    stability_checks = {
        "minimumWindowObserved": window is not None and window >= criteria["minArrivalWindowSeconds"],
        "allOfferedAcceptedFinite": derived["allOfferedAcceptedFinite"],
        "noInitialUnknown": derived["unknownAtInitialDeadline"] == 0,
        "noUnresolvedUnknown": derived["unknownUnresolved"] == 0,
        "arrivalWindowGoodputFraction": goodput_fraction is not None and goodput_fraction >= criteria["minArrivalWindowGoodputFraction"],
        "boundedDrain": derived["drainSeconds"] is not None and derived["drainSeconds"] <= drain_limit,
        "boundedSecondHalfBacklogGrowth": queue["secondHalfFittedGrowthCommands"] is not None and queue["secondHalfFittedGrowthCommands"] <= growth_limit,
    }
    valid = all(validation_checks.values())
    stable = valid and all(stability_checks.values())
    assessment_complete = valid and stability_checks["minimumWindowObserved"] and queue["secondHalfFittedGrowthCommands"] is not None
    classification = ("OBSERVED_STABLE_WINDOW" if stable else "OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT" if assessment_complete
                      else "INSUFFICIENT_WINDOW_OBSERVATIONS" if valid else "INVALID_OR_INCOMPLETE")
    conditional_p99 = derived["latency"]["conditionalAccepted"]["p99Millis"]
    target = criteria["latencyTargetP99Millis"]
    comparison = {key: configuration.get(key) for key in COMPARISON_KEYS}
    comparison.update(identity)
    fingerprint = hashlib.sha256(json.dumps(comparison, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"id": trial.get("id", directory.name), "directory": str(directory), "sourceResult": source_name,
            "phase": trial.get("phase"), "repetition": trial.get("repetition"), "trial": trial,
            "configuration": configuration, "fixedLeaderCheck": fixed_leader,
            "comparisonConfiguration": comparison, "comparisonFingerprintSha256": fingerprint,
            "configurationIdentityIssues": identity_issues,
            "configurationIdentityScope": "Checks completeness and agreement of declared source/deployment/prepared-state/configuration identities. Artifact bytes and actual node configuration require separate deployment evidence. Rate, worker count and queue size are not inside this fingerprint; grouping additionally separates phase/workers/queue.",
            "targetArrivalRatePerSecond": rate, "scheduledArrivals": scheduled, "arrivalWindowSeconds": window,
            "workers": field("workers"), "queueCapacityPerWorker": field("queueCapacityPerWorker", "queuePerWorker"),
            "rawSummary": {key: raw[key] for key in RAW_KEYS if key in raw},
            "derived": derived, "backlog": queue, "inputErrors": errors, "countMismatches": consistency,
            "inputSha256": sources, "validationChecks": validation_checks,
            "stabilityChecks": stability_checks, "effectiveDrainLimitSeconds": drain_limit,
            "effectiveBacklogGrowthLimitCommands": growth_limit, "arrivalWindowGoodputFraction": goodput_fraction,
            "measurementValid": valid, "observedStableWindow": stable, "classification": classification,
            "stabilityAssessmentComplete": assessment_complete,
            "latencyTargetMet": None if target is None or conditional_p99 is None else conditional_p99 <= target,
            "failureArtifactPresent": failure_present}


def summarize_groups(trials):
    grouped = defaultdict(list)
    for trial in trials:
        grouped[(str(trial["phase"]), str(trial["workers"]), str(trial["queueCapacityPerWorker"]), trial["comparisonFingerprintSha256"])].append(trial)
    groups = []
    for key, rows in sorted(grouped.items()):
        by_rate = defaultdict(list)
        for row in rows:
            if row["targetArrivalRatePerSecond"] is not None:
                by_rate[row["targetArrivalRatePerSecond"]].append(row)
        points = [{"targetArrivalRatePerSecond": rate, "trialIds": [row["id"] for row in entries],
                   "trials": len(entries), "validTrials": sum(row["measurementValid"] for row in entries),
                   "observedStableTrials": sum(row["observedStableWindow"] for row in entries),
                   "allReplicationsObservedStable": all(row["observedStableWindow"] for row in entries)}
                  for rate, entries in sorted(by_rate.items())]
        stable_rates = [point["targetArrivalRatePerSecond"] for point in points if point["allReplicationsObservedStable"]]
        lower = max(stable_rates, default=None)
        higher_observed = [row["targetArrivalRatePerSecond"] for row in rows if row["classification"] == "OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT"
                           and row["targetArrivalRatePerSecond"] is not None and (lower is None or row["targetArrivalRatePerSecond"] > lower)]
        groups.append({"phase": key[0], "workers": rows[0]["workers"], "queueCapacityPerWorker": rows[0]["queueCapacityPerWorker"],
                       "comparisonFingerprintSha256": key[3],
                       "points": points, "highestAllReplicationsStableObservedRate": lower,
                       "lowestHigherValidNonstableObservedRate": min(higher_observed, default=None),
                       "scope": "Observed finite windows with this client concurrency and bounded queues; no untested-rate, long-run or unconstrained-engine limit claim."})
    return groups


CSV_FIELDS = ("id", "phase", "repetition", "target_rate_per_second", "workers", "queue_per_worker", "arrival_window_seconds",
              "valid", "observed_stable_window", "classification", "accepted", "client_not_sent", "client_queue_full_not_sent",
              "business_rejected", "server_errors", "initial_unknown", "unresolved_unknown", "scheduler_invalid",
              "arrival_window_goodput_per_second", "including_drain_per_second", "drain_seconds", "conditional_reply_p99_ms",
              "conditional_accepted_p99_ms", "all_offered_accepted_finite", "all_offered_accepted_p99_ms", "second_half_backlog_growth",
              "peak_queue_depth", "peak_in_flight", "failure_artifact_present")


def csv_row(trial):
    derived, queue, raw = trial["derived"], trial["backlog"], trial["rawSummary"]
    values = [trial["id"], trial["phase"], trial["repetition"], trial["targetArrivalRatePerSecond"], trial["workers"], trial["queueCapacityPerWorker"],
              trial["arrivalWindowSeconds"], trial["measurementValid"], trial["observedStableWindow"], trial["classification"],
              derived["confirmedAccepted"], derived["clientNotSent"], derived["clientQueueFullNotSent"], derived["businessRejected"], derived["serverErrors"],
              derived["unknownAtInitialDeadline"], derived["unknownUnresolved"], raw.get("generatorTimingInvalid"),
              derived["arrivalWindowGoodputPerSecond"], derived["confirmedIncludingDrainPerSecond"], derived["drainSeconds"],
              derived["latency"]["conditionalReply"]["p99Millis"], derived["latency"]["conditionalAccepted"]["p99Millis"],
              derived["allOfferedAcceptedFinite"], derived["allOfferedAcceptedP99Millis"], queue["secondHalfFittedGrowthCommands"],
              queue["peakQueueDepth"], queue["peakInFlight"], trial["failureArtifactPresent"]]
    return dict(zip(CSV_FIELDS, values))


def plot_trials(trials, output_dir):
    # Font cache goes in a temporary directory; do not write into user config/home.
    with tempfile.TemporaryDirectory(prefix="vectormatch-capacity-plot-") as cache:
        previous = os.environ.get("MPLCONFIGDIR")
        os.environ["MPLCONFIGDIR"] = cache
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return {"status": "skipped", "reason": "matplotlib-not-installed; no dependency installation attempted"}
        finally:
            if previous is None:
                os.environ.pop("MPLCONFIGDIR", None)
            else:
                os.environ["MPLCONFIGDIR"] = previous
        figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
        groups = defaultdict(list)
        for trial in trials:
            if trial["targetArrivalRatePerSecond"] is not None:
                groups[(trial["phase"], trial["workers"], trial["queueCapacityPerWorker"], trial["comparisonFingerprintSha256"])].append(trial)
        for (phase, workers, queue, fingerprint), rows in groups.items():
            rows = sorted(rows, key=lambda row: row["targetArrivalRatePerSecond"])
            label = f"{phase or 'trial'}: workers={workers}, queue={queue}, cfg={fingerprint[:6]}"
            x = [row["targetArrivalRatePerSecond"] for row in rows]
            axes[0, 0].plot(x, [row["derived"]["arrivalWindowGoodputPerSecond"] for row in rows], "o-", label=label)
            axes[0, 1].plot(x, [row["derived"]["latency"]["conditionalAccepted"]["p99Millis"] for row in rows], "o-", label=label)
            axes[1, 0].plot(x, [row["derived"]["clientNotSent"] / row["scheduledArrivals"] if row["scheduledArrivals"] else None for row in rows], "o-", label=label)
            axes[1, 1].plot(x, [row["backlog"]["secondHalfFittedGrowthCommands"] for row in rows], "o-", label=label)
            invalid = [row for row in rows if not row["measurementValid"]]
            for row in invalid:
                value = row["derived"]["arrivalWindowGoodputPerSecond"]
                if value is not None:
                    axes[0, 0].scatter([row["targetArrivalRatePerSecond"]], [value], marker="x", color="red", s=90, zorder=5)
        titles = (("Accepted goodput during arrival window", "commands / second"),
                  ("Accepted-response conditional p99 (includes queue)", "milliseconds"),
                  ("Client admission / drain loss", "fraction of offered arrivals"),
                  ("Second-half fitted outstanding growth", "commands"))
        for axis, (title, ylabel) in zip(axes.flat, titles):
            axis.set(title=title, xlabel="Target offered arrivals / second", ylabel=ylabel)
            axis.grid(alpha=.25)
            if groups:
                axis.legend(fontsize=7)
        figure.suptitle("VectorMatch finite-window capacity trials — every trial retained; red X = invalid measurement", fontsize=12)
        files = []
        for extension in ("png", "svg"):
            path = output_dir / f"capacity.{extension}"
            figure.savefig(path, dpi=160)
            files.append(path.name)
        plt.close(figure)
        return {"status": "generated", "files": files,
                "scope": "Conditional p99 excludes unconfirmed/rejected offers; use CSV all-offered-finite and loss columns. Lines connect observations, not fitted capacity estimates."}


def finite_nonnegative(value):
    number_value = float(value)
    if not math.isfinite(number_value) or number_value < 0:
        raise argparse.ArgumentTypeError("Expected finite nonnegative value")
    return number_value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--campaign", "--manifest", type=Path)
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--allow-missing-fixed-term-check", action="store_true", help="Explicitly relax independent term-observation requirement")
    for key, flag in (("minArrivalWindowSeconds", "min-arrival-window-seconds"),
                      ("minArrivalWindowGoodputFraction", "min-goodput-fraction"),
                      ("maxDrainSecondsFloor", "max-drain-seconds-floor"),
                      ("maxDrainWindowFraction", "max-drain-window-fraction"),
                      ("maxBacklogGrowthCommandsFloor", "max-backlog-growth-floor"),
                      ("maxBacklogGrowthArrivalFraction", "max-backlog-growth-arrival-fraction"),
                      ("latencyTargetP99Millis", "latency-target-p99-ms")):
        parser.add_argument("--" + flag, dest=key, default=DEFAULT_CRITERIA[key], type=finite_nonnegative)
    args = parser.parse_args(argv)
    if not args.runs_dir.is_dir():
        parser.error("--runs-dir must be an existing directory")
    if args.minArrivalWindowGoodputFraction > 1:
        parser.error("--min-goodput-fraction must be <= 1")
    criteria = {key: getattr(args, key) for key in DEFAULT_CRITERIA if key != "requireFixedLeaderTermEvidence"}
    criteria["requireFixedLeaderTermEvidence"] = not args.allow_missing_fixed_term_check
    trials = [analyze_trial(path, criteria) for path in sorted(args.runs_dir.iterdir()) if path.is_dir()]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    campaign_path = args.campaign or args.runs_dir.parent / "campaign.json"
    campaign = read_json(campaign_path) if campaign_path.exists() else None
    summary = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(),
               "runsDirectory": str(args.runs_dir), "campaign": campaign, "criteria": criteria,
               "criteriaScope": "Observed stable finite window requires all validationChecks and stabilityChecks true. "
                   "p99 is reported and optional target attainment is separate; latency is not a default overload criterion. "
                   "A nonstable valid trial may expose the bounded client/FIFO path rather than the matching engine. "
                   "No finite trial establishes indefinite capacity; all rounds, failures and invalid generator timing are retained.",
               "trials": trials, "groups": summarize_groups(trials),
               "counts": {"trials": len(trials), "valid": sum(trial["measurementValid"] for trial in trials),
                          "observedStableWindows": sum(trial["observedStableWindow"] for trial in trials)},
               "plots": plot_trials(trials, args.output_dir) if args.plot else {"status": "not-requested"}}
    temporary = args.output_dir / "summary.json.tmp"
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_dir / "summary.json")
    temporary_csv = args.output_dir / "capacity.csv.tmp"
    with temporary_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_row(trial) for trial in trials)
    temporary_csv.replace(args.output_dir / "capacity.csv")
    print(json.dumps({"summary": str(args.output_dir / "summary.json"), **summary["counts"], "plots": summary["plots"]}))


if __name__ == "__main__":
    main()
