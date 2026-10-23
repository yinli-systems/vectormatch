"""Ownership and configuration regression tests; no cloud or Java process required."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("remote_service", Path(__file__).with_name("remote_service.py"))
remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote)


class RemoteServiceTest(unittest.TestCase):
    @staticmethod
    def command_hash(args):
        return hashlib.sha256(b"\0".join(os.fsencode(arg) for arg in args) + b"\0").hexdigest()

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

    def test_receive_buffer_opt_in_preserves_optional_state_profile_position(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            original, environment = remote.command("node", 0, Path("/state/node-0"), "start")
            original_fingerprint = remote.configuration_fingerprint("node", environment)
            self.assertEqual(len(original[original.index(remote.MAINS["node"]) + 1:]), 6)
            os.environ["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"] = "131072"
            explicit, configured = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(explicit[-2:], ["default", "131072"])
            self.assertEqual(explicit[:-2], original)
            self.assertNotEqual(original_fingerprint, remote.configuration_fingerprint("node", configured))
            os.environ["VECTOR_STATE_PROFILE"] = "capacity-190k-v1"
            os.environ["VECTOR_OUTBOX_CAPACITY"] = "524288"
            os.environ["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"] = "1048576"
            capacity, _ = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(capacity[-3:], [settings["VECTOR_CLUSTER_HOSTS"], "capacity-190k-v1", "1048576"])

    def test_receive_buffer_bounds_are_validated_before_launch(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            for value in ("65536", "1048576", "4194304"):
                with self.subTest(value=value):
                    os.environ["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"] = value
                    args, environment = remote.command("node", 1, Path("/state/node-1"), "start")
                    self.assertEqual(args[-1], value)
                    self.assertEqual(environment["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"], value)
            for value in ("", "0", "65535", "4194305", "-1", "1m", "131072 -Xmx8g"):
                with self.subTest(value=value):
                    os.environ["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"] = value
                    with self.assertRaises(ValueError):
                        remote.command("node", 1, Path("/state/node-1"), "start")

    def test_absent_receive_buffer_retains_historical_fingerprint_and_is_node_only(self):
        environment = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4", "VECTOR_AERON_MTU_LENGTH": "1248"}
        historical = {"version": 1, "role": "node", "settings": {
            "VECTOR_CLUSTER_HOSTS": environment["VECTOR_CLUSTER_HOSTS"], "VECTOR_AERON_MTU_LENGTH": "1248",
            "VECTOR_APPOINTED_LEADER_ID": None, "VECTOR_MAX_CLUSTER_SESSIONS": None, "VECTOR_STATE_PROFILE": None}}
        expected = hashlib.sha256(json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(expected, remote.configuration_fingerprint("node", environment))
        changed = {**environment, "VECTOR_SOCKET_RECEIVE_BUFFER_BYTES": "1048576"}
        self.assertNotEqual(expected, remote.configuration_fingerprint("node", changed))
        self.assertEqual(remote.configuration_fingerprint("gateway", environment),
                         remote.configuration_fingerprint("gateway", changed))

    def test_changed_receive_buffer_refuses_to_hot_change_running_driver(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4",
                    "VECTOR_SOCKET_RECEIVE_BUFFER_BYTES": "131072"}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            state = Path(temporary)
            args, environment = remote.command("node", 0, state, "start")
            existing = {"pid": 42, "commandSha256": self.command_hash(args),
                        "configurationVersion": remote.CONFIGURATION_VERSION,
                        "configurationSha256": remote.configuration_fingerprint("node", environment)}
            os.environ["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"] = "1048576"
            with patch.object(remote, "record_state", return_value=("running", existing)), \
                    patch.object(remote.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "different arguments"):
                    remote.start("node", 0, state, state / "process.json")
                launch.assert_not_called()

    def test_driver_threading_opt_in_preserves_ninth_argument_position(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            original, _ = remote.command("node", 0, Path("/state/node-0"), "start")
            os.environ["VECTOR_DRIVER_THREADING_MODE"] = "SHARED"
            explicit, configured = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(explicit[:-3], original)
            self.assertEqual(explicit[-3:], ["default", "131072", "SHARED"])
            self.assertNotIn("VECTOR_SOCKET_RECEIVE_BUFFER_BYTES", configured)
            os.environ.update(VECTOR_STATE_PROFILE="capacity-190k-v1", VECTOR_OUTBOX_CAPACITY="524288",
                              VECTOR_SOCKET_RECEIVE_BUFFER_BYTES="1048576", VECTOR_DRIVER_THREADING_MODE="DEDICATED")
            dedicated, _ = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(dedicated[-3:], ["capacity-190k-v1", "1048576", "DEDICATED"])

    def test_nak_delay_is_strict_node_only_opt_in_and_changes_owned_command_identity(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            original, old_environment = remote.command("node", 0, Path("/state/node-0"), "start")
            old_fingerprint = remote.configuration_fingerprint("node", old_environment)
            self.assertFalse(any("aeron.nak" in arg for arg in original))
            for delay in ("1000", "100000", "1000000"):
                os.environ["VECTOR_NAK_UNICAST_DELAY_NS"] = delay
                arguments, environment = remote.command("node", 0, Path("/state/node-0"), "start")
                flag = "-Daeron.nak.unicast.delay=" + delay
                self.assertEqual([flag], [arg for arg in arguments if "aeron.nak" in arg])
                self.assertLess(arguments.index(flag), arguments.index("-cp"))
                self.assertEqual(original, [arg for arg in arguments if arg != flag])
                self.assertNotEqual(old_fingerprint, remote.configuration_fingerprint("node", environment))
                self.assertNotEqual(self.command_hash(original), self.command_hash(arguments))
                self.assertEqual(remote.configuration_fingerprint("gateway", old_environment),
                                 remote.configuration_fingerprint("gateway", environment))
            os.environ["VECTOR_CLIENT_EGRESS_HOST"] = "10.0.0.4"
            gateway, _ = remote.command("gateway", None, Path("/state/gateway"), "start")
            self.assertFalse(any("aeron.nak" in arg for arg in gateway), "The opt-in is node-only")

    def test_nak_delay_rejects_noncanonical_values_and_implicit_jvm_overrides(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            for value in ("", "999", "1000001", "-1000", "+1000", "01000", "1000ns", "1000.0", "1_000", "1000 ", "1000 -Xmx8g"):
                os.environ["VECTOR_NAK_UNICAST_DELAY_NS"] = value
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "NAK_UNICAST_DELAY_NS"):
                    remote.command("node", 0, Path("/state/node-0"), "start")
            os.environ["VECTOR_NAK_UNICAST_DELAY_NS"] = "1000"
            for name in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
                with patch.dict(os.environ, {name: "-Daeron.nak.unicast.retry.delay.ratio=100"}):
                    with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Hidden Aeron NAK"):
                        remote.command("node", 0, Path("/state/node-0"), "start")

    def test_absent_nak_keeps_exact_previous_configuration_fingerprint(self):
        environment = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4", "VECTOR_AERON_MTU_LENGTH": "1248",
                       "VECTOR_DRIVER_THREADING_MODE": "SHARED", "VECTOR_SOCKET_RECEIVE_BUFFER_BYTES": "131072"}
        old_settings = {name: environment.get(name) for name in remote.CONFIGURATION_KEYS["node"]}
        old_settings.update(VECTOR_DRIVER_THREADING_MODE="SHARED", VECTOR_SOCKET_RECEIVE_BUFFER_BYTES="131072")
        expected = hashlib.sha256(json.dumps({"version": 1, "role": "node", "settings": old_settings},
                                            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(expected, remote.configuration_fingerprint("node", environment))
        default = {**environment, "VECTOR_NAK_UNICAST_DELAY_NS": "1000"}
        tuned = {**environment, "VECTOR_NAK_UNICAST_DELAY_NS": "100000"}
        self.assertEqual(3, len({expected, remote.configuration_fingerprint("node", default),
                               remote.configuration_fingerprint("node", tuned)}))

    def test_driver_threading_rejects_every_non_whitelisted_value(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            for invalid in ("", "shared", "dedicated", "INVOKER", "SHARED_NETWORK", "SHARED ", "DEDICATED -Xmx8g"):
                os.environ["VECTOR_DRIVER_THREADING_MODE"] = invalid
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "DRIVER_THREADING_MODE"):
                    remote.command("node", 0, Path("/state/node-0"), "start")

    def test_absent_threading_keeps_previous_network_fingerprint_and_is_node_only(self):
        environment = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4", "VECTOR_AERON_MTU_LENGTH": "1248",
                       "VECTOR_SOCKET_RECEIVE_BUFFER_BYTES": "1048576"}
        # Byte-for-byte fingerprint contract from the previous receive-only release.
        historical = {"version": 1, "role": "node", "settings": {
            "VECTOR_CLUSTER_HOSTS": environment["VECTOR_CLUSTER_HOSTS"], "VECTOR_AERON_MTU_LENGTH": "1248",
            "VECTOR_APPOINTED_LEADER_ID": None, "VECTOR_MAX_CLUSTER_SESSIONS": None, "VECTOR_STATE_PROFILE": None,
            "VECTOR_SOCKET_RECEIVE_BUFFER_BYTES": "1048576"}}
        expected = hashlib.sha256(json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(expected, remote.configuration_fingerprint("node", environment))
        shared = {**environment, "VECTOR_DRIVER_THREADING_MODE": "SHARED"}
        dedicated = {**environment, "VECTOR_DRIVER_THREADING_MODE": "DEDICATED"}
        self.assertNotEqual(expected, remote.configuration_fingerprint("node", shared))
        self.assertNotEqual(remote.configuration_fingerprint("node", shared), remote.configuration_fingerprint("node", dedicated))
        self.assertEqual(remote.configuration_fingerprint("gateway", shared), remote.configuration_fingerprint("gateway", dedicated))

    def test_changed_threading_refuses_to_hot_change_running_driver(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4", "VECTOR_DRIVER_THREADING_MODE": "SHARED"}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            state = Path(temporary)
            args, environment = remote.command("node", 0, state, "start")
            existing = {"pid": 42, "commandSha256": self.command_hash(args),
                        "configurationVersion": remote.CONFIGURATION_VERSION,
                        "configurationSha256": remote.configuration_fingerprint("node", environment)}
            os.environ["VECTOR_DRIVER_THREADING_MODE"] = "DEDICATED"
            with patch.object(remote, "record_state", return_value=("running", existing)), \
                    patch.object(remote.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "different arguments"):
                    remote.start("node", 0, state, state / "process.json")
                launch.assert_not_called()

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

    def test_capacity_state_profile_is_explicit_bounded_node_configuration(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4",
                    "VECTOR_STATE_PROFILE": "capacity-190k-v1", "VECTOR_OUTBOX_CAPACITY": "524288",
                    "VECTOR_MAX_HEAP": "2g"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            args, environment = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(args[-7:], ["0", "/state", "19000", "2", "524288",
                                          settings["VECTOR_CLUSTER_HOSTS"], "capacity-190k-v1"])
            self.assertIn("-Xmx2g", args)
            self.assertNotEqual(remote.configuration_fingerprint("node", environment),
                                remote.configuration_fingerprint("node", {**environment, "VECTOR_STATE_PROFILE": "default"}))
            os.environ["VECTOR_OUTBOX_CAPACITY"] = "262144"
            with self.assertRaisesRegex(ValueError, "requires outbox"):
                remote.command("node", 0, Path("/state/node-0"), "start")
            os.environ["VECTOR_STATE_PROFILE"] = "unknown-profile"
            with self.assertRaisesRegex(ValueError, "VECTOR_STATE_PROFILE"):
                remote.command("node", 0, Path("/state/node-0"), "start")

    def test_350k_profile_requires_exact_outbox_and_explicit_256_sessions(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4",
                    "VECTOR_STATE_PROFILE": "capacity-350k-v1", "VECTOR_OUTBOX_CAPACITY": "800000",
                    "VECTOR_MAX_CLUSTER_SESSIONS": "256", "VECTOR_MAX_HEAP": "2g"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            args, environment = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(args[-7:], ["0", "/state", "19000", "2", "800000",
                                        settings["VECTOR_CLUSTER_HOSTS"], "capacity-350k-v1"])
            self.assertEqual(["-Daeron.cluster.max.sessions=256"],
                             [arg for arg in args if arg.startswith("-Daeron.cluster.max.sessions=")])
            fingerprint = remote.configuration_fingerprint("node", environment)
            for name, changed in (("VECTOR_MAX_CLUSTER_SESSIONS", "128"),
                                  ("VECTOR_STATE_PROFILE", "capacity-190k-v1")):
                self.assertNotEqual(fingerprint,
                                    remote.configuration_fingerprint("node", {**environment, name: changed}))
            os.environ["VECTOR_SOCKET_RECEIVE_BUFFER_BYTES"] = "1048576"
            os.environ["VECTOR_DRIVER_THREADING_MODE"] = "DEDICATED"
            args, _ = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertEqual(["capacity-350k-v1", "1048576", "DEDICATED"], args[-3:])
            for capacity in ("524288", "799999", "800001"):
                os.environ["VECTOR_OUTBOX_CAPACITY"] = capacity
                with self.subTest(capacity=capacity), self.assertRaisesRegex(ValueError, "requires outbox capacity 800000"):
                    remote.command("node", 0, Path("/state/node-0"), "start")
            os.environ["VECTOR_OUTBOX_CAPACITY"] = "800000"
            for profile in ("capacity-350k", "CAPACITY_350K_V1", "capacity-350k-v1 "):
                os.environ["VECTOR_STATE_PROFILE"] = profile
                with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, "VECTOR_STATE_PROFILE"):
                    remote.command("node", 0, Path("/state/node-0"), "start")

    def test_appointed_leader_is_explicit_test_only_node_configuration(self):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4"}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            normal, original = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertFalse(any("appointed.leader" in arg for arg in normal))
            os.environ["VECTOR_APPOINTED_LEADER_ID"] = "0"
            pinned, configured = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertIn("-Daeron.cluster.appointed.leader.id=0", pinned)
            self.assertNotEqual(remote.configuration_fingerprint("node", original),
                                remote.configuration_fingerprint("node", configured))
            os.environ["VECTOR_MAX_CLUSTER_SESSIONS"] = "128"
            more_sessions, expanded = remote.command("node", 0, Path("/state/node-0"), "start")
            self.assertIn("-Daeron.cluster.max.sessions=128", more_sessions)
            self.assertNotEqual(remote.configuration_fingerprint("node", configured),
                                remote.configuration_fingerprint("node", expanded))
            for invalid_sessions in ("0", "257", "not-an-int"):
                os.environ["VECTOR_MAX_CLUSTER_SESSIONS"] = invalid_sessions
                with self.assertRaises(ValueError):
                    remote.command("node", 0, Path("/state/node-0"), "start")
            os.environ.pop("VECTOR_MAX_CLUSTER_SESSIONS")
            for invalid in ("-1", "3", "0 -Xmx8g", "invalid"):
                os.environ["VECTOR_APPOINTED_LEADER_ID"] = invalid
                with self.assertRaisesRegex(ValueError, "APPOINTED_LEADER"):
                    remote.command("node", 0, Path("/state/node-0"), "start")

    def test_changed_mtu_repeated_start_refuses_the_existing_process(self):
        configuration = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4",
                         "VECTOR_AERON_MTU_LENGTH": "1248"}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, configuration, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            state = Path(temporary)
            args, environment = remote.command("node", 1, state, "start")
            existing = {"pid": 42, "commandSha256": self.command_hash(args),
                        "configurationVersion": remote.CONFIGURATION_VERSION,
                        "configurationSha256": remote.configuration_fingerprint("node", environment)}
            os.environ["VECTOR_AERON_MTU_LENGTH"] = "1216"
            self.assertEqual(args, remote.command("node", 1, state, "start")[0], "MTU is not an argv setting")
            with patch.object(remote, "record_state", return_value=("running", existing)), \
                    patch.object(remote.subprocess, "Popen") as launch:
                with self.assertRaisesRegex(ValueError, "different non-secret configuration"):
                    remote.start("node", 1, state, state / "process.json")
                launch.assert_not_called()

    def test_existing_process_without_configuration_fingerprint_requires_explicit_stop(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        existing = {"pid": 42, "commandSha256": self.command_hash(args)}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("running", existing)), \
                patch.object(remote.subprocess, "Popen") as launch:
            state = Path(temporary)
            with self.assertRaisesRegex(ValueError, "no recognized configuration fingerprint"):
                remote.start("node", 0, state, state / "process.json")
            launch.assert_not_called()

    def test_matching_configuration_keeps_repeated_start_idempotent(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        existing = {"pid": 42, "commandSha256": self.command_hash(args),
                    "configurationVersion": remote.CONFIGURATION_VERSION,
                    "configurationSha256": remote.configuration_fingerprint("node", environment)}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("running", existing)), \
                patch.object(remote.subprocess, "Popen") as launch:
            state = Path(temporary)
            remote.start("node", 0, state, state / "process.json")
            launch.assert_not_called()

    def test_configuration_fingerprint_excludes_credentials_and_jdbc_urls(self):
        environment = {"VECTOR_CLUSTER_HOSTS": "10.0.0.2,10.0.0.3,10.0.0.4", "VM_CLUSTER_ID": "lineage-one",
                       "VM_PG_URL": "jdbc:postgresql://user:short-password@host/db?password=1234",
                       "VM_PG_PASSWORD": "1234", "VM_PG_USER": "database-user", "OTHER_API_TOKEN": "short-token"}
        real_sha = hashlib.sha256
        with patch.object(remote.hashlib, "sha256", wraps=real_sha) as hashed:
            original = remote.configuration_fingerprint("projector", environment)
            encoded = hashed.call_args.args[0]
            for excluded in ("VM_PG_URL", "VM_PG_PASSWORD", "VM_PG_USER", "OTHER_API_TOKEN",
                             "short-password", "1234", "database-user", "short-token", "jdbc:"):
                self.assertNotIn(excluded.encode(), encoded)
        changed_secrets = {**environment, "VM_PG_URL": "jdbc:postgresql://another-host/other-db?password=other",
                           "VM_PG_PASSWORD": "5678", "VM_PG_USER": "another-user", "OTHER_API_TOKEN": "other"}
        self.assertEqual(original, remote.configuration_fingerprint("projector", changed_secrets))
        self.assertNotEqual(original, remote.configuration_fingerprint("projector", {**environment, "VM_CLUSTER_ID": "lineage-two"}))

    def test_stop_uses_recorded_identity_even_after_environment_has_changed(self):
        legacy_record = {"pid": 42, "startTicks": 100, "commandSha256": "recorded-command"}
        with tempfile.TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {"VECTOR_AERON_MTU_LENGTH": "bad-new-setting", "VECTOR_CLUSTER_HOSTS": "bad-hosts"}, clear=True), \
                patch.object(remote, "record_state", side_effect=[("running", legacy_record),
                             ("running", legacy_record), ("stopped", legacy_record)]), \
                patch.object(remote, "command") as command, \
                patch.object(remote, "configuration_fingerprint") as fingerprint, \
                patch.object(remote.os, "pidfd_open", return_value=999, create=True), \
                patch.object(remote.signal, "pidfd_send_signal", create=True) as send, \
                patch.object(remote.os, "close"):
            state = Path(temporary)
            remote.stop(state, state / "process.json")
            send.assert_called_once_with(999, remote.signal.SIGTERM)
            command.assert_not_called()
            fingerprint.assert_not_called()

    def test_start_waits_for_missing_then_pre_exec_command_then_exact_identity(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        expected = {"startTicks": 100, "commandSha256": self.command_hash(args)}
        child = Mock(pid=42, returncode=None)
        child.poll.return_value = None
        clock = [0.0]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("stopped", None)), \
                patch.object(remote.subprocess, "Popen", return_value=child), \
                patch.object(remote, "proc_identity", side_effect=[None,
                    {"startTicks": 100, "commandSha256": "pre-exec-command"}, expected]) as identity, \
                patch.object(remote.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(remote.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            state = Path(temporary)
            record_path = state / "process.json"
            remote.start("node", 0, state, record_path)
            record = json.loads(record_path.read_text())
            self.assertEqual(record["pid"], 42)
            self.assertEqual(record["startTicks"], expected["startTicks"])
            self.assertEqual(record["commandSha256"], expected["commandSha256"])
            self.assertEqual(identity.call_count, 3)
            child.terminate.assert_not_called()
            self.assertLessEqual(clock[0], 2.3)

    def test_start_identity_timeout_preserves_previous_record_and_stops_only_its_child(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        child = Mock(pid=42, returncode=None)
        child.poll.return_value = None
        child.wait.return_value = 0
        clock = [0.0]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("stopped", None)), \
                patch.object(remote.subprocess, "Popen", return_value=child), \
                patch.object(remote, "proc_identity", return_value={"startTicks": 100, "commandSha256": "wrong-command"}), \
                patch.object(remote, "write_json") as write, \
                patch.object(remote.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(remote.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            state = Path(temporary)
            record_path = state / "process.json"
            record_path.write_text("preserve previous stopped record\n")
            with self.assertRaisesRegex(RuntimeError, "identity was not established"):
                remote.start("node", 0, state, record_path)
            self.assertEqual(record_path.read_text(), "preserve previous stopped record\n")
            write.assert_not_called()
            child.terminate.assert_called_once_with()
            child.wait.assert_called_once_with(timeout=10)
            self.assertAlmostEqual(clock[0], 2.0)

    def test_start_child_exit_during_identity_wait_fails_fast_without_a_pid_record(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        child = Mock(pid=42, returncode=7)
        child.poll.side_effect = [None, 7, 7]
        clock = [0.0]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("stopped", None)), \
                patch.object(remote.subprocess, "Popen", return_value=child), \
                patch.object(remote, "proc_identity", return_value=None) as identity, \
                patch.object(remote, "write_json") as write, \
                patch.object(remote.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(remote.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            state = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "exited with code 7"):
                remote.start("node", 0, state, state / "process.json")
            self.assertFalse((state / "process.json").exists())
            self.assertEqual(identity.call_count, 1)
            write.assert_not_called()
            child.terminate.assert_not_called()
            child.wait.assert_not_called()
            self.assertLess(clock[0], 0.02)

    def test_start_refuses_changed_start_ticks_even_if_command_later_matches(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        child = Mock(pid=42, returncode=None)
        child.poll.return_value = None
        clock = [0.0]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("stopped", None)), \
                patch.object(remote.subprocess, "Popen", return_value=child), \
                patch.object(remote, "proc_identity", side_effect=[
                    {"startTicks": 100, "commandSha256": "pre-exec-command"},
                    {"startTicks": 101, "commandSha256": self.command_hash(args)}]), \
                patch.object(remote, "write_json") as write, \
                patch.object(remote.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(remote.time, "sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            state = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "start time changed"):
                remote.start("node", 0, state, state / "process.json")
            write.assert_not_called()
            self.assertFalse((state / "process.json").exists())

    def test_start_child_exit_after_matching_sample_does_not_write_record(self):
        args, environment = ["/jdk/bin/java", "Main"], {"VECTOR_AERON_MTU_LENGTH": "1248"}
        child = Mock(pid=42, returncode=3)
        child.poll.side_effect = [None, 3, 3]
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(remote, "command", return_value=(args, environment)), \
                patch.object(remote, "record_state", return_value=("stopped", None)), \
                patch.object(remote.subprocess, "Popen", return_value=child), \
                patch.object(remote, "proc_identity", return_value={"startTicks": 100, "commandSha256": self.command_hash(args)}), \
                patch.object(remote, "write_json") as write:
            state = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "exited with code 3"):
                remote.start("node", 0, state, state / "process.json")
            self.assertFalse((state / "process.json").exists())
            write.assert_not_called()
            child.terminate.assert_not_called()
            child.wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
