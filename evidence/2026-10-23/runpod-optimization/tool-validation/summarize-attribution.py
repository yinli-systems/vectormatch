#!/usr/bin/env python3
"""Summarize owned thread/socket observers without changing benchmark evidence.

Usage: summarize-attribution.py ROOT_DIR OUTPUT_JSON [--max-gap-multiplier 1.5]
Only adjacent observations entirely inside the approximate UTC arrival window
are differenced. All rates use local monotonic clocks. Cohorts stay separate.
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
import statistics


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def counter(value):
    value = number(value)
    return value if value is not None and value >= 0 else None


def get(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def sha(content):
    return hashlib.sha256(content).hexdigest()


def read_json(path, inputs):
    raw = path.read_bytes()
    inputs.append({"path": str(path), "sha256": sha(raw), "bytes": len(raw)})
    return json.loads(raw)


def read_jsonl(path, inputs):
    if not path.exists():
        return {"status": "missing", "rows": [], "parseErrors": []}
    raw = path.read_bytes()
    inputs.append({"path": str(path), "sha256": sha(raw), "bytes": len(raw)})
    rows, errors = [], []
    for line_number, line in enumerate(raw.splitlines(), 1):
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("Expected object")
            rows.append(row)
        except (ValueError, TypeError):
            errors.append({"line": line_number, "error": "invalid-json-object"})
    return {"status": "partial" if errors else "read", "rows": rows, "parseErrors": errors}


def utc(value):
    if not isinstance(value, str):
        return None
    try:
        # Python 3.9 accepts microseconds, whereas Instant emits nanoseconds.
        compatible = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
        parsed = datetime.fromisoformat(compatible)
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def gauge(values):
    values = [value for value in values if number(value) is not None]
    ordered = sorted(values)
    return {"observations": len(values), "minimum": min(values) if values else None,
            "median": statistics.median(values) if values else None,
            "p95": ordered[max(0, math.ceil(.95 * len(ordered)) - 1)] if ordered else None,
            "maximum": max(values) if values else None}


def selection(document, start, end, gap_multiplier):
    metadata = next((row for row in document["rows"] if row.get("type") == "metadata"), {})
    interval = counter(metadata.get("intervalSeconds"))
    if interval is None or interval <= 0:
        interval = None
    samples = [row for row in document["rows"] if row.get("type") == "sample"]
    def observed_window(row):
        wall = utc(row.get("wallTimeUtc"))
        duration = counter(row.get("collectionElapsedNs"))
        if duration is None:
            first, last = counter(row.get("monotonicNs")), counter(row.get("collectionFinishedMonotonicNs"))
            duration = last - first if first is not None and last is not None and last >= first else None
        return (wall, wall + duration / 1e9) if wall is not None and duration is not None else None
    def inside(row):
        observed = observed_window(row)
        return observed is not None and start <= observed[0] and observed[1] <= end
    selected = [row for row in samples if inside(row)]
    pairs, rejected = [], Counter()
    for first, last in zip(samples, samples[1:]):
        if not (inside(first) and inside(last)):
            continue
        elapsed = ((counter(last.get("monotonicNs")) or 0) - (counter(first.get("monotonicNs")) or 0))
        if counter(first.get("monotonicNs")) is None or counter(last.get("monotonicNs")) is None or elapsed <= 0:
            rejected["missing-or-nonincreasing-monotonic"] += 1
        elif type(first.get("sequence")) is not int or last.get("sequence") != first["sequence"] + 1:
            rejected["nonadjacent-sample-sequence"] += 1
        elif interval is None:
            rejected["missing-configured-interval"] += 1
        elif elapsed > interval * gap_multiplier * 1e9:
            rejected["overlong-monotonic-gap"] += 1
        else:
            pairs.append((first, last, elapsed))
    span_ns = selected[-1]["monotonicNs"] - selected[0]["monotonicNs"] if len(selected) >= 2 and all(counter(row.get("monotonicNs")) is not None for row in (selected[0], selected[-1])) else None
    complete = next((row for row in reversed(document["rows"]) if row.get("type") == "complete"), None)
    detail = {"status": document["status"], "parseErrors": document["parseErrors"],
              "completeRecordPresent": complete is not None, "completeReason": get(complete, "reason"),
              "configuredIntervalSeconds": interval, "maximumAcceptedGapMultiplier": gap_multiplier,
              "allSamples": len(samples), "selectedSamples": len(selected), "adjacentAcceptedPairs": len(pairs),
              "selectionRequiresWholeCollectionInsideArrivalWindow": True,
              "sampleStartsInsideButCollectionCrossesEnd": sum(utc(row.get("wallTimeUtc")) is not None and start <= utc(row["wallTimeUtc"]) <= end
                                                               and observed_window(row) is not None and observed_window(row)[1] > end for row in samples),
              "missingCollectionTimingSamples": sum(observed_window(row) is None for row in samples),
              "rejectedInteriorPairs": dict(rejected),
              "firstSelectedWallTimeUtc": selected[0].get("wallTimeUtc") if selected else None,
              "lastSelectedWallTimeUtc": selected[-1].get("wallTimeUtc") if selected else None,
              "firstSelectedMonotonicNs": selected[0].get("monotonicNs") if selected else None,
              "lastSelectedMonotonicNs": selected[-1].get("monotonicNs") if selected else None,
              "selectedMonotonicSpanSeconds": span_ns / 1e9 if span_ns is not None else None,
              "adjacentCoveredSeconds": sum(pair[2] for pair in pairs) / 1e9,
              "arrivalWindowCoverageFraction": sum(pair[2] for pair in pairs) / 1e9 / (end - start)}
    return selected, pairs, metadata, detail


def process_identity(row):
    if get(row, "status") != "verified":
        return None
    values = tuple(get(row, key) for key in ("pid", "startTicks", "commandSha256"))
    return values if all(value is not None for value in values) else None


def thread_map(process):
    rows = get(process, "threads", "sampled")
    if not isinstance(rows, list):
        return None
    result = {}
    for row in rows:
        if type(get(row, "tid")) is int and counter(get(row, "startTicks")) is not None:
            key = row["tid"], row["startTicks"]
            if key in result:
                return None
            result[key] = row
    return result


def thread_summary(selected, pairs, role, ticks, max_gap_ns):
    states, detail_states, wchans, unavailable_details = Counter(), Counter(), Counter(), Counter()
    process_status, coverage_errors = Counter(), Counter()
    gauges = {"sampledThreadCount": [], "fdCountBefore": [], "fdCountAfter": [],
              "threadReadFailures": [], "fdReadFailuresBefore": [], "fdReadFailuresAfter": []}
    truncations = Counter()
    rows_seen, aggregates = {}, {}
    for sample in selected:
        process = get(sample, "processes", role)
        process_status[str(get(process, "status") or "not-configured")] += 1
        if process_identity(process) is None:
            continue
        for label, path in (("sampledThreadCount", ("threads", "sampledThreads")), ("fdCountBefore", ("fdScan", "scannedFds")),
                            ("fdCountAfter", ("fdScanAfter", "scannedFds")), ("threadReadFailures", ("threads", "readFailures")),
                            ("fdReadFailuresBefore", ("fdScan", "readFailures")), ("fdReadFailuresAfter", ("fdScanAfter", "readFailures"))):
            gauges[label].append(get(process, *path))
        for name in ("threads", "fdScan", "fdScanAfter"):
            if get(process, name, "status") != "ok":
                coverage_errors[f"{name}:{get(process, name, 'status')}"] += 1
            if get(process, name, "truncated") is True:
                truncations[name] += 1
        mapping = thread_map(process)
        if mapping is None:
            coverage_errors["unavailable-or-duplicate-thread-map"] += 1
            continue
        for key, thread in mapping.items():
            full_key = (*process_identity(process), *key)
            rows_seen[full_key] = thread
            states[str(thread.get("state"))] += 1
            detail_states[str(thread.get("detailStatus"))] += 1
            if thread.get("detailStatus") == "identity-verified":
                wchan = get(thread, "details", "wchan", "value")
                if isinstance(wchan, str) and wchan:
                    wchans[wchan] += 1
                else:
                    unavailable_details[f"wchan:{get(thread, 'details', 'wchan', 'error') or 'empty'}"] += 1
    covered_ns, cpu_ticks, matched_pairs, new_threads, vanished_threads = 0, 0, 0, 0, 0
    for first, last, elapsed in pairs:
        before, after = get(first, "processes", role), get(last, "processes", role)
        identity = process_identity(before)
        if identity is None or identity != process_identity(after):
            coverage_errors["process-unavailable-or-identity-changed-pairs"] += 1
            continue
        a, b = thread_map(before), thread_map(after)
        if a is None or b is None:
            coverage_errors["thread-map-unavailable-pairs"] += 1
            continue
        covered_ns += elapsed
        new_threads += len(b.keys() - a.keys())
        vanished_threads += len(a.keys() - b.keys())
        for key in a.keys() & b.keys():
            initial, final = a[key], b[key]
            values = [counter(get(row, name)) for row in (initial, final) for name in ("userCpuTicks", "systemCpuTicks", "observedMonotonicNs")]
            if None in values:
                coverage_errors["thread-counter-unavailable-pairs"] += 1
                continue
            user_a, system_a, mono_a, user_b, system_b, mono_b = values
            thread_elapsed = mono_b - mono_a
            delta = user_b + system_b - user_a - system_a
            if delta < 0 or thread_elapsed <= 0 or thread_elapsed > max_gap_ns:
                coverage_errors["thread-counter-reset-or-monotonic-gap-pairs"] += 1
                continue
            full_key = (*identity, *key)
            entry = aggregates.setdefault(full_key, {"cpuTicks": 0, "coveredNs": 0, "pairs": 0,
                                                     "schedstatPairs": 0, "schedstatCoveredNs": 0,
                                                     "runtimeNs": 0, "runqueueWaitNs": 0, "timeslices": 0,
                                                     "wchanObservations": Counter()})
            entry["cpuTicks"] += delta
            entry["coveredNs"] += thread_elapsed
            entry["pairs"] += 1
            cpu_ticks += delta
            matched_pairs += 1
            sched_a, sched_b = get(initial, "details", "schedstat", "value"), get(final, "details", "schedstat", "value")
            if initial.get("detailStatus") == final.get("detailStatus") == "identity-verified" and isinstance(sched_a, dict) and isinstance(sched_b, dict):
                deltas = {name: counter(sched_b.get(name)) - counter(sched_a.get(name))
                          for name in ("runtimeNs", "runqueueWaitNs", "timeslices")
                          if counter(sched_a.get(name)) is not None and counter(sched_b.get(name)) is not None}
                if len(deltas) == 3 and all(value >= 0 for value in deltas.values()):
                    entry["schedstatPairs"] += 1
                    entry["schedstatCoveredNs"] += thread_elapsed
                    for name, value in deltas.items():
                        entry[name] += value
    # Wait-channel observations are sparse top-16 snapshots, not a distribution
    # over every owned thread or over every instant of the arrival window.
    for sample in selected:
        process = get(sample, "processes", role)
        mapping, identity = thread_map(process), process_identity(process)
        if mapping is None or identity is None:
            continue
        for key, thread in mapping.items():
            entry = aggregates.get((*identity, *key))
            wchan = get(thread, "details", "wchan", "value")
            if entry is not None and thread.get("detailStatus") == "identity-verified" and isinstance(wchan, str) and wchan:
                entry["wchanObservations"][wchan] += 1
    top, names = [], defaultdict(lambda: {"cpuTicks": 0, "threadIdentities": 0})
    for key, entry in aggregates.items():
        row = rows_seen[key]
        cpu_seconds = entry["cpuTicks"] / ticks if ticks else None
        sched = {"adjacentDetailPairs": entry["schedstatPairs"], "coveredSeconds": entry["schedstatCoveredNs"] / 1e9,
                 "runtimeSeconds": entry["runtimeNs"] / 1e9 if entry["schedstatPairs"] else None,
                 "runqueueWaitSeconds": entry["runqueueWaitNs"] / 1e9 if entry["schedstatPairs"] else None,
                 "timeslices": entry["timeslices"] if entry["schedstatPairs"] else None}
        top.append({"pid": key[0], "processStartTicks": key[1], "tid": key[3], "threadStartTicks": key[4],
                    "comm": row["comm"], "cpuSeconds": cpu_seconds,
                    "cpuCoresOverObservedIntervals": cpu_seconds / (entry["coveredNs"] / 1e9) if cpu_seconds is not None and entry["coveredNs"] else None,
                    "coveredSeconds": entry["coveredNs"] / 1e9, "adjacentCounterPairs": entry["pairs"],
                    "wchanObservations": dict(entry["wchanObservations"]), "schedstat": sched})
        names[row["comm"]]["cpuTicks"] += entry["cpuTicks"]
        names[row["comm"]]["threadIdentities"] += 1
    top.sort(key=lambda row: -(row["cpuSeconds"] or 0))
    by_name = [{"comm": name, "threadIdentities": data["threadIdentities"],
                "cpuSeconds": data["cpuTicks"] / ticks if ticks else None,
                "combinedCoresOverProcessCoveredIntervals": data["cpuTicks"] / ticks / (covered_ns / 1e9) if ticks and covered_ns else None}
               for name, data in names.items()]
    by_name.sort(key=lambda row: -(row["cpuSeconds"] or 0))
    return {"processStatusCounts": dict(process_status), "coverageIssues": dict(coverage_errors),
            "truncatedSampleCounts": dict(truncations),
            **{name: gauge(values) for name, values in gauges.items()},
            "coveredProcessSeconds": covered_ns / 1e9,
            "matchedThreadCounterPairs": matched_pairs, "observedThreadIdentities": len(rows_seen),
            "newThreadObservationsBetweenPairs": new_threads, "disappearedThreadObservationsBetweenPairs": vanished_threads,
            "matchedThreadCpuSeconds": cpu_ticks / ticks if ticks and matched_pairs else None,
            "matchedThreadCoresOverProcessCoveredIntervals": cpu_ticks / ticks / (covered_ns / 1e9) if ticks and matched_pairs and covered_ns else None,
            "stateObservations": dict(states), "detailStatusCounts": dict(detail_states),
            "selectedThreadWchanObservations": dict(wchans), "detailUnavailableCounts": dict(unavailable_details),
            "topThreadsByObservedCpuSeconds": top[:32], "threadsOmittedFromTopList": max(0, len(top) - 32),
            "byKernelThreadName": by_name,
            "scope": "CPU joins require identical process identity and TID/startTicks; new/disappeared threads contribute no guessed CPU. "
                     "Thread-name groups can combine many instances and kernel-truncated names. schedstat/wchan only cover the collector's selected top16 threads; "
                     "wchan=0 can mean running or unavailable, and zero schedstat can mean disabled instrumentation. This does not identify a unique causal bottleneck."}


def sockets(process, family):
    table = get(process, "udp", family)
    if not isinstance(get(table, "sockets"), list):
        return None
    result = {}
    for row in table["sockets"]:
        if row.get("ownershipConfirmedAfterRead") is not True:
            continue
        key = (family, row.get("inode"), row.get("localAddress"), row.get("localPort"))
        if any(value is None for value in key) or key in result:
            return None
        result[key] = row
    return result


def socket_summary(selected, pairs, role):
    observed, counts, table_states, issues = {}, [], Counter(), Counter()
    unparsed_rows, ownership_losses = [], []
    for sample in selected:
        process = get(sample, "processes", role)
        identity = process_identity(process)
        if identity is None:
            continue
        count_now, available = 0, True
        for family in ("ipv4", "ipv6"):
            table_states[f"{family}:{get(process, 'udp', family, 'status')}"] += 1
            unparsed_rows.append(get(process, "udp", family, "unparsedRows"))
            ownership_losses.append(get(process, "udp", family, "ownershipLostDuringRead"))
            mapping = sockets(process, family)
            if mapping is None:
                available = False
                continue
            count_now += len(mapping)
            for key, row in mapping.items():
                entry = observed.setdefault((*identity, *key), {"receive": [], "transmit": [], "dropGauges": [],
                                                               "matchedPairs": 0, "coveredNs": 0, "dropDelta": 0,
                                                               "firstWallTimeUtc": sample.get("wallTimeUtc")})
                entry["receive"].append(row.get("receiveQueueKernelBytes"))
                entry["transmit"].append(row.get("transmitQueueKernelBytes"))
                entry["dropGauges"].append(row.get("drops"))
                entry["lastWallTimeUtc"] = sample.get("wallTimeUtc")
        if available:
            counts.append(count_now)
    matched_pairs, drops, newly_observed, disappeared = 0, 0, 0, 0
    for first, last, elapsed in pairs:
        before, after = get(first, "processes", role), get(last, "processes", role)
        identity = process_identity(before)
        if identity is None or identity != process_identity(after):
            issues["process-unavailable-or-identity-changed-pairs"] += 1
            continue
        for family in ("ipv4", "ipv6"):
            a, b = sockets(before, family), sockets(after, family)
            if a is None or b is None:
                issues[f"{family}:unavailable-table-pairs"] += 1
                continue
            newly_observed += len(b.keys() - a.keys())
            disappeared += len(a.keys() - b.keys())
            for key in a.keys() & b.keys():
                if not set(a[key].get("fdNumbers") or []) & set(b[key].get("fdNumbers") or []):
                    issues["socket-fd-set-disjoint-pairs"] += 1
                    continue
                initial, final = counter(a[key].get("drops")), counter(b[key].get("drops"))
                if initial is None or final is None:
                    issues["missing-drop-counter-pairs"] += 1
                    continue
                if final < initial:
                    issues["drop-counter-reset-or-wrap-pairs"] += 1
                    continue
                entry = observed[(*identity, *key)]
                entry["matchedPairs"] += 1
                entry["coveredNs"] += elapsed
                entry["dropDelta"] += final - initial
                drops += final - initial
                matched_pairs += 1
    details = []
    for key, entry in observed.items():
        details.append({"pid": key[0], "processStartTicks": key[1], "family": key[3], "inode": key[4],
                        "localAddress": key[5], "localPort": key[6],
                        "firstWallTimeUtc": entry["firstWallTimeUtc"], "lastWallTimeUtc": entry["lastWallTimeUtc"],
                        "receiveQueueKernelBytes": gauge(entry["receive"]), "transmitQueueKernelBytes": gauge(entry["transmit"]),
                        "dropCounterObserved": gauge(entry["dropGauges"]),
                        "matchedAdjacentDropCounterPairs": entry["matchedPairs"],
                        "coveredSeconds": entry["coveredNs"] / 1e9,
                        "dropDeltaOverMatchedAdjacentPairs": entry["dropDelta"] if entry["matchedPairs"] else None})
    details.sort(key=lambda row: (-(row["dropDeltaOverMatchedAdjacentPairs"] or 0), -(row["receiveQueueKernelBytes"]["maximum"] or 0), row["inode"]))
    return {"ownedUdpSocketCount": gauge(counts), "distinctObservedSocketIdentities": len(observed),
            "unparsedRowsPerTableSample": gauge(unparsed_rows), "ownershipLossesPerTableSample": gauge(ownership_losses),
            "tableStatusCounts": dict(table_states), "coverageIssues": dict(issues),
            "matchedAdjacentSocketCounterPairs": matched_pairs,
            "observedDropDeltaOverMatchedAdjacentPairs": drops if matched_pairs else None,
            "newSocketObservationsBetweenAdjacentPairs": newly_observed,
            "disappearedSocketObservationsBetweenAdjacentPairs": disappeared,
            "sockets": details,
            "scope": "Only verified owned PID sockets with fd/inode ownership rechecked by the collector. Adjacent joins require identical process/family/inode/localbind "
                     "and an overlapping fd set. Newly observed counters are not counted as arrival-window drops. Disappearance is observed absence, not a certified close; "
                     "gaps, races and fd caps can hide sockets. Queue gauges are kernel-accounting bytes, not packets or effective SO_RCVBUF capacity. "
                     "Drops are observed socket drop-counter increments, not business-command losses or proof of the unique loss mechanism; resets/wraps are excluded."}


def aggregate_process_cpu(document, start, end, role, multiplier):
    selected, pairs, metadata, coverage = selection(document, start, end, multiplier)
    ticks = counter(get(metadata, "hardware", "clockTicksPerSecond"))
    elapsed_total, delta_total, valid_pairs, errors = 0, 0, 0, Counter()
    for first, last, elapsed in pairs:
        a, b = get(first, "processes", role), get(last, "processes", role)
        if process_identity(a) is None or process_identity(a) != process_identity(b):
            errors["process-unavailable-or-identity-changed-pairs"] += 1
            continue
        values = [counter(get(row, "metrics", "stat", "value", name)) for row in (a, b) for name in ("userCpuTicks", "systemCpuTicks")]
        if None in values or values[2] + values[3] < values[0] + values[1]:
            errors["counter-unavailable-or-reset-pairs"] += 1
            continue
        delta_total += values[2] + values[3] - values[0] - values[1]
        elapsed_total += elapsed
        valid_pairs += 1
    verified = [get(row, "processes", role) for row in selected if process_identity(get(row, "processes", role)) is not None]
    memory = {label: gauge(get(row, "metrics", "status", "value", field) for row in verified)
              for label, field in (("rssBytes", "VmRSSBytes"), ("anonymousRssBytes", "RssAnonBytes"), ("fileBackedRssBytes", "RssFileBytes"))}
    return {"cpuSeconds": delta_total / ticks if ticks and valid_pairs else None,
            "coveredSeconds": elapsed_total / 1e9,
            "cpuCores": delta_total / ticks / (elapsed_total / 1e9) if ticks and valid_pairs and elapsed_total else None,
            **memory,
            "validAdjacentPairs": valid_pairs, "coverageIssues": dict(errors), "selection": coverage}


def observer_summary(path, telemetry_path, start, end, inputs, multiplier):
    document = read_jsonl(path, inputs)
    selected, pairs, metadata, coverage = selection(document, start, end, multiplier)
    ticks = counter(get(metadata, "hardware", "clockTicksPerSecond"))
    interval = coverage["configuredIntervalSeconds"]
    roles = sorted({role for sample in selected for role in (sample.get("processes") or {})})
    max_gap_ns = interval * multiplier * 1e9 if interval else 0
    cpu_costs = [counter(row.get("collectorCpuElapsedNs")) for row in selected]
    wall_costs = [counter(row.get("collectionElapsedNs")) for row in selected]
    known_costs = [value for value in cpu_costs if value is not None]
    estimated_cores = statistics.mean(known_costs) / (interval * 1e9) if known_costs and interval else None
    aggregate = read_jsonl(telemetry_path, inputs)
    aggregate_roles = {role: aggregate_process_cpu(aggregate, start, end, role, multiplier) for role in roles}
    load_cpu = get(aggregate_roles, "load", "cpuCores")
    return {"path": str(path), "selection": coverage,
            "hardware": metadata.get("hardware"),
            "observer": {"collectionWallMillis": gauge([value / 1e6 if value is not None else None for value in wall_costs]),
                         "collectionCpuMillis": gauge([value / 1e6 if value is not None else None for value in cpu_costs]),
                         "missingCollectionCpuCostSamples": sum(value is None for value in cpu_costs),
                         "estimatedCollectorCoresAtConfiguredCadence": estimated_cores,
                         "estimatedCollectionCpuAsFractionOfConcurrentLoadCpu": estimated_cores / load_cpu if estimated_cores is not None and load_cpu and load_cpu > 0 else None,
                         "scope": "Mean per-sample collector process CPU cost divided by configured cadence, not an observer-off comparison. "
                                  "Per-collection cost excludes JSON serialization/flush and idle; the complete observer's total CPU includes other phases. "
                                  "Ratio to load CPU uses independently sampled local aggregate telemetry intervals and is approximate."},
            "aggregateProcessCpuFromCapacityTelemetry": aggregate_roles,
            "processes": {role: {"threads": thread_summary(selected, pairs, role, ticks, max_gap_ns),
                                 "udpSockets": socket_summary(selected, pairs, role)} for role in roles}}


def summarize(root, multiplier):
    inputs, cohorts, pending = [], {}, []
    for cohort in ("isolated", "shared"):
        trials = []
        for directory in sorted((root / cohort / "runs").glob("*")):
            if not directory.is_dir():
                continue
            result_path = directory / "load-result.json"
            if not result_path.exists():
                result_path = directory / "result.json"
            if not result_path.exists():
                pending.append({"cohort": cohort, "id": directory.name, "reason": "no-load-result"})
                continue
            validation_path = directory / "result.json"
            observer_paths = sorted(directory.glob("node*-attribution.jsonl"))
            observers_complete = len(observer_paths) == 3
            for path in observer_paths:
                try:
                    last = json.loads(path.read_bytes().splitlines()[-1])
                    observers_complete = observers_complete and last.get("type") == "complete"
                except (ValueError, IndexError):
                    observers_complete = False
            if not validation_path.exists() or not observers_complete:
                pending.append({"cohort": cohort, "id": directory.name, "reason": "final-validation-or-three-complete-observers-not-exported"})
                continue
            result = read_json(result_path, inputs)
            validation = read_json(validation_path, inputs) if validation_path != result_path else result
            origin, window = utc(result.get("scheduledOriginUtcApproximate")), counter(result.get("arrivalWindowSeconds"))
            if origin is None or window is None or window <= 0:
                pending.append({"cohort": cohort, "id": directory.name, "reason": "missing-positive-arrival-window-or-origin"})
                continue
            trial_path = directory / "trial.json"
            manifest = read_json(trial_path, inputs) if trial_path.exists() else None
            leader_path = directory / "fixed-leader-check.json"
            leader = read_json(leader_path, inputs) if leader_path.exists() else None
            trials.append({"id": directory.name, "manifest": manifest,
                           "arrivalWindow": {"scheduledOriginUtcApproximate": result["scheduledOriginUtcApproximate"],
                                             "arrivalWindowSeconds": window,
                                             "endUtcApproximate": datetime.fromtimestamp(origin + window, timezone.utc).isoformat(),
                                             "scope": "Load-generator UTC origin is approximate; wall clocks are not verified synchronized. "
                                                      "Only interior adjacent samples are differenced; monotonic time determines every rate. "
                                                      "A lack of samples is unavailable, never a zero-CPU/zero-drop claim."},
                           "fixedLeaderCheckPassed": get(leader, "passed"),
                           "validationPassed": validation.get("passed"),
                           "observerFileCount": len(observer_paths),
                           "observers": [observer_summary(path, directory / path.name.replace("-attribution.jsonl", "-telemetry.jsonl"),
                                                          origin, origin + window, inputs, multiplier) for path in observer_paths]})
        cohorts[cohort] = {"completedLoadResultTrials": len(trials), "trials": trials}
    return {"schemaVersion": 1, "test": "capacity-owned-thread-socket-attribution-summary",
            "generatedAt": datetime.now(timezone.utc).isoformat(), "rootDirectory": str(root),
            "scriptSha256": sha(Path(__file__).read_bytes()), "maximumAcceptedGapMultiplier": multiplier,
            "cohorts": cohorts, "pendingOrUnavailableTrials": pending, "inputs": inputs,
            "scope": "Cohorts and trials remain separate. Results are finite-window direct observations and associations, not unique causal proof. "
                     "Different local observer/process coverage intervals and ~1Hz non-atomic samples can miss bursts, short-lived threads and socket closures. "
                     "No baseline observation is silently merged with a changed client-driver cohort; no missing value is replaced with zero."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root_dir", type=Path, nargs="?")
    parser.add_argument("output_json", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true", help="Run offline identity/window/counter boundary checks")
    parser.add_argument("--max-gap-multiplier", type=float, default=1.5)
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.root_dir is None or args.output_json is None:
        parser.error("ROOT_DIR and OUTPUT_JSON are required unless --self-test is used")
    if not math.isfinite(args.max_gap_multiplier) or args.max_gap_multiplier < 1:
        parser.error("--max-gap-multiplier must be finite and >=1")
    result = summarize(args.root_dir, args.max_gap_multiplier)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_json)
    print(json.dumps({"output": str(args.output_json), "completedLoadResults": {key: value["completedLoadResultTrials"] for key, value in result["cohorts"].items()},
                      "pending": len(result["pendingOrUnavailableTrials"])}))


def self_test():
    """Small synthetic checks kept with the reproducible, standalone script."""
    assert utc("2026-10-23T21:37:59.974287529Z") is not None
    start = utc("2026-10-23T00:00:00Z")
    def sample(sequence, second, thread_start=500, ticks=0, drops=7, inode=123):
        mono = int(second * 1e9)
        thread = {"tid": 10, "startTicks": thread_start, "comm": "worker", "state": "R",
                  "userCpuTicks": ticks, "systemCpuTicks": 0, "observedMonotonicNs": mono,
                  "detailStatus": "not-selected"}
        socket = {"inode": inode, "localAddress": "10.0.0.1", "localPort": 23000,
                  "fdNumbers": [3], "ownershipConfirmedAfterRead": True, "drops": drops,
                  "receiveQueueKernelBytes": 64, "transmitQueueKernelBytes": 0}
        process = {"status": "verified", "pid": 41, "startTicks": 1, "commandSha256": "a" * 64,
                   "threads": {"status": "ok", "sampled": [thread], "sampledThreads": 1},
                   "fdScan": {"status": "ok"}, "fdScanAfter": {"status": "ok"},
                   "udp": {"ipv4": {"status": "ok", "sockets": [socket]}, "ipv6": {"status": "ok", "sockets": []}}}
        return {"type": "sample", "sequence": sequence,
                "wallTimeUtc": datetime.fromtimestamp(start + second, timezone.utc).isoformat(),
                "monotonicNs": mono, "collectionElapsedNs": 10_000_000, "processes": {"load": process}}
    a, b = sample(0, 1, ticks=0), sample(1, 2, ticks=100, drops=10)
    document = {"status": "read", "parseErrors": [], "rows": [{"type": "metadata", "intervalSeconds": 1}, a, b]}
    selected, pairs, metadata, coverage = selection(document, start, start + 3, 1.5)
    assert coverage["adjacentAcceptedPairs"] == 1
    cpu = thread_summary(selected, pairs, "load", 100, 1.5e9)
    assert cpu["matchedThreadCpuSeconds"] == 1 and cpu["matchedThreadCoresOverProcessCoveredIntervals"] == 1
    assert socket_summary(selected, pairs, "load")["observedDropDeltaOverMatchedAdjacentPairs"] == 3
    # A collection beginning inside but finishing outside must not pull teardown
    # reads into the measurement window.
    b["collectionElapsedNs"] = 2_000_000_000
    assert selection(document, start, start + 3, 1.5)[3]["selectedSamples"] == 1
    b["collectionElapsedNs"] = 10_000_000
    b["sequence"] = 2
    assert selection(document, start, start + 3, 1.5)[3]["adjacentAcceptedPairs"] == 0
    b = sample(1, 2, thread_start=501, ticks=1, drops=10, inode=999)
    cpu = thread_summary([a, b], [(a, b, 1_000_000_000)], "load", 100, 1.5e9)
    assert cpu["matchedThreadCpuSeconds"] is None and cpu["newThreadObservationsBetweenPairs"] == 1
    sockets_result = socket_summary([a, b], [(a, b, 1_000_000_000)], "load")
    assert sockets_result["observedDropDeltaOverMatchedAdjacentPairs"] is None
    assert sockets_result["newSocketObservationsBetweenAdjacentPairs"] == 1
    assert sockets_result["disappearedSocketObservationsBetweenAdjacentPairs"] == 1
    b = sample(1, 2, ticks=1, drops=1)
    result = socket_summary([a, b], [(a, b, 1_000_000_000)], "load")
    assert result["observedDropDeltaOverMatchedAdjacentPairs"] is None
    assert result["coverageIssues"]["drop-counter-reset-or-wrap-pairs"] == 1
    b["processes"]["load"]["commandSha256"] = "b" * 64
    assert thread_summary([a, b], [(a, b, 1_000_000_000)], "load", 100, 1.5e9)["matchedThreadCpuSeconds"] is None
    print(json.dumps({"status": "PASS", "checks": ["nanosecond-UTC-Python3.9", "matched-thread-CPU", "matched-socket-delta",
                      "whole-collection-window", "sequence-gap", "TID-reuse", "new-socket-not-inherited-drops",
                      "disappearance-is-observation", "counter-reset-not-zero", "process-identity-change"]}))


if __name__ == "__main__":
    main()
