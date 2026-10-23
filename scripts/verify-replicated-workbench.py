#!/usr/bin/env python3
"""A real loopback HTTP -> replicated core -> PostgreSQL observation smoke, not a load test."""
import datetime
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import uuid


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path not in ("", "/"):
        raise ValueError("Only loopback workbench URLs are supported")
    output = Path(sys.argv[2] if len(sys.argv) > 2 else "reports/local/replicated-workbench")
    output.mkdir(parents=True, exist_ok=False)
    trace = []

    def request(route, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base.rstrip("/") + route, data=data,
                                     headers={"Content-Type": "application/json"})
        started = time.monotonic_ns()
        with urllib.request.urlopen(req, timeout=35) as response:
            result = json.load(response)
        trace.append({"route": route, "request": payload, "response": result,
                      "elapsedMillis": (time.monotonic_ns() - started) / 1e6})
        return result

    try:
        initial = request("/api/state")
        assert initial["health"]["mode"] == "CLUSTER_REPLICATED", "Expected actual replicated backend"
        assert initial["health"]["status"] == "UP", "Backend must be writable"
        request("/api/control/flow", {"enabled": False})
        producer = "verify-" + uuid.uuid4().hex[:16]
        order = {"accountId": 1, "producerId": producer, "requestSeq": 1,
                 "clientOrderId": producer, "side": "BUY", "priceTicks": 1,
                 "quantityLots": 3, "timeInForce": "GTC"}
        placed = request("/api/orders", order)
        assert placed["result"]["code"] == "ACCEPTED"
        duplicate = request("/api/orders", order)
        assert duplicate["replayed"] and placed["result"] == duplicate["result"]
        conflict = request("/api/orders", {**order, "quantityLots": 4})
        assert conflict["result"]["code"] == "IDEMPOTENCY_CONFLICT"
        cancelled = request("/api/cancel", {"accountId": 1, "producerId": producer,
                                             "requestSeq": 2, "orderId": placed["result"]["orderId"]})
        assert cancelled["result"]["code"] == "ACCEPTED"
        expected_event = max(event["eventSeq"] for event in cancelled["events"])
        verification = request("/api/control/replay", {})
        assert verification["consistent"], "Authoritative core snapshot and mirror must agree"
        deadline = time.monotonic() + 30
        while True:
            final = request("/api/state")
            projection = final.get("projection", {})
            if projection.get("status") == "OBSERVED" and (projection.get("cursor") or 0) >= expected_event:
                break
            assert time.monotonic() < deadline, "PostgreSQL did not reach confirmed event within 30 seconds"
            time.sleep(0.5)
        before = next(a for a in initial["accounts"] if a["id"] == 1)
        after = next(a for a in final["accounts"] if a["id"] == 1)
        assert before == after, "Place/cancel must restore account 1 balances (avoid concurrent manual trading)"
        summary = {"passed": True, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "scope": "HTTP -> Aeron quorum -> gateway mirror -> asynchronous PostgreSQL cursor observation",
                   "independentMachines": False, "commands": 2, "trades": placed["result"]["tradeCount"],
                   "idempotentReplayVerified": True, "payloadConflictVerified": True,
                   "balancesRestored": True, "replicatedSnapshotVerified": True,
                   "confirmedEventSeq": expected_event, "projection": projection,
                   "limitations": ["Functional smoke, not a latency or capacity benchmark.",
                                   "Three cluster processes, gateway and PostgreSQL share one host.",
                                   "PostgreSQL cursor is a cached observation, not an atomic source/database snapshot."]}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
    finally:
        (output / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")


if __name__ == "__main__":
    main()
