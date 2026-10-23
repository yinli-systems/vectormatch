#!/usr/bin/env python3
"""HTTP -> replicated core -> PostgreSQL smoke via loopback or an SSH tunnel, not a load test."""
import datetime
import ipaddress
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import uuid


SUMMARY_SCOPE = "HTTP -> Aeron quorum -> gateway mirror -> asynchronous PostgreSQL cursor observation"
MANIFEST_KEYS = frozenset(("scope", "clusterMemberCount", "clusterPrivateIps", "physicalHostIsolationVerified",
                           "gatewaySharesClusterMember", "postgresSharesClusterMember", "networkEvidencePath"))
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"))


def load_deployment_manifest(path):
    source = Path(path)
    if source.stat().st_size > 16_384:
        raise ValueError("Deployment manifest must be at most 16 KiB")
    manifest = json.loads(source.read_text())
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise ValueError("Deployment manifest must contain exactly: " + ", ".join(sorted(MANIFEST_KEYS)))
    for key, maximum in (("scope", 500), ("networkEvidencePath", 1000)):
        if not isinstance(manifest[key], str) or not manifest[key].strip() or len(manifest[key]) > maximum:
            raise ValueError(f"Deployment manifest {key} must be a nonempty string of at most {maximum} characters")
    if type(manifest["clusterMemberCount"]) is not int or manifest["clusterMemberCount"] != 3:
        raise ValueError("Deployment manifest clusterMemberCount must be the integer 3")
    for key in ("physicalHostIsolationVerified", "gatewaySharesClusterMember", "postgresSharesClusterMember"):
        if type(manifest[key]) is not bool:
            raise ValueError(f"Deployment manifest {key} must be a boolean")
    addresses = manifest["clusterPrivateIps"]
    if not isinstance(addresses, list) or len(addresses) != 3 or any(not isinstance(value, str) for value in addresses):
        raise ValueError("Deployment manifest clusterPrivateIps must contain three private IPv4 strings")
    canonical = []
    for value in addresses:
        address = ipaddress.IPv4Address(value)
        if not any(address in network for network in PRIVATE_NETWORKS):
            raise ValueError("Deployment manifest clusterPrivateIps must be RFC1918/CGNAT private IPv4 addresses")
        canonical.append(str(address))
    if len(set(canonical)) != 3:
        raise ValueError("Deployment manifest must list three distinct private IPs")
    return manifest


def deployment_metadata(manifest):
    limitations = ["Functional smoke, not a latency or capacity benchmark."]
    if manifest is None:
        limitations.append("Three cluster processes, gateway and PostgreSQL share one host.")
        result = {"scope": SUMMARY_SCOPE, "independentMachines": False}
    else:
        layout = (f"cluster members={manifest['clusterMemberCount']}; "
                  f"gatewaySharesClusterMember={str(manifest['gatewaySharesClusterMember']).lower()}; "
                  f"postgresSharesClusterMember={str(manifest['postgresSharesClusterMember']).lower()}")
        result = {"scope": SUMMARY_SCOPE + " | Caller-supplied layout: " + manifest["scope"] + "; " + layout,
                  "independentMachines": None,
                  "deploymentManifest": manifest,
                  "deploymentMetadataProvenance": "Caller-supplied topology metadata; not independently verified by this HTTP verifier.",
                  "hostIsolationVerification": "NOT_PERFORMED_BY_HTTP_VERIFIER"}
        limitations.extend([
            "Topology, private IPs and service placement are caller-supplied metadata; this HTTP verifier does not inspect hosts or UDP paths.",
            "physicalHostIsolationVerified in deploymentManifest is the caller's declaration, not this verifier's conclusion; independentMachines remains unknown.",
            "networkEvidencePath is a caller-supplied evidence reference; this verifier does not open or validate that artifact.",
        ])
    limitations.append("PostgreSQL cursor is a cached observation, not an atomic source/database snapshot.")
    result["limitations"] = limitations
    return result


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) > 3:
        raise ValueError("Usage: verify-replicated-workbench.py [LOOPBACK_URL] [OUTPUT_DIR] [DEPLOYMENT_MANIFEST_JSON]")
    base = args[0] if args else "http://127.0.0.1:8001"
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.path not in ("", "/"):
        raise ValueError("Only loopback workbench URLs are supported")
    manifest = load_deployment_manifest(args[2]) if len(args) > 2 else None
    output = Path(args[1] if len(args) > 1 else "reports/local/replicated-workbench")
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
                   **deployment_metadata(manifest), "commands": 2, "trades": placed["result"]["tradeCount"],
                   "idempotentReplayVerified": True, "payloadConflictVerified": True,
                   "balancesRestored": True, "replicatedSnapshotVerified": True,
                   "confirmedEventSeq": expected_event, "projection": projection}
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
    finally:
        (output / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")


if __name__ == "__main__":
    main()
