#!/usr/bin/env python3
"""Offline, read-only summaries of explicit capacity-trial observer evidence.

Usage: summarize-capacity-telemetry.py RUNS_DIR OUTPUT_JSON
UTC selects an approximate arrival window; each node's monotonic clock supplies
its rate denominator. Cross-host UTC synchronization has not been established.
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


SCOPE = ("Approximate selection by recorded scheduledOriginUtcApproximate and each observer's UTC timestamps. "
         "No verified cross-host clock synchronization; this is not precise distributed alignment or one-way latency. "
         "Rates use monotonic deltas on the same host. cgroup/network are shared container observations. "
         "CnC counters are sequential, non-atomic reads; registration identity is preserved. "
         "Instantaneous position differences are signed observations, not exact queue/replication lag. "
         "Archive write-time includes write, configured force and descheduling elapsed time; it is not a pure fsync histogram.")


def get(value, *keys):
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def utc_seconds(value):
    # Java emits nanosecond UTC, whereas Python <=3.10 accepts microseconds only.
    text = re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00"))
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp has no timezone")
    return parsed.timestamp()


def read_json(path):
    result = json.loads(path.read_text())
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    json.dumps(result, allow_nan=False)
    return result


def read_jsonl(path):
    rows, errors = [], []
    try:
        text = path.read_text()
    except OSError as exc:
        return [], [{"error": type(exc).__name__}]
    for index, line in enumerate(text.splitlines()):
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("Expected JSON object")
            json.dumps(value, allow_nan=False)
            rows.append(value)
        except ValueError as exc:
            errors.append({"line": index + 1, "error": type(exc).__name__})
    return rows, errors


def delta(first, last):
    if not numeric(first) or not numeric(last):
        return {"first": first, "last": last, "delta": None, "unavailable": "missing-or-nonnumeric-counter"}
    if last < first:
        return {"first": first, "last": last, "delta": None, "unavailable": "counter-decreased-or-reset"}
    return {"first": first, "last": last, "delta": last - first}


def gauge(values):
    values = [value for value in values if numeric(value)]
    return {"first": values[0] if values else None, "last": values[-1] if values else None,
            "minObserved": min(values) if values else None, "maxObserved": max(values) if values else None,
            "observations": len(values)}


def coverage(samples, start, end, timestamp_key, monotonic_key):
    selected, invalid = [], []
    for index, row in enumerate(samples):
        try:
            wall = utc_seconds(row[timestamp_key])
            if start is not None and end is not None and start <= wall <= end:
                selected.append(row)
        except (KeyError, TypeError, ValueError):
            invalid.append(index)
    result = {"observerSamples": len(samples), "selectedSamples": len(selected),
              "selectionStartUtcApproximate": datetime.fromtimestamp(start, timezone.utc).isoformat() if start is not None else None,
              "selectionEndUtcApproximate": datetime.fromtimestamp(end, timezone.utc).isoformat() if end is not None else None,
              "invalidTimestampSampleIndices": invalid,
              "firstSelectedUtc": selected[0][timestamp_key] if selected else None,
              "lastSelectedUtc": selected[-1][timestamp_key] if selected else None,
              "firstSelectedMonotonic": selected[0].get(monotonic_key) if selected else None,
              "lastSelectedMonotonic": selected[-1].get(monotonic_key) if selected else None,
              "monotonicField": monotonic_key, "monotonicUnits": "nanoseconds"}
    duration = None
    if len(selected) >= 2:
        first, last = selected[0].get(monotonic_key), selected[-1].get(monotonic_key)
        if numeric(first) and numeric(last) and last > first:
            duration = (last - first) / 1e9
        wall_duration = utc_seconds(selected[-1][timestamp_key]) - utc_seconds(selected[0][timestamp_key])
        result["selectedWallSpanSeconds"] = wall_duration
        result["wallMinusMonotonicSpanSeconds"] = wall_duration - duration if duration is not None else None
    result["selectedMonotonicSpanSeconds"] = duration
    result["fractionOfArrivalWindowCoveredByDelta"] = duration / (end - start) if duration is not None and start is not None and end > start else None
    return selected, result


def cgroup_metrics(row):
    group = row.get("cgroup", {})
    if group.get("status") == "mapped-v2-leaf":
        metrics = group.get("metrics", {})
        cpu = get(metrics, "cpu.stat", "value") or {}
        return {"version": 2, "quotaCores": get(metrics, "cpu.max", "value", "quotaCpuUpperBound"),
                "cpuUsageNanos": cpu["usage_usec"] * 1000 if numeric(cpu.get("usage_usec")) else None,
                "cpuPeriods": cpu.get("nr_periods"), "throttledPeriods": cpu.get("nr_throttled"),
                "throttledNanos": cpu["throttled_usec"] * 1000 if numeric(cpu.get("throttled_usec")) else None,
                "memoryBytes": get(metrics, "memory.current", "value"),
                "memoryEvents": get(metrics, "memory.events", "value") or {},
                "directory": group.get("directory"), "rawCpu": cpu, "rawQuota": get(metrics, "cpu.max", "value")}
    if group.get("status") == "mapped-v1-leaves":
        cpu_metrics, memory_metrics, cpu_directory = {}, {}, None
        for hierarchy in group.get("hierarchies", []):
            if "cpu" in hierarchy.get("controllers", []) or "cpuacct" in hierarchy.get("controllers", []):
                cpu_metrics.update(hierarchy.get("metrics", {}))
                cpu_directory = hierarchy.get("directory")
            if "memory" in hierarchy.get("controllers", []):
                memory_metrics.update(hierarchy.get("metrics", {}))
        cpu = get(cpu_metrics, "cpu.stat", "value") or {}
        quota, period = get(cpu_metrics, "cpu.cfs_quota_us", "value"), get(cpu_metrics, "cpu.cfs_period_us", "value")
        memory_events = get(memory_metrics, "memory.oom_control", "value") or {}
        failure_count = get(memory_metrics, "memory.failcnt", "value")
        if failure_count is not None:
            memory_events = {**memory_events, "allocationFailures": failure_count}
        return {"version": 1, "quotaCores": quota / period if numeric(quota) and quota > 0 and numeric(period) and period > 0 else None,
                "cpuUsageNanos": get(cpu_metrics, "cpuacct.usage", "value"), "cpuPeriods": cpu.get("nr_periods"),
                "throttledPeriods": cpu.get("nr_throttled"), "throttledNanos": cpu.get("throttled_time"),
                "memoryBytes": get(memory_metrics, "memory.usage_in_bytes", "value"), "memoryEvents": memory_events,
                "directory": cpu_directory, "rawCpu": cpu, "rawQuota": {"quotaMicros": quota, "periodMicros": period}}
    return {"unavailable": group.get("status", "cgroup-record-missing")}


def process_summary(samples, role, ticks_per_second, quota):
    status_counts = Counter(get(row, "processes", role, "status") or "not-configured" for row in samples)
    valid = [row for row in samples if get(row, "processes", role, "status") == "verified"]
    result = {"identityStatusCounts": dict(status_counts), "verifiedSamples": len(valid),
              "clockTicksPerSecond": ticks_per_second, "visibleQuotaCores": quota,
              "averageLogicalCores": None, "percentOfVisibleQuota": None}
    if len(valid) < 2:
        return {**result, "unavailable": "fewer-than-two-verified-process-samples"}
    first, last = valid[0], valid[-1]
    identities = {(get(row, "processes", role, "pid"), get(row, "processes", role, "startTicks"),
                   get(row, "processes", role, "commandSha256")) for row in valid}
    result["identitiesObserved"] = [{"pid": value[0], "startTicks": value[1], "commandSha256": value[2]} for value in sorted(identities)]
    if len(identities) != 1:
        return {**result, "unavailable": "process-identity-changed-within-selection"}
    duration = (last["monotonicNs"] - first["monotonicNs"]) / 1e9
    result["firstVerifiedUtc"], result["lastVerifiedUtc"], result["spanSeconds"] = first["wallTimeUtc"], last["wallTimeUtc"], duration
    if duration <= 0:
        return {**result, "unavailable": "nonpositive-monotonic-span"}
    counter = lambda row, name: get(row, "processes", role, "metrics", "stat", "value", name)
    result["cpuTickCounters"] = {name: delta(counter(first, name), counter(last, name)) for name in ("userCpuTicks", "systemCpuTicks")}
    ticks = [result["cpuTickCounters"][name]["delta"] for name in ("userCpuTicks", "systemCpuTicks")]
    if all(value is not None for value in ticks) and numeric(ticks_per_second) and ticks_per_second > 0:
        result["cpuSeconds"] = sum(ticks) / ticks_per_second
        result["averageLogicalCores"] = result["cpuSeconds"] / duration
        result["percentOfVisibleQuota"] = result["averageLogicalCores"] / quota * 100 if numeric(quota) and quota > 0 else None
    io_first, io_last = get(first, "processes", role, "metrics", "io", "value") or {}, get(last, "processes", role, "metrics", "io", "value") or {}
    result["ioCounters"] = {name: delta(io_first.get(name), io_last.get(name)) for name in
                            ("read_bytes", "write_bytes", "cancelled_write_bytes", "rchar", "wchar", "syscr", "syscw")}
    result["rssBytes"] = gauge(get(row, "processes", role, "metrics", "status", "value", "VmRSSBytes") for row in valid)
    result["threadCount"] = gauge(get(row, "processes", role, "metrics", "stat", "value", "threadCount") for row in valid)
    result["pageFaultCounters"] = {name: delta(counter(first, name), counter(last, name)) for name in ("majorFaults", "minorFaults")}
    result["ioScope"] = "Process /proc IO accounting, not device utilization, sync latency or total physical disk traffic."
    return result


def telemetry_summary(path, start, end, node):
    rows, errors = read_jsonl(path)
    samples = [row for row in rows if row.get("type") == "sample"]
    selected, window = coverage(samples, start, end, "wallTimeUtc", "monotonicNs")
    metadata = next((row for row in rows if row.get("type") == "metadata"), {})
    result = {"file": str(path), "readErrors": errors, "coverage": window,
              "completion": next((row for row in reversed(rows) if row.get("type") == "complete"), None)}
    if len(selected) < 2 or window["selectedMonotonicSpanSeconds"] is None:
        return {**result, "unavailable": "insufficient-selected-samples"}
    first, last, duration = selected[0], selected[-1], window["selectedMonotonicSpanSeconds"]
    cg_first, cg_last = cgroup_metrics(first), cgroup_metrics(last)
    quota_stable = cg_first.get("quotaCores") == cg_last.get("quotaCores") and cg_first.get("version") == cg_last.get("version")
    quota = cg_first.get("quotaCores") if quota_stable else None
    usage = delta(cg_first.get("cpuUsageNanos"), cg_last.get("cpuUsageNanos"))
    cgroup = {"version": cg_first.get("version"), "directory": cg_first.get("directory"), "quotaStable": quota_stable,
              "firstRawQuota": cg_first.get("rawQuota"), "lastRawQuota": cg_last.get("rawQuota"), "visibleQuotaCores": quota,
              "cpuUsageNanos": usage, "averageLogicalCores": usage["delta"] / 1e9 / duration if usage["delta"] is not None else None,
              "cpuPeriods": delta(cg_first.get("cpuPeriods"), cg_last.get("cpuPeriods")),
              "throttledPeriods": delta(cg_first.get("throttledPeriods"), cg_last.get("throttledPeriods")),
              "throttledNanos": delta(cg_first.get("throttledNanos"), cg_last.get("throttledNanos")),
              "memoryBytes": gauge(cgroup_metrics(row).get("memoryBytes") for row in selected),
              "memoryEvents": {key: delta(cg_first.get("memoryEvents", {}).get(key), cg_last.get("memoryEvents", {}).get(key))
                               for key in sorted(set(cg_first.get("memoryEvents", {})) | set(cg_last.get("memoryEvents", {})))},
              "scope": "Sampler's shared current leaf; quota is a visible upper bound, not dedicated CPU. Hidden ancestors are not measured. "
                       "v1 under_oom/oom_kill_disable are state gauges; allocationFailures are not OOM kills."}
    for key in ("under_oom", "oom_kill_disable"):
        if key in cgroup["memoryEvents"]:
            cgroup["memoryEvents"][key] = {"kind": "state-gauge", "first": cg_first.get("memoryEvents", {}).get(key),
                                           "last": cg_last.get("memoryEvents", {}).get(key)}
    cgroup["percentOfVisibleQuota"] = cgroup["averageLogicalCores"] / quota * 100 if cgroup["averageLogicalCores"] is not None and numeric(quota) and quota > 0 else None
    ticks = get(metadata, "hardware", "clockTicksPerSecond")
    result.update({"hardware": metadata.get("hardware"), "cgroup": cgroup,
                   "processes": {role: process_summary(selected, role, ticks, quota) for role in (f"node-{node}", "load")}})
    udp_first, udp_last = get(first, "network", "udp", "value") or {}, get(last, "network", "udp", "value") or {}
    result["udpAvailableAtBothBoundaries"] = bool(udp_first and udp_last)
    result["udpReadStatusAtBoundaries"] = {"first": get(first, "network", "udp"), "last": get(last, "network", "udp")}
    result["udpCounters"] = {key: delta(udp_first.get(key), udp_last.get(key)) for key in sorted(set(udp_first) | set(udp_last))}
    result["interface"] = get(first, "network", "interface")
    result["interfaceUnchanged"] = result["interface"] == get(last, "network", "interface")
    result["interfaceCounters"] = {direction: {name: delta(get(first, "network", "device", "value", direction, name),
                                                                   get(last, "network", "device", "value", direction, name))
                                                    for name in ("bytes", "packets", "drop", "errs", "fifo")}
                                   for direction in ("receive", "transmit")}
    result["networkScope"] = "Pod network namespace/interface counters, not per-process packet loss. NoPorts counts datagrams to unbound ports; do not equate it with benchmark command loss."
    return result


def counter_key(counter):
    return tuple(counter.get(key) for key in ("counterId", "registrationId", "typeId", "label"))


def counter_identity(key):
    return dict(zip(("counterId", "registrationId", "typeId", "label"), key))


def position_category(counter):
    kind, label = counter.get("typeId"), counter.get("label", "")
    if kind == 203:
        return "commitPosition"
    if " 100 " not in label or "alias=log" not in label:
        return None
    if kind == 12:
        return "appendPublicationPosition"
    if kind == 2:
        return "senderPosition"
    if kind == 3:
        return "receiveHighWaterPosition"
    if kind == 100:
        return "archiveRecordingPosition"
    if kind == 4 and "alias=log-sc-" in label:
        return "serviceSubscriptionPosition"
    return None


def cnc_summary(path, start, end):
    rows, errors = read_jsonl(path)
    samples = [row for row in rows if row.get("kind") == "sample"]
    selected, window = coverage(samples, start, end, "timestamp", "elapsedNanos")
    result = {"file": str(path), "readErrors": errors, "coverage": window,
              "completion": next((row for row in reversed(rows) if row.get("kind") == "complete"), None),
              "failure": next((row for row in reversed(rows) if row.get("kind") == "failure"), None)}
    if len(selected) < 2 or window["selectedMonotonicSpanSeconds"] is None:
        return {**result, "unavailable": "insufficient-selected-samples"}
    first = {counter_key(value): value.get("value") for value in selected[0].get("counters", [])}
    last = {counter_key(value): value.get("value") for value in selected[-1].get("counters", [])}
    diagnostic, archive = [], []
    for key in sorted(first.keys() & last.keys()):
        kind, label = key[2], key[3] or ""
        value = {**counter_identity(key), **delta(first[key], last[key])}
        if kind in (106, 107):
            value["units"] = "bytes" if kind == 106 else "nanoseconds-wall-time-in-write-path"
            if kind == 107 and value["delta"] is not None:
                value["elapsedWriteTimeToObservedWallRatio"] = value["delta"] / 1e9 / window["selectedMonotonicSpanSeconds"]
            archive.append(value)
        if kind in (212, 215, 213, 217, 219) or kind == 0 and any(term in label for term in
                ("NAKs", "Retransmit", "back-pressure", "Loss gap", "Errors:", "Invalid packets", "Short sends", "Client liveness", "Error Frames", "exceeded threshold count")):
            diagnostic.append(value)
    roles, terms, maxima = set(), set(), {}
    positions, lag_series = [], []
    for row in selected:
        categories = defaultdict(list)
        for counter in row.get("counters", []):
            kind = counter.get("typeId")
            if kind == 201:
                roles.add(counter.get("value"))
            if kind == 239:
                terms.add(counter.get("value"))
            if kind in (105, 103, 216, 218) or kind == 0 and "max cycle time" in counter.get("label", ""):
                key = counter_key(counter)
                if numeric(counter.get("value")):
                    maxima[key] = max(maxima.get(key, counter["value"]), counter["value"])
            category = position_category(counter)
            if category:
                categories[category].append({**counter_identity(counter_key(counter)), "value": counter.get("value")})
        positions.append({"timestamp": row["timestamp"], "elapsedNanos": row["elapsedNanos"], "positions": dict(categories)})
        lag = {"timestamp": row["timestamp"], "elapsedNanos": row["elapsedNanos"]}
        for name, left, right in (("appendMinusCommitBytes", "appendPublicationPosition", "commitPosition"),
                                  ("commitMinusServiceBytes", "commitPosition", "serviceSubscriptionPosition"),
                                  ("appendMinusRecordingBytes", "appendPublicationPosition", "archiveRecordingPosition"),
                                  ("receiveHighWaterMinusRecordingBytes", "receiveHighWaterPosition", "archiveRecordingPosition")):
            left_values, right_values = categories.get(left, []), categories.get(right, [])
            lag[name] = left_values[0]["value"] - right_values[0]["value"] if len(left_values) == len(right_values) == 1 and numeric(left_values[0]["value"]) and numeric(right_values[0]["value"]) else None
        lag_series.append(lag)
    return {**result, "diagnosticCounterDeltas": diagnostic, "archiveWriteCounterDeltas": archive,
            "lifetimeMaximaObserved": [{**counter_identity(key), "maxObservedNanos": value,
                                       "scope": "Lifetime high-water gauge, possibly set during startup/warmup before arrival window"}
                                      for key, value in sorted(maxima.items())],
            "observedRoles": sorted(roles), "observedTerms": sorted(terms),
            "positionSamples": positions, "nonAtomicSignedPositionDifferenceSamples": lag_series,
            "positionDifferenceRanges": {key: gauge(row[key] for row in lag_series) for key in lag_series[0] if key.endswith("Bytes")},
            "counterIdentitiesOnlyInFirstSample": [counter_identity(key) for key in sorted(first.keys() - last.keys())],
            "counterIdentitiesOnlyInLastSample": [counter_identity(key) for key in sorted(last.keys() - first.keys())],
            "scope": "Only unchanged counter id + registration id + type + label identities are differenced; missing/reused registrations are not assumed zero. "
                     "Positions identified by label/type and log stream 100. Follower receive-HWM is distinct from leader append position. "
                     "Position differences are signed non-atomic observations, not exact lag or fsync durability proof."}


def trial_summary(directory):
    errors, hashes = [], {}
    def optional(name):
        path = directory / name
        if not path.exists():
            return None
        try:
            return read_json(path)
        except (OSError, ValueError) as exc:
            errors.append({"file": name, "error": type(exc).__name__})
            return None
    result = optional("result.json") or optional("load-result.json") or {}
    trial = optional("trial.json")
    origin, duration = result.get("scheduledOriginUtcApproximate"), result.get("arrivalWindowSeconds")
    try:
        start = utc_seconds(origin)
        end = start + duration
        if not numeric(duration) or duration <= 0:
            raise ValueError("Invalid arrival duration")
    except (ValueError, TypeError, AttributeError):
        start = end = None
        errors.append({"error": "arrival-origin-or-duration-unavailable"})
    nodes = {}
    for name in ("result.json", "load-result.json", "trial.json", "fixed-leader-check.json", "configuration.json", "failure.json"):
        path = directory / name
        if path.exists():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for node in range(3):
        telemetry_path, cnc_path = directory / f"node{node}-telemetry.jsonl", directory / f"node{node}-counters.jsonl"
        nodes[str(node)] = {"telemetry": telemetry_summary(telemetry_path, start, end, node), "cnc": cnc_summary(cnc_path, start, end)}
        for path in (telemetry_path, cnc_path):
            if path.exists():
                hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"id": directory.name, "trial": trial, "resultPassed": result.get("passed"), "measurementValidReported": result.get("measurementValid"),
            "targetArrivalRatePerSecond": result.get("targetArrivalRatePerSecond"), "workers": result.get("workers"),
            "arrivalOriginUtcApproximate": origin, "arrivalWindowSeconds": duration, "inputErrors": errors,
            "inputSha256": hashes, "nodes": nodes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs_dir", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args(argv)
    if not args.runs_dir.is_dir():
        parser.error("RUNS_DIR must exist")
    trials = [trial_summary(directory) for directory in sorted(args.runs_dir.iterdir()) if directory.is_dir()
              and ((directory / "result.json").exists() or (directory / "failure.json").exists())]
    summary = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(), "scope": SCOPE,
               "selection": "First and last observer samples whose recorded UTC lies within the approximate arrival window. "
                            "At 1 Hz the delta usually covers window minus about one second; the exact coverage is reported. "
                            "No interpolation, zero filling, raw evidence modification or live node access.",
               "trials": trials}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_json)
    print(json.dumps({"output": str(args.output_json), "completedTrials": len(trials)}))


if __name__ == "__main__":
    main()
