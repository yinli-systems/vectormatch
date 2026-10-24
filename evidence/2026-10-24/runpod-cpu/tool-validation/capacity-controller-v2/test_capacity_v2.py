"""Inherit all20 frozen v1 guards, then cover the explicit CPU loopback-only adapter."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


V2 = load("cpu_capacity_v2_under_test", BASE / "capacity_v2.py")
OLD = load("cpu_capacity_v2_inherited_guards", BASE / "test_capacity.py")
OLD.C = V2


class InheritedCapacityGuards(OLD.CapacityGuards):
    pass


class LoopbackAdapterGuards(unittest.TestCase):
    def environment(self):
        return {V2.LOOPBACK_DECLARATION: V2.SCOPE, "VECTOR_CLUSTER_HOSTS": V2.LOOPBACK_HOSTS,
                "VECTOR_CLIENT_EGRESS_HOST": "127.0.0.1", "VECTOR_AERON_MTU_LENGTH": "1248"}

    def test_explicit_exact_cpu_loopback_is_accepted_without_other_environment_mutation(self):
        env = {**self.environment(), "JAVA_HOME": "/pinned/jdk", "UNRELATED": "preserved"}
        with patch.dict(os.environ, env, clear=True):
            returned = V2.cpu_loopback_network_environment("node")
            self.assertEqual(returned, env)
            self.assertEqual(dict(os.environ), env)

    def test_remote_mixed_malformed_and_noncanonical_networks_are_rejected(self):
        for hosts in ("10.0.0.1,10.0.0.2,10.0.0.3", "127.0.0.1,10.0.0.2,127.0.0.1",
                      "127.0.0.1,127.0.0.1", "127.0.0.1,127.0.0.1,127.0.0.1,127.0.0.1",
                      "127.0.0.1, 127.0.0.1,127.0.0.1", "127.0.0.2,127.0.0.2,127.0.0.2", "::1,::1,::1"):
            with self.subTest(hosts=hosts), patch.dict(os.environ, {**self.environment(), "VECTOR_CLUSTER_HOSTS": hosts}, clear=True), self.assertRaises(ValueError):
                V2.cpu_loopback_network_environment("node")

    def test_missing_scope_egress_or_canonical_mtu_and_non_node_roles_are_rejected(self):
        for key, value in ((V2.LOOPBACK_DECLARATION, None), (V2.LOOPBACK_DECLARATION, "THREE_HOSTS"),
                           ("VECTOR_CLIENT_EGRESS_HOST", None), ("VECTOR_CLIENT_EGRESS_HOST", "10.0.0.1"),
                           ("VECTOR_AERON_MTU_LENGTH", None), ("VECTOR_AERON_MTU_LENGTH", "01248"),
                           ("VECTOR_AERON_MTU_LENGTH", "1408"), ("VECTOR_CLIENT_EGRESS_PORT", "0")):
            env = self.environment()
            if value is None:
                env.pop(key)
            else:
                env[key] = value
            with self.subTest(key=key, value=value), patch.dict(os.environ, env, clear=True), self.assertRaises(ValueError):
                V2.cpu_loopback_network_environment("node")
        for role in ("gateway", "projector", "", None):
            with patch.dict(os.environ, self.environment(), clear=True), self.assertRaises(ValueError):
                V2.cpu_loopback_network_environment(role)

    def test_plan_pins_adapter_mapping_and_source_and_rejects_frozen_r1(self):
        p = V2.draft_plan("cpu-pilot-10000-w128-r2")
        self.assertEqual(p["launcherAdapter"]["mapping"]["launch"], "in-process original supervisor.start")
        for mutation in (lambda p: p.pop("launcherAdapter"),
                         lambda p: p["launcherAdapter"].update(adapterSourceSha256="0" * 64),
                         lambda p: p["launcherAdapter"]["mapping"].update(clusterHosts="10.0.0.1,10.0.0.2,10.0.0.3")):
            modified = copy.deepcopy(p)
            mutation(modified)
            modified["planSha256"] = V2.plan_identity(modified)
            with self.assertRaises(ValueError):
                V2.validate_plan(modified)
        with self.assertRaises(ValueError):
            V2.draft_plan("cpu-pilot-10000-w128-r1")

    def test_original_supervisor_only_network_function_changes(self):
        p = V2.draft_plan("cpu-pilot-offline-v2-adapter")
        supervisor = V2.import_file("cpu_v2_original_supervisor_guard", V2.REPO / "runtime/cloud/optimization-20261024/mux-window" / ("build-" + V2.REVISION) / "deploy/remote_service.py")
        names = p["launcherAdapter"]["mapping"]["preserved"]
        original = {name: getattr(supervisor, name) for name in names}
        metadata = V2.install_launcher_adapter(p, supervisor)
        self.assertTrue(metadata["preservedFunctionObjectsVerified"])
        self.assertIs(supervisor.network_environment, V2.cpu_loopback_network_environment)
        for name, value in original.items():
            self.assertIs(getattr(supervisor, name), value)

    def test_node_start_uses_in_process_original_start_and_restores_environment_even_on_failure(self):
        p = V2.draft_plan("cpu-pilot-offline-v2-start")
        supervisor = V2.import_file("cpu_v2_original_supervisor_start_guard", V2.REPO / "runtime/cloud/optimization-20261024/mux-window" / ("build-" + V2.REVISION) / "deploy/remote_service.py")
        V2.install_launcher_adapter(p, supervisor)
        original_environment = dict(os.environ)
        with tempfile.TemporaryDirectory() as temp:
            env = {**self.environment(), "JAVA_HOME": "/pinned/jdk"}
            def original_start(role, node, state, record):
                self.assertEqual((role, node), ("node", 1))
                self.assertEqual(dict(os.environ), env)
                self.assertEqual(state, Path(temp) / "node-1")
                self.assertEqual(record, state / "process.json")
            with patch.object(supervisor, "start", side_effect=original_start) as start, \
                 patch.object(V2.subprocess, "run", side_effect=AssertionError("No subprocess launcher allowed")):
                result = V2.start_cpu_node(supervisor, 1, temp, env)
            self.assertEqual(result["exitCode"], 0)
            self.assertFalse(result["subprocessLauncherUsed"])
            start.assert_called_once()
            self.assertEqual(dict(os.environ), original_environment)
            with patch.object(supervisor, "start", side_effect=ValueError("source start failed")):
                failed = V2.start_cpu_node(supervisor, 1, temp, env)
            self.assertEqual(failed["exitCode"], 1)
            self.assertEqual(dict(os.environ), original_environment)

    def test_uninstalled_adapter_or_invalid_node_cannot_launch(self):
        supervisor = Mock()
        for node in (-1, 3, True, "0"):
            with self.assertRaises(ValueError):
                V2.start_cpu_node(supervisor, node, "/unused", self.environment())
        with self.assertRaises(ValueError):
            V2.start_cpu_node(supervisor, 0, "/unused", self.environment())
        supervisor.start.assert_not_called()

    def test_original_node_argv_and_configuration_fingerprint_are_preserved(self):
        p = V2.draft_plan("cpu-pilot-offline-v2-argv")
        supervisor = V2.import_file("cpu_v2_original_supervisor_argv_guard", V2.REPO / "runtime/cloud/optimization-20261024/mux-window" / ("build-" + V2.REVISION) / "deploy/remote_service.py")
        V2.install_launcher_adapter(p, supervisor)
        env = V2.clean_environment(p)
        expected_fingerprint = supervisor.configuration_fingerprint("node", env)
        for node in range(3):
            state = Path(p["paths"]["state"]) / ("node-" + str(node))
            with patch.dict(os.environ, env, clear=True), patch.object(supervisor, "java", return_value=str(V2.JAVA)), \
                 patch.object(supervisor, "distribution", return_value=V2.RELEASE / "dist/cluster"):
                arguments, actual_environment = supervisor.command("node", node, state, "start")
            expected = [str(V2.JAVA), *V2.OPENS, "-Xmx2g", "-Dvm.process.identity=" + str(state),
                        "-Daeron.cluster.appointed.leader.id=0", "-Daeron.cluster.max.sessions=256",
                        "-Daeron.nak.unicast.delay=1000", "-Dvectormatch.node.dataPathMaxParkNs=1000000",
                        "-cp", str(V2.RELEASE / "dist/cluster/lib/*"), "io.vectormatch.cluster.ClusterNodeMain",
                        str(node), str(state.parent), "23000", "2", "800000", V2.LOOPBACK_HOSTS,
                        "capacity-350k-v1", "131072", "SHARED"]
            self.assertEqual(arguments, expected)
            self.assertEqual(supervisor.configuration_fingerprint("node", actual_environment), expected_fingerprint)

    def test_v2_is_python38_grammar_and_old_source_stays_frozen(self):
        ast.parse((BASE / "capacity_v2.py").read_text(), feature_version=(3, 8))
        self.assertEqual(V2.sha(BASE / "capacity.py"), "1680ad3da2c16914a8ac94f39f5d338602f001af52faf2100ec42176aa304d9c")


if __name__ == "__main__":
    unittest.main()
