#!/usr/bin/env python3
"""Conservatively verify fixed leader/term from official members output and CnC samples.

Read-only inputs. The derived fixed-leader-check.json can be regenerated. Aeron
1.53.3 mappings are from AeronCounters, ConsensusModule.State, Cluster.Role and
ConsensusModule's ClusterCounters.allocate labels. Sampled observations cannot
exclude transitions wholly between samples; unchanged leadership term plus
before/after official member views strengthen that limited observation.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone


# Official Aeron 1.53.3: io.aeron.AeronCounters and io.aeron.cluster enums.
COUNTERS = {
    "moduleState": (200, "Consensus Module state - clusterId=0"),
    "role": (201, "Cluster node role - clusterId=0"),
    "term": (239, "Cluster leadership term id - clusterId=0"),
}
OPTIONAL = {
    "electionState": (207, "Cluster election state - clusterId=0"),
    "electionCount": (238, "Cluster election count - clusterId=0"),
}
FOLLOWER, LEADER, ACTIVE, ELECTION_CLOSED = 0, 2, 1, 17


def integer(value):
    return type(value) is int


def members(path: Path, errors: list[str]) -> int | None:
    try:
        document = json.loads(path.read_text())
        if not isinstance(document, dict) or not isinstance(document.get("stdout"), str):
            raise ValueError("expected an object with official list-members stdout")
        for key in ("exit_code", "exitCode", "returncode"):
            if key in document and document[key] != 0:
                raise ValueError(f"official list-members returned nonzero {key}")
        output = document["stdout"]
        leader = re.search(r"\bleaderMemberId=(-?\d+)\b", output)
        if leader is None or int(leader.group(1)) != 0:
            raise ValueError("official leaderMemberId must be 0")
        active = re.search(r"\bactiveMembers=\[(.*)\]\s*$", output, re.DOTALL)
        if active is None:
            raise ValueError("official activeMembers list missing")
        entries = re.findall(r"ClusterMember\{([^}]*)\}", active.group(1))
        terms, ids = set(), set()
        for entry in entries:
            member = re.search(r"(?:^|,\s*)id=(\d+)(?:,|$)", entry)
            term = re.search(r"\bleadershipTermId=(-?\d+)(?:,|$)", entry)
            is_leader = re.search(r"\bisLeader=(true|false)(?:,|$)", entry)
            if member is None or term is None or is_leader is None:
                raise ValueError("member entry is missing id, term or leader role")
            node = int(member.group(1))
            if node in ids:
                raise ValueError("duplicate member id")
            ids.add(node)
            value = int(term.group(1))
            if value < 0:
                raise ValueError("member leadership term is not initialized")
            terms.add(value)
            if (is_leader.group(1) == "true") != (node == 0):
                raise ValueError(f"member {node} has unexpected leader role")
        if ids != {0, 1, 2} or len(terms) != 1:
            raise ValueError("expected exactly members 0,1,2 with one leadership term")
        return next(iter(terms))
    except (OSError, ValueError, TypeError) as failure:
        errors.append(f"{path.name}: {failure}")
        return None


def read_counter(sample: dict, name: str, spec: tuple[int, str], errors: list[str], context: str,
                 required: bool = True) -> dict | None:
    counters = sample.get("counters")
    if not isinstance(counters, list):
        errors.append(f"{context}: counters must be an array")
        return None
    matches = [counter for counter in counters if isinstance(counter, dict)
               and counter.get("typeId") == spec[0] and counter.get("label") == spec[1]]
    if len(matches) != 1:
        if required or matches:
            errors.append(f"{context}: expected one {name} counter type={spec[0]} label={spec[1]!r}, found {len(matches)}")
        return None
    counter = matches[0]
    if not integer(counter.get("counterId")) or not integer(counter.get("value")):
        errors.append(f"{context}: {name} counter ID/value must be integers")
        return None
    return counter


def node_observations(path: Path, node: int, expected_term: int | None, errors: list[str]) -> dict:
    observed = {name: set() for name in (*COUNTERS, *OPTIONAL)}
    identities = {name: set() for name in COUNTERS}
    samples = 0
    metadata = complete = None
    last_elapsed = -1
    try:
        with path.open() as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("JSON line must be an object")
                    kind = row.get("kind")
                    context = f"{path.name}:{line_number}"
                    if kind == "metadata":
                        if metadata is not None or line_number != 1:
                            errors.append(f"{context}: metadata must occur exactly once at the start")
                        metadata = row
                        if row.get("readOnlyMapping") is not True:
                            errors.append(f"{context}: collector did not declare read-only mapping")
                    elif kind == "complete":
                        if complete is not None:
                            errors.append(f"{context}: duplicate completion record")
                        complete = row
                    elif kind == "failure":
                        errors.append(f"{context}: collector failure: {row.get('errorType')}: {row.get('error')}")
                    elif kind == "sample":
                        if complete is not None:
                            errors.append(f"{context}: sample appears after completion")
                        if row.get("sample") != samples:
                            errors.append(f"{context}: missing or reordered sample index")
                        elapsed = row.get("elapsedNanos")
                        if not integer(elapsed) or elapsed <= last_elapsed:
                            errors.append(f"{context}: sample elapsed time is missing or non-monotonic")
                        else:
                            last_elapsed = elapsed
                        samples += 1
                        for name, spec in (*COUNTERS.items(), *OPTIONAL.items()):
                            counter = read_counter(row, name, spec, errors, context, name in COUNTERS)
                            if counter is None:
                                continue
                            value = counter["value"]
                            observed[name].add(value)
                            if name in identities:
                                identities[name].add((counter["counterId"], counter.get("registrationId")))
                            expected = {"moduleState": ACTIVE, "role": LEADER if node == 0 else FOLLOWER,
                                        "term": expected_term, "electionState": ELECTION_CLOSED}.get(name)
                            if expected is not None and value != expected:
                                errors.append(f"{context}: {name}={value}, expected {expected}")
                    else:
                        errors.append(f"{context}: unknown collector record kind {kind!r}")
                except (ValueError, TypeError) as failure:
                    errors.append(f"{path.name}:{line_number}: {failure}")
    except OSError as failure:
        errors.append(f"{path.name}: {failure}")
    if metadata is None:
        errors.append(f"{path.name}: missing collector metadata")
    if complete is None:
        errors.append(f"{path.name}: missing completion record; collection may be truncated")
    elif complete.get("samples") != samples:
        errors.append(f"{path.name}: completion sample count differs")
    if samples < 2:
        errors.append(f"{path.name}: at least two complete samples are required")
    if len(observed["term"]) != 1:
        errors.append(f"{path.name}: expected one observed leadership term, found {sorted(observed['term'])}")
    for name, values in identities.items():
        if len(values) > 1:
            errors.append(f"{path.name}: {name} counter identity changed during observation")
    if len(observed["electionCount"]) > 1:
        errors.append(f"{path.name}: election count changed during observation")
    return {"node": node, "samples": samples, "complete": complete is not None,
            "observedTerms": sorted(observed["term"]), "observedRoles": sorted(observed["role"]),
            "observedConsensusModuleStates": sorted(observed["moduleState"]),
            "observedElectionStates": sorted(observed["electionState"]),
            "observedElectionCounts": sorted(observed["electionCount"])}


def check_trial(directory: Path) -> dict:
    errors: list[str] = []
    before = members(directory / "pre-members.json", errors)
    after = members(directory / "post-members.json", errors)
    if before is not None and after is not None and before != after:
        errors.append(f"leadership term changed: pre={before}, post={after}")
    nodes = [node_observations(directory / f"node{node}-counters.jsonl", node, before, errors)
             for node in range(3)]
    terms = sorted({term for node in nodes for term in node["observedTerms"]})
    if before is not None and terms != [before]:
        errors.append(f"observed terms {terms} differ from official pre term {before}")
    return {"test": "capacity-fixed-leader-check", "checkedAt": datetime.now(timezone.utc).isoformat(),
            "aeronVersion": "1.53.3", "expectedLeader": 0, "clusterId": 0,
            "passed": not errors, "verified": not errors,
            "preTerm": before, "postTerm": after, "observedTerms": terms,
            "observedRoles": {str(node["node"]): node["observedRoles"] for node in nodes},
            "nodes": nodes, "errors": errors,
            "scope": "All recorded CnC samples plus official pre/post list-members views; requires complete collector files from the pre-ready point through post-measurement. This checker cannot infer missing time coverage or exclude unobserved transitions between samples. Source type/label mappings are fixed to Aeron 1.53.3 clusterId=0."}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("Usage: check-capacity-leader.py TRIAL_DIR")
    directory = Path(args[0]).resolve()
    if not directory.is_dir():
        raise SystemExit("TRIAL_DIR must be an existing directory")
    result = check_trial(directory)
    target = directory / "fixed-leader-check.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(target)
    print(json.dumps({key: result[key] for key in ("passed", "preTerm", "postTerm", "observedTerms", "observedRoles", "errors")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
