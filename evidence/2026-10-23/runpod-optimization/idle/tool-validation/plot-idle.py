#!/usr/bin/env python3
"""Render only frozen node-idle evidence; never run analyzers, verifiers or load.

Formal (requires all four complete registered A1/B1/A2/B2 attempts):
  .tools/capacity-venv/bin/python -B THIS_FILE
Separate pilot, never substituted for a formal point:
  .tools/capacity-venv/bin/python -B THIS_FILE --pilot

Writes only idle/analysis/idle-{comparison,pilot}.{png,svg} and the matching
*-plot-inputs.json. Archives are verified by full streaming decompression if
arrivals.csv is absent. No original evidence is written or reclassified.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET

NODE_REVISION = "87ad09c11807a78d4f8e3b2ad6088e6940e33261"
NODE_BUNDLE = "1317d767d1e6f1cc43320dea284818cc4fa246de7242c275d05408220aa270d0"
LOAD_REVISION = "e57e341909a49692b9ecbf9693803ed62a240b06"
LOAD_BUNDLE = "f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937"
ANALYSIS_REVISION = "3fd86fe535fc0858e300e0337d4da154f622ae32"
ANALYSIS_IDENTITY = "31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f"
PREPARED_SHA = "2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4"
MAX_RAW_BYTES = 256 * 1024 * 1024
COLORS = {"A": "#1767a5", "B": "#c45b1c", "P": "#407b63"}
MARKERS = {"stable": "o", "overload": "^", "short": "D", "invalid": "X", "unverified": "s"}
SCOPE = (
    "Each point is one terminal attempt; no averaging, pooled percentiles or fitted lines. "
    "A changes only node data-path maximum park from1000000ns to B100000ns; both arms use "
    "the same new node artifact, fixed e57 multiplexed1 session/shared1 driver/logicalW128/Q64, "
    "and separate analysis31e. Driver spins/yields10/5, archive/consensus/service10/20, minimum1000ns "
    "and sync2 stay fixed. Goodput is accepted confirmations within the arrival window. "
    "Conditional accepted scheduled-to-confirmed p99 includes client queueing/drain and excludes "
    "not-sent/rejected/errored/final-unknown arrivals. A dagger marks unavailable all-offered p99. "
    "Invalid points are diagnostics, not validated business success/capacity. Finite shared-host "
    "windows establish neither sustained production capacity nor a matching-engine ceiling."
)

def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def status(row):
    if row.get("measurementValid") is not True:
        return "invalid"
    return {"OBSERVED_STABLE_WINDOW": "stable",
            "OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT": "overload",
            "INSUFFICIENT_WINDOW_OBSERVATIONS": "short"}.get(row.get("classification"), "unverified")


def require(condition, message):
    if not condition:
        raise ValueError(message)


class FrozenInputs:
    def __init__(self, root):
        self.root, self.files, self.archived_raw = root, {}, {}

    def remember(self, path):
        require(not path.is_symlink() and path.is_file(), "Missing or non-regular frozen input: " + str(path))
        key = str(path.relative_to(self.root))
        observed = {"sha256": sha256(path), "bytes": path.stat().st_size}
        require(key not in self.files or self.files[key] == observed, "Frozen input changed: " + key)
        self.files[key] = observed
        return observed

    def read_json(self, path):
        expected = self.remember(path)
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected["sha256"], "Input changed while reading: " + str(path))
        return json.loads(raw)

    def verify_raw(self, directory, name, expected):
        relative = Path(name)
        require(not relative.is_absolute() and ".." not in relative.parts,
                "Unsafe input path in frozen receipt: " + name)
        path = directory / relative
        if path.is_file() or path.is_symlink() or name != "arrivals.csv":
            require(self.remember(path)["sha256"] == expected, "Frozen raw SHA mismatch: " + str(path))
            return
        manifest = self.read_json(directory / "arrivals-archive.json")
        packed = directory / "arrivals.csv.gz"
        compressed = self.remember(packed)
        require(manifest.get("rawFile") == "arrivals.csv" and manifest.get("archiveFile") == "arrivals.csv.gz",
                "Unexpected arrivals archive names")
        require(manifest.get("rawSha256") == expected and manifest.get("compressedSha256") == compressed["sha256"]
                and manifest.get("compressedBytes") == compressed["bytes"], "Archive metadata/SHA mismatch")
        result, count = hashlib.sha256(), 0
        with gzip.open(packed, "rb") as stream:
            while chunk := stream.read(1024 * 1024):
                count += len(chunk)
                require(count <= MAX_RAW_BYTES, "Decoded arrivals exceed the fixed 256 MiB limit")
                result.update(chunk)
        require(result.hexdigest() == expected and count == manifest.get("rawBytes"), "Decoded arrivals SHA/size mismatch")
        self.archived_raw[str(path.relative_to(self.root))] = {
            "sha256": expected, "bytes": count, "verifiedByFullStreamingDecompression": True,
            "archive": str(packed.relative_to(self.root)), "plaintextCreated": False}

    def verify_unchanged(self):
        for name, expected in self.files.items():
            path = self.root / name
            require(path.is_file() and not path.is_symlink() and path.stat().st_size == expected["bytes"]
                    and sha256(path) == expected["sha256"], "Frozen input changed during plotting: " + name)


def tasks(pilot):
    if pilot:
        return [{"id": "i-pilot-park100000-10000-w128", "cohort": "pilot", "rate": 10000,
                 "arrivals": 350000, "workers": 128, "transportMode": "multiplexed", "maxParkNs": 100000,
                 "phase": "node-idle-strict350k-canonical-pilot", "repetition": 1}]
    return [{"id": f"i-park{park}-26000-w128-r{rep}", "cohort": f"park{park}", "rate": 26000,
             "arrivals": 350000, "workers": 128, "transportMode": "multiplexed", "maxParkNs": park,
             "phase": "node-only-data-path-max-park-control", "repetition": rep}
            for rep in (1, 2) for park in (1000000, 100000)]


def load_point(inputs, task, plan, label):
    ident, cohort = task["id"], task["cohort"]
    directory = inputs.root / cohort / "runs" / ident
    summary = inputs.read_json(inputs.root / cohort / "analysis/summary.json")
    rows = [row for row in summary["trials"] if row["id"] == ident]
    require(len(rows) == 1, "Missing/duplicate frozen point: " + ident)
    row = rows[0]
    require(row["trial"].get("completedAt"), "In-progress point cannot be plotted: " + ident)
    for name, expected in row["inputSha256"].items():
        inputs.verify_raw(directory, name, expected)
    stop = inputs.read_json(directory / "all-owned-processes-stopped.json")
    require(stop.get("passed") is True and len(stop.get("nodes", [])) == 3
            and {node.get("node") for node in stop["nodes"]} == {0, 1, 2}
            and all(node.get("passed") is True and node.get("records")
                    and all(record.get("passed") is True and record.get("recordPresent") is True
                            and record.get("after") == "stopped" for record in node["records"])
                    for node in stop["nodes"]), "Complete owned cleanup required: " + ident)
    receipt = inputs.read_json(directory / "receipt.json")
    verify = inputs.read_json(directory / "configuration-verification.json")
    require(verify.get("passed") is True, "Verified recorded configuration required: " + ident)
    for name, expected in verify.get("rawSha256", {}).items():
        inputs.verify_raw(directory, name, expected)
    sidecar = inputs.read_json(directory / "postprocessor-identity.json")
    post = inputs.read_json(directory / "postprocess.json")
    require(sidecar == plan["postprocessor"] == post.get("postprocessor")
            and sidecar.get("revision") == ANALYSIS_REVISION
            and sidecar.get("analysisIdentitySha256") == post.get("analysisIdentitySha256")
            == post.get("analysis", {}).get("analysisIdentitySha256") == ANALYSIS_IDENTITY,
            "Independent postprocessor identity mismatch: " + ident)
    require(all(post.get(section, {}).get("exitCode") == 0 for section in ("configuration", "analysis", "archive"))
            and post["analysis"].get("rawInputsUnchanged") is True
            and post["analysis"].get("arrivalsShaAgrees") is True,
            "Incomplete retained postprocessing: " + ident)
    require(set(post["analysis"].get("immutableOutputSha256", {})) == {"analysis-summary.json", "analysis-capacity.csv"},
            "Immutable analysis snapshots required: " + ident)
    for name, expected in post["analysis"]["immutableOutputSha256"].items():
        inputs.verify_raw(directory, name, expected)
    for name, expected in post["analysis"]["inputSha256Before"].items():
        require(Path(name).name == name, "Unexpected analyzed input name")
        inputs.verify_raw(directory, name, expected)
    frozen = inputs.read_json(directory / "analysis-summary.json")
    require([value for value in frozen["trials"] if value["id"] == ident] == [row],
            "Current and immutable per-attempt analysis differ: " + ident)
    campaign = inputs.read_json(inputs.root / cohort / "campaign.json")
    comparison, config, trial, derived = (row[key] for key in ("comparisonConfiguration", "configuration", "trial", "derived"))
    fingerprint = hashlib.sha256(json.dumps(comparison, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(fingerprint == row["comparisonFingerprintSha256"], "Configuration fingerprint mismatch: " + ident)
    fixed = comparison["fixedNodeConfiguration"]
    require(campaign["fixed"] == trial["fixedNodeConfiguration"] == fixed, "Fixed campaign/trial/comparison differ: " + ident)
    expected_fixed = {"leader": 0, "syncLevel": 2, "nodeHeap": "2g", "loadHeap": "2g", "maxClusterSessions": 256,
                      "outboxCapacity": 800000, "maxRetainedOrders": 360000, "stateProfile": "capacity-350k-v1",
                      "driverThreading": "SHARED", "socketReceiveBufferBytes": 131072, "nakUnicastDelayNs": 1000,
                      "clientNakUnicastDelayNs": 1000, "nakUnicastRetryDelayRatio": 100,
                      "clientTransportMode": "multiplexed", "clientSessionCount": 1,
                      "nodeDataPathMaxParkNs": task["maxParkNs"], "driverIdleMaxParkNs": task["maxParkNs"],
                      "nodeDataPathIdlePolicyVersion": 1, "nodeDataPathIdleAgentMaxYields": 20,
                      "nodeDataPathIdleMinParkNs": 1000, "driverIdleMaxSpins": 10, "driverIdleMaxYields": 5,
                      "driverIdleMinParkNs": 1000}
    require(all(fixed.get(key) == expected for key, expected in expected_fixed.items()), "Node-idle fixed scope differs: " + ident)
    require(config.get("clientTransportMode") == "multiplexed" and config.get("clientSessionCount") == 1
            and config.get("clientAeronMode") == "one-session-one-network-owner"
            and config.get("clientDriverMode") == "shared" and config.get("clientDriverCount") == 1
            and config.get("clientNakUnicastDelayNs") == 1000 and config.get("clientNakUnicastRetryDelayRatio") == 100,
            "Actual fixed load transport differs: " + ident)
    require(row["workers"] == 128 and row["queueCapacityPerWorker"] == 64 and row["scheduledArrivals"] == 350000
            and row["targetArrivalRatePerSecond"] == task["rate"] and trial["phase"] == task["phase"]
            and trial["repetition"] == task["repetition"], "Registered workload changed: " + ident)
    expected_sources = {"sourceRevision": NODE_REVISION, "deploymentBundleSha256": NODE_BUNDLE,
                        "loadGeneratorRevision": LOAD_REVISION, "loadGeneratorBundleSha256": LOAD_BUNDLE,
                        "preparedSnapshotSha256": PREPARED_SHA}
    require(all(comparison.get(key) == value for key, value in expected_sources.items()), "Node/load/prepared identity mismatch: " + ident)
    require(trial.get("loadGeneratorJvmArguments") == ["-Dvectormatch.capacity.client.driver=shared", "-Daeron.nak.unicast.delay=1000",
                                                      "-Dvectormatch.capacity.client.transport=multiplexed"],
            "Node-only idle flag leaked into load JVM or load arguments changed: " + ident)
    goodput, p99 = derived["arrivalWindowGoodputPerSecond"], derived["latency"]["conditionalAccepted"]["p99Millis"]
    require((goodput is None or finite(goodput)) and (p99 is None or finite(p99)), "Nonfinite plot metric: " + ident)
    return {"id": ident, "cohort": cohort, "label": label, "arm": label[0], "maxParkNs": task["maxParkNs"],
            "mode": "multiplexed", "physicalSessionCount": 1, "logicalWorkers": 128, "queuePerWorker": 64, "totalFifoSlots": 8192,
            "status": status(row), "classification": row["classification"], "measurementValid": row["measurementValid"],
            "capacityEligible": row["measurementValid"] is True and row["validationChecks"].get("canonicalSnapshotBytesVerified") is True,
            "receiptExitCode": receipt.get("exitCode"), "configurationVerification": verify,
            "comparisonFingerprintSha256": fingerprint, "comparisonConfiguration": comparison,
            "nodeRevision": NODE_REVISION, "nodeBundleSha256": NODE_BUNDLE,
            "loadGeneratorRevision": LOAD_REVISION, "loadGeneratorBundleSha256": LOAD_BUNDLE,
            "analysisIdentitySha256": ANALYSIS_IDENTITY, "preparedSnapshotSha256": PREPARED_SHA,
            "offeredPerSecond": row["targetArrivalRatePerSecond"], "scheduledArrivals": row["scheduledArrivals"],
            "arrivalWindowSeconds": row["arrivalWindowSeconds"], "arrivalWindowGoodputPerSecond": goodput,
            "conditionalAcceptedP99Millis": p99, "allOfferedAcceptedP99Millis": derived["allOfferedAcceptedP99Millis"],
            "allOfferedAcceptedFinite": derived["allOfferedAcceptedFinite"], "clientNotSent": derived["clientNotSent"],
            "businessRejected": derived["businessRejected"], "serverErrors": derived["serverErrors"],
            "unknownAtInitialDeadline": derived["unknownAtInitialDeadline"], "finalUnresolved": derived["unknownUnresolved"],
            "confirmedAccepted": derived["confirmedAccepted"], "drainSeconds": derived["drainSeconds"], "backlog": row["backlog"],
            "validationChecks": row["validationChecks"], "stabilityChecks": row["stabilityChecks"],
            "effectiveDrainLimitSeconds": row["effectiveDrainLimitSeconds"],
            "effectiveBacklogGrowthLimitCommands": row["effectiveBacklogGrowthLimitCommands"],
            "rawDerived": derived, "inputSha256": row["inputSha256"], "trial": trial}


def validate_comparison(points, pilot):
    require(len(points) == (1 if pilot else 4), "Complete separate pilot or four formal attempts required")
    if pilot:
        require(points[0]["label"] == "P", "Pilot cannot substitute for formal attempts")
        return
    require([point["label"] for point in points] == ["A1", "B1", "A2", "B2"], "Ordered formal A/B/A/B required")
    for arm in ("A", "B"):
        require(len({p["comparisonFingerprintSha256"] for p in points if p["arm"] == arm}) == 1,
                "Replicate fingerprint changed: " + arm)
    require(points[0]["comparisonFingerprintSha256"] != points[1]["comparisonFingerprintSha256"], "Distinct park fingerprints required")
    normalized = []
    for point in points:
        config = json.loads(json.dumps(point["comparisonConfiguration"]))
        for key in ("nodeDataPathMaxParkNs", "driverIdleMaxParkNs", "idleStrategy"):
            config["fixedNodeConfiguration"].pop(key, None)
        normalized.append(config)
    require(all(config == normalized[0] for config in normalized), "Unexpected factor besides node max park changed")
    for key in ("nodeRevision", "loadGeneratorRevision", "nodeBundleSha256", "loadGeneratorBundleSha256",
                "analysisIdentitySha256", "preparedSnapshotSha256", "offeredPerSecond", "scheduledArrivals", "arrivalWindowSeconds"):
        require(len({point[key] for point in points}) == 1, "Fixed identity/workload changed: " + key)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="Render only the separate pilot; never substitute it for formal attempts")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    inputs = FrozenInputs(root)
    plan = inputs.read_json(root / ("pilot-plan.json" if args.pilot else "plan.json"))
    require(plan.get("kind") == ("pilot" if args.pilot else "matrix"), "Registration kind mismatch")
    expected_tasks = tasks(args.pilot)
    require(plan.get("trials") == expected_tasks, "Frozen registration IDs/order/workload differ")
    require(plan.get("analysisIdentitySha256") == ANALYSIS_IDENTITY
            and plan.get("postprocessor", {}).get("revision") == ANALYSIS_REVISION, "Registered postprocessor identity differs")
    release = inputs.read_json(root / "node-release.json")
    inputs.read_json(root / "node-deployment-manifest.json")
    upload = inputs.read_json(root / "node-upload-receipt.json")
    require(release == plan["node"] and release.get("revision") == NODE_REVISION and release.get("bundleSha256") == NODE_BUNDLE
            and plan["load"].get("revision") == LOAD_REVISION and plan["load"].get("bundleSha256") == LOAD_BUNDLE,
            "Frozen independent node/load release differs")
    require(upload.get("bundleSha256") == NODE_BUNDLE and {node.get("node") for node in upload.get("nodes", [])} == {0, 1, 2}
            and len(upload["nodes"]) == 3 and all(node.get("verified") is True for node in upload["nodes"]),
            "All three immutable node upload receipts required")
    timeline = root / "timeline.jsonl"
    expected = inputs.remember(timeline)
    timeline_bytes = timeline.read_bytes()
    require(hashlib.sha256(timeline_bytes).hexdigest() == expected["sha256"], "Completion timeline changed while reading")
    action = "node-idle-" + ("pilot" if args.pilot else "matrix") + "-completed"
    completed = [json.loads(line) for line in timeline_bytes.splitlines() if line.strip()]
    completed = [event for event in completed if event.get("action") == action]
    require(len(completed) == 1 and [trial["id"] for trial in completed[0].get("trials", [])]
            == [task["id"] for task in expected_tasks], "Complete registered execution timeline required")
    labels = ["P"] if args.pilot else ["A1", "B1", "A2", "B2"]
    points = [load_point(inputs, task, plan, label) for task, label in zip(expected_tasks, labels)]
    validate_comparison(points, args.pilot)
    output = root / "analysis"
    output.mkdir(exist_ok=True)
    stem = "idle-pilot" if args.pilot else "idle-comparison"
    for suffix in (".png", ".svg", "-plot-inputs.json"):
        target = output / (stem + suffix)
        require(not target.is_symlink(), "Refuse symlink output: " + str(target))
    # Import plotting libraries only after every required terminal point/input has verified.
    with tempfile.TemporaryDirectory(prefix="vectormatch-idle-plot-") as cache:
        os.environ["MPLCONFIGDIR"] = cache
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.ticker import FuncFormatter
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                             "axes.spines.right": False, "text.color": "#172c40", "axes.labelcolor": "#223548",
                             "svg.hashsalt": "vectormatch-idle-comparison-v1"})
        fig = plt.figure(figsize=(17, 12), facecolor="white")
        grid = fig.add_gridspec(3, 2, left=.075, right=.975, top=.79, bottom=.17,
                               height_ratios=(1.35, 1.05, .95), hspace=.52, wspace=.20)
        first = points[0]
        fig.suptitle("VectorMatch: node data-path maximum park" + (" — separate pilot" if args.pilot else " — formal A/B/A/B"),
                     x=.075, y=.975, ha="left", fontsize=19, fontweight="bold")
        fig.text(.075, .944, "A: node maximum park 1,000,000 ns    B: 100,000 ns    Both: fixed e57 mux1 session, W128 / FIFO8192",
                 fontsize=11, color="#465e72")
        fig.text(.075, .918,
                 f"{first['offeredPerSecond']:,.0f} offered/s | {first['scheduledArrivals']:,} arrivals | {first['arrivalWindowSeconds']:.6f} s | "
                 "leader0, sync2 | node/load2g | NAK node/load1000ns, retry100", fontsize=10, color="#465e72")
        fig.text(.075, .894, f"Node {first['nodeRevision'][:12]} / bundle {first['nodeBundleSha256'][:12]} | load {first['loadGeneratorRevision'][:12]} / bundle {first['loadGeneratorBundleSha256'][:12]} | analysis 31e4dbc7af8c6e84",
                 fontsize=9, color="#465e72")
        fig.text(.075, .871, "Configuration SHA: " + "  /  ".join(f"{arm} {next(p for p in points if p['arm'] == arm)['comparisonFingerprintSha256'][:16]}"
                 for arm in dict.fromkeys(p["arm"] for p in points)), fontsize=9, color="#465e72")
        fig.text(.075, .845, "Each point retains its frozen classification. Invalid confirmations/latencies are reported diagnostics, not validated capacity.",
                 fontsize=10, color="#7d3f37")
        axes = [fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]),
                fig.add_subplot(grid[1, 0]), fig.add_subplot(grid[1, 1])]
        metrics = [("arrivalWindowGoodputPerSecond", "Arrival-window accepted confirmations/s", None),
                   ("conditionalAcceptedP99Millis", "Conditional scheduled-to-confirmed p99 (ms)", None),
                   ("peakQueueDepth", "Peak sampled client FIFO queue depth", "backlog"),
                   ("drainSeconds", "Drain after arrival window (s)", None)]
        for axis, (key, label, section) in zip(axes, metrics):
            axis.set_axisbelow(True); axis.grid(axis="y", color="#dce4eb", linewidth=.7)
            axis.set_xticks(range(len(points)), [p["label"] for p in points]); axis.set_xlim(-.5, len(points) - .5)
            axis.set_ylabel(label)
            values = [p[section].get(key) if section else p.get(key) for p in points]
            available = [v for v in values if finite(v)]
            max_value = max(available + [1])
            if key == "arrivalWindowGoodputPerSecond":
                max_value = max(max_value, first["offeredPerSecond"])
                axis.axhline(first["offeredPerSecond"], color="#718395", linewidth=1, linestyle=(0, (4, 3)))
                axis.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
            axis.set_ylim(0, max_value * 1.32)
            for index, (p, value) in enumerate(zip(points, values)):
                if not finite(value):
                    axis.text(index, max_value * .1, "unavailable", ha="center", fontsize=8)
                    continue
                color = COLORS[p["arm"]]
                axis.scatter(index, value, color=color, marker=MARKERS[p["status"]], s=110,
                             edgecolors="white", linewidths=1.1, zorder=3)
                dagger = "†" if key == "conditionalAcceptedP99Millis" and p["allOfferedAcceptedP99Millis"] is None else ""
                text = f"{value:,.0f}" if key == "peakQueueDepth" else f"{value:,.3f}"
                axis.annotate(text + dagger, (index, value), xytext=(0, 12), textcoords="offset points",
                              ha="center", fontsize=10, color=color, fontweight="bold")
        table_axis = fig.add_subplot(grid[2, :]); table_axis.axis("off")
        columns = ["Point / status", "Not sent", "Rejected", "Errors", "Initial unknown", "Final unknown", "Peak outstanding", "Drain (ms)"]
        cells = [[f"{p['label']}  {p['status']}", f"{p['clientNotSent']:,}", f"{p['businessRejected']:,}",
                  f"{p['serverErrors']:,}", f"{p['unknownAtInitialDeadline']:,}", f"{p['finalUnresolved']:,}",
                  "N/A" if p["backlog"].get("peakObservedOutstanding") is None else f"{p['backlog']['peakObservedOutstanding']:,}",
                  "N/A" if p["drainSeconds"] is None else f"{p['drainSeconds'] * 1000:,.3f}"] for p in points]
        table = table_axis.table(cellText=cells, colLabels=columns, loc="center", cellLoc="center",
                                 colWidths=[.17, .10, .10, .08, .13, .12, .15, .15])
        table.auto_set_font_size(False); table.set_fontsize(9); table.scale(1, 1.8)
        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor("#d8e2eb")
            if row == 0: cell.set_facecolor("#edf3f8"); cell.set_text_props(weight="bold")
        legends = [Line2D([], [], marker=marker, color="#53697b", linestyle="None", markersize=8, label=name)
                   for name, marker in MARKERS.items()]
        fig.legend(handles=legends, loc="lower left", bbox_to_anchor=(.07, .125), ncol=5, frameon=False, fontsize=9)
        fig.text(.075, .116, "† All-offered accepted p99 is null. Conditional p99 excludes loss, rejection, error and unresolved requests; it is never an all-request latency claim.",
                 fontsize=8.5, color="#465e72")
        fig.text(.075, .097, "Backlog is a non-atomic sampled observation; peak outstanding = sampled queue + in-flight. Exact raw values, checks and source/build identities are in the input manifest.",
                 fontsize=8.3, color="#465e72")
        fig.text(.075, .078, "Only node maximum park changes: driver spin/yield10/5; archive/consensus/service10/20; minimum1us. Client idle and transport are fixed. No pooled percentiles.",
                 fontsize=8.3, color="#465e72")
        fig.text(.075, .055, "  |  ".join(p["label"] + " " + p["id"] for p in points[:2]), fontsize=8, color="#465e72")
        if len(points) > 2:
            fig.text(.075, .037, "  |  ".join(p["label"] + " " + p["id"] for p in points[2:]), fontsize=8, color="#465e72")
        fig.text(.075, .018, "Separate 35-second functional pilot; not a formal capacity comparison." if args.pilot else
                 "All four registered attempts are retained individually. Finite windows on shared cloud hosts do not establish sustained production capacity or a matching-engine ceiling.",
                 fontsize=8.3, color="#465e72")
        with tempfile.TemporaryDirectory(prefix="." + stem + "-", dir=output) as staging:
            staging = Path(staging)
            png, svg = staging / (stem + ".png"), staging / (stem + ".svg")
            fig.savefig(png, dpi=180, facecolor="white", metadata={"Description": SCOPE})
            fig.savefig(svg, facecolor="white", metadata={"Description": SCOPE, "Date": None})
            plt.close(fig)
            inputs.verify_unchanged()
            with png.open("rb") as stream: header = stream.read(24)
            require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", "Invalid PNG output")
            width, height = struct.unpack(">II", header[16:24])
            xml = ET.parse(svg).getroot(); require(xml.tag.endswith("svg"), "Invalid SVG output")
            manifest = {"schemaVersion": 1, "generatedAtUtc": datetime.now(timezone.utc).isoformat(), "scope": SCOPE,
                        "scriptSha256": sha256(Path(__file__).resolve()), "pythonExecutable": sys.executable,
                        "pythonVersion": platform.python_version(), "matplotlibVersion": matplotlib.__version__,
                        "command": [sys.executable, "-B", str(Path(__file__).resolve()), *(["--pilot"] if args.pilot else [])],
                        "formalTrials": 0 if args.pilot else 4, "pilotIncludedAsFormal": False, "pilotOnly": args.pilot,
                        "registration": plan, "artifact": release, "loadArtifact": plan["load"], "analysisIdentity": plan["postprocessor"], "points": points,
                        "inputs": dict(sorted(inputs.files.items())), "archivedRawInputs": inputs.archived_raw,
                        "outputs": {"png": {"file": png.name, "sha256": sha256(png), "bytes": png.stat().st_size,
                                              "widthPixels": width, "heightPixels": height, "signatureVerified": True},
                                    "svg": {"file": svg.name, "sha256": sha256(svg), "bytes": svg.stat().st_size,
                                              "viewBox": xml.attrib.get("viewBox"), "xmlRootVerified": True}}}
            generated = staging / (stem + "-plot-inputs.json")
            generated.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
            for item in (png, svg, generated): os.replace(item, output / item.name)
    print(json.dumps({"formalTrials": 0 if args.pilot else 4, "pilotOnly": args.pilot,
                      "readOnlyInputsVerified": len(inputs.files), "png": str(output / (stem + ".png")),
                      "svg": str(output / (stem + ".svg")), "widthPixels": width, "heightPixels": height,
                      "pythonExecutable": sys.executable}))


if __name__ == "__main__":
    main()
