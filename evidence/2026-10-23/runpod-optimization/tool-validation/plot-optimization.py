#!/usr/bin/env python3
"""Plot frozen optimization summaries without re-running analysis or changing evidence.

Run: .tools/capacity-venv/bin/python -B THIS_FILE
Optionally add --include-window350k after all four formal concurrency trials finish.
Only analysis/optimization-comparison.png, .svg and plot-inputs.json are written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
    "Each point is one complete trial, in A1/B1/A2/B2 execution order; no averages, "
    "pooled percentiles, fitted curves or cross-factor connections. Goodput counts accepted "
    "confirmations within the arrival window. Conditional accepted p99 includes scheduled "
    "queueing time but excludes not-sent, rejected, errored and unresolved arrivals. A dagger "
    "marks unavailable all-offered accepted p99. Status is copied from frozen summaries. "
    "Finite windows on shared cloud hosts establish neither sustained production capacity "
    "nor a bare matching-engine ceiling. The optional fourth comparison changes workers "
    "and total FIFO capacity together. Functional smoke and the 350k pilot are not formal points."
)
COLORS = {"A": "#1767a5", "B": "#c45b1c"}
MARKERS = {"stable": "o", "overload": "^", "short": "D", "invalid": "X", "unverified": "s"}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def status(row):
    if row["measurementValid"] is not True:
        return "invalid"
    return {"OBSERVED_STABLE_WINDOW": "stable",
            "OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT": "overload",
            "INSUFFICIENT_WINDOW_OBSERVATIONS": "short"}.get(row["classification"], "unverified")


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-window350k", action="store_true")
    args = parser.parse_args(argv)
    inputs, summaries = {}, {}

    def remember(path):
        if path.is_symlink() or not path.is_file():
            raise ValueError("Expected regular input file: " + str(path))
        key = str(path.relative_to(root))
        observed = {"sha256": digest(path), "bytes": path.stat().st_size}
        if key in inputs and inputs[key] != observed:
            raise ValueError("Input changed during plotting: " + key)
        inputs[key] = observed
        return observed

    def summary(cohort):
        if cohort not in summaries:
            path = root / cohort / "analysis/summary.json"
            remembered = remember(path)
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != remembered["sha256"]:
                raise ValueError("Summary changed while reading")
            summaries[cohort] = json.loads(content)
        return summaries[cohort]

    def point(cohort, ident, label):
        rows = [row for row in summary(cohort)["trials"] if row["id"] == ident]
        if len(rows) != 1:
            raise ValueError("Missing/duplicate frozen trial: " + ident)
        row = rows[0]
        directory = root / cohort / "runs" / ident
        for name, expected in row["inputSha256"].items():
            if Path(name).name != name:
                raise ValueError("Unexpected input filename")
            if remember(directory / name)["sha256"] != expected:
                raise ValueError("Frozen summary/input SHA mismatch: " + ident + "/" + name)
        trial = row["trial"]
        if not trial.get("completedAt"):
            raise ValueError("In-progress trial cannot be plotted: " + ident)
        comparison = row["comparisonConfiguration"]
        observed = row["derived"]
        goodput = observed["arrivalWindowGoodputPerSecond"]
        p99 = observed["latency"]["conditionalAccepted"]["p99Millis"]
        if not finite(goodput) or (p99 is not None and not finite(p99)):
            raise ValueError("Nonfinite metric: " + ident)
        node = comparison.get("sourceRevision") or trial.get("deploymentRevision")
        load = comparison.get("loadGeneratorRevision") or node
        return {"id": ident, "cohort": cohort, "label": label, "arm": label[0],
                "status": status(row), "classification": row["classification"],
                "measurementValid": row["measurementValid"],
                "comparisonFingerprintSha256": row["comparisonFingerprintSha256"],
                "nodeRevision": node, "loadGeneratorRevision": load,
                "nodeBundleSha256": comparison["deploymentBundleSha256"],
                "loadGeneratorBundleSha256": comparison.get("loadGeneratorBundleSha256"),
                "configuration": comparison, "inputSha256": row["inputSha256"],
                "offeredPerSecond": row["targetArrivalRatePerSecond"],
                "scheduledArrivals": row["scheduledArrivals"],
                "arrivalWindowSeconds": row["arrivalWindowSeconds"],
                "workers": row["workers"], "queuePerWorker": row["queueCapacityPerWorker"],
                "arrivalWindowGoodputPerSecond": goodput,
                "conditionalAcceptedP99Millis": p99,
                "allOfferedAcceptedP99Millis": observed["allOfferedAcceptedP99Millis"],
                "allOfferedAcceptedFinite": observed["allOfferedAcceptedFinite"],
                "acceptedCommands": observed["confirmedAccepted"],
                "clientNotSentCommands": observed["clientNotSent"],
                "unresolvedFinal": observed["unknownUnresolved"],
                "businessRejected": observed["businessRejected"], "serverErrors": observed["serverErrors"]}

    definitions = [
        ("client-drivers", "Client MediaDriver count", "isolated", "shared",
         "o-isolated-15000-w128-r{r}", "o-shared-15000-w128-r{r}"),
        ("receive-buffer", "Node UDP receive buffer (requested bytes)", "network/receive128k", "network/receive1m",
         "n-r128k-15000-w128-r{r}", "n-r1m-15000-w128-r{r}"),
        ("node-threading", "Node MediaDriver threading", "threading/shared", "threading/dedicated",
         "t-shared-15000-w128-r{r}", "t-dedicated-15000-w128-r{r}"),
    ]
    if args.include_window350k:
        definitions.append(("concurrency-configuration", "Workers AND total FIFO slots (whole configuration)",
                            "window350k/w128", "window350k/w256",
                            "w-window-26000-w128-r{r}", "w-window-26000-w256-r{r}"))
    factors = []
    for name, title, a, b, pattern_a, pattern_b in definitions:
        points = [point(cohort, pattern.format(r=repetition), arm + str(repetition))
                  for repetition in (1, 2)
                  for arm, cohort, pattern in (("A", a, pattern_a), ("B", b, pattern_b))]
        # Validate the declared comparison, without pooling its two distinct fingerprints.
        for arm in ("A", "B"):
            fingerprints = {p["comparisonFingerprintSha256"] for p in points if p["arm"] == arm}
            if len(fingerprints) != 1 or None in fingerprints:
                raise ValueError("Replicate configuration differs: " + name + "/" + arm)
        for key in ("nodeRevision", "loadGeneratorRevision", "nodeBundleSha256", "loadGeneratorBundleSha256",
                    "scheduledArrivals", "offeredPerSecond", "arrivalWindowSeconds", "queuePerWorker"):
            if len({p[key] for p in points}) != 1:
                raise ValueError("Fixed comparison identity differs: " + name + "/" + key)
        a_config, b_config = points[0]["configuration"], points[1]["configuration"]
        if name == "client-drivers":
            arm_labels = [f"{v['clientDriverCount']} {v['clientDriverMode']} driver" + ("s" if v['clientDriverCount'] != 1 else "")
                          for v in (a_config, b_config)]
        elif name == "receive-buffer":
            arm_labels = [f"{v['fixedNodeConfiguration']['socketReceiveBufferBytes']:,} B" for v in (a_config, b_config)]
        elif name == "node-threading":
            arm_labels = [v["fixedNodeConfiguration"]["driverThreading"] for v in (a_config, b_config)]
        else:
            arm_labels = [f"W{p['workers']} / {p['workers'] * p['queuePerWorker']:,} FIFO slots" for p in points[:2]]
        factors.append({"id": name, "title": title, "armLabels": dict(zip(("A", "B"), arm_labels)), "points": points})

    # Functional smoke remains an independent annotation. The live 350k pilot is never read or plotted.
    smoke = point("shared", "o-smoke-shared-8000-w128", "B0")
    output = root / "analysis"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vectormatch-optimization-mpl-") as cache:
        os.environ["MPLCONFIGDIR"] = cache
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
        from matplotlib.ticker import FuncFormatter

        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                             "axes.spines.top": False, "axes.spines.right": False,
                             "axes.labelcolor": "#223548", "text.color": "#172c40",
                             "xtick.color": "#31485b", "ytick.color": "#31485b",
                             "svg.hashsalt": "vectormatch-optimization-comparison-v1"})
        count = len(factors)
        fig = plt.figure(figsize=(17, 4.0 * count + 2.2), facecolor="white")
        grid = fig.add_gridspec(count * 4, 2, height_ratios=[.48, 1.6, .53, .22] * count,
                               left=.07, right=.975, bottom=.105, top=.90, hspace=.04, wspace=.17)
        fig.suptitle("VectorMatch: controlled finite-window optimization comparisons", x=.07, y=.973,
                     ha="left", fontsize=19, fontweight="bold")
        fig.text(.07, .944, "One trial per point, ordered A1 / B1 / A2 / B2. Arms and artifact versions are local to each row.",
                 fontsize=11, color="#465e72")
        for index, factor in enumerate(factors):
            points = factor["points"]
            first = points[0]
            header = fig.add_subplot(grid[index * 4, :])
            header.axis("off")
            header.text(0, .91, f"{index + 1}. {factor['title']}    A: {factor['armLabels']['A']}    B: {factor['armLabels']['B']}",
                        fontsize=12, fontweight="bold", va="top")
            workers = "/".join(str(value) for value in sorted({p["workers"] for p in points}))
            header.text(0, .49,
                        f"{first['offeredPerSecond']:,.0f} offered/s  |  {first['scheduledArrivals']:,} offers  |  "
                        f"{first['arrivalWindowSeconds']:.3f} s  |  W{workers}, Q{first['queuePerWorker']}/worker  |  "
                        f"node {first['nodeRevision'][:8]}  |  load {first['loadGeneratorRevision'][:8]}",
                        fontsize=9, va="top", color="#465e72")
            header.text(0, .25,
                        f"Profile {first['configuration'].get('fixedNodeConfiguration', {}).get('capacityProfile', first['configuration'].get('profile', 'extended-190k-128'))}  |  "
                        f"config SHA A {points[0]['comparisonFingerprintSha256'][:12]} / B {points[1]['comparisonFingerprintSha256'][:12]}  |  "
                        "leader 0, sync 2; separate configurations, no pooled p99",
                        fontsize=8.6, va="top", color="#465e72")
            goodput = fig.add_subplot(grid[index * 4 + 1, 0])
            latency = fig.add_subplot(grid[index * 4 + 1, 1])
            for axis in (goodput, latency):
                axis.set_axisbelow(True)
                axis.grid(axis="y", color="#dce4eb", linewidth=.7)
                axis.set_xlim(-.55, 3.55)
                axis.set_xticks(range(4), [p["label"] for p in points])
                axis.tick_params(axis="x", length=0, labelsize=10)
                axis.spines["bottom"].set_color("#acbac6")
                axis.spines["left"].set_color("#acbac6")
            goodput.set_ylabel("Arrival-window goodput (accepted/s)")
            goodput.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
            goodput.set_ylim(0, first["offeredPerSecond"] * 1.15)
            goodput.axhline(first["offeredPerSecond"], color="#718395", linewidth=1, linestyle=(0, (4, 3)))
            goodput.text(3.5, first["offeredPerSecond"] * 1.02, "offered rate", ha="right", fontsize=8, color="#667b8c")
            latency.set_ylabel("Conditional accepted p99 (ms)")
            maximum = max([p["conditionalAcceptedP99Millis"] or 0 for p in points] + [1])
            latency.set_ylim(0, maximum * 1.27)
            for offset, p in enumerate(points):
                color = COLORS[p["arm"]]
                marker = MARKERS[p["status"]]
                goodput.scatter(offset, p["arrivalWindowGoodputPerSecond"], color=color, s=95,
                                marker=marker, linewidths=1.2, edgecolors="white", zorder=3)
                goodput.annotate(f"{p['arrivalWindowGoodputPerSecond']:,.1f}",
                                (offset, p["arrivalWindowGoodputPerSecond"]), xytext=(0, -20),
                                textcoords="offset points", ha="center", fontsize=10, fontweight="bold", color=color)
                goodput.text(offset, first["offeredPerSecond"] * .28,
                             f"not sent: {p['clientNotSentCommands']:,}\nunresolved: {p['unresolvedFinal']:,}",
                             ha="center", va="center", fontsize=8.4, color="#53697b")
                value = p["conditionalAcceptedP99Millis"]
                if value is None:
                    latency.text(offset, maximum * .1, "p99 unavailable", ha="center", fontsize=8, rotation=45)
                else:
                    latency.scatter(offset, value, color=color, s=95, marker=marker, linewidths=1.2,
                                    edgecolors="white", zorder=3)
                    dagger = "\u2020" if p["allOfferedAcceptedP99Millis"] is None else ""
                    latency.annotate(f"{value:,.1f}{dagger}", (offset, value), xytext=(0, 12),
                                     textcoords="offset points", ha="center", fontsize=10, fontweight="bold", color=color)
            ids = fig.add_subplot(grid[index * 4 + 2, :])
            ids.axis("off")
            for arm, x in (("A", 0), ("B", .54)):
                labels = [f"{p['label']}  {p['id']}  [{p['status']}]" for p in points if p["arm"] == arm]
                ids.text(x, .82, "\n".join(labels), fontsize=8.5, va="top", color=COLORS[arm], linespacing=1.7)
        legend = [Line2D([], [], marker=marker, color="#53697b", linestyle="None", markersize=8, label=name)
                  for name, marker in MARKERS.items()]
        fig.legend(handles=legend, loc="lower left", bbox_to_anchor=(.064, .065), ncol=5, frameon=False, fontsize=9)
        fig.text(.07, .052, "\u2020 All-offered accepted p99 is unavailable: that trial includes not-sent/rejected/error/unresolved arrivals. No loss is assigned a finite latency.",
                 fontsize=8.6, color="#465e72")
        fig.text(.07, .032,
                 f"Functional smoke only (excluded above): {smoke['id']}, {smoke['arrivalWindowSeconds']:.1f} s, "
                 f"goodput {smoke['arrivalWindowGoodputPerSecond']:,.1f}/s, p99 {smoke['conditionalAcceptedP99Millis']:.3f} ms [{smoke['status']}].",
                 fontsize=8.3, color="#465e72")
        fig.text(.07, .014, "350k pilot excluded. Each formal finite window retains its own fingerprint; shared cloud hosts and colocated load generation limit generalization.",
                 fontsize=8.3, color="#465e72")
        png = output / "optimization-comparison.png"
        svg = output / "optimization-comparison.svg"
        fig.savefig(png, dpi=180, facecolor="white", metadata={"Description": SCOPE})
        fig.savefig(svg, facecolor="white", metadata={"Description": SCOPE, "Date": None})
        plt.close(fig)
        mpl_version = matplotlib.__version__
    # Prove read-only plotting: every frozen summary/raw input must retain its input SHA.
    for name, expected in inputs.items():
        if digest(root / name) != expected["sha256"] or (root / name).stat().st_size != expected["bytes"]:
            raise ValueError("Input changed during plotting: " + name)
    with png.open("rb") as stream:
        signature = stream.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n" or signature[12:16] != b"IHDR":
        raise ValueError("Invalid PNG output")
    width, height = struct.unpack(">II", signature[16:24])
    xml = ET.parse(svg).getroot()
    if not xml.tag.endswith("svg"):
        raise ValueError("Invalid SVG output")
    manifest = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(),
                "scope": SCOPE, "scriptSha256": digest(Path(__file__).resolve()),
                "pythonExecutable": sys.executable, "pythonVersion": platform.python_version(),
                "matplotlibVersion": mpl_version, "command": [sys.executable, "-B", str(Path(__file__).resolve()),
                 *(["--include-window350k"] if args.include_window350k else [])],
                "inputs": dict(sorted(inputs.items())), "factors": factors,
                "functionalSmokeAnnotation": smoke, "pilotIncludedAsFormal": False,
                "artifacts": {"png": {"file": png.name, "sha256": digest(png), "bytes": png.stat().st_size,
                                       "widthPixels": width, "heightPixels": height, "signatureVerified": True},
                              "svg": {"file": svg.name, "sha256": digest(svg), "bytes": svg.stat().st_size,
                                       "viewBox": xml.attrib.get("viewBox"), "xmlRootVerified": True}}}
    (output / "plot-inputs.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"factors": len(factors), "formalTrials": sum(len(factor["points"]) for factor in factors),
                      "readOnlyInputsVerified": len(inputs), "png": str(png), "svg": str(svg),
                      "widthPixels": width, "heightPixels": height, "pythonExecutable": sys.executable}))


if __name__ == "__main__":
    main()
