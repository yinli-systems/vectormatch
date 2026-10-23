import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "capacity-attribution.py"
SPEC = importlib.util.spec_from_file_location("capacity_attribution_test", SCRIPT)
attribution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(attribution)


def stat(tid=41, start=500, user=10, system=2, comm="aeron (shared) x"):
    fields = ["0"] * 40
    fields[0], fields[11], fields[12], fields[17], fields[19] = "S", str(user), str(system), "1", str(start)
    return f"{tid} ({comm}) " + " ".join(fields)


def udp(inode=1234, drops=7, local="0100007F:59D8", remote="DEADBEEF:FFFF"):
    return f"1: {local} {remote} 07 00000020:00000040 00:00000000 00000000 9999 0 {inode} 2 DEADBEEF {drops}\n"


HEADER = "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode ref pointer drops\n"


class CapacityAttributionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.proc = self.base / "proc"
        self.pid = self.proc / "41"
        (self.pid / "task/41").mkdir(parents=True)
        (self.pid / "fd").mkdir()
        (self.pid / "net").mkdir()
        (self.pid / "stat").write_text(stat())
        (self.pid / "cmdline").write_bytes(b"java\0project-only\0")
        (self.pid / "task/41/stat").write_text(stat())
        (self.pid / "task/41/schedstat").write_text("1200 300 7\n")
        (self.pid / "task/41/wchan").write_text("futex_wait_queue\n")
        os.symlink("socket:[1234]", self.pid / "fd/3")
        os.symlink("/unrelated-file-name-not-to-serialize", self.pid / "fd/4")
        (self.pid / "net/udp").write_text(HEADER + udp() + udp(inode=9999, local="0200007F:0123"))
        (self.pid / "net/udp6").write_text(HEADER)
        self.record = self.base / "state/node-0/process.json"
        self.record.parent.mkdir(parents=True)
        self.identity = {"startTicks": 500, "commandSha256": hashlib.sha256((self.pid / "cmdline").read_bytes()).hexdigest()}
        self.record.write_text(json.dumps({"version": 1, "pid": 41, **self.identity}))

    def test_thread_stat_comm_parentheses_and_schedstat_units(self):
        row = attribution.parse_thread_stat(stat(comm="a ) b ( c"))
        self.assertEqual("a ) b ( c", row["comm"])
        self.assertEqual((41, 500, 10, 2), tuple(row[key] for key in ("tid", "startTicks", "userCpuTicks", "systemCpuTicks")))
        self.assertEqual({"runtimeNs": 1200, "runqueueWaitNs": 300, "timeslices": 7}, attribution.parse_schedstat("1200 300 7"))
        with self.assertRaises(ValueError):
            attribution.parse_schedstat("1200 -1 7")

    def test_udp_join_excludes_unowned_rows_and_peer_uid_pointer(self):
        owned, scan = attribution.owned_socket_inodes(self.pid, 4096)
        self.assertEqual({1234: [3]}, owned)
        table = attribution.udp_table(self.pid / "net/udp", owned, "ipv4")
        self.assertEqual(1, len(table["sockets"]))
        row = table["sockets"][0]
        self.assertEqual(("127.0.0.1", 23000, 32, 64, 7), tuple(row[key] for key in (
            "localAddress", "localPort", "transmitQueueKernelBytes", "receiveQueueKernelBytes", "drops")))
        encoded = json.dumps(table)
        self.assertNotIn("DEADBEEF", encoded)
        self.assertNotIn("9999", encoded)
        self.assertNotIn("unrelated-file", encoded)

    def test_ipv6_and_malformed_owned_udp_are_explicit(self):
        row, issue = attribution.parse_owned_udp_row(udp(local="00000000000000000000000001000000:59D8"), {1234: [3]}, "ipv6")
        self.assertEqual("::1", row["localAddress"])
        self.assertIsNone(issue)
        (self.pid / "net/udp").write_text(HEADER + " ".join(udp().split()[:10]) + "\n")
        table = attribution.udp_table(self.pid / "net/udp", {1234: [3]}, "ipv4")
        self.assertEqual("partial", table["status"])
        self.assertEqual(1, table["unparsedRows"])
        self.assertEqual([], table["sockets"])

    def test_verified_process_reports_details_and_no_command_line(self):
        collector = attribution.Collector(self.proc)
        row, previous = collector.process(self.record, "node-0")
        self.assertEqual("verified", row["status"])
        thread = row["threads"]["sampled"][0]
        self.assertEqual("identity-verified", thread["detailStatus"])
        self.assertEqual("futex_wait_queue", thread["details"]["wchan"]["value"])
        self.assertTrue(row["udp"]["ipv4"]["sockets"][0]["ownershipConfirmedAfterRead"])
        self.assertNotIn("project-only", json.dumps(row))
        self.assertEqual(1, len(previous))

    def test_pid_reuse_before_or_during_sample_discards_all_metrics(self):
        collector = attribution.Collector(self.proc)
        other = {**self.identity, "startTicks": 501}
        with patch.object(attribution.common, "proc_identity", return_value=other):
            row, previous = collector.process(self.record, "node-0")
        self.assertEqual("identity-mismatch", row["status"])
        self.assertNotIn("threads", row)
        with patch.object(attribution.common, "proc_identity", side_effect=[self.identity, other]):
            row, previous = collector.process(self.record, "node-0")
        self.assertEqual("identity-changed-during-read", row["status"])
        self.assertNotIn("udp", row)
        self.assertEqual({}, previous)

    def test_thread_reuse_does_not_subtract_counters_from_old_identity(self):
        collector = attribution.Collector(self.proc)
        row = collector.sample(node_records=[self.record])
        (self.pid / "task/41/stat").write_text(stat(start=501, user=1, system=0))
        row = collector.sample(node_records=[self.record])
        thread = row["processes"]["node-0"]["threads"]["sampled"][0]
        self.assertEqual(501, thread["startTicks"])
        self.assertIsNone(thread["deltaCpuTicks"])
        self.assertIsNone(thread["elapsedSincePreviousNs"])

    def test_same_thread_cpu_delta_and_missing_wait_channel_are_not_fake_zero(self):
        collector = attribution.Collector(self.proc)
        collector.sample(node_records=[self.record])
        (self.pid / "task/41/stat").write_text(stat(user=20, system=3))
        (self.pid / "task/41/wchan").unlink()
        row = collector.sample(node_records=[self.record])
        thread = row["processes"]["node-0"]["threads"]["sampled"][0]
        self.assertEqual(11, thread["deltaCpuTicks"])
        self.assertGreater(thread["elapsedSincePreviousNs"], 0)
        self.assertIsNone(thread["details"]["wchan"]["value"])
        self.assertEqual("FileNotFoundError", thread["details"]["wchan"]["error"])

    def test_fd_ownership_lost_during_read_is_not_attributed_to_process(self):
        collector = attribution.Collector(self.proc)
        scans = [({1234: [3]}, {"status": "ok"}), ({}, {"status": "ok"})]
        with patch.object(attribution, "owned_socket_inodes", side_effect=scans):
            row, previous = collector.process(self.record, "node-0")
        self.assertEqual([], row["udp"]["ipv4"]["sockets"])
        self.assertEqual(1, row["udp"]["ipv4"]["ownershipLostDuringRead"])

    def test_fd_scan_failure_does_not_look_like_no_udp_sockets(self):
        collector = attribution.Collector(self.proc)
        with patch.object(attribution, "owned_socket_inodes", return_value=({}, {"status": "unavailable", "value": None})):
            row, previous = collector.process(self.record, "node-0")
        self.assertEqual("ownership-scan-unavailable", row["udp"]["ipv4"]["status"])
        self.assertIsNone(row["udp"]["ipv4"]["sockets"])

    def test_detail_reads_are_bounded_and_thread_scan_truncation_explicit(self):
        for tid in range(42, 65):
            thread = self.pid / "task" / str(tid)
            thread.mkdir()
            (thread / "stat").write_text(stat(tid=tid, user=tid))
            (thread / "schedstat").write_text("1 2 3")
            (thread / "wchan").write_text("0")
        row, previous = attribution.Collector(self.proc).process(self.record, "node-0")
        self.assertEqual(16, sum(thread["detailStatus"] == "identity-verified" for thread in row["threads"]["sampled"]))
        row, previous = attribution.Collector(self.proc, max_threads=2).process(self.record, "node-0")
        self.assertTrue(row["threads"]["truncated"])
        self.assertEqual("partial", row["threads"]["status"])
        self.assertEqual(2, row["threads"]["sampledThreads"])

    def test_limits_missing_records_tables_and_sysctls_remain_visible(self):
        os.symlink("socket:[2222]", self.pid / "fd/5")
        owned, scan = attribution.owned_socket_inodes(self.pid, 1)
        self.assertTrue(scan["truncated"])
        self.assertEqual("partial", scan["status"])
        table = attribution.udp_table(self.pid / "net/missing", {1234: [3]}, "ipv4")
        self.assertIsNone(table["sockets"])
        self.assertIsNone(table["value"])
        collector = attribution.Collector(self.proc)
        row = collector.sample(node_records=[self.record], load_pid_file=self.base / "delayed-load.json")
        self.assertEqual("record-unavailable", row["processes"]["load"]["status"])
        metadata = attribution.system_metadata(self.proc)
        self.assertIsNone(metadata["sysctls"]["net.core.rmem_max"]["value"])

    def test_output_existing_file_is_never_overwritten_and_handlers_restored(self):
        output = self.base / "existing.jsonl"
        output.write_text("keep-this\n")
        previous = signal.getsignal(signal.SIGTERM)
        args = SimpleNamespace(output=output, max_threads=1024, max_fds=4096, interval=1,
                               duration=.1, state_dir=self.base / "state", load_pid_file=None)
        with self.assertRaises(FileExistsError):
            attribution.run(args)
        self.assertEqual("keep-this\n", output.read_text())
        self.assertEqual(previous, signal.getsignal(signal.SIGTERM))

    def test_exact_cli_aliases_and_defaults_for_controller(self):
        with patch.object(attribution.platform, "system", return_value="Linux"), patch.object(attribution, "run") as run:
            attribution.main(["--node-record", str(self.record), "--load-record", "delayed.json", "--output", "new.jsonl"])
        args = run.call_args.args[0]
        self.assertEqual([self.record], args.node_record)
        self.assertEqual(Path("delayed.json"), args.load_pid_file)
        self.assertEqual((1, 600, 1024, 4096), (args.interval, args.duration, args.max_threads, args.max_fds))

    def test_graceful_signal_emits_complete_and_flushes_jsonl(self):
        output = self.base / "signal.jsonl"
        args = SimpleNamespace(output=output, max_threads=1024, max_fds=4096, interval=1,
                               duration=600, state_dir=None, node_record=[self.record], load_pid_file=None)
        def sample(*args):
            os.kill(os.getpid(), signal.SIGTERM)
            return {"type": "sample", "monotonicNs": 1}
        with patch.object(attribution.Collector, "sample", side_effect=sample):
            attribution.run(args)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual(["metadata", "sample", "complete"], [row["type"] for row in rows])
        self.assertEqual("signal", rows[-1]["reason"])
        self.assertEqual(signal.SIGTERM, rows[-1]["signal"])


if __name__ == "__main__":
    unittest.main()
