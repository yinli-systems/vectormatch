import importlib.util
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "udp-preflight.py"
spec = importlib.util.spec_from_file_location("udp_preflight_test", SCRIPT)
udp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(udp)
KEY, RUN = bytes(range(32)), bytes(range(16))


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DatagramValidationTest(unittest.TestCase):
    def test_authentication_run_and_kind_are_checked_before_echo(self):
        packet = udp.make_packet(KEY, RUN, udp.REQUEST, 7, 1000, 1408)
        parsed, error = udp.parse_packet(packet, KEY, RUN, udp.REQUEST)
        self.assertIsNone(error)
        self.assertEqual((7, 1000, 1408), (parsed["sequence"], parsed["sentNs"], parsed["packetBytes"]))
        corrupt = bytearray(packet)
        corrupt[-1] ^= 1
        self.assertEqual("authentication", udp.parse_packet(bytes(corrupt), KEY, RUN, udp.REQUEST)[1])
        self.assertEqual("protocol_or_run", udp.parse_packet(packet, KEY, bytes(16), udp.REQUEST)[1])
        self.assertEqual("protocol_or_run", udp.parse_packet(packet, KEY, RUN, udp.RESPONSE)[1])
        self.assertEqual("size", udp.parse_packet(packet + b"x", KEY, RUN, udp.REQUEST)[1])

    def test_only_explicit_private_addresses_are_accepted(self):
        for address in ("10.0.212.169", "172.16.1.1", "192.168.5.4", "100.64.1.5"):
            self.assertEqual(address, udp.private_address(address))
        for address in ("0.0.0.0", "8.8.8.8", "127.0.0.1", "224.0.0.1", "169.254.1.1"):
            with self.assertRaises(ValueError):
                udp.private_address(address)
        self.assertEqual("127.0.0.1", udp.private_address("127.0.0.1", allow_loopback=True))
        with self.assertRaises(ValueError):
            udp.private_address("0.0.0.0", allow_loopback=True)

    def test_loss_duplicate_order_source_and_unmatched_echo_are_separate(self):
        peer = ("10.1.60.60", 19080)
        results = udp.ClientResults(KEY, RUN, peer)
        packets = {}
        for sequence, size in enumerate(udp.PACKET_SIZES):
            packet = udp.make_packet(KEY, RUN, udp.RESPONSE, sequence, 1000 + sequence, size)
            parsed, _ = udp.parse_packet(packet, KEY, RUN, udp.RESPONSE)
            results.sent[sequence] = (parsed["sentNs"], size, parsed["padding"])
            packets[sequence] = packet
        results.record(packets[0], (peer[0], peer[1] + 1), 2_001_000)
        self.assertEqual(1, results.invalid["source"])
        results.record(packets[2], peer, 2_001_002)
        results.record(packets[0], peer, 3_001_000)
        results.record(packets[0], peer, 4_001_000)
        summary = results.summary(0)
        self.assertEqual(1, summary["packetsLost"])
        self.assertEqual(1, summary["duplicates"])
        self.assertEqual(1, summary["reordered"])
        self.assertEqual(2, summary["rtt"]["samples"])
        self.assertFalse(summary["passed"])
        self.assertEqual(1, summary["perPacketSize"][1]["lost"])
        unmatched = udp.make_packet(KEY, RUN, udp.RESPONSE, 1, 999999, 512)
        results.record(unmatched, peer, 5_000_000)
        self.assertEqual(1, results.invalid["unmatched"])

    def test_key_is_never_overwritten_or_accepted_with_public_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "key"
            first = subprocess.run([sys.executable, str(SCRIPT), "init-key", str(path)],
                                   capture_output=True, text=True, timeout=5)
            self.assertEqual(0, first.returncode, first.stderr)
            key = udp.read_key(path)
            self.assertEqual(32, len(key))
            self.assertNotIn(key.hex(), first.stdout)
            second = subprocess.run([sys.executable, str(SCRIPT), "init-key", str(path)],
                                    capture_output=True, text=True, timeout=5)
            self.assertNotEqual(0, second.returncode)
            self.assertEqual(key, udp.read_key(path))
            if os.name == "posix":
                path.chmod(0o644)
                with self.assertRaises(ValueError):
                    udp.read_key(path)


class DatagramSocketTest(unittest.TestCase):
    def test_real_socket_authenticated_echo_ignores_invalid_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key = directory / "key"
            key.write_text(KEY.hex())
            key.chmod(0o600)
            server_port, client_port = free_port(), free_port()
            while client_port == server_port:
                client_port = free_port()
            common = ["--bind", "127.0.0.1", "--peer", "127.0.0.1", "--allow-loopback",
                      "--key-file", str(key), "--run-id", RUN.hex(), "--sizes", "96,1248,1408", "--count", "5"]
            server = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "server", *common,
                                       "--port", str(server_port), "--duration", "4", "--output", str(directory / "server.json")],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([server.stdout], [], [], 3)[0], "Server did not bind before deadline")
                ready = json.loads(server.stdout.readline())
                self.assertEqual("READY", ready["status"])
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as noise:
                    noise.bind(("127.0.0.1", 0))
                    noise.settimeout(.1)
                    unauthenticated = bytearray(udp.make_packet(KEY, RUN, udp.REQUEST, 0, 1000, 96))
                    unauthenticated[-1] ^= 1
                    noise.sendto(bytes(unauthenticated), ("127.0.0.1", server_port))
                    noise.sendto(udp.make_packet(KEY, bytes(16), udp.REQUEST, 0, 1000, 96), ("127.0.0.1", server_port))
                    with self.assertRaises(socket.timeout):
                        noise.recvfrom(2048)
                client = subprocess.run([sys.executable, "-B", str(SCRIPT), "client", *common,
                                         "--port", str(client_port), "--peer-port", str(server_port), "--rate", "200",
                                         "--drain", ".2", "--duration", "2", "--output", str(directory / "client.json")],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(0, client.returncode, client.stdout + client.stderr)
                stdout, stderr = server.communicate(timeout=5)
                self.assertEqual(0, server.returncode, stdout + stderr)
                server_result = json.loads((directory / "server.json").read_text())
                client_result = json.loads((directory / "client.json").read_text())
                self.assertTrue(server_result["passed"])
                self.assertEqual(1, server_result["rejectedPackets"]["authentication"])
                self.assertEqual(1, server_result["rejectedPackets"]["protocol_or_run"])
                self.assertEqual(15, client_result["echoesReceivedUnique"])
                self.assertEqual(0, client_result["packetsLost"])
                self.assertEqual([{ "ip": "127.0.0.1", "port": server_port, "packets": 15}], client_result["authenticatedSources"])
                self.assertIsNone(client_result["providerMachineId"])
                self.assertIn("does NOT prove", client_result["fragmentationNote"])
            finally:
                if server.poll() is None:
                    server.terminate()
                    server.communicate(timeout=3)

    def test_unreachable_peer_produces_failed_evidence_and_exits_on_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            key, output = directory / "key", directory / "failure.json"
            key.write_text(KEY.hex())
            key.chmod(0o600)
            started = time.monotonic()
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), "client", "--bind", "127.0.0.1",
                                     "--peer", "127.0.0.1", "--allow-loopback", "--port", str(free_port()),
                                     "--peer-port", str(free_port()), "--key-file", str(key), "--run-id", RUN.hex(),
                                     "--count", "1", "--rate", "1000", "--drain", ".1", "--duration", ".3",
                                     "--output", str(output)], capture_output=True, text=True, timeout=3)
            self.assertEqual(1, result.returncode, result.stderr)
            report = json.loads(output.read_text())
            self.assertFalse(report["passed"])
            self.assertEqual(3, report["packetsLost"])
            self.assertIsNone(report["rtt"]["p99Millis"])
            self.assertLess(time.monotonic() - started, 2)


if __name__ == "__main__":
    unittest.main()
