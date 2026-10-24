#!/usr/bin/env python3
"""Analyze capacity CSV evidence with bounded row retention and legacy-equivalent metrics.

The adjacent reference analyzer remains unchanged. Its SHA pins the shared CLI,
validation, classification, identity and report code. Only arrival loading,
accumulation and exact percentile computation are replaced. No live access.
"""
from __future__ import annotations

from array import array
from collections import Counter
import csv
import hashlib
import importlib.util
import io
import math
from pathlib import Path

REFERENCE_SHA256 = "5fba16bbdbb5e90318c65f945991f2eb4ddb256fb36f93e28e26133b9e65c80b"
REFERENCE_PATH = Path(__file__).with_name("analyze-capacity.py")
if hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest() != REFERENCE_SHA256:
    raise RuntimeError("Reference capacity analyzer changed; review streaming parity before use")
_spec = importlib.util.spec_from_file_location("vectormatch_capacity_reference_for_streaming", REFERENCE_PATH)
reference = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reference)
_original_load_csv = reference.load_csv
number, truth, OUTCOMES = reference.number, reference.truth, reference.OUTCOMES


class CompactIntegers:
    """Signed64 storage with an exact Python-int fallback, never truncation."""
    def __init__(self):
        self.values = array("q")

    def append(self, value):
        if isinstance(self.values, array) and not -(1 << 63) <= value < (1 << 63):
            self.values = list(self.values)
        self.values.append(value)

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)


class IndexCoverage:
    """Equivalent to unique sorted indices == range(row count), without sorting."""
    def __init__(self):
        self.seen = set()
        self.count = 0
        self.maximum = -1

    def append(self, value):
        self.count += 1
        self.seen.add(value)
        self.maximum = max(self.maximum, value)

    def valid_for(self, row_count):
        # Indices have already been checked as nonnegative by the legacy logic.
        return self.count == len(self.seen) == row_count and self.maximum == row_count - 1


def distribution_ns(values):
    # The reference sorts again for every percentile. Sort just once per column.
    ordered = sorted(values)
    count = len(ordered)
    return {"count": count, "minMillis": ordered[0] / 1e6 if count else None,
            **{name + "Millis": ordered[max(0, math.ceil(count * fraction) - 1)] / 1e6 if count else None
               for name, fraction in (("p50", .5), ("p95", .95), ("p99", .99), ("p999", .999))},
            "maxMillis": ordered[-1] / 1e6 if count else None}


class HashingReader(io.RawIOBase):
    """Hash the original bytes as the CSV decoder consumes them, without reread."""
    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.handle.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
        return count


class StreamingRows:
    def __init__(self, path, errors, sources):
        self.path, self.errors, self.sources = path, errors, sources
        self.error_position = len(errors)
        self.count = 0
        self.failed = False
        self.consumed = False

    def __len__(self):
        return self.count

    def __iter__(self):
        if self.consumed:
            raise RuntimeError("Arrival CSV must be streamed exactly once")
        self.consumed = True
        self.active = self._read_rows()
        return self.active

    def _read_rows(self):
        try:
            with self.path.open("rb") as raw:
                hashing = HashingReader(raw)
                # Match Path.open(newline="")'s locale encoding/newline semantics.
                with io.TextIOWrapper(io.BufferedReader(hashing), newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                        raise ValueError("Missing or repeated CSV header")
                    invalid_width = False
                    for row in reader:
                        if None in row or any(value is None for value in row.values()):
                            invalid_width = True
                        # Legacy first parses every row and only then checks all
                        # widths. A later decoder/csv.Error must take precedence.
                        if not invalid_width:
                            self.count += 1
                            yield row
                    if invalid_width:
                        raise ValueError("CSV row/header length mismatch")
                    self.sources[self.path.name] = hashing.digest.hexdigest()
        except (OSError, ValueError, csv.Error) as exc:
            self.failed = True
            self.count = 0
            self.sources.pop(self.path.name, None)
            # The old loader runs before backlog/offered-field validation. Preserve
            # the original error ordering although this file is consumed lazily.
            self.errors.insert(self.error_position, {"file": self.path.name, "error": type(exc).__name__})


def load_csv(directory, name, errors, sources):
    if name == "arrivals.csv":
        return StreamingRows(directory / name, errors, sources)
    return _original_load_csv(directory, name, errors, sources)


def _accumulate_arrivals(rows, scheduled, window_seconds):
    outcomes = Counter()
    latency = {name: CompactIntegers() for name in ("conditionalReply", "conditionalAccepted", "initialExecute", "queue", "scheduler")}
    accepted_within, initial_unknown, resolved_unknown, invalid = 0, 0, 0, []
    last_accepted_confirmation = 0
    indices = IndexCoverage()
    for index, row in enumerate(rows):
        try:
            arrival_index = number(row["index"], True)
            if arrival_index is None or arrival_index < 0:
                raise ValueError("Invalid arrival index")
            indices.append(arrival_index)
            outcome = row["outcome"]
            outcomes[outcome] += 1
            if outcome not in OUTCOMES:
                invalid.append({"row": index, "issue": "nonterminal-or-unrecognized-outcome", "outcome": outcome})
            confirmed = number(row["confirmed_offset_ns"], True)
            scheduled_to_confirmed = number(row["scheduled_to_confirmed_ns"], True)
            if confirmed is not None:
                if scheduled_to_confirmed is None or scheduled_to_confirmed < 0:
                    raise ValueError("Missing or negative returned-response latency")
                planned = number(row.get("planned_offset_ns"), True)
                if planned is not None and confirmed - planned != scheduled_to_confirmed:
                    raise ValueError("Latency differs from confirmation minus planned offset")
                latency["conditionalReply"].append(scheduled_to_confirmed)
                if outcome == "CONFIRMED_ACCEPTED":
                    latency["conditionalAccepted"].append(scheduled_to_confirmed)
                    last_accepted_confirmation = max(last_accepted_confirmation, confirmed)
                    if window_seconds is not None and confirmed <= window_seconds * 1e9:
                        accepted_within += 1
            elif outcome in ("CONFIRMED_ACCEPTED", "BUSINESS_REJECTED", "SERVER_ERROR", "INVALID_REPLY"):
                raise ValueError("Returned outcome lacks confirmation timestamp")
            for key, column in (("initialExecute", "initial_execute_rtt_ns"), ("queue", "queue_delay_ns"), ("scheduler", "scheduler_lateness_ns")):
                value = number(row.get(column), True)
                if value is not None:
                    if value < 0:
                        raise ValueError("Negative latency")
                    latency[key].append(value)
            if truth(row["unknown_at_initial_deadline"]):
                initial_unknown += 1
                if confirmed is not None:
                    resolved_unknown += 1
        except (ValueError, KeyError, TypeError) as exc:
            invalid.append({"row": index, "issue": type(exc).__name__})
    if not indices.valid_for(len(rows)):
        invalid.append({"issue": "arrival-indices-must-be-unique-and-contiguous"})
    if scheduled is not None and len(rows) != scheduled:
        invalid.append({"issue": "arrival-row-count-differs-from-scheduled", "expected": scheduled, "actual": len(rows)})
    accepted = outcomes["CONFIRMED_ACCEPTED"]
    all_finite = bool(rows) and not invalid and len(latency["conditionalAccepted"]) == len(rows) == scheduled
    completion_seconds = max(window_seconds or 0, last_accepted_confirmation / 1e9)
    distributions = {name: distribution_ns(values) for name, values in latency.items()}
    result = {"rows": len(rows), "outcomes": dict(sorted(outcomes.items())), "confirmedAccepted": accepted,
              "businessRejected": outcomes["BUSINESS_REJECTED"], "serverErrors": outcomes["SERVER_ERROR"] + outcomes["INVALID_REPLY"],
              "clientQueueFullNotSent": outcomes["CLIENT_QUEUE_FULL_NOT_SENT"], "drainNotSent": outcomes["DRAIN_NOT_SENT"],
              "workerBlockedUnknownNotSent": outcomes["WORKER_BLOCKED_UNKNOWN_NOT_SENT"],
              "clientNotSent": sum(outcomes[name] for name in ("CLIENT_QUEUE_FULL_NOT_SENT", "DRAIN_NOT_SENT", "WORKER_BLOCKED_UNKNOWN_NOT_SENT")),
              "unknownAtInitialDeadline": initial_unknown, "resolvedAfterInitialUnknown": resolved_unknown,
              "unknownUnresolved": outcomes["UNKNOWN_UNRESOLVED"], "confirmedWithinArrivalWindow": accepted_within,
              "arrivalWindowGoodputPerSecond": accepted_within / window_seconds if window_seconds and window_seconds > 0 else None,
              "completionWindowSeconds": completion_seconds,
              "confirmedIncludingDrainPerSecond": accepted / completion_seconds if completion_seconds > 0 else None,
              "drainSeconds": max(0, completion_seconds - window_seconds) if window_seconds is not None else None,
              "allOfferedAcceptedFinite": all_finite,
              "allOfferedAcceptedP99Millis": distributions["conditionalAccepted"]["p99Millis"] if all_finite else None,
              "latency": distributions, "validationIssues": invalid}
    return result

def analyze_arrivals(rows, scheduled, window_seconds):
    try:
        result = _accumulate_arrivals(rows, scheduled, window_seconds)
    except Exception:
        if not isinstance(rows, StreamingRows) or not rows.consumed:
            raise
        # Legacy checks the entire CSV structure before any numeric parsing.
        # Defer an otherwise uncaught numeric error until remaining CSV input has
        # been checked: a later structural failure takes precedence and clears it.
        for _ in rows.active:
            pass
        if rows.failed:
            return _accumulate_arrivals([], scheduled, window_seconds)
        raise
    if isinstance(rows, StreamingRows) and rows.failed:
        # Legacy CSV loading is all-or-nothing. A malformed late row discards
        # every prior aggregate and never leaves an input hash or partial result.
        return _accumulate_arrivals([], scheduled, window_seconds)
    return result


# Each imported function resolves globals in the reference module. Replace only
# these three narrow hooks; all reporting and validation code remains pinned.
reference.load_csv = load_csv
reference.analyze_arrivals = analyze_arrivals
reference.distribution_ns = distribution_ns
analyze_trial = reference.analyze_trial
main = reference.main

if __name__ == "__main__":
    main()
