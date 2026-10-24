#!/usr/bin/env python3
"""Plot only frozen pipeline evidence; never run an analyzer, verifier or load.

Formal (requires all four complete A1/B1/A2/B2 attempts):
  .tools/capacity-venv/bin/python -B THIS_FILE
Separate functional pilot (never included as a formal point):
  .tools/capacity-venv/bin/python -B THIS_FILE --pilot

Writes only pipeline/analysis/pipeline-{comparison,pilot}.{png,svg} and the
corresponding pipeline-{comparison,pilot}-plot-inputs.json. Lossless archived
arrivals are verified in memory if the plaintext CSV has not been restored.
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

SCOPE = (
    "Each point is one terminal attempt, with no averaging, pooled percentiles or fitted lines. "
    "Goodput is accepted confirmations within the fixed arrival window. Scheduled-to-confirmed "
    "conditional accepted p99 includes client queueing and drain, but excludes not-sent, rejected, "
    "errored and final-unknown arrivals. A dagger marks unavailable all-offered accepted p99; "
    "no lost request receives a finite latency. Invalid points are client-reported diagnostics, "
    "not validated business success or capacity. The complete physical-session/network-owner/dispatch "
    "arrangement changes; logical in-flight and total FIFO remain fixed. Finite shared-host windows "
    "establish neither sustained production capacity nor a bare matching-engine ceiling."
)
COLORS = {"A": "#1767a5", "B": "#c45b1c", "P": "#407b63"}
MARKERS = {"stable": "o", "overload": "^", "short": "D", "invalid": "X", "unverified": "s"}
MAX_RAW_BYTES = 256 * 1024 * 1024


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


def load_point(inputs, task, pilot=False):
    root = inputs.root
    cohort, ident = task["cohort"], task["id"]
    directory = root / cohort / "runs" / ident
    summary = inputs.read_json(root / cohort / "analysis/summary.json")
    rows = [row for row in summary["trials"] if row["id"] == ident]
    require(len(rows) == 1, "Missing/duplicate frozen complete point: " + ident)
    row = rows[0]
    require(row["trial"].get("completedAt"), "In-progress attempt cannot be plotted: " + ident)
    for name, expected in row["inputSha256"].items():
        inputs.verify_raw(directory, name, expected)
    stopped = inputs.read_json(directory / "all-owned-processes-stopped.json")
    require(stopped.get("passed") is True, "Terminal owned-process cleanup receipt required: " + ident)
    receipt = inputs.read_json(directory / "receipt.json")
    configuration_verification = inputs.read_json(directory / "configuration-verification.json")
    for name, expected in configuration_verification.get("rawSha256", {}).items():
        inputs.verify_raw(directory, name, expected)
    inputs.read_json(directory / "postprocess.json")
    inputs.read_json(root / cohort / "campaign.json")
    comparison, configuration, trial, derived = (row[k] for k in ("comparisonConfiguration", "configuration", "trial", "derived"))
    calculated_fingerprint = hashlib.sha256(json.dumps(comparison, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(calculated_fingerprint == row["comparisonFingerprintSha256"], "Frozen configuration fingerprint mismatch: " + ident)
    fixed = comparison["fixedNodeConfiguration"]
    mode = task["transportMode"]
    sessions = 128 if mode == "direct" else 1
    expected_aeron = "one-independent-Aeron-per-client" if mode == "direct" else "one-session-one-network-owner"
    require(configuration.get("clientTransportMode") == fixed.get("clientTransportMode") == mode,
            "Actual transport metadata differs from registered point: " + ident)
    require(configuration.get("clientSessionCount") == fixed.get("clientSessionCount") == sessions,
            "Physical session metadata differs from registered point: " + ident)
    require(configuration.get("clientAeronMode") == expected_aeron and configuration.get("clientDriverMode") == "shared"
            and configuration.get("clientDriverCount") == 1, "Actual driver/session arrangement mismatch: " + ident)
    require(row["workers"] == 128 and row["queueCapacityPerWorker"] == 64 and row["scheduledArrivals"] == 350000
            and row["targetArrivalRatePerSecond"] == (10000 if pilot else 26000), "Registered workload changed: " + ident)
    expected_fixed = {"leader": 0, "syncLevel": 2, "nodeHeap": "2g", "loadHeap": "2g", "maxClusterSessions": 256,
                      "outboxCapacity": 800000, "maxRetainedOrders": 360000, "stateProfile": "capacity-350k-v1",
                      "driverThreading": "SHARED", "socketReceiveBufferBytes": 131072, "nakUnicastDelayNs": 1000,
                      "clientNakUnicastDelayNs": 1000, "nakUnicastRetryDelayRatio": 100}
    require(all(fixed.get(k) == v for k, v in expected_fixed.items()), "Fixed pipeline scope changed: " + ident)
    require(configuration.get("clientNakUnicastDelayNs") == 1000 and configuration.get("clientNakUnicastRetryDelayRatio") == 100,
            "Actual client NAK values differ: " + ident)
    node = comparison["sourceRevision"]
    require(node == comparison["loadGeneratorRevision"] and comparison["deploymentBundleSha256"] == comparison["loadGeneratorBundleSha256"],
            "Pipeline requires identical node/load artifact: " + ident)
    goodput = derived["arrivalWindowGoodputPerSecond"]
    p99 = derived["latency"]["conditionalAccepted"]["p99Millis"]
    require(finite(goodput) and (p99 is None or finite(p99)), "Missing/nonfinite plotted metric: " + ident)
    return {"id": ident, "cohort": cohort, "label": task["label"], "arm": task["label"][0], "mode": mode,
            "physicalSessionCount": sessions, "logicalWorkers": 128, "queuePerWorker": 64, "totalFifoSlots": 8192,
            "status": status(row), "classification": row["classification"], "measurementValid": row["measurementValid"],
            "capacityEligible": row["measurementValid"] is True and row["validationChecks"].get("canonicalSnapshotBytesVerified") is True,
            "receiptExitCode": receipt.get("exitCode"), "configurationVerification": configuration_verification,
            "comparisonFingerprintSha256": row["comparisonFingerprintSha256"], "comparisonConfiguration": comparison,
            "nodeRevision": node, "loadGeneratorRevision": comparison["loadGeneratorRevision"],
            "nodeBundleSha256": comparison["deploymentBundleSha256"], "loadGeneratorBundleSha256": comparison["loadGeneratorBundleSha256"],
            "preparedSnapshotSha256": comparison["preparedSnapshotSha256"], "offeredPerSecond": row["targetArrivalRatePerSecond"],
            "scheduledArrivals": row["scheduledArrivals"], "arrivalWindowSeconds": row["arrivalWindowSeconds"],
            "arrivalWindowGoodputPerSecond": goodput, "conditionalAcceptedP99Millis": p99,
            "allOfferedAcceptedP99Millis": derived["allOfferedAcceptedP99Millis"],
            "allOfferedAcceptedFinite": derived["allOfferedAcceptedFinite"],
            "clientNotSent": derived["clientNotSent"], "businessRejected": derived["businessRejected"],
            "serverErrors": derived["serverErrors"], "unknownAtInitialDeadline": derived["unknownAtInitialDeadline"],
            "finalUnresolved": derived["unknownUnresolved"], "confirmedAccepted": derived["confirmedAccepted"],
            "drainSeconds": derived["drainSeconds"], "backlog": row["backlog"],
            "validationChecks": row["validationChecks"], "stabilityChecks": row["stabilityChecks"],
            "effectiveDrainLimitSeconds": row["effectiveDrainLimitSeconds"],
            "effectiveBacklogGrowthLimitCommands": row["effectiveBacklogGrowthLimitCommands"],
            "rawDerived": derived, "inputSha256": row["inputSha256"], "trial": trial}


def validate_comparison(points, pilot):
    if pilot:
        require(len(points) == 1, "Pilot plot must contain exactly one separate point")
        return
    require([p["label"] for p in points] == ["A1", "B1", "A2", "B2"], "Four ordered formal attempts required")
    for arm in ("A", "B"):
        require(len({p["comparisonFingerprintSha256"] for p in points if p["arm"] == arm}) == 1,
                "Replicate configuration fingerprint changed: " + arm)
    require(points[0]["comparisonFingerprintSha256"] != points[1]["comparisonFingerprintSha256"],
            "Distinct arrangement fingerprints required")
    for key in ("nodeRevision", "loadGeneratorRevision", "nodeBundleSha256", "loadGeneratorBundleSha256",
                "preparedSnapshotSha256", "offeredPerSecond", "scheduledArrivals", "arrivalWindowSeconds"):
        require(len({p[key] for p in points}) == 1, "Fixed identity/workload changed: " + key)
    normalized = []
    for point in points:
        config = json.loads(json.dumps(point["comparisonConfiguration"]))
        for key in ("clientAeronMode", "clientTransportMode", "clientSessionCount"):
            config.pop(key, None)
        for key in ("clientTransportMode", "clientSessionCount"):
            config["fixedNodeConfiguration"].pop(key, None)
        normalized.append(config)
    require(all(value == normalized[0] for value in normalized), "Unexpected additional configuration factor changed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", action="store_true", help="Render the single functional pilot separately; never substitute it for formal points")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    inputs = FrozenInputs(root)
    plan = inputs.read_json(root / ("pilot-plan.json" if args.pilot else "plan.json"))
    release = inputs.read_json(root / "node-release.json")
    inputs.read_json(root / "node-deployment-manifest.json")
    inputs.read_json(root / "node-upload-receipt.json")
    if args.pilot:
        tasks = [{"id": "p-pilot-multiplexed-10000-w128", "cohort": "pilot", "transportMode": "multiplexed", "label": "P"}]
    else:
        tasks = [{"id": f"p-{mode}-26000-w128-r{r}", "cohort": mode, "transportMode": mode, "label": arm + str(r)}
                 for r in (1, 2) for arm, mode in (("A", "direct"), ("B", "multiplexed"))]
    require([(t["id"], t["cohort"], t["transportMode"]) for t in plan["trials"]] ==
            [(t["id"], t["cohort"], t["transportMode"]) for t in tasks], "Frozen registration order/IDs differ")
    points = [load_point(inputs, task, args.pilot) for task in tasks]
    validate_comparison(points, args.pilot)
    require(all(p["nodeRevision"] == release["revision"] and p["nodeBundleSha256"] == release["bundleSha256"] for p in points),
            "Registered artifact differs from frozen deployment release")
    output = root / "analysis"
    output.mkdir(exist_ok=True)
    stem = "pipeline-pilot" if args.pilot else "pipeline-comparison"
    for suffix in (".png", ".svg", "-plot-inputs.json"):
        target = output / (stem + suffix)
        require(not target.is_symlink(), "Refuse symlink output: " + str(target))
    # Import plotting libraries only after every required terminal point/input has verified.
    with tempfile.TemporaryDirectory(prefix="vectormatch-pipeline-plot-") as cache:
        os.environ["MPLCONFIGDIR"] = cache
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.ticker import FuncFormatter
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                             "axes.spines.right": False, "text.color": "#172c40", "axes.labelcolor": "#223548",
                             "svg.hashsalt": "vectormatch-pipeline-comparison-v1"})
        fig = plt.figure(figsize=(17, 12), facecolor="white")
        grid = fig.add_gridspec(3, 2, left=.075, right=.975, top=.79, bottom=.17,
                               height_ratios=(1.35, 1.05, .95), hspace=.52, wspace=.20)
        first = points[0]
        fig.suptitle("VectorMatch: session / network-owner arrangement" + (" — separate pilot" if args.pilot else " — formal A/B/A/B"),
                     x=.075, y=.975, ha="left", fontsize=19, fontweight="bold")
        fig.text(.075, .944, "A: direct 128 physical sessions    B: multiplexed 1 physical session    Both: W128, Q64 / FIFO8192, shared driver1",
                 fontsize=11, color="#465e72")
        fig.text(.075, .918,
                 f"{first['offeredPerSecond']:,.0f} offered/s | {first['scheduledArrivals']:,} arrivals | {first['arrivalWindowSeconds']:.6f} s | "
                 "leader0, sync2 | node/load2g | NAK node/load1000ns, retry100", fontsize=10, color="#465e72")
        fig.text(.075, .894, f"Same node/load revision {first['nodeRevision']} | bundle SHA {first['nodeBundleSha256'][:20]}…",
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
        fig.text(.075, .078, "Changing the complete session / network-owner / dispatch arrangement is not a pure logical-window or server-only experiment. No percentile pooling or cross-point fitted lines.",
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
                        "registration": plan, "artifact": release, "points": points,
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
