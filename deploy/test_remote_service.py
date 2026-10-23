"""Ownership and configuration regression tests; no cloud or Java process required."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("remote_service", Path(__file__).with_name("remote_service.py"))
remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote)


class RemoteServiceTest(unittest.TestCase):
    def test_proc_stat_accepts_parentheses_and_spaces_in_process_name(self):
        fields = ["S"] + ["0"] * 18 + ["123456"] + ["0"] * 5
        command = b"/usr/bin/java\0Main\0"
        def fake_read_text(path):
            self.assertEqual(str(path), "/proc/42/stat")
            return "42 (java worker) test) " + " ".join(fields)
        with patch.object(Path, "read_text", fake_read_text), patch.object(Path, "read_bytes", return_value=command):
            self.assertEqual(remote.proc_identity(42), {
                "startTicks": 123456, "commandSha256": hashlib.sha256(command).hexdigest()})

    def test_zombie_is_stopped(self):
        with patch.object(Path, "read_text", return_value="42 (java) Z " + "0 " * 25):
            self.assertIsNone(remote.proc_identity(42))

    def test_start_time_prevents_pid_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "process.json"
            remote.write_json(record, {"version": 1, "pid": 42, "startTicks": 1, "commandSha256": "abc"})
            with patch.object(remote, "proc_identity", return_value={"startTicks": 2, "commandSha256": "abc"}):
                self.assertEqual(remote.record_state(record)[0], "identity-mismatch")

    def test_stop_refuses_mismatched_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            with patch.object(remote, "record_state", return_value=("identity-mismatch", {"pid": 42})), \
                    patch.object(remote.os, "pidfd_open", create=True) as opened:
                with self.assertRaisesRegex(ValueError, "unrelated process"):
                    remote.stop(state, state / "process.json")
                opened.assert_not_called()

    def test_pidfd_stop_rechecks_identity_before_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = {"pid": 42}
            with patch.object(remote, "record_state", side_effect=[("running", record), ("identity-mismatch", record)]), \
                    patch.object(remote.os, "pidfd_open", return_value=999, create=True), \
                    patch.object(remote.os, "close") as closed, \
                    patch.object(remote.signal, "pidfd_send_signal", create=True) as send:
                with self.assertRaisesRegex(ValueError, "no signal sent"):
                    remote.stop(Path(temporary), Path(temporary) / "process.json")
                send.assert_not_called()
                closed.assert_called_once_with(999)

    def test_network_rejects_duplicate_nodes_and_requires_client_address(self):
        with patch.dict(os.environ, {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.2,10.0.0.4"}, clear=True):
            with self.assertRaisesRegex(ValueError, "distinct"):
                remote.network_environment("node")
        with patch.dict(os.environ, {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}, clear=True):
            with self.assertRaisesRegex(ValueError, "EGRESS"):
                remote.network_environment("gateway")

    def test_node_command_uses_sync_two_and_conservative_mtu(self):
        with patch.dict(os.environ, {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            args, environment = remote.command("node", 1, Path("/state/node-1"), "start")
            self.assertEqual(args[-6:], ["1", "/state", "19000", "2", "65536", "10.0.0.2,10.0.0.3,10.0.0.4"])
            self.assertEqual(environment["VECTOR_AERON_MTU_LENGTH"], "1248")
            self.assertIn("-Xmx1g", args)

    def test_database_secrets_are_not_command_arguments(self):
        configuration = {"VM_PG_URL": "jdbc:postgresql://127.0.0.1/test", "VM_CLUSTER_ID": "generation-42",
                         "VM_PG_PASSWORD": "secret-value"}
        with patch.dict(os.environ, configuration, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/projector")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            args, environment = remote.command("projector", None, Path("/state/projector"), "init")
            self.assertNotIn("secret-value", json.dumps(args))
            self.assertNotIn(configuration["VM_PG_URL"], json.dumps(args))
            self.assertEqual(environment["VM_PG_PASSWORD"], "secret-value")
            self.assertEqual(args[-1], "init")


if __name__ == "__main__":
    unittest.main()
