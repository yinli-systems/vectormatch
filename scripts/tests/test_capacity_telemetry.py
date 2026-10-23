import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "capacity-telemetry.py"
SPEC = importlib.util.spec_from_file_location("capacity_telemetry_test", SCRIPT)
telemetry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(telemetry)


def stat_text(start=123, state="S"):
    fields = [state] + ["0"] * 49
    for index, value in {7: 5, 9: 2, 11: 100, 12: 20, 17: 3, 19: start, 20: 4096, 21: 7}.items():
        fields[index] = str(value)
    return "42 (worker) with ) odd name) " + " ".join(fields)


class ProcessSampleTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.proc = self.root / "proc"
        self.base = self.proc / "42"
        self.base.mkdir(parents=True)
        self.command = b"java\0-Xmx1g\0fake-main\0"
        (self.base / "cmdline").write_bytes(self.command)
        (self.base / "stat").write_text(stat_text())
        (self.base / "status").write_text("Name:\tprivate process name\nVmRSS:\t12 kB\nThreads:\t3\nvoluntary_ctxt_switches:\t11\n")
        (self.base / "io").write_text("read_bytes: 123\nwrite_bytes: 456\nsyscr: 9\n")
        self.record = self.root / "process.json"
        self.values = {"version": 1, "pid": 42, "startTicks": 123,
                       "commandSha256": hashlib.sha256(self.command).hexdigest(),
                       "arguments": ["never exported", "secret-sentinel"]}
        self.record.write_text(json.dumps(self.values))

    def test_verified_sample_parses_odd_comm_units_and_omits_command_arguments(self):
        result = telemetry.process_sample(self.record, self.proc)
        self.assertEqual("verified", result["status"])
        self.assertEqual(100, result["metrics"]["stat"]["value"]["userCpuTicks"])
        self.assertEqual(123, result["metrics"]["stat"]["value"]["startTicks"])
        self.assertEqual(12 * 1024, result["metrics"]["status"]["value"]["VmRSSBytes"])
        self.assertEqual(456, result["metrics"]["io"]["value"]["write_bytes"])
        self.assertNotIn("secret-sentinel", json.dumps(result))
        self.assertNotIn("private process name", json.dumps(result))

    def test_pid_reuse_or_changed_argv_refuses_all_metrics(self):
        for filename, content in (("stat", stat_text(start=999)), ("cmdline", b"other\0")):
            with self.subTest(filename=filename):
                (self.base / "stat").write_text(stat_text())
                (self.base / "cmdline").write_bytes(self.command)
                (self.base / filename).write_bytes(content.encode() if isinstance(content, str) else content)
                result = telemetry.process_sample(self.record, self.proc)
                self.assertEqual("identity-mismatch", result["status"])
                self.assertNotIn("metrics", result)

    def test_identity_change_during_collection_discards_metrics(self):
        identity = {name: self.values[name] for name in ("startTicks", "commandSha256")}
        with patch.object(telemetry, "proc_identity", side_effect=[identity, {**identity, "startTicks": 999}]):
            result = telemetry.process_sample(self.record, self.proc)
        self.assertEqual("identity-changed-during-read", result["status"])
        self.assertNotIn("metrics", result)

    def test_gone_zombie_or_malformed_record_is_explicit_missing_not_zero(self):
        (self.base / "stat").write_text(stat_text(state="Z"))
        result = telemetry.process_sample(self.record, self.proc)
        self.assertEqual("identity-unavailable", result["status"])
        self.assertEqual("ProcessLookupError", result["error"])
        for payload in ("42", "{", json.dumps({**self.values, "pid": True}), json.dumps({**self.values, "startTicks": 0})):
            with self.subTest(payload=payload):
                self.record.write_text(payload)
                self.assertEqual("record-unavailable", telemetry.process_sample(self.record, self.proc)["status"])

    def test_missing_io_does_not_erase_valid_other_metrics_or_fake_zero(self):
        (self.base / "io").unlink()
        result = telemetry.process_sample(self.record, self.proc)
        self.assertEqual("verified", result["status"])
        self.assertEqual("FileNotFoundError", result["metrics"]["io"]["error"])
        self.assertNotIn("value", result["metrics"]["io"])
        self.assertIn("value", result["metrics"]["stat"])

    def test_sampling_only_visits_fixed_node_records_and_explicit_load_record(self):
        with patch.object(telemetry, "process_sample", return_value={"status": "record-unavailable"}) as collect:
            row = telemetry.sample(self.root, self.record, proc_root=self.proc)
        self.assertEqual({"node-0", "node-1", "node-2", "load"}, set(row["processes"]))
        self.assertEqual([self.root / f"node-{index}/process.json" for index in range(3)] + [self.record],
                         [call.args[0] for call in collect.call_args_list])
        self.assertEqual("FileNotFoundError", row["network"]["device"]["error"])


class CounterParsersTest(unittest.TestCase):
    def test_cgroup_mapping_honors_delegated_root_and_escaped_mountpoint(self):
        result = telemetry.resolve_cgroup_leaf("0::/tenant/job\n", "28 1 0:28 /tenant /sys/fs/cgroup/cpu\\040slice rw - cgroup2 cgroup rw")
        self.assertEqual("/sys/fs/cgroup/cpu slice/job", result["directory"])
        self.assertEqual("/tenant", result["mountRoot"])

    def test_cgroup_mismatched_root_and_traversal_are_refused(self):
        for membership in ("0::/other/job", "0::/tenant/../other", "2:cpu:/tenant/job"):
            with self.subTest(membership=membership), self.assertRaises(ValueError):
                telemetry.resolve_cgroup_leaf(membership, "28 1 0:28 /tenant /sys/fs/cgroup rw - cgroup2 cgroup rw")

    def test_cpu_quota_and_zero_memory_counter_are_not_missing(self):
        self.assertEqual({"quotaMicros": 510000, "periodMicros": 100000, "quotaCpuUpperBound": 5.1},
                         telemetry.parse_cpu_max("510000 100000\n"))
        self.assertIsNone(telemetry.parse_cpu_max("max 100000")["quotaMicros"])
        self.assertEqual({"oom": 0, "oom_kill": 2}, telemetry.parse_key_counters("oom 0\noom_kill 2\n"))
        with self.assertRaises(ValueError):
            telemetry.parse_cpu_max("1000 0")
        with self.assertRaises(ValueError):
            telemetry.parse_key_counters("usage_usec -1")

    def test_network_selected_interface_only_and_udp_header_validation(self):
        text = "Inter-| Receive | Transmit\n lo: " + " ".join(["999"] * 16) + "\n podnet1: " + " ".join(map(str, range(16)))
        result = telemetry.parse_interface(text, "podnet1")
        self.assertEqual(0, result["receive"]["bytes"])
        self.assertEqual(8, result["transmit"]["bytes"])
        self.assertEqual(11, result["transmit"]["drop"])
        with self.assertRaises(KeyError):
            telemetry.parse_interface(text, "missing")
        self.assertEqual({"InDatagrams": 8, "RcvbufErrors": 1}, telemetry.parse_udp("Ip: x\nIp: 0\nUdp: InDatagrams RcvbufErrors\nUdp: 8 1\n"))
        with self.assertRaises(ValueError):
            telemetry.parse_udp("Udp: InDatagrams RcvbufErrors\nUdp: 8\n")

    def test_cgroup_samples_current_leaf_and_missing_file_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc, leaf = root / "proc", root / "group/job"
            (proc / "self").mkdir(parents=True)
            leaf.mkdir(parents=True)
            (proc / "self/cgroup").write_text("0::/tenant/job\n")
            (proc / "self/mountinfo").write_text(f"28 1 0:28 /tenant {root}/group rw - cgroup2 cgroup rw")
            (leaf / "cpu.stat").write_text("usage_usec 10\nnr_throttled 2\n")
            (leaf / "cpu.max").write_text("510000 100000")
            (leaf / "memory.current").write_text("0")
            result = telemetry.cgroup_sample(proc)
            self.assertEqual("mapped-v2-leaf", result["status"])
            self.assertEqual(0, result["metrics"]["memory.current"]["value"])
            self.assertEqual(10, result["metrics"]["cpu.stat"]["value"]["usage_usec"])
            self.assertEqual("FileNotFoundError", result["metrics"]["memory.events"]["error"])

    def test_cgroup_v1_maps_separate_cpu_memory_leaves_with_raw_units(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc, cpu, memory = root / "proc", root / "cpu", root / "memory"
            (proc / "self").mkdir(parents=True)
            cpu.mkdir()
            memory.mkdir()
            (proc / "self/cgroup").write_text("2:cpu,cpuacct:/docker/pod\n3:memory:/docker/pod\n0::/ignored\n")
            (proc / "self/mountinfo").write_text(
                f"28 1 0:28 /docker/pod {cpu} rw - cgroup cgroup rw,cpu,cpuacct\n"
                f"29 1 0:29 /docker/pod {memory} rw - cgroup cgroup rw,memory\n")
            (cpu / "cpu.stat").write_text("nr_throttled 2\nthrottled_time 1234\n")
            (cpu / "cpuacct.usage").write_text("9000")
            (cpu / "cpu.cfs_quota_us").write_text("-1")
            (memory / "memory.usage_in_bytes").write_text("0")
            result = telemetry.cgroup_sample(proc)
            self.assertEqual("mapped-v1-leaves", result["status"])
            self.assertEqual(2, len(result["hierarchies"]))
            self.assertEqual(1234, result["hierarchies"][0]["metrics"]["cpu.stat"]["value"]["throttled_time"])
            self.assertEqual(-1, result["hierarchies"][0]["metrics"]["cpu.cfs_quota_us"]["value"])
            self.assertEqual(0, result["hierarchies"][1]["metrics"]["memory.usage_in_bytes"]["value"])
            self.assertIn("unavailable-in-v1", result["v2OnlyFiles"]["memory.events"])


class BoundedRunTest(unittest.TestCase):
    def test_bounded_run_flushes_json_lines_refuses_overwrite_and_has_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(state_dir=Path(directory), output=Path(directory) / "out.jsonl",
                                   duration=.12, interval=.05, load_pid_file=None, interface="podnet1")
            with patch.object(telemetry, "metadata", return_value={}), patch.object(telemetry, "sample", return_value={"type": "sample"}):
                telemetry.run(args)
                with self.assertRaises(FileExistsError):
                    telemetry.run(args)
            rows = [json.loads(line) for line in args.output.read_text().splitlines()]
            self.assertEqual("metadata", rows[0]["type"])
            self.assertEqual("complete", rows[-1]["type"])
            self.assertEqual("duration", rows[-1]["reason"])
            self.assertGreaterEqual(rows[-1]["samples"], 2)
            self.assertEqual(list(range(rows[-1]["samples"])), [row["sequence"] for row in rows[1:-1]])

    @unittest.skipUnless(sys.platform.startswith("linux"), "Actual Linux /proc and signal integration")
    def test_sigterm_preserves_parseable_partial_evidence_and_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.jsonl"
            child = subprocess.Popen([sys.executable, "-B", str(SCRIPT), "--state-dir", directory,
                                      "--output", str(output), "--duration", "30", "--interval", ".05", "--interface", "lo"])
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if output.exists() and len(output.read_text().splitlines()) >= 2:
                        break
                    time.sleep(.02)
                else:
                    self.fail("Sampler did not flush a sample")
                child.send_signal(signal.SIGTERM)
                self.assertEqual(0, child.wait(timeout=5))
                rows = [json.loads(line) for line in output.read_text().splitlines()]
                self.assertEqual("signal", rows[-1]["reason"])
                self.assertEqual(signal.SIGTERM, rows[-1]["signal"])
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)

    def test_nonfinite_or_unbounded_durations_are_refused(self):
        for value in ("nan", "inf", "-1", "100000"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                telemetry.bounded_float(value, .1, 86400)


if __name__ == "__main__":
    unittest.main()
