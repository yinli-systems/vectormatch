#!/usr/bin/env python3
"""Plot every 13k/14k/15k/16k long-window W128 trial from raw backlog CSV.

Run with .tools/capacity-venv/bin/python -B THIS_SCRIPT after the final summary
has been generated. Only backlog.png, backlog.svg and backlog-plot.json are
written to the output directory. No source evidence is changed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET


RATES = (13000, 14000, 15000, 16000)
FIELDS = ("offset_ns", "queue_depth", "in_flight", "client_not_sent")
SCOPE = (
    "Raw non-atomic queue_depth + in_flight observations, sampled approximately "
    "once per second plus terminal samples. Lines connect observations; they do "
    "not reconstruct unsampled peaks or exact queue conservation. Each panel has "
    "its own y scale. Dashed lines, when present, use the right axis and are raw "
    "cumulative client_not_sent, not server rejections. A bounded queue can plateau "
    "while commands are not sent. Finite-window observations do not establish "
    "sustained capacity, monotonic capacity or a bare matching-engine ceiling."
)


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def read_samples(path):
    content = path.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    if not reader.fieldnames or not set(FIELDS).issubset(reader.fieldnames):
        raise ValueError(f"Missing required backlog columns: {path}")
    samples = []
    for line, row in enumerate(reader, start=2):
        sample = {}
        for name in FIELDS:
            try:
                value = int(row[name])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid integer {name} at {path}:{line}") from exc
            if value < 0:
                raise ValueError(f"Negative {name} at {path}:{line}")
            sample[name] = value
        if samples and sample["offset_ns"] < samples[-1]["offset_ns"]:
            raise ValueError(f"Regressing offset at {path}:{line}")
        if samples and sample["client_not_sent"] < samples[-1]["client_not_sent"]:
            raise ValueError(f"Regressing cumulative client_not_sent at {path}:{line}")
        samples.append(sample)
    if not samples:
        raise ValueError(f"Empty backlog CSV: {path}")
    return content, samples, reader.fieldnames


def main(argv=None):
    cohort = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, default=cohort / "analysis/summary.json")
    parser.add_argument("--runs-dir", type=Path, default=cohort / "runs")
    parser.add_argument("--output-dir", type=Path, default=cohort / "analysis")
    parser.add_argument("--expected-total-trials", type=int, default=10,
                        help="Refuse an incomplete summary (default: 10)")
    args = parser.parse_args(argv)
    summary_bytes = args.summary.read_bytes()
    summary = json.loads(summary_bytes)
    trials = summary["trials"]
    if len(trials) != args.expected_total_trials:
        raise ValueError(f"Expected {args.expected_total_trials} summary trials, found {len(trials)}")
    fingerprints = {trial.get("comparisonFingerprintSha256") for trial in trials}
    if len(fingerprints) != 1 or None in fingerprints:
        raise ValueError("All cohort trials must have one fixed configuration fingerprint")
    selected = [trial for trial in trials if trial.get("workers") == 128
                and trial.get("targetArrivalRatePerSecond") in RATES]
    selected.sort(key=lambda trial: (trial["targetArrivalRatePerSecond"], trial["id"]))
    if {trial["targetArrivalRatePerSecond"] for trial in selected} != set(RATES):
        raise ValueError("All four requested high-rate panels require at least one trial")
    if len({trial["id"] for trial in selected}) != len(selected):
        raise ValueError("Duplicate trial IDs")
    prepared = []
    for trial in selected:
        identifier = trial["id"]
        if not isinstance(identifier, str) or Path(identifier).name != identifier:
            raise ValueError("Invalid trial ID path")
        csv_path = args.runs_dir / identifier / "backlog.csv"
        raw, samples, columns = read_samples(csv_path)
        window = trial["arrivalWindowSeconds"]
        if type(window) not in (int, float) or not math.isfinite(window) or window <= 0:
            raise ValueError(f"Invalid arrival window for {identifier}")
        outstanding = [sample["queue_depth"] + sample["in_flight"] for sample in samples]
        # This is a consistency check against the analyzer's interpretation of
        # these same non-atomic raw fields, not a conservation assertion.
        if trial["backlog"]["samples"] != len(samples):
            raise ValueError(f"Analyzer/raw sample count mismatch: {identifier}")
        if trial["backlog"]["peakObservedOutstanding"] != max(outstanding):
            raise ValueError(f"Analyzer/raw observed peak mismatch: {identifier}")
        if trial["derived"]["clientNotSent"] != samples[-1]["client_not_sent"]:
            raise ValueError(f"Analyzer/raw terminal not-sent mismatch: {identifier}")
        prepared.append((trial, samples, {
            "id": identifier, "phase": trial.get("phase"),
            "repetition": trial.get("repetition"),
            "classification": trial["classification"],
            "measurementValid": trial["measurementValid"],
            "ratePerSecond": trial["targetArrivalRatePerSecond"],
            "workers": trial["workers"], "queuePerWorker": trial["queueCapacityPerWorker"],
            "scheduledArrivals": trial["scheduledArrivals"], "arrivalWindowSeconds": window,
            "backlogCsv": str(csv_path), "backlogCsvSha256": sha256(raw),
            "backlogCsvBytes": len(raw), "columns": columns, "samples": len(samples),
            "firstOffsetSeconds": samples[0]["offset_ns"] / 1e9,
            "lastOffsetSeconds": samples[-1]["offset_ns"] / 1e9,
            "observedPeakQueueDepth": max(sample["queue_depth"] for sample in samples),
            "observedPeakInFlight": max(sample["in_flight"] for sample in samples),
            "observedPeakQueuedPlusInFlight": max(outstanding),
            "terminalQueuedPlusInFlight": outstanding[-1],
            "terminalCumulativeClientNotSent": samples[-1]["client_not_sent"],
        }))

    # A temporary Matplotlib config/cache avoids mutating the repository or a
    # user's home directory. A fixed SVG salt and omitted date stabilize output.
    with tempfile.TemporaryDirectory(prefix="vectormatch-backlog-mpl-") as cache:
        os.environ["MPLCONFIGDIR"] = cache
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator, StrMethodFormatter

        matplotlib.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                                    "axes.titlesize": 12, "axes.labelsize": 10,
                                    "svg.hashsalt": sha256(summary_bytes)})
        fig, panels = plt.subplots(2, 2, figsize=(16, 10))
        fig.suptitle("VectorMatch | Backlog across every high-rate repeat", fontsize=20,
                     fontweight="bold", x=0.06, ha="left", y=0.975)
        fig.text(0.06, 0.93,
                 "Fixed configuration · 128 clients · queue 64/client · 190,000 arrivals/trial",
                 color="#475569", fontsize=12)
        colors = ("#2563eb", "#d97706", "#7c3aed", "#059669")
        for ax, rate in zip(panels.flat, RATES):
            panel_trials = [item for item in prepared if item[0]["targetArrivalRatePerSecond"] == rate]
            loss_axis = ax.twinx() if any(item[2]["terminalCumulativeClientNotSent"] for item in panel_trials) else None
            handles, labels = [], []
            windows = sorted({item[0]["arrivalWindowSeconds"] for item in panel_trials})
            for index, (trial, samples, metadata) in enumerate(panel_trials):
                x = [sample["offset_ns"] / 1e9 for sample in samples]
                y = [sample["queue_depth"] + sample["in_flight"] for sample in samples]
                color = colors[index % len(colors)]
                line, = ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=3.7,
                                label=trial["id"])
                handles.append(line)
                verdict = ("stable window" if trial.get("observedStableWindow") is True
                           else "nonstable window") if trial["measurementValid"] else "invalid measurement"
                labels.append(f"{trial['id']} · {verdict}")
                if loss_axis is not None and metadata["terminalCumulativeClientNotSent"]:
                    rejected, = loss_axis.plot(x, [sample["client_not_sent"] for sample in samples],
                                              color=color, linewidth=1.8, linestyle="--")
                    handles.append(rejected)
                    labels.append(f"{trial['id']} · cumulative not sent")
            for window in windows:
                ax.axvline(window, color="#64748b", linestyle=":", linewidth=1.5)
            window_label = ", ".join(f"{window:.3f}" for window in windows)
            ax.set_title(f"{rate:,} arrivals/s   |   arrival end {window_label} s", loc="left", y=1.30, pad=0,
                         fontweight="bold")
            ax.set_xlabel("Seconds since first scheduled arrival")
            ax.set_ylabel("Observed queued + in flight (commands)")
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            ax.grid(axis="both", alpha=0.2)
            ax.spines[["top", "right"]].set_visible(False)
            if loss_axis is not None:
                loss_axis.set_ylim(bottom=0)
                loss_axis.set_ylabel("Cumulative client not sent (dashed)", color="#475569")
                loss_axis.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
                loss_axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
                loss_axis.spines["top"].set_visible(False)
            ax.legend(handles, labels, loc="lower left", bbox_to_anchor=(0, 1.015),
                      borderaxespad=0, fontsize=7.7, frameon=False)
        fig.subplots_adjust(left=0.07, right=0.93, bottom=0.16, top=0.81, hspace=0.67, wspace=0.36)
        fig.text(0.06, 0.09,
                 "Dots are raw ~1 Hz observations; connecting lines do not reveal unsampled peaks. "
                 "Queue + in-flight reads are non-atomic. Each panel uses its own y scale.",
                 fontsize=10, color="#475569")
        fig.text(0.06, 0.065,
                 "Dotted vertical line: scheduled arrival-window end. Dashed right-axis line: "
                 "cumulative client not sent. A bounded queue can plateau while rejecting arrivals.",
                 fontsize=10, color="#475569")
        fig.text(0.06, 0.04,
                 "All repeats are shown individually. Stability labels come from the analyzer's "
                 "explicit finite-window criteria; the lines alone do not establish sustained capacity.",
                 fontsize=10, color="#475569")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        title = "VectorMatch raw backlog, all long-window W128 high-rate repeats"
        for suffix in ("png", "svg"):
            metadata = {"Title": title, "Description": SCOPE}
            if suffix == "svg":
                metadata.update(Creator="VectorMatch plot-backlog.py", Date=None)
            else:
                metadata["Software"] = f"VectorMatch plot-backlog.py; Matplotlib {matplotlib.__version__}"
            fig.savefig(args.output_dir / f"backlog.{suffix}", dpi=150,
                        metadata=metadata, facecolor="white")
        plt.close(fig)
        matplotlib_version = matplotlib.__version__

    png_path, svg_path = (args.output_dir / f"backlog.{suffix}" for suffix in ("png", "svg"))
    png, svg = png_path.read_bytes(), svg_path.read_bytes()
    if png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        raise ValueError("Invalid PNG header")
    dimensions = struct.unpack(">II", png[16:24])
    root = ET.fromstring(svg)
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("Invalid SVG root")
    record = {
        "schemaVersion": 1, "test": "raw-backlog-high-rate-repeat-plot",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, "-B", str(Path(__file__).resolve()), *sys.argv[1:]],
        "workingDirectory": str(Path.cwd()), "pythonVersion": platform.python_version(),
        "matplotlibVersion": matplotlib_version,
        "scriptSha256": sha256(Path(__file__).read_bytes()),
        "inputSummary": str(args.summary), "inputSummarySha256": sha256(summary_bytes),
        "inputSummaryTrialCount": len(trials), "plottedTrialCount": len(prepared),
        "ratesPerSecond": list(RATES), "workers": 128,
        "configurationFingerprintSha256": next(iter(fingerprints)),
        "scope": SCOPE, "series": [item[2] for item in prepared],
        "artifacts": {
            "png": {"path": str(png_path), "sha256": sha256(png), "bytes": len(png),
                    "signatureVerified": True, "widthPixels": dimensions[0], "heightPixels": dimensions[1]},
            "svg": {"path": str(svg_path), "sha256": sha256(svg), "bytes": len(svg),
                    "xmlRootVerified": True, "viewBox": root.get("viewBox")},
        },
    }
    (args.output_dir / "backlog-plot.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"summaryTrials": len(trials), "plottedTrials": len(prepared),
                      "outputDirectory": str(args.output_dir),
                      "pngPixels": list(dimensions), "inputSummarySha256": sha256(summary_bytes)}))


if __name__ == "__main__":
    main()
