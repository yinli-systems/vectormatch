#!/usr/bin/env python3
"""Measure recorded coordinator phase exposure, not CPU or causal attribution."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct
import tarfile


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            result.update(block)
    return result.hexdigest()


def transitions(body):
    if body[:8] != struct.pack(">Ii", 0x564D5434, 1):
        raise ValueError("unsupported trace header")
    offset, sequence, previous_ns = 8, 0, -1
    phases = []
    while offset < len(body):
        if offset + 24 > len(body):
            raise ValueError("truncated trace frame")
        kind, number, ns, size = struct.unpack_from(">iqqi", body, offset)
        offset += 24
        if (kind not in range(1, 6) or number != sequence + 1 or ns < previous_ns
                or not 0 < size <= 12288 or offset + size > len(body)):
            raise ValueError("invalid trace frame")
        payload = body[offset:offset + size]
        offset += size
        sequence, previous_ns = number, ns
        if kind == 3:
            value = json.loads(payload)
            if "from" in value:
                phases.append((ns, value["from"], value["to"]))
    return phases


def exposure(phases, begin, end, policy):
    if policy not in {"PAUSE", "CONTINUE"} or end <= begin:
        raise ValueError("invalid exposure interval/policy")
    if not phases or phases[0][0] > begin:
        raise ValueError("missing original phase at arrival origin")
    for left, right in zip(phases, phases[1:]):
        if right[0] < left[0] or right[1] != left[2]:
            raise ValueError("phase continuity differs")
    durations = collections.Counter()
    for index, (ns, _, state) in enumerate(phases):
        next_ns = phases[index + 1][0] if index + 1 < len(phases) else end
        overlap = max(0, min(end, next_ns) - max(begin, ns))
        if overlap:
            durations[state] += overlap
    if sum(durations.values()) != end - begin:
        raise ValueError("phase coverage differs from complete arrival interval")
    if durations.get("READ_YIELD", 0) or durations.get("READ_DRAIN", 0):
        raise ValueError("this analysis requires the registered closed read-bank control")
    allowed = {"IDLE"} | ({"VERIFY_WAIT", "FILE_WAIT"} if policy == "CONTINUE" else set())
    permit = sum(n for state, n in durations.items() if state in allowed)
    return {"windowNs": end - begin, "phaseNs": dict(sorted(durations.items())),
            "phaseAllowsNewBusinessNs": permit,
            "phaseDisallowsNewBusinessNs": end - begin - permit,
            "readPhaseNs": sum(durations.get(s, 0) for s in ["ARCHIVE_READ", "EVENT_READ"]),
            "verificationAndFileWaitNs": sum(durations.get(s, 0) for s in ["VERIFY_WAIT", "FILE_WAIT"]),
            "scope": "Recorded coordinator state exposure. A permitted phase can still wait for credits or an exact cut. These are not CPU busy time, I/O service time or per-request waiting attribution."}


def analyse(archive, expected_sha, output):
    if sha(archive) != expected_sha:
        raise ValueError("archive SHA-256 differs from private receipt")
    wanted = {"native/load/maintenance-v4.bin", "native/load/configuration.json",
              "native/load/load-result.json", "MEMBER_MANIFEST.json"}
    bodies = {}
    with tarfile.open(archive, "r|gz") as stream:
        for member in stream:
            if member.name not in wanted:
                continue
            if member.name in bodies or not member.isfile() or member.size > 512 * 1024**2:
                raise ValueError("invalid/duplicate input member")
            body = stream.extractfile(member).read()
            if len(body) != member.size:
                raise ValueError("truncated member")
            bodies[member.name] = body
    if set(bodies) != wanted:
        raise ValueError("missing original trace/configuration")
    manifest = json.loads(bodies["MEMBER_MANIFEST.json"])["files"]
    for name, body in bodies.items():
        if name != "MEMBER_MANIFEST.json":
            item = manifest[name]
            if len(body) != item["bytes"] or hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise ValueError("member bytes differ: " + name)
    config = json.loads(bodies["native/load/configuration.json"])
    summary = json.loads(bodies["native/load/load-result.json"])
    if config["fileWorkDispatchPolicy"] != summary["fileWorkDispatchPolicy"]:
        raise ValueError("policy mismatch")
    begin = config["scheduledOriginMonotonicNs"]
    result = exposure(transitions(bodies["native/load/maintenance-v4.bin"]), begin,
                      begin + 20_000_000_000, config["fileWorkDispatchPolicy"])
    result.update(archiveSha256=expected_sha, policy=config["fileWorkDispatchPolicy"],
                  ratePerSecond=config["ratePerSecond"],
                  traceSha256=manifest["native/load/maintenance-v4.bin"]["sha256"],
                  analyserSha256=sha(__file__))
    with Path(output).open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(analyse(args.archive, args.sha256, args.output)))
