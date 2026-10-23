#!/usr/bin/env python3
"""Attribute node SHARED/DEDICATED trials while the client driver stays shared.

Usage: summarize-threading-attribution.py THREADING_ROOT OUTPUT_JSON
Frozen core/network scripts and reports are imported read-only. Only the output
JSON is written; no aliases are created in the filesystem.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ALIASES = {"isolated": "shared", "shared": "dedicated"}
CGROUP_COUNTERS = ("cpuUsageNanos", "cpuPeriods", "throttledPeriods", "throttledNanos")


def digest(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cgroup_summary(path, start, end, core, helper, inputs):
    document = core.read_jsonl(path, inputs)
    selected, pairs, metadata, selection = core.selection(document, start, end, 1.5)
    issues, quota_values, identities = Counter(), set(), set()
    totals = {name: 0 for name in CGROUP_COUNTERS}
    covered = {name: 0 for name in CGROUP_COUNTERS}
    counts = {name: 0 for name in CGROUP_COUNTERS}
    memory, raw_quotas = [], []
    for sample in selected:
        group = helper.cgroup_metrics(sample)
        if group.get("unavailable"):
            issues[f"sample:{group['unavailable']}"] += 1
        memory.append(group.get("memoryBytes"))
        quota = core.counter(group.get("quotaCores"))
        if quota is not None and quota > 0:
            quota_values.add(quota)
        raw_quota = group.get("rawQuota")
        if raw_quota not in raw_quotas:
            raw_quotas.append(raw_quota)
    for first, last, elapsed in pairs:
        before, after = helper.cgroup_metrics(first), helper.cgroup_metrics(last)
        a = (before.get("version"), before.get("directory"), before.get("quotaCores"))
        b = (after.get("version"), after.get("directory"), after.get("quotaCores"))
        if a[0] is None or a[1] is None or a != b:
            issues["cgroup-unavailable-or-version-path-quota-changed-pairs"] += 1
            continue
        identities.add(a)
        for name in CGROUP_COUNTERS:
            initial, final = core.counter(before.get(name)), core.counter(after.get(name))
            if initial is None or final is None:
                issues[f"{name}:unavailable-pairs"] += 1
            elif final < initial:
                issues[f"{name}:counter-reset-or-wrap-pairs"] += 1
            else:
                totals[name] += final - initial
                covered[name] += elapsed
                counts[name] += 1
    quota = next(iter(quota_values)) if len(quota_values) == 1 and len(identities) == 1 else None
    usage_cores = totals["cpuUsageNanos"] / covered["cpuUsageNanos"] if counts["cpuUsageNanos"] and covered["cpuUsageNanos"] else None
    return {"path": str(path), "selection": selection,
            "cgroupIdentities": [{"version": row[0], "directory": row[1], "visibleQuotaCores": row[2]} for row in sorted(identities, key=str)],
            "observedVisibleQuotaCoreValues": sorted(quota_values), "visibleQuotaCores": quota,
            "rawQuotasObserved": raw_quotas,
            "counterDeltasOverAdjacentPairs": {name: totals[name] if counts[name] else None for name in CGROUP_COUNTERS},
            "validCounterPairs": counts, "coveredSecondsByCounter": {name: covered[name] / 1e9 for name in CGROUP_COUNTERS},
            "averageLogicalCores": usage_cores,
            "percentOfVisibleQuota": usage_cores / quota * 100 if usage_cores is not None and quota is not None and quota > 0 else None,
            "memoryBytes": core.gauge(memory), "coverageIssues": dict(issues),
            "scope": "Current visible cgroup leaf, shared with sampler and other processes; node2 also contains the load JVM. "
                     "CPU usage and throttling counters are joined only across adjacent whole-collection-interior samples with the same version/path/quota. "
                     "Nanosecond counters remain nanoseconds; cpuPeriods/throttledPeriods are counts. Missing/reset counters remain unavailable, never zero. "
                     "Visible quota is an upper bound, not dedicated cores; hidden ancestors and physical host contention are not measured. "
                     "Aggregate spare quota does not establish spare capacity in any one thread."}


def summarize(threading):
    optimization = threading.parent
    network_script = optimization / "network/tool-validation/summarize-network-attribution.py"
    frozen_network = optimization / "network/analysis/attribution-summary.json"
    network_identity = digest(network_script)
    frozen_network_data = json.loads(frozen_network.read_bytes())
    if frozen_network_data.get("scriptSha256") != network_identity["sha256"]:
        raise ValueError("Frozen network report and network wrapper SHA do not agree")
    network = load_module("frozen_network_attribution_wrapper", network_script)
    # Directory mapping is an in-memory parameter of the imported wrapper. The
    # module's on-disk source, historical report and all evidence stay unchanged.
    network.ALIASES = dict(ALIASES)
    result = network.summarize(threading)
    frozen_helper_sha = frozen_network_data.get("tools", {}).get("cncSummaryHelper", {}).get("sha256")
    if frozen_helper_sha != result["tools"]["cncSummaryHelper"]["sha256"]:
        raise ValueError("CnC helper changed since the frozen network report")
    core = load_module("frozen_threading_attribution_core", optimization / "tool-validation/summarize-attribution.py")
    helper_path = Path(result["tools"]["cncSummaryHelper"]["path"])
    helper = load_module("frozen_threading_telemetry_helper", helper_path)
    result["test"] = "node-media-driver-threading-owned-attribution-summary"
    result["reusedNetworkWrapperSha256"] = result.pop("scriptSha256")
    result["scriptSha256"] = digest(Path(__file__))["sha256"]
    result["tools"]["networkReuseWrapper"] = result["tools"].pop("wrapper")
    result["tools"].update(threadingWrapper=digest(Path(__file__)), frozenNetworkReport=digest(frozen_network))
    result["reproduction"] = {"argv": [sys.executable, "-B", str(Path(__file__).resolve()), str(threading), "OUTPUT_JSON"],
                              "directoryAliasesInMemoryOnly": ALIASES,
                              "scope": "Internal frozen core directory keys are mapped to actual node-mode cohort directories; "
                                       "SHARED/DEDICATED label the node MediaDriver, while every client/load driver stays shared."}
    for cohort, data in result["cohorts"].items():
        fixed = core.get(data, "campaign", "fixed") or {}
        data["modeContext"] = {"nodeMediaDriverThreading": fixed.get("driverThreading"),
                               "declaredNodeMediaDriverRunnerCount": 4 if fixed.get("driverThreading") == "DEDICATED" else 1 if fixed.get("driverThreading") == "SHARED" else None,
                               "clientDriverMode": core.get(data, "campaign", "clientDriverMode"),
                               "nodeSocketReceiveBufferRequestedBytes": fixed.get("socketReceiveBufferArgumentBytes"),
                               "scope": "Runner count is a configuration expectation: DEDICATED includes sender, receiver, conductor and native-resource runners. "
                                        "Observed TIDs/CPU are retained under raw kernel-truncated comm names; no name is expanded into an invented role."}
        for trial in data["trials"]:
            directory = threading / cohort / "runs" / trial["id"]
            source = directory / "load-result.json"
            if not source.exists():
                source = directory / "result.json"
            load = json.loads(source.read_bytes())
            trial["clientModeObservedFromLoadResult"] = {"driverMode": load.get("clientDriverMode"),
                                                       "driverCount": load.get("clientDriverCount"),
                                                       "aeronMode": load.get("clientAeronMode"), "workers": load.get("workers")}
            start = core.utc(trial["arrivalWindow"]["scheduledOriginUtcApproximate"])
            end = start + trial["arrivalWindow"]["arrivalWindowSeconds"]
            trial["cgroupQuotaAndThrottling"] = [cgroup_summary(directory / f"node{node}-telemetry.jsonl", start, end,
                                                               core, helper, result["inputs"]) for node in range(3)]
    result["scope"] = (
        "Only node MediaDriver SHARED versus DEDICATED scheduling is grouped here; client driver mode remains shared and is recorded independently. "
        "This matrix uses its own common node artifact, explicit independent idle strategies and fixed receive buffer. It is not merged with driver-count or "
        "receive-buffer experiments. Frozen whole-collection/identity/socket/CnC rules are reused, with exact tool/input SHA identities. "
        "Declared one-versus-four node runners is not a measurement-derived label; native-resource is included in DEDICATED. "
        "All observed thread names remain kernel-truncated. Cgroup quotas/throttling, owned socket drops, recorder wall time and observer costs are observations "
        "with separate coverage, not proof of a unique causal bottleneck, sustained capacity or bare matching-engine ceiling."
    )
    return result


def self_test():
    threading = Path(__file__).resolve().parents[1]
    core = load_module("threading_cgroup_selftest_core", threading.parent / "tool-validation/summarize-attribution.py")
    class Helper:
        @staticmethod
        def cgroup_metrics(row):
            return row["testCgroup"]
    start = core.utc("2026-10-23T00:00:00Z")
    def sample(sequence, second, usage, periods, throttled, throttle_ns, quota=5.1):
        return {"type": "sample", "sequence": sequence, "wallTimeUtc": datetime.fromtimestamp(start + second, timezone.utc).isoformat(),
                "monotonicNs": int(second * 1e9), "collectionElapsedNs": 10_000_000,
                "testCgroup": {"version": 1, "directory": "/owned/leaf", "quotaCores": quota,
                               "cpuUsageNanos": usage, "cpuPeriods": periods, "throttledPeriods": throttled,
                               "throttledNanos": throttle_ns, "memoryBytes": 100, "rawQuota": {"quota": quota}}}
    a, b = sample(0, 1, 100, 10, 0, 0), sample(1, 2, 1_000_000_100, 20, 1, 50)
    document = {"status": "read", "parseErrors": [], "rows": [{"type": "metadata", "intervalSeconds": 1}, a, b]}
    reader = core.read_jsonl
    core.read_jsonl = lambda path, inputs: document
    try:
        result = cgroup_summary(Path("owned.jsonl"), start, start + 3, core, Helper, [])
        assert result["averageLogicalCores"] == 1 and result["visibleQuotaCores"] == 5.1
        assert result["counterDeltasOverAdjacentPairs"]["throttledNanos"] == 50
        b["testCgroup"]["throttledNanos"] = None
        assert cgroup_summary(Path("owned.jsonl"), start, start + 3, core, Helper, [])["counterDeltasOverAdjacentPairs"]["throttledNanos"] is None
        b["testCgroup"]["quotaCores"] = 6
        changed = cgroup_summary(Path("owned.jsonl"), start, start + 3, core, Helper, [])
        assert changed["averageLogicalCores"] is None and changed["visibleQuotaCores"] is None
        b["testCgroup"]["quotaCores"] = 5.1
        b["testCgroup"]["cpuUsageNanos"] = 1
        assert cgroup_summary(Path("owned.jsonl"), start, start + 3, core, Helper, [])["averageLogicalCores"] is None
    finally:
        core.read_jsonl = reader
    print(json.dumps({"status": "PASS", "checks": ["adjacent-cgroup-CPU-and-quota", "throttle-nanosecond-delta",
                      "missing-throttle-not-zero", "quota-change-rejects-join", "reset-counter-unavailable"]}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("threading_root", type=Path, nargs="?")
    parser.add_argument("output_json", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.threading_root is None or args.output_json is None:
        parser.error("THREADING_ROOT and OUTPUT_JSON are required")
    result = summarize(args.threading_root)
    result["reproduction"]["argv"][-1] = str(args.output_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_json)
    print(json.dumps({"output": str(args.output_json), "cohorts": {name: data["completedLoadResultTrials"] for name, data in result["cohorts"].items()},
                      "pending": len(result["pendingOrUnavailableTrials"]), "wrapperSha256": result["scriptSha256"]}))


if __name__ == "__main__":
    main()
