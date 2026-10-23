#!/usr/bin/env python3
"""Authenticated, bounded, private IPv4 UDP echo probe; not a capacity benchmark.

Run one server/client pair, then swap their roles with a NEW run ID. A successful
echo proves packets crossed in both directions for that initiator. The reverse
run also checks the other node's listener and source-address behavior.
"""
import argparse
import datetime
import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import secrets
import select
import socket
import stat
import struct
import sys
import tempfile
import time


MAGIC = b"VMUDP001"
HEADER = struct.Struct("!8s16sBQQH")
MAC_BYTES = 32
OVERHEAD = HEADER.size + MAC_BYTES
PACKET_SIZES = (96, 512, 1248)
REQUEST, RESPONSE = 1, 2
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"))


def private_address(value, allow_loopback=False):
    address = ipaddress.IPv4Address(value)
    if any(address in network for network in PRIVATE_NETWORKS) or (allow_loopback and address.is_loopback):
        return str(address)
    raise ValueError("Use an explicit RFC1918/CGNAT private IPv4 address; wildcard and public listeners are refused")


def read_key(path):
    source = Path(path)
    if os.name == "posix" and stat.S_IMODE(source.stat().st_mode) & 0o077:
        raise ValueError("Key file permissions must exclude group/other access (chmod 600)")
    value = source.read_text(encoding="ascii").strip()
    if len(value) != 64:
        raise ValueError("Key file must contain exactly 32 bytes encoded as 64 hexadecimal characters")
    key = bytes.fromhex(value)
    if len(key) != 32:
        raise ValueError("Invalid key length")
    return key


def make_packet(key, run_id, kind, sequence, sent_ns, size, padding=None):
    if not OVERHEAD <= size <= 1408:
        raise ValueError("Unsupported packet size")
    padding = os.urandom(size - OVERHEAD) if padding is None else padding
    if len(padding) != size - OVERHEAD:
        raise ValueError("Incorrect padding length")
    body = HEADER.pack(MAGIC, run_id, kind, sequence, sent_ns, len(padding)) + padding
    return body + hmac.digest(key, body, "sha256")


def parse_packet(data, key, run_id, expected_kind):
    if not OVERHEAD <= len(data) <= 1408:
        return None, "size"
    body, supplied_mac = data[:-MAC_BYTES], data[-MAC_BYTES:]
    if not hmac.compare_digest(supplied_mac, hmac.digest(key, body, "sha256")):
        return None, "authentication"
    magic, received_run, kind, sequence, sent_ns, padding_size = HEADER.unpack_from(body)
    if magic != MAGIC or received_run != run_id or kind != expected_kind or padding_size != len(body) - HEADER.size:
        return None, "protocol_or_run"
    return {"sequence": sequence, "sentNs": sent_ns, "padding": body[HEADER.size:], "packetBytes": len(data)}, None


def quantiles(values):
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0, "minMillis": None, "p50Millis": None, "p95Millis": None,
                "p99Millis": None, "maxMillis": None}
    return {"samples": len(ordered), "minMillis": ordered[0],
            "p50Millis": ordered[math.ceil(len(ordered) * .50) - 1],
            "p95Millis": ordered[math.ceil(len(ordered) * .95) - 1],
            "p99Millis": ordered[math.ceil(len(ordered) * .99) - 1], "maxMillis": ordered[-1]}


def hardware():
    try:
        affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    except OSError:
        affinity = None
    report = {"hostname": socket.gethostname(), "system": platform.system(), "kernel": platform.release(),
              "architecture": platform.machine(), "logicalCpuCount": os.cpu_count(), "allowedCpuIds": affinity,
              "scope": "Container-visible hardware only; hostname/CPU identity do not prove physical host separation"}
    report["interfaceMtu"] = {}
    for mtu_file in Path("/sys/class/net").glob("*/mtu"):
        try:
            report["interfaceMtu"][mtu_file.parent.name] = int(mtu_file.read_text().strip())
        except (OSError, ValueError):
            pass
    try:
        cpu_text = Path("/proc/cpuinfo").read_text()
        report["cpuModel"] = next((line.split(":", 1)[1].strip() for line in cpu_text.splitlines()
                                  if line.startswith("model name")), None)
    except OSError:
        report["cpuModel"] = None
    try:
        report["hostVisibleMemory"] = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                                       for line in Path("/proc/meminfo").read_text().splitlines()
                                       if line.startswith(("MemTotal:", "MemAvailable:"))}
    except OSError:
        report["hostVisibleMemory"] = None
    return report


def report_base(args):
    return {"schemaVersion": 1, "mode": args.mode, "runId": args.run_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "hardware": hardware(), "expectedPeerIp": args.peer,
            "packetSizesBytes": list(args.sizes), "expectedPerPacketSize": args.count,
            "dontFragment": args.dont_fragment,
            "fragmentationNote": "DF probe: Linux IP_MTU_DISCOVER=IP_PMTUDISC_DO; packet bytes exclude 20-byte IPv4 and 8-byte UDP headers"
                                 if args.dont_fragment else "Fragmentation allowed by OS; success does NOT prove these datagram sizes fit path MTU",
            "scope": "Authenticated raw IPv4 UDP echo on explicitly bound addresses; low-rate reachability probe, "
                     "not throughput capacity, clock synchronization, physical-host-separation or HA evidence",
            "oneWayLatencyMeasured": False, "providerMachineId": None,
            "providerMachineIdNote": "Record provider machineId externally for every node; this probe does not infer it"}


def write_report(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(report, output, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def new_socket(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((args.bind, args.port))
        if args.dont_fragment:
            if platform.system() != "Linux":
                raise ValueError("--dont-fragment currently requires Linux")
            # Linux uapi: IP_MTU_DISCOVER=10, IP_PMTUDISC_DO=2. Python does not expose these on every build.
            sock.setsockopt(socket.IPPROTO_IP, getattr(socket, "IP_MTU_DISCOVER", 10), 2)
        sock.setblocking(False)
        return sock
    except BaseException:
        sock.close()
        raise


def endpoint_rows(counts):
    return [{"ip": endpoint[0], "port": endpoint[1], "packets": count}
            for endpoint, count in sorted(counts.items())]


def serve(args, key, run_id):
    report = report_base(args)
    total = args.count * len(args.sizes)
    seen, sources, per_size = set(), {}, {size: 0 for size in args.sizes}
    rejected = {"source": 0, "size": 0, "authentication": 0, "protocol_or_run": 0, "sequence_or_size": 0}
    duplicates, reordered, highest, sent, send_errors = 0, 0, -1, 0, 0
    start = time.monotonic()
    with new_socket(args) as sock:
        report["boundEndpoint"] = {"ip": sock.getsockname()[0], "port": sock.getsockname()[1]}
        # Printed only after bind: orchestrators can wait for readiness without races.
        print(json.dumps({"status": "READY", "boundEndpoint": report["boundEndpoint"], "runId": args.run_id}), flush=True)
        while time.monotonic() - start < args.duration and len(seen) < total:
            readable, _, _ = select.select([sock], [], [], min(.1, max(0, args.duration - (time.monotonic() - start))))
            if not readable:
                continue
            data, source = sock.recvfrom(65535)
            if source[0] != args.peer or (args.peer_port is not None and source[1] != args.peer_port):
                rejected["source"] += 1
                continue
            packet, error = parse_packet(data, key, run_id, REQUEST)
            if error:
                rejected[error] += 1
                continue
            sequence, size = packet["sequence"], packet["packetBytes"]
            if sequence >= total or size != args.sizes[sequence // args.count]:
                rejected["sequence_or_size"] += 1
                continue
            sources[source] = sources.get(source, 0) + 1
            if sequence in seen:
                duplicates += 1
            else:
                seen.add(sequence)
                per_size[size] += 1
                if sequence < highest:
                    reordered += 1
                highest = max(highest, sequence)
            response = make_packet(key, run_id, RESPONSE, sequence, packet["sentNs"], size, packet["padding"])
            try:
                sock.sendto(response, source)
                sent += 1
            except OSError:
                send_errors += 1
    reasons = []
    if len(seen) != total:
        reasons.append("Not all expected authenticated request sequences arrived before the server deadline")
    if send_errors:
        reasons.append("One or more echo sends failed")
    if duplicates or reordered:
        reasons.append("Duplicate or reordered requests observed")
    report.update({"elapsedSeconds": time.monotonic() - start, "uniqueRequestsReceived": len(seen),
                   "expectedRequests": total, "requestsMissing": total - len(seen), "echoesSent": sent,
                   "echoSendErrors": send_errors, "duplicates": duplicates, "reordered": reordered,
                   "authenticatedSources": endpoint_rows(sources), "rejectedPackets": rejected,
                   "packetSizeCounts": {str(size): count for size, count in per_size.items()},
                   "passed": not reasons, "failureReasons": reasons,
                   "verdictScope": "Server reception and echo sends only; inspect the paired client report for returned echoes and RTT"})
    return report


class ClientResults:
    """Keep wire validation, loss, duplicate and ordering accounting independently testable."""
    def __init__(self, key, run_id, peer, sizes=PACKET_SIZES):
        self.key, self.run_id, self.peer = key, run_id, peer
        self.sizes = sizes
        self.sent, self.received, self.samples = {}, set(), []
        self.sources, self.invalid = {}, {"source": 0, "size": 0, "authentication": 0,
                                        "protocol_or_run": 0, "unmatched": 0}
        self.duplicates, self.reordered, self.highest = 0, 0, -1

    def record(self, data, source, received_ns):
        if source != self.peer:
            self.invalid["source"] += 1
            return
        packet, error = parse_packet(data, self.key, self.run_id, RESPONSE)
        if error:
            self.invalid[error] += 1
            return
        sequence = packet["sequence"]
        expected = self.sent.get(sequence)
        if expected is None or (packet["sentNs"], packet["packetBytes"], packet["padding"]) != expected:
            self.invalid["unmatched"] += 1
            return
        self.sources[source] = self.sources.get(source, 0) + 1
        if sequence in self.received:
            self.duplicates += 1
            return
        self.received.add(sequence)
        if sequence < self.highest:
            self.reordered += 1
        self.highest = max(self.highest, sequence)
        self.samples.append({"sequence": sequence, "packetBytes": packet["packetBytes"],
                             "rttMillis": (received_ns - packet["sentNs"]) / 1e6,
                             "sourceIp": source[0], "sourcePort": source[1]})

    def summary(self, maximum_loss):
        per_size = []
        reasons = []
        for size in self.sizes:
            sent = sum(1 for row in self.sent.values() if row[1] == size)
            samples = [row["rttMillis"] for row in self.samples if row["packetBytes"] == size]
            loss = (sent - len(samples)) / sent if sent else None
            per_size.append({"packetBytes": size, "sent": sent, "receivedUnique": len(samples),
                             "lost": sent - len(samples), "lossFraction": loss, "rtt": quantiles(samples)})
            if not sent or not samples or loss > maximum_loss:
                reasons.append(f"Packet size {size} did not meet the configured echo/loss requirement")
        if self.duplicates or self.reordered:
            reasons.append("Duplicate or reordered echoes observed")
        # Wrong-endpoint traffic is ignored. Authenticated but unmatched replies indicate a bad test/protocol.
        if self.invalid["unmatched"]:
            reasons.append("Authenticated echo did not match a request from this client")
        return {"packetsSent": len(self.sent), "echoesReceivedUnique": len(self.received),
                "packetsLost": len(self.sent) - len(self.received), "maximumAllowedLossFraction": maximum_loss,
                "duplicates": self.duplicates, "reordered": self.reordered, "perPacketSize": per_size,
                "rtt": quantiles([row["rttMillis"] for row in self.samples]),
                "authenticatedSources": endpoint_rows(self.sources), "rejectedPackets": self.invalid,
                "passed": not reasons, "failureReasons": reasons, "samples": self.samples}


def probe(args, key, run_id):
    report = report_base(args)
    results = ClientResults(key, run_id, (args.peer, args.peer_port), args.sizes)
    total = args.count * len(args.sizes)
    start = time.monotonic()
    final_send = None
    with new_socket(args) as sock:
        report["boundEndpoint"] = {"ip": sock.getsockname()[0], "port": sock.getsockname()[1]}
        sequence = 0
        while True:
            now = time.monotonic()
            if now - start >= args.duration:
                break
            if final_send is not None and now >= final_send + args.drain:
                break
            if sequence < total and now >= start + sequence / args.rate:
                size, sent_ns = args.sizes[sequence // args.count], time.perf_counter_ns()
                data = make_packet(key, run_id, REQUEST, sequence, sent_ns, size)
                packet, _ = parse_packet(data, key, run_id, REQUEST)
                try:
                    sock.sendto(data, (args.peer, args.peer_port))
                except OSError as error:
                    report["sendError"] = {"type": type(error).__name__, "errno": error.errno, "message": str(error),
                                           "packetBytes": size, "ipv4UdpBytes": size + 28}
                    break
                results.sent[sequence] = (sent_ns, size, packet["padding"])
                sequence += 1
                if sequence == total:
                    final_send = time.monotonic()
            next_send = start + sequence / args.rate if sequence < total else float("inf")
            deadline = min(start + args.duration, final_send + args.drain if final_send is not None else float("inf"))
            wait = max(0, min(.05, next_send - time.monotonic(), deadline - time.monotonic()))
            readable, _, _ = select.select([sock], [], [], wait)
            if readable:
                data, source = sock.recvfrom(65535)
                results.record(data, source, time.perf_counter_ns())
    report.update(results.summary(args.max_loss))
    report.update({"expectedRequests": total, "requestsNotSent": total - len(results.sent),
                   "elapsedSeconds": time.monotonic() - start, "configuredPacketsPerSecond": args.rate,
                   "clientDrainSeconds": args.drain,
                   "verdictScope": "One initiator's authenticated private-IP request/echo path for each tested packet size; "
                                   "repeat with node roles reversed and a new run ID"})
    if report["requestsNotSent"] or report.get("sendError"):
        report["passed"] = False
        report["failureReasons"].append("Not all planned requests were successfully sent")
    return report


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    init = sub.add_parser("init-key", help="Create a mode-600 random shared key; never prints its contents")
    init.add_argument("path")
    for mode in ("server", "client"):
        command = sub.add_parser(mode)
        command.add_argument("--bind", required=True, help="Explicit local RFC1918/CGNAT IPv4")
        command.add_argument("--peer", required=True, help="Explicit peer RFC1918/CGNAT IPv4 (no DNS or public IP)")
        command.add_argument("--port", type=int, default=19080 if mode == "server" else 19081)
        command.add_argument("--peer-port", type=int, default=None if mode == "server" else 19080)
        command.add_argument("--key-file", required=True)
        command.add_argument("--run-id", required=True, help="32 hex characters; use a NEW value for each direction")
        command.add_argument("--count", type=int, default=100, help="Requests per packet size, 1..1000")
        command.add_argument("--duration", type=float, default=15, help="Hard lifetime in seconds, 0.1..60")
        command.add_argument("--output", required=True)
        command.add_argument("--sizes", default="96,512,1248", help="Comma-separated UDP payload sizes, 75..1408; default fits MTU1300")
        command.add_argument("--dont-fragment", action="store_true", help="Linux only: refuse IPv4 fragmentation (DF) on both endpoints")
        command.add_argument("--allow-loopback", action="store_true", help="Local integration tests only; still refuses wildcard/public IPs")
        if mode == "client":
            command.add_argument("--rate", type=float, default=100, help="Requests per second, 1..1000")
            command.add_argument("--drain", type=float, default=2, help="Drain replies after last send, 0.1..10 seconds")
            command.add_argument("--max-loss", type=float, default=0, help="Allowed loss fraction per packet size, default 0")
    args = parser.parse_args(argv)
    if args.mode == "init-key":
        return args
    try:
        args.bind = private_address(args.bind, args.allow_loopback)
        args.peer = private_address(args.peer, args.allow_loopback)
        args.sizes = tuple(int(value) for value in args.sizes.split(","))
        if not args.sizes or len(args.sizes) > 8 or len(set(args.sizes)) != len(args.sizes) or any(not OVERHEAD <= size <= 1408 for size in args.sizes):
            raise ValueError("Use 1..8 distinct packet sizes between protocol overhead and 1408 bytes")
        if not 1 <= args.port <= 65535 or (args.peer_port is not None and not 1 <= args.peer_port <= 65535):
            raise ValueError("Ports must be in 1..65535")
        if len(args.run_id) != 32 or len(bytes.fromhex(args.run_id)) != 16:
            raise ValueError("Run ID must be exactly 16 bytes encoded as 32 hex characters")
        if not 1 <= args.count <= 1000 or not .1 <= args.duration <= 60:
            raise ValueError("Count must be 1..1000 and duration 0.1..60 seconds")
        if args.mode == "client":
            if not 1 <= args.rate <= 1000 or not .1 <= args.drain <= 10 or not 0 <= args.max_loss <= 1:
                raise ValueError("Invalid rate, drain, or maximum loss")
            if (args.count * len(args.sizes) - 1) / args.rate + args.drain >= args.duration:
                raise ValueError("Duration must exceed the complete scheduled send period plus drain time")
    except (ValueError, ipaddress.AddressValueError) as error:
        parser.error(str(error))
    return args


def main(argv=None):
    args = arguments(argv)
    if args.mode == "init-key":
        path = Path(args.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(secrets.token_hex(32) + "\n")
        print(json.dumps({"keyFile": str(path), "suggestedRunId": secrets.token_hex(16)}))
        return 0
    try:
        key, run_id = read_key(args.key_file), bytes.fromhex(args.run_id)
        report = serve(args, key, run_id) if args.mode == "server" else probe(args, key, run_id)
    except (OSError, ValueError) as error:
        report = report_base(args)
        report.update({"passed": False, "failureReasons": [f"Probe failed: {type(error).__name__}"],
                       "error": str(error)})
    write_report(args.output, report)
    print(json.dumps({"status": "PASS" if report["passed"] else "FAIL", "output": str(args.output),
                      "failureReasons": report["failureReasons"]}), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
