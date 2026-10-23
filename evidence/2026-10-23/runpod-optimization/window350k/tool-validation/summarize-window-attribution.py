#!/usr/bin/env python3
"""Reuse frozen attribution rules for the full-350k pilot or W128/W256 matrix.

Usage: summarize-window-attribution.py WINDOW_ROOT OUTPUT_JSON [--cohorts pilot]
Use --cohorts w128,w256 for the registered formal matrix. Missing or incomplete
cohorts are reported as unavailable, never manufactured as measured W256 points.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


EMPTY = "__unused_window_attribution_cohort__"


def digest(path):
    hasher, size = hashlib.sha256(), 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
            size += len(block)
    return {"path": str(path), "sha256": hasher.hexdigest(), "bytes": size}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observer_limits(path, start, end, core, inputs):
    document = core.read_jsonl(path, inputs)
    selected, pairs, metadata, coverage = core.selection(document, start, end, 1.5)
    limits = {"maxThreads": metadata.get("maxThreads"), "maxFds": metadata.get("maxFds"), "detailThreads": metadata.get("detailThreads")}
    roles = sorted({role for sample in selected for role in (sample.get("processes") or {})})
    results = {}
    for role in roles:
        processes = [core.get(sample, "processes", role) for sample in selected]
        verified = [value for value in processes if core.process_identity(value) is not None]
        observations = {}
        for section, count_field, limit_name in (("threads", "enumeratedThreads", "maxThreads"),
                                                ("fdScan", "scannedFds", "maxFds"), ("fdScanAfter", "scannedFds", "maxFds")):
            counts = [core.get(value, section, count_field) for value in verified]
            truncated = [core.get(value, section, "truncated") for value in verified]
            failures = [core.get(value, section, "readFailures") for value in verified]
            known_counts = [value for value in counts if core.counter(value) is not None]
            limit = core.counter(limits[limit_name])
            complete_flags = bool(verified) and all(type(value) is bool for value in truncated)
            observations[section] = {
                "configuredLimit": limit, "countObserved": core.gauge(counts), "readFailures": core.gauge(failures),
                "unknownCountSamples": sum(core.counter(value) is None for value in counts),
                "unknownTruncationSamples": sum(type(value) is not bool for value in truncated),
                "truncatedSamples": sum(value is True for value in truncated),
                "noObservedTruncation": not any(truncated) if complete_flags else None,
                "maximumObservedCountBelowConfiguredCap": max(known_counts) < limit if known_counts and limit is not None else None,
                "allSelectedReadsComplete": all(value == 0 for value in failures) if failures and all(core.counter(value) is not None for value in failures) else None,
            }
        results[role] = {"verifiedProcessSamples": len(verified), "unverifiedProcessSamples": len(processes) - len(verified),
                         "observations": observations}
    return {"path": str(path), "selection": coverage, "configuredLimits": limits,
            "expectedLimitsMatched": limits["maxThreads"] == 1024 and limits["maxFds"] == 4096,
            "processes": results,
            "scope": "Actual selected whole-collection-interior samples, not an assumption from worker count. A bounded scan cannot establish the total beyond its cap; "
                     "missing counts/flags/read metrics remain unavailable. No truncation and no read errors are separate checks. "
                     "Counts below 1024 TIDs/4096 FDs are observed scan coverage, not a future resource-capacity claim."}


def csv_archives(directory, inputs):
    archives = []
    for path in sorted(directory.glob("*.csv.gz")):
        identity = digest(path)
        inputs.append(identity)
        hasher, size = hashlib.sha256(), 0
        with gzip.open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
                size += len(block)
        archives.append({**identity, "uncompressedSha256": hasher.hexdigest(), "uncompressedBytes": size,
                         "gzipReadThroughEndAndCrcVerified": True})
    manifests = []
    for pattern in ("*manifest*.json", "*archive*.json", "*compression*.json"):
        for path in sorted(directory.glob(pattern)):
            if str(path) not in {row["path"] for row in manifests}:
                identity = digest(path)
                inputs.append(identity)
                manifests.append(identity)
    return {"archives": archives, "manifests": manifests,
            "scope": "Attribution computation reads result/observer JSON and needs no restored plaintext CSV. Gzip streams are read through their CRC and independently "
                     "hashed after decompression without writing plaintext. Manifest files retain their own exact hashes; a manifest hash alone is not claimed as a "
                     "semantic comparison to the independently computed raw hash. CSV outcome/latency row audit is separate."}


def summarize(window, cohorts):
    if cohorts not in (("pilot",), ("w128", "w256")):
        raise ValueError("Use pilot only, or the formal w128,w256 pair")
    if (window / EMPTY).exists():
        raise ValueError("Reserved empty cohort sentinel must not exist")
    optimization = window.parent
    source = optimization / "threading/tool-validation/summarize-threading-attribution.py"
    frozen_path = optimization / "threading/analysis/attribution-summary.json"
    frozen = json.loads(frozen_path.read_bytes())
    if frozen.get("scriptSha256") != digest(source)["sha256"]:
        raise ValueError("Frozen threading report and source SHA do not agree")
    threading = load_module("frozen_window_threading_wrapper", source)
    threading.ALIASES = {"isolated": cohorts[0], "shared": cohorts[1] if len(cohorts) == 2 else EMPTY}
    result = threading.summarize(window)
    result["cohorts"].pop(EMPTY, None)
    result["pendingOrUnavailableTrials"] = [value for value in result["pendingOrUnavailableTrials"] if value["cohort"] != EMPTY]
    unavailable = []
    for name in list(result["cohorts"]):
        if result["cohorts"][name]["completedLoadResultTrials"] == 0:
            unavailable.append({"cohort": name, "reason": "no-complete-exported-trial"})
            del result["cohorts"][name]
    core = load_module("frozen_window_attribution_core", optimization / "tool-validation/summarize-attribution.py")
    result["test"] = "full-350k-window-owned-attribution-summary"
    result["reusedThreadingWrapperSha256"] = result.pop("scriptSha256")
    result["scriptSha256"] = digest(Path(__file__))["sha256"]
    result["tools"].update(windowWrapper=digest(Path(__file__)), frozenThreadingWrapper=digest(source), frozenThreadingReport=digest(frozen_path))
    result["requestedCohorts"] = list(cohorts)
    result["unavailableCohorts"] = unavailable
    result["generatedAt"] = datetime.now(timezone.utc).isoformat()
    result["reproduction"] = {"argv": [sys.executable, "-B", str(Path(__file__).resolve()), str(window), "OUTPUT_JSON", "--cohorts", ",".join(cohorts)],
                              "directoryAliasesInMemoryOnly": threading.ALIASES,
                              "scope": "Only the pilot is requested by default. Formal W128/W256 requires the explicit cohort argument; absent/incomplete groups have no manufactured measured point."}
    for cohort, data in result["cohorts"].items():
        for trial in data["trials"]:
            directory = window / cohort / "runs" / trial["id"]
            configuration = directory / "configuration.json"
            config = core.read_json(configuration, result["inputs"]) if configuration.exists() else {}
            load_path = directory / "load-result.json"
            if not load_path.exists():
                load_path = directory / "result.json"
            load = json.loads(load_path.read_bytes())
            workers, per_worker = core.counter(load.get("workers")), core.counter(load.get("queueCapacityPerWorker"))
            expected_workers = 256 if cohort == "w256" else 128
            if workers is not None and workers != expected_workers:
                raise ValueError(f"Cohort worker label mismatch: {trial['id']}")
            trial["workerAndRetentionContext"] = {
                "workers": workers, "queueCapacityPerWorker": per_worker,
                "totalConfiguredFifoSlots": workers * per_worker if workers is not None and per_worker is not None else None,
                "maxSynchronousRequestsInFlight": config.get("maxServiceRequestsInFlight"),
                "profile": config.get("profile"), "stateProfile": config.get("expectedStateProfile"),
                "profileMaximumArrivals": config.get("profileMaximumArrivals"), "profileMaximumWorkers": config.get("profileMaximumWorkers"),
                "declaredCoreLimits": config.get("expectedCoreLimits"),
                "declaredResultCachePerProducer": config.get("expectedResultCachePerProducer"),
                "initialResultCachePerProducer": config.get("initialResultCachePerProducer"),
                "scope": "Worker count also changes aggregate FIFO capacity at fixed per-worker queue size. This is a finite client/concurrency/buffering-path experiment. "
                         "Global cached-result retention remains bounded by the declared 100k profile limit and per-producer retention by 1024 where verified in configuration; "
                         "350k measured commands do not imply retaining every result indefinitely. Configuration fields missing from evidence remain null."}
            start = core.utc(trial["arrivalWindow"]["scheduledOriginUtcApproximate"])
            end = start + trial["arrivalWindow"]["arrivalWindowSeconds"]
            trial["observerCapCoverage"] = [observer_limits(directory / f"node{node}-attribution.jsonl", start, end,
                                                            core, result["inputs"]) for node in range(3)]
            trial["csvArchiveEvidence"] = csv_archives(directory, result["inputs"])
    result["scope"] = (
        "Only the explicitly requested full-350k-profile pilot or formal W128/W256 cohorts are included; no absent W256 capacity is inferred. "
        "A new common node/load artifact, maxsessions256, SHARED node driver, shared client driver and requested receive buffer131072 define this experiment. "
        "It is not merged with the earlier 190k-profile driver, buffer or threading matrices. Frozen whole-collection/identity/socket/CnC/cgroup rules are reused. "
        "Changing workers also changes aggregate FIFO slots, Aeron/client/thread/socket resources and potential cache working set; it is not a pure server-engine optimization. "
        "Read failures/caps/gaps remain explicit. Finite observation is not sustained capacity, monotonic capacity or proof of a unique bottleneck."
    )
    return result


def self_test():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        raw = b"column_a,column_b\n1,2\n"
        (path / "arrivals.csv.gz").write_bytes(gzip.compress(raw, mtime=0))
        (path / "compressed-input-manifest.json").write_text(json.dumps({"rawSha256": hashlib.sha256(raw).hexdigest()}))
        evidence = csv_archives(path, [])
        assert evidence["archives"][0]["uncompressedSha256"] == hashlib.sha256(raw).hexdigest()
        assert evidence["archives"][0]["uncompressedBytes"] == len(raw)
        assert len(evidence["manifests"]) == 1
        assert not (path / "arrivals.csv").exists()
    window = Path(__file__).resolve().parents[1]
    core = load_module("window_cap_selftest_core", window.parent / "tool-validation/summarize-attribution.py")
    start = core.utc("2026-10-23T00:00:00Z")
    process = {"status": "verified", "pid": 41, "startTicks": 1, "commandSha256": "a" * 64,
               "threads": {"enumeratedThreads": 549, "truncated": False, "readFailures": 0},
               "fdScan": {"scannedFds": 600, "truncated": False, "readFailures": 0},
               "fdScanAfter": {"scannedFds": 600, "truncated": False, "readFailures": 0}}
    document = {"status": "read", "parseErrors": [], "rows": [
        {"type": "metadata", "intervalSeconds": 1, "maxThreads": 1024, "maxFds": 4096, "detailThreads": 16},
        {"type": "sample", "sequence": 0, "wallTimeUtc": "2026-10-23T00:00:01Z", "monotonicNs": 1_000_000_000,
         "collectionElapsedNs": 1_000_000, "processes": {"load": process}}]}
    original = core.read_jsonl
    core.read_jsonl = lambda path, inputs: document
    try:
        checked = observer_limits(Path("owned.jsonl"), start, start + 3, core, [])
        threads = checked["processes"]["load"]["observations"]["threads"]
        assert checked["expectedLimitsMatched"] and threads["noObservedTruncation"] is True
        assert threads["maximumObservedCountBelowConfiguredCap"] is True
        process["threads"]["truncated"] = True
        assert observer_limits(Path("owned.jsonl"), start, start + 3, core, [])["processes"]["load"]["observations"]["threads"]["noObservedTruncation"] is False
        process["threads"]["readFailures"] = None
        assert observer_limits(Path("owned.jsonl"), start, start + 3, core, [])["processes"]["load"]["observations"]["threads"]["allSelectedReadsComplete"] is None
    finally:
        core.read_jsonl = original
    print(json.dumps({"status": "PASS", "checks": ["gzip-raw-sha-and-crc", "manifest-discovered-and-hashed", "no-plaintext-restoration",
                      "observed-TID-FD-caps", "truncation-visible", "missing-read-counter-not-zero"]}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("window_root", type=Path, nargs="?")
    parser.add_argument("output_json", type=Path, nargs="?")
    parser.add_argument("--cohorts", default="pilot", choices=("pilot", "w128,w256"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.window_root is None or args.output_json is None:
        parser.error("WINDOW_ROOT and OUTPUT_JSON are required")
    result = summarize(args.window_root, tuple(args.cohorts.split(",")))
    result["reproduction"]["argv"][4] = str(args.output_json)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(args.output_json)
    print(json.dumps({"output": str(args.output_json), "cohorts": {name: data["completedLoadResultTrials"] for name, data in result["cohorts"].items()},
                      "pending": len(result["pendingOrUnavailableTrials"]), "unavailableCohorts": result["unavailableCohorts"], "wrapperSha256": result["scriptSha256"]}))


if __name__ == "__main__":
    main()
