#!/usr/bin/env python3
"""Exact service-call percentiles from bounded V4 pack frames; this is not an arrival-latency audit.

Business replay is performed by AnchoredContinuityRunV4.audit. This separate reader
checks every frame digest and sample sequence, and ignores CSV/summary percentiles.
"""
import collections
import gzip
import hashlib
import io
import json
import math
import struct
import sys
import tarfile
import zlib
from pathlib import Path

MAX_FRAME = 32 * 1024 * 1024
MAX_DISTINCT_DURATIONS = 1_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(stream, count):
    data = stream.read(count)
    require(len(data) == count, "truncated proof")
    return data


def integer(stream, size=4):
    return struct.unpack(">i" if size == 4 else ">q", exact(stream, size))[0]


def blob(stream):
    size = integer(stream)
    require(0 <= size <= MAX_FRAME, "blob bound")
    return exact(stream, size)


def ascii_utf(stream):
    size = struct.unpack(">H", exact(stream, 2))[0]
    value = exact(stream, size)
    require(all(c < 128 for c in value), "expected bounded ASCII metadata")
    return value.decode("ascii")


def quantiles(histogram):
    total = sum(histogram.values())
    require(total > 0, "no fresh order samples")
    thresholds = {"p50Ns": math.ceil(total * .5), "p99Ns": math.ceil(total * .99),
                  "p999Ns": math.ceil(total * .999)}
    result = {"samples": total, "maximumNs": max(histogram)}
    cumulative = 0
    for duration, count in sorted(histogram.items()):
        cumulative += count
        for key, threshold in thresholds.items():
            if key not in result and cumulative >= threshold:
                result[key] = duration
    return result


def read_pack(stream):
    require(exact(stream, 8) == struct.pack(">ii", 0x564D5034, 1), "pack envelope")
    histogram = collections.Counter()
    first = previous = None
    frames = 0
    stage = 1
    lineage = parent = initial_hash = final_hash = None
    while True:
        header = stream.read(44)
        if not header:
            break
        require(len(header) == 44, "truncated frame header")
        kind, raw_size, compressed_size = struct.unpack(">iii", header[:12])
        require(0 <= raw_size <= MAX_FRAME and 0 < compressed_size <= MAX_FRAME + 65536, "frame bound")
        compressed = exact(stream, compressed_size)
        decoder = zlib.decompressobj(31)
        raw = decoder.decompress(compressed, raw_size + 1)
        require(len(raw) == raw_size and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                "gzip envelope/length differs")
        require(hashlib.sha256(raw).digest() == header[12:], "frame digest differs")
        frames += 1
        data = io.BytesIO(raw)
        if kind == 1:
            require(stage == 1 and frames == 1, "start order")
            lineage = ascii_utf(data); profile = ascii_utf(data); parent = ascii_utf(data)
            require(len(profile) == 64 and len(parent) == 64, "hash metadata")
            target = integer(data, 8); initial_hash = hashlib.sha256(blob(data)).hexdigest()
            require(1 <= target <= 100_000_000, "cumulative target")
            stage = 2
        elif kind == 2:
            require(stage == 2, "business stage")
            cut = integer(data, 8)
            require(cut > 0, "cut counter")
            for _ in range(3):
                blob(data)  # ACK envelope, canonical business archive and raw outbox.
            count = integer(data)
            require(1 <= count <= 1536, "sample count")
            for _ in range(count):
                command = integer(data, 8); duration = integer(data, 8)
                require(command > 0 and duration >= 0, "invalid sample")
                require(previous is None or command == previous + 1, "sample sequence gap/duplicate")
                if first is None:
                    first = command
                previous = command
                if command >= 3:  # Commands 1 and 2 are deposits, not accepted orders.
                    histogram[duration] += 1
                    require(len(histogram) <= MAX_DISTINCT_DURATIONS, "exact histogram distinct-value budget exceeded")
            stage = 3
        elif kind == 3:
            require(stage == 3, "journal stage"); stage = 4
            data.seek(len(raw))  # Full journal projection is independently replayed by Java.
        elif kind == 4:
            require(stage == 4, "checkpoint stage")
            integer(data, 8); blob(data)
            for _ in range(10):
                require(integer(data, 8) >= -1, "invalid native metric")
            stage = 2
        elif kind == 5:
            require(stage == 2 and previous == target + 2, "incomplete cumulative target")
            final_hash = hashlib.sha256(blob(data)).hexdigest()
            require(integer(data, 8) >= 0, "invalid duration")
            stage = 6
        else:
            raise ValueError("unknown frame")
        require(not data.read(1), "trailing payload bytes")
    require(stage == 6 and first is not None, "missing complete end frame")
    return dict(lineage=lineage, parentPackSha256=parent, initialSnapshotSha256=initial_hash,
                finalSnapshotSha256=final_hash, firstCommand=first, lastCommand=previous,
                acceptedTotal=target, frames=frames, **quantiles(histogram)), histogram


def archive_samples(path, output):
    observations = []
    combined = collections.Counter()
    with tarfile.open(path, "r|gz") as archive:
        for member in archive:
            if member.isfile() and member.name.endswith("/raw.pack"):
                observation, histogram = read_pack(archive.extractfile(member))
                observation["member"] = member.name; observations.append(observation)
                combined.update(histogram)
                require(len(combined) <= MAX_DISTINCT_DURATIONS, "combined exact histogram budget")
    require(observations, "no raw packs")
    result = {"schema": "anchored-exact-service-samples-1", "metric": "closed_loop_service_call_excluding_maintenance_and_network",
              "replicated": False, "allArrivalLatencyProven": False,
              "packs": observations, "freshOrderSamples": quantiles(combined)}
    output = Path(output); output.mkdir(exist_ok=True)
    (output / "EXACT_SERVICE_SAMPLES.json").write_text(json.dumps(result, indent=2) + "\n")
    with gzip.open(output / "exact-service-frequency.csv.gz", "wt") as stream:
        stream.write("duration_ns,count\n")
        for duration, count in sorted(combined.items()):
            stream.write(f"{duration},{count}\n")
    return result


if __name__ == "__main__":
    result = archive_samples(sys.argv[1], sys.argv[2])
    print(json.dumps(result))
