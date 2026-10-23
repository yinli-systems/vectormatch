#!/usr/bin/env python3
"""Reuse frozen attribution logic for the two receive-buffer cohorts.

Usage: summarize-network-attribution.py NETWORK_ROOT OUTPUT_JSON
The old script and old report remain unchanged. Directory aliases exist only in
memory; output labels and all input paths use receive128k/receive1m.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ALIASES = {"isolated": "receive128k", "shared": "receive1m"}


class MappedRoot:
    def __init__(self, path):
        self.path = Path(path)

    def __truediv__(self, key):
        return self.path / ALIASES.get(key, key)

    def __str__(self):
        return str(self.path)


def digest(path):
    content = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cnc_window_rows(rows, start, end, core):
    selected, issues = [], Counter()
    original_samples = 0
    for row in rows:
        if row.get("kind") != "sample":
            selected.append(row)
            continue
        original_samples += 1
        wall = core.utc(row.get("timestamp"))
        duration = core.counter(row.get("samplingNanos"))
        if wall is None or duration is None:
            issues["missing-sampling-timing"] += 1
        elif wall - duration / 1e9 >= start and wall <= end:
            selected.append(row)
        elif start <= wall <= end:
            issues["timestamp-inside-but-sampling-straddles-start"] += 1
    return selected, {"originalObserverSamples": original_samples,
                      "wholeSamplingIntervalSelectedSamples": sum(row.get("kind") == "sample" for row in selected),
                      "excludedTimingIssues": dict(issues)}


def recorder_summary(path, start, end, core, helper, inputs):
    if path.exists():
        inputs.append(digest(path))
    original_reader = helper.read_jsonl
    rows, errors = original_reader(path)
    selected, coverage = cnc_window_rows(rows, start, end, core)
    # The helper accepts a path rather than rows. Supply its immutable parsed
    # rows in memory for this one call; never write a filtered raw evidence file.
    def selected_reader(requested):
        if Path(requested) != path:
            raise ValueError("Unexpected CnC helper path")
        return selected, errors
    helper.read_jsonl = selected_reader
    try:
        result = helper.cnc_summary(path, start, end)
    finally:
        helper.read_jsonl = original_reader
    result["samplingSelection"] = coverage
    result["samplingScope"] = (
        "CapacityCounters records timestamp after the counter scan; samplingNanos spans the scan and timestamp construction. "
        "Conservatively require timestamp-samplingNanos >= arrival start and timestamp <= arrival end. "
        "The frozen helper then differences first/last identical counter registrations over elapsedNanos, which is local monotonic time at scan start. "
        "This cumulative-counter coverage may span missed interior observations, unlike adjacent-pair thread/socket CPU coverage. "
        "Counter values and position differences are non-atomic; no exact lag or physical disk service-time inference. "
        "Archive type107 is cumulative wall time in the write path including write+force+descheduling; it is not pure fsync latency."
    )
    return result


def buffer_attestation(path, core, inputs):
    if not path.exists():
        return {"status": "missing", "nodes": None}
    raw = core.read_json(path, inputs)
    nodes = []
    for node in raw.get("nodes", []):
        result = node.get("result") or {}
        nodes.append({"node": result.get("node"), "exitCode": node.get("exitCode"), "passed": result.get("passed"),
                      "pid": result.get("pid"), "startTicks": result.get("startTicks"),
                      "commandSha256": result.get("commandSha256"), "observedAtUtc": result.get("observedAtUtc"),
                      "diagnosticCodes": result.get("diagnosticCodes"),
                      "sockets": [{"inode": value.get("inode"), "role": value.get("role"),
                                   "localAddress": value.get("localAddress"), "localPort": value.get("localPort"),
                                   "receiveBufferKernelBytes": value.get("receiveBufferKernelBytes"),
                                   "sendBufferKernelBytes": value.get("sendBufferKernelBytes"),
                                   "absoluteOutsideWindowDropCounter": value.get("socketDrops")}
                                  for value in result.get("sockets", [])]})
    return {"status": "read", "timestamp": raw.get("timestamp"), "probeSourceSha256": raw.get("probeSourceSha256"),
            "allThreeNodesPassed": len(nodes) == 3 and all(node["passed"] is True and node["exitCode"] == 0 for node in nodes),
            "nodes": nodes, "scope": "Outside-window owned-socket pre/post attestation only. rb/tb are actual Linux kernel accounting budgets, "
            "not exact payload capacity. Absolute drop counters are not substituted for the strictly selected arrival-window deltas."}


def summarize(network):
    source = network.parent / "tool-validation/summarize-attribution.py"
    frozen_report = network.parent / "analysis/attribution-summary.json"
    repository = next(parent for parent in network.parents if (parent / "scripts/summarize-capacity-telemetry.py").exists())
    helper_path = repository / "scripts/summarize-capacity-telemetry.py"
    source_identity = digest(source)
    frozen = json.loads(frozen_report.read_bytes())
    if frozen.get("scriptSha256") != source_identity["sha256"]:
        raise ValueError("Frozen driver report and attribution source SHA do not agree")
    core = load_module("frozen_capacity_attribution_summary", source)
    helper = load_module("frozen_capacity_cnc_summary", helper_path)
    result = core.summarize(MappedRoot(network), 1.5)
    result["cohorts"] = {ALIASES[key]: value for key, value in result["cohorts"].items()}
    for pending in result["pendingOrUnavailableTrials"]:
        pending["cohort"] = ALIASES[pending["cohort"]]
    result["test"] = "network-receive-buffer-owned-thread-socket-attribution-summary"
    result["coreAttributionScriptSha256"] = result.pop("scriptSha256")
    result["scriptSha256"] = digest(Path(__file__)) ["sha256"]
    result["reproduction"] = {"argv": [sys.executable, "-B", str(Path(__file__).resolve()), str(network), "OUTPUT_JSON"],
                              "directoryAliasesInMemoryOnly": ALIASES,
                              "scope": "Only frozen internal cohort-directory lookups are mapped; no filesystem aliases or source/raw/report mutations. "
                                       "All output cohort labels and evidence paths use the real receive-buffer cohort names."}
    result["tools"] = {"wrapper": digest(Path(__file__)), "frozenAttributionCore": source_identity,
                       "frozenDriverReport": digest(frozen_report), "cncSummaryHelper": digest(helper_path)}
    for cohort, data in result["cohorts"].items():
        campaign = network / cohort / "campaign.json"
        data["campaign"] = core.read_json(campaign, result["inputs"]) if campaign.exists() else None
        for trial in data["trials"]:
            directory = network / cohort / "runs" / trial["id"]
            start = core.utc(trial["arrivalWindow"]["scheduledOriginUtcApproximate"])
            end = start + trial["arrivalWindow"]["arrivalWindowSeconds"]
            trial["recorderCounters"] = [recorder_summary(directory / f"node{node}-counters.jsonl", start, end,
                                                          core, helper, result["inputs"]) for node in range(3)]
            trial["outsideWindowSocketBufferAttestation"] = {
                boundary: buffer_attestation(directory / f"socket-buffer-{boundary}.json", core, result["inputs"])
                for boundary in ("before", "after")}
    result["scope"] += " Receive-buffer cohorts are not merged with the frozen driver experiment. The same node artifact is required by the campaign; "
    result["scope"] += "effective rb/tb attestations, hot-window owned socket increments and recorder write-path observations have separate time scopes."
    return result


def self_test():
    assert MappedRoot(Path("/tmp/network")) / "isolated" == Path("/tmp/network/receive128k")
    assert MappedRoot(Path("/tmp/network")) / "shared" == Path("/tmp/network/receive1m")
    class Core:
        @staticmethod
        def utc(value):
            return value
        @staticmethod
        def counter(value):
            return value if type(value) is int and value >= 0 else None
    rows = [{"kind": "metadata"}, {"kind": "sample", "timestamp": 11, "samplingNanos": 100_000_000},
            {"kind": "sample", "timestamp": 10.05, "samplingNanos": 100_000_000},
            {"kind": "sample", "timestamp": 11.9}, {"kind": "sample", "timestamp": 12.1, "samplingNanos": 1},
            {"kind": "complete"}]
    selected, coverage = cnc_window_rows(rows, 10, 12, Core)
    assert len(selected) == 3 and coverage["wholeSamplingIntervalSelectedSamples"] == 1
    assert coverage["excludedTimingIssues"] == {"timestamp-inside-but-sampling-straddles-start": 1, "missing-sampling-timing": 1}
    print(json.dumps({"status": "PASS", "checks": ["in-memory-cohort-directory-mapping", "CnC-scan-entirely-inside",
                      "CnC-start-straddle-excluded", "missing-CnC-timing-unavailable", "metadata-completion-preserved"]}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("network_root", type=Path, nargs="?")
    parser.add_argument("output_json", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.network_root is None or args.output_json is None:
        parser.error("NETWORK_ROOT and OUTPUT_JSON are required")
    result = summarize(args.network_root)
    result["reproduction"]["argv"][-1] = str(args.output_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_json)
    print(json.dumps({"output": str(args.output_json), "cohorts": {name: data["completedLoadResultTrials"] for name, data in result["cohorts"].items()},
                      "pending": len(result["pendingOrUnavailableTrials"]), "wrapperSha256": result["scriptSha256"]}))


if __name__ == "__main__":
    main()
