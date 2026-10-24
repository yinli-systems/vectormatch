#!/usr/bin/env python3
"""Independently remeasure the four original read8/read32 native ABAB runs.

Reads one .tar.zst sequentially without extracting or trusting reported summary
percentiles. Missing, duplicated, rejected or incomplete evidence fails closed.
This is a performance/protocol audit, not an independent matching-engine oracle.
"""

import argparse
import csv
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tarfile


ARMS = {"A1": 8, "B1": 32, "A2": 8, "B2": 32}
PREFIX = "vectormatch-read32-r1"
CSV_LIMIT = 24 * 1024 * 1024
OTHER_LIMIT = 2 * 1024 * 1024
REQUIRED_COLUMNS = ("arrival_index", "scheduled_offset_ns", "arrival_offset_ns",
                    "reply_completion_offset_ns", "status", "result_code", "order_id")


def paths(cycles):
    output = {}
    for arm in ARMS:
        base = f"{PREFIX}/{arm}"
        output[f"{base}/load/arrivals.csv"] = (arm, "arrivals")
        for filename, key in (("load/load-result.json", "load"), ("completion.json", "completion"),
                              ("physical-reference-reconciliation.json", "reference")):
            output[f"{base}/{filename}"] = (arm, key)
        for cycle in range(1, cycles + 1):
            output[f"{base}/load/maintenance/cycle-{cycle}.verified.txt"] = (arm, f"cycle{cycle}")
    return output


def select_tar_members(archive, expected):
    """Bounded, duplicate-refusing extraction from an already-open TAR stream."""
    matched = {}
    for member in archive:
        if member.name not in expected:
            continue
        if member.name in matched:
            raise ValueError("duplicate archive member " + member.name)
        limit = CSV_LIMIT if member.name.endswith("/arrivals.csv") else OTHER_LIMIT
        if not member.isfile() or not 0 < member.size <= limit:
            raise ValueError("invalid or oversized evidence member " + member.name)
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError("evidence member cannot be read " + member.name)
        data = stream.read(limit + 1)
        if len(data) != member.size:
            raise ValueError("truncated evidence member " + member.name)
        matched[member.name] = data
    absent = set(expected) - set(matched)
    if absent:
        raise ValueError("missing " + str(len(absent)) + " required members: " + sorted(absent)[0])
    return {arm: {key: matched[filename] for filename, (a, key) in expected.items() if a == arm}
            for arm in ARMS}


def open_zstd_tar(path, expected):
    # Stream the archive rather than extracting its very large Aeron files.
    process = subprocess.Popen(["zstd", "-dc", "--", str(path)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            result = select_tar_members(archive, expected)
        process.stdout.close()
        error = process.stderr.read(8192)
        if process.wait() != 0:
            raise ValueError("archive decompression failed: " + error.decode("utf-8", "replace"))
        return result
    except BaseException:
        process.kill() if process.poll() is None else None
        process.communicate()
        raise
    finally:
        process.stderr.close()


def parse_arrivals(source, expected_count, interval_ns):
    reader = csv.DictReader(io.StringIO(source.decode("utf-8"), newline=""))
    if reader.fieldnames is None or any(key not in reader.fieldnames for key in REQUIRED_COLUMNS):
        raise ValueError("arrival CSV lacks mandatory columns")
    by_id = set()
    order_ids = set()
    latencies = []
    for row in reader:
        if any(value is None for value in row.values()):
            raise ValueError("arrival row has missing fields")
        index = int(row["arrival_index"])
        if not 0 <= index < expected_count or index in by_id:
            raise ValueError("duplicate or out-of-range arrival index")
        by_id.add(index)
        if row["status"] != "APPLIED" or row["result_code"] != "ACCEPTED":
            raise ValueError("arrival did not confirm ACCEPTED")
        order_id = int(row["order_id"])
        if order_id <= 0 or order_id in order_ids:
            raise ValueError("duplicate or missing accepted order identity")
        order_ids.add(order_id)
        scheduled = int(row["scheduled_offset_ns"])
        actual = int(row["arrival_offset_ns"])
        received = int(row["reply_completion_offset_ns"])
        if scheduled != index * interval_ns or received < actual or actual < scheduled:
            raise ValueError("arrival timing/schedule is inconsistent")
        if actual - scheduled > 20_000_000:
            raise ValueError("scheduler missed the 20ms validity gate")
        latencies.append(received - scheduled)
    if len(by_id) != expected_count:
        raise ValueError("missing arrivals; all-arrival latency undefined")
    latencies.sort()
    return {"arrivals": expected_count,
            "p50Ns": latencies[math.ceil(expected_count * .50) - 1],
            "p95Ns": latencies[math.ceil(expected_count * .95) - 1],
            "p99Ns": latencies[math.ceil(expected_count * .99) - 1]}


def parse_cycles(source, width, expected_cycles):
    count = 0
    wall_ns = 0
    for number in range(1, expected_cycles + 1):
        values = {}
        for line in source[f"cycle{number}"].decode("utf-8").splitlines():
            if "=" not in line:
                raise ValueError("invalid cycle field")
            key, value = line.split("=", 1)
            if key in values:
                raise ValueError("duplicate cycle field")
            values[key] = value
        start = int(values["cycleStartedMonotonicNs"])
        end = int(values["cycleEndedMonotonicNs"])
        if (int(values["cycle"]) != number or int(values["readWindow"]) != width
                or int(values["archiveChunkBytes"]) != 6144 or int(values["eventFetchCount"]) != 32
                or values["forceAndReadbackBeforeBothAcks"] != "true" or end <= start):
            raise ValueError("cycle metadata does not match the predeclared fixed experiment")
        count += 1
        wall_ns += end - start
    return {"cycles": count, "maintenanceWallNs": wall_ns}


def analyze(source, expected_count=33792, interval_ns=2_000_000, cycles=12):
    rows = {}
    for arm, width in ARMS.items():
        files = source[arm]
        arrival = parse_arrivals(files["arrivals"], expected_count, interval_ns)
        timing = parse_cycles(files, width, cycles)
        load = json.loads(files["load"])
        complete = json.loads(files["completion"])
        reference = json.loads(files["reference"])
        if (load.get("scheduledArrivals") != expected_count
                or load.get("confirmedAcceptedUniqueOrders") != expected_count
                or load.get("allArrivalP99Ns") != arrival["p99Ns"]
                or load.get("notSent") != 0 or load.get("unknownFinal") != 0
                or load.get("schedulerLatenessOver20ms") != 0
                or load.get("maintenanceCycles") != cycles
                or load.get("readWindow") != width
                or load.get("maintenanceRpcMetrics", {}).get("logicalRpcCount") != 4738
                or load.get("maintenanceRpcMetrics", {}).get("failed") is not False
                or load.get("maintenanceRpcMetrics", {}).get("completedCycles") != cycles):
            raise ValueError("load receipt mismatches recomputed exact fixed-workload values: " + arm)
        if (complete.get("passed") is not True or complete.get("allOwnedStopped") is not True
                or complete.get("readWindow") != width or complete.get("capacityOrEnduranceProven") is not False
                or complete.get("independentHosts") is not False
                or complete.get("commonReadWindow32Envelope") is not True
                or reference.get("passed") is not True):
            raise ValueError("completion or reference reconciliation failed: " + arm)
        rows[arm] = {"credit": width, **arrival, **timing}

    def mean(field, arms):
        return sum(rows[arm][field] for arm in arms) / len(arms)

    def reduction(first, second):
        return (second / first - 1) * 100

    baseline_p99, treatment_p99 = mean("p99Ns", ("A1", "A2")), mean("p99Ns", ("B1", "B2"))
    baseline_wall, treatment_wall = mean("maintenanceWallNs", ("A1", "A2")), mean("maintenanceWallNs", ("B1", "B2"))
    return {"schema": "vectormatch.read-window-abab-independent-audit.v1", "passed": True,
            "source": "recomputed original all-arrival CSV and cycle timing; reports verified but not trusted for quantiles",
            "scope": "same-host tmpfs; two unrandomized pairs; no independent economic oracle or SSD claim",
            "arms": rows,
            "pairedP99ChangePercent": [reduction(rows[a]["p99Ns"], rows[b]["p99Ns"]) for a, b in (("A1", "B1"), ("A2", "B2"))],
            "descriptiveMeans": {"read8P99Ms": baseline_p99 / 1e6, "read32P99Ms": treatment_p99 / 1e6,
                                 "p99ChangePercent": reduction(baseline_p99, treatment_p99),
                                 "read8MaintenanceSeconds": baseline_wall / 1e9,
                                 "read32MaintenanceSeconds": treatment_wall / 1e9,
                                 "maintenanceChangePercent": reduction(baseline_wall, treatment_wall)}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Unmodified four-arm native .tar.zst archive")
    parser.add_argument("--expected-arrivals", type=int, default=33792)
    parser.add_argument("--interval-ns", type=int, default=2_000_000)
    parser.add_argument("--cycles", type=int, default=12)
    args = parser.parse_args(argv)
    if not 0 < args.expected_arrivals <= 1_000_000 or not 0 < args.cycles <= 64 or args.interval_ns <= 0:
        parser.error("invalid bounded plan")
    try:
        report = analyze(open_zstd_tar(args.archive, paths(args.cycles)), args.expected_arrivals,
                         args.interval_ns, args.cycles)
    except (OSError, ValueError, KeyError, UnicodeError, tarfile.TarError, subprocess.SubprocessError) as error:
        print(json.dumps({"passed": False, "errorType": type(error).__name__, "error": str(error)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
