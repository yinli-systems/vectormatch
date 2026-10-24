#!/usr/bin/env python3
"""Independently stream every original NAK arrival; never rewrite benchmark inputs.

Run on the repository checkout with --require-local-raw for the original audit.
A fresh clone can omit that flag and verify decoded bytes against both the gzip
manifest and immutable analyzer input digest without restoring the ignored CSV.
No SSH, command submission, frozen analyzer invocation or failure relabeling.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from datetime import datetime, timezone

MAX_BYTES = 256 * 1024 * 1024
HEADER = "index,worker,account_id,producer_id,request_seq,client_order_id,planned_offset_ns,enqueued_offset_ns,execute_started_offset_ns,initial_attempt_end_offset_ns,confirmed_offset_ns,ended_offset_ns,scheduler_lateness_ns,queue_delay_ns,initial_execute_rtt_ns,execute_through_resolution_ns,scheduled_to_confirmed_ns,missed_dispatch_deadline,outcome,attempts,unknown_at_initial_deadline,initial_leader,final_leader,result_code,result_reason,order_id,trade_count,replayed,result_command_seq,reply_command_seq,event_seq,market_seq,error".split(",")
GUARD = "Confirmed-only replay skipped: {count} UNKNOWN_UNRESOLVED identities may already have executed; canonical validation is incomplete. Preserve the original identities for same-key recovery; no core business mismatch is established."


def check(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def digest(stream):
    size, sha = 0, hashlib.sha256()
    with stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            check(size <= MAX_BYTES, "File/decoded size exceeds fixed audit bound")
            sha.update(block)
    return {"bytes": size, "sha256": sha.hexdigest()}


def p99(values):
    return sorted(values)[math.ceil(len(values) * .99) - 1] / 1e6 if values else None


def audit(root, task, plan, require_raw):
    directory = root / task["cohort"] / "runs" / task["id"]
    config, trial = read(directory / "configuration.json"), read(directory / "trial.json")
    load, manifest = read(directory / "load-result.json"), read(directory / "arrivals-archive.json")
    summary = read(directory.parent.parent / "analysis/summary.json")
    summary = next(row for row in summary["trials"] if row["id"] == task["id"])
    offered, rate, workers = task["arrivals"], task["rate"], task["workers"]
    check(offered == 350000 and workers == 256 and rate in (10000, 26000), "Unexpected registered NAK fixture")
    check((config["scheduledArrivals"], config["workers"], config["ratePerSecond"]) == (offered, workers, rate), "Workload differs from registration")
    window = offered * 10**9 // rate
    compressed = digest((directory / "arrivals.csv.gz").open("rb"))
    decoded = digest(gzip.open(directory / "arrivals.csv.gz", "rb"))
    check(compressed == {"bytes": manifest["compressedBytes"], "sha256": manifest["compressedSha256"]}, "Compressed manifest mismatch")
    check(decoded == {"bytes": manifest["rawBytes"], "sha256": manifest["rawSha256"]}, "Decoded manifest mismatch")
    check(summary["inputSha256"]["arrivals.csv"] == decoded["sha256"], "Frozen analyzer input digest mismatch")
    raw_path = directory / "arrivals.csv"
    check(not require_raw or raw_path.exists(), "Original local CSV required")
    original = digest(raw_path.open("rb")) if raw_path.exists() else None
    check(original is None or original == decoded, "Original local CSV differs from gzip")
    counters, identities, sequences = collections.Counter(), set(), set()
    latencies, api_all, api_known, queue_latencies = [], [], [], []
    per_worker = [collections.Counter() for _ in range(workers)]
    initial_unknown = resolved = within = 0
    with gzip.open(directory / "arrivals.csv.gz", "rt", newline="") as stream:
        rows = csv.DictReader(stream)
        check(rows.fieldnames == HEADER, "Original 33-column schema differs")
        for index, row in enumerate(rows):
            check(None not in row and all(value is not None for value in row.values()), "Missing/extra column")
            worker = index % workers
            key = (int(row["account_id"]), row["producer_id"], int(row["request_seq"]))
            check(int(row["index"]) == index and int(row["worker"]) == worker, "Index/worker changed")
            check(key == (1000100 + worker % 64, config["producerPrefix"] + "-w" + str(worker), index // workers + 1), "Business identity changed")
            check(row["client_order_id"] == "ioc-" + config["producerPrefix"] + "-" + str(index), "Client order identity changed")
            check(int(row["planned_offset_ns"]) == index * 10**9 // rate, "Planned arrival changed")
            check(key not in identities, "Duplicate offered identity")
            identities.add(key)
            outcome = row["outcome"]
            counters[outcome] += 1
            stats = per_worker[worker]
            stats[outcome] += 1
            check(row["unknown_at_initial_deadline"] in ("true", "false"), "Invalid unknown flag")
            unknown = row["unknown_at_initial_deadline"] == "true"
            initial_unknown += unknown
            if row["execute_started_offset_ns"]:
                start, initial_end, end = (int(row[name]) for name in ("execute_started_offset_ns", "initial_attempt_end_offset_ns", "ended_offset_ns"))
                check(0 <= start <= initial_end <= end, "Execution timestamp ordering differs")
                check(int(row["initial_execute_rtt_ns"]) == initial_end - start, "Initial API duration differs")
                api_all.append(initial_end - start)
                stats["occupiedNs"] += max(0, min(window, end) - max(0, start))
            if outcome == "CONFIRMED_ACCEPTED":
                check(row["result_code"] == "ACCEPTED" and row["trade_count"] == "1", "Accepted response shape differs")
                check(row["initial_leader"] == row["final_leader"] == "0", "Client observed leader changed")
                confirmed = int(row["confirmed_offset_ns"])
                check(confirmed == end and confirmed >= initial_end, "Confirmation ordering differs")
                check(int(row["scheduled_to_confirmed_ns"]) == confirmed - int(row["planned_offset_ns"]), "End-to-end duration differs")
                sequence = int(row["result_command_seq"])
                check(sequence not in sequences, "Distinct identities share a business result sequence")
                sequences.add(sequence)
                within += confirmed <= window
                resolved += unknown
                latencies.append(int(row["scheduled_to_confirmed_ns"]))
                api_known.append(int(row["initial_execute_rtt_ns"]))
                queue_latencies.append(int(row["queue_delay_ns"]))
                stats["rttNs"] += int(row["initial_execute_rtt_ns"])
            elif outcome == "UNKNOWN_UNRESOLVED":
                check(unknown and int(row["attempts"]) > 0 and row["confirmed_offset_ns"] == "", "Invalid unresolved row")
            else:
                check(outcome in ("CLIENT_QUEUE_FULL_NOT_SENT", "WORKER_BLOCKED_UNKNOWN_NOT_SENT"), "Unexpected outcome retained for review")
                check(row["attempts"] == "0" and row["execute_started_offset_ns"] == row["confirmed_offset_ns"] == row["scheduled_to_confirmed_ns"] == "", "Unsent request given invented execution/latency")
    check(len(identities) == offered and sum(counters.values()) == offered, "Arrival omitted")
    accepted, unresolved = counters["CONFIRMED_ACCEPTED"], counters["UNKNOWN_UNRESOLVED"]
    check(initial_unknown == resolved + unresolved, "Unknown accounting mismatch")
    check(accepted == load["confirmedAcceptedCommands"] and within == load["confirmedWithinArrivalWindow"], "Reported confirmation counts differ")
    check(initial_unknown == load["unknownAtInitialDeadline"] and unresolved == load["unresolvedFinal"] and resolved == load["resolvedAfterInitialUnknown"], "Reported unknown counts differ")
    not_sent = counters["CLIENT_QUEUE_FULL_NOT_SENT"] + counters["WORKER_BLOCKED_UNKNOWN_NOT_SENT"]
    check(not_sent == load["clientNotSentCommands"] and counters["CLIENT_QUEUE_FULL_NOT_SENT"] == load["clientQueueFullNotSent"] and counters["WORKER_BLOCKED_UNKNOWN_NOT_SENT"] == load["workerBlockedUnknownNotSent"], "Reported not-sent counts differ")
    check(math.isclose(p99(latencies), load["acceptedScheduledToConfirmedMicroseconds"]["p99"] / 1000, abs_tol=1e-8), "Conditional p99 differs")
    check(math.isclose(within * 1e9 / window, load["confirmedWithinArrivalWindowPerSecond"], abs_tol=1e-8), "Window goodput differs")
    check(not_sent == 0 and unresolved == 0 or load["allOfferedAcceptedP99Microseconds"] is None, "All-offered p99 invented")
    configuration_receipt = read(directory / "configuration-verification.json")
    check(configuration_receipt["passed"] is True, "Configuration attestation failed")
    for name, expected in configuration_receipt["rawSha256"].items():
        check(Path(name).name == name or name.startswith(("node0/", "node1/", "node2/")), "Unexpected config evidence path")
        check(digest((directory / name).open("rb"))["sha256"] == expected, "Configuration input digest differs: " + name)
    delay = task["nakDelayNs"]
    check(config["clientNakUnicastDelayNs"] == delay and config["clientNakUnicastRetryDelayRatio"] == 100, "Actual client NAK context differs")
    check(trial["loadGeneratorJvmArguments"] == ["-Dvectormatch.capacity.client.driver=shared", "-Daeron.nak.unicast.delay=" + str(delay)], "Load NAK flag differs")
    check(trial["deploymentRevision"] == trial["loadGeneratorRevision"] == plan["node"]["revision"] == plan["load"]["revision"], "Node/load source mixed")
    check(trial["deploymentBundleSha256"] == trial["loadGeneratorBundleSha256"] == plan["node"]["bundleSha256"] == plan["load"]["bundleSha256"], "Node/load artifact mixed")
    check(trial["release"] == trial["loadGeneratorRelease"] == plan["node"]["root"], "Release differs")
    for node in range(3):
        arguments = read(directory / f"node{node}/process.json")["arguments"]
        check([arg for arg in arguments if "aeron.nak" in arg] == ["-Daeron.nak.unicast.delay=" + str(delay)], "Actual node NAK flag differs")
        check(arguments[arguments.index("-cp") + 1] == plan["node"]["root"] + "/dist/cluster/lib/*", "Actual node classpath differs")
        started = [line for line in (directory / f"node{node}/process.log").read_text().splitlines() if line.startswith("VECTOR_CLUSTER_STARTED ")]
        check(started and all(re.findall(r"(?:^|\s)nakUnicastDelayNs=(\S+)", line) == [str(delay)] and re.findall(r"(?:^|\s)nakUnicastRetryDelayRatio=(\S+)", line) == ["100"] for line in started), "Actual node NAK startup differs")
    prepared = digest((directory / "prepared-snapshot.bin").open("rb"))
    check(prepared["sha256"] == config["preparedSnapshotSha256"] == plan["preparedSnapshotSha256"], "Preparation differs")
    fixed = trial["fixedNodeConfiguration"]
    check((fixed["nakUnicastDelayNs"], fixed["clientNakUnicastDelayNs"], fixed["nakUnicastRetryDelayRatio"]) == (delay, delay, 100), "Fixed NAK declaration differs")
    check(read(directory / "fixed-leader-check.json")["observedTerms"] == [0], "Recorded term differs")
    check(read(directory / "all-owned-processes-stopped.json")["passed"] is True, "Owned-process cleanup not confirmed")
    exit_receipt = read(directory / "receipt.json")
    result_path = directory / "result.json"
    canonical = None
    if result_path.exists():
        result = read(result_path)
        check(exit_receipt["exitCode"] == 0 and result["passed"] is True and result["measurementValid"] is True, "Terminal normal result invalid")
        check(result["canonicalSnapshotBytesVerified"] is True and result["assetConservationVerified"] is True and result["perReplyDeterministicResultVerified"] is True and result["outboxPendingVerified"] is True, "Canonical/source account checks incomplete")
        canonical = digest((directory / "final-snapshot.bin").open("rb"))
        check(canonical == digest((directory / "expected-snapshot.bin").open("rb")), "Final/reference canonical bytes differ")
        check(unresolved == initial_unknown == 0 and sequences == set(range(168, 168 + accepted)), "Known execution sequence delta differs")
        check(result["finalRetainedOrders"] == 101 + accepted and result["finalOutboxPending"] == 267 + 2 * accepted, "Retained/outbox result counters differ")
        canonical_verified = True
    else:
        failure = read(directory / "failure.json")
        check(type(exit_receipt["exitCode"]) is int and exit_receipt["exitCode"] != 0 and unresolved > 0, "Terminal failed UNKNOWN receipt differs")
        check(failure["passed"] is False and failure["errorType"] == "java.lang.IllegalStateException" and failure["error"] == GUARD.format(count=unresolved) and failure["loadSummary"] == load, "Unexpected terminal failure signature")
        check(configuration_receipt["configurationOnly"] is True and configuration_receipt["businessCorrectnessVerified"] is False, "Failed run mislabeled as business validated")
        canonical_verified = False
    busy = sum(stats["occupiedNs"] for stats in per_worker)
    return {"id": task["id"], "cohort": task["cohort"], "sourceRevision": plan["node"]["revision"], "bundleSha256": plan["node"]["bundleSha256"], "rows": offered, "columns": len(HEADER), "allIndicesAndBusinessIdentitiesVerified": True, "archive": {"compressed": compressed, "decoded": decoded, "localOriginal": original, "analyzerInputSha256": summary["inputSha256"]["arrivals.csv"]}, "outcomes": dict(counters), "initialUnknown": initial_unknown, "resolvedAfterInitialUnknown": resolved, "unresolvedFinal": unresolved, "clientReportedAccepted": accepted, "confirmedWithinArrivalWindow": within, "inWindowReportedConfirmationsPerSecond": within * 1e9 / window, "conditionalAcceptedP99Millis": p99(latencies), "allOfferedAcceptedP99Millis": None if load["allOfferedAcceptedP99Microseconds"] is None else load["allOfferedAcceptedP99Microseconds"] / 1000, "initialApiMeanMillisAllStartedIncludingTimeouts": sum(api_all) / len(api_all) / 1e6, "initialApiMeanMillisReturnedAccepted": sum(api_known) / len(api_known) / 1e6, "initialApiP99MillisAllStarted": p99(api_all), "queueP99MillisReturnedAccepted": p99(queue_latencies), "meanOccupiedLogicalWorkerSlots": busy / window, "occupiedLogicalWorkerPercent": busy / window / workers * 100, "windowSeconds": window / 1e9, "drainSeconds": load["drainSeconds"], "backlog": summary["backlog"], "classification": summary["classification"], "businessCanonicalValidated": canonical_verified, "capacityEligibilityScope": "Canonical-valid finite-window classification remains separate from stability; failures retain client-reported confirmations only, never validated business throughput.", "configurationInputHashesVerified": len(configuration_receipt["rawSha256"]), "nodeAndClientActualNakDelayNs": delay, "nodeAndClientActualNakRetryRatio": 100, "prepared": prepared, "finalAndReferenceCanonicalBytes": canonical, "originalExitCode": exit_receipt["exitCode"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--require-local-raw", action="store_true")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    pilot, formal = read(options.root / "pilot-plan.json"), read(options.root / "plan.json")
    check(len(pilot["trials"]) == 1 and len(formal["trials"]) == 4, "Registered 1+4 attempt scope differs")
    check(pilot["node"] == formal["node"] and pilot["load"] == formal["load"], "Pilot/formal artifacts differ")
    audits = [audit(options.root, task, plan, options.require_local_raw) for plan in (pilot, formal) for task in plan["trials"]]
    report = {"schemaVersion": 1, "test": "independent-full-NAK-arrivals-archive-audit", "generatedAtUtc": datetime.now(timezone.utc).isoformat(), "auditToolSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "registeredPlanSha256": {name: digest((options.root / name).open("rb"))["sha256"] for name in ("pilot-plan.json", "plan.json")}, "requireLocalRaw": options.require_local_raw, "runs": audits, "completedRunsAudited": len(audits), "totalRowsAuditedAcrossSeparateFreshLineages": sum(row["rows"] for row in audits), "scope": "Every original CSV row/column, original identity and decoded byte verified. No frozen analyzer rerun or input/CSV rewrite. Nonzero failures remain invalid; conditional percentiles exclude missing replies without inventing zeros. Canonical reference uses the same implementation; no replicated-checkpoint restart, one-way latency, stable capacity or globally unique cumulative-count claim.", "passed": True}
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if options.output:
        with options.output.open("x") as stream:
            stream.write(text)
        print(json.dumps({"passed": True, "output": str(options.output), "runs": len(audits), "allRows": report["totalRowsAuditedAcrossSeparateFreshLineages"], "auditSha256": hashlib.sha256(text.encode()).hexdigest()}))
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
