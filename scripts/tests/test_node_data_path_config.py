import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


remote = module("node_idle_remote", ROOT / "deploy/remote_service.py")
verify = module("node_idle_verify", ROOT / "scripts/verify-capacity-config.py")
fixtures = module("node_idle_fixture", ROOT / "scripts/tests/test_capacity_config.py")
ENV = "VECTOR_DATA_PATH_MAX_PARK_NS"
PROPERTY = "vectormatch.node.dataPathMaxParkNs"


def evidence(maximum=100000, node=0, started=None):
    if started is None:
        started = (f"VECTOR_CLUSTER_STARTED node={node} driverThreading=SHARED driverIdleMaxSpins=10 "
                   f"driverIdleMaxYields=5 driverIdleMinParkNs=1000 driverIdleMaxParkNs={maximum}")
    result = [started + f" nodeDataPathIdlePolicyVersion=1 nodeDataPathMaxParkNs={maximum} nodeDataPathIdleInstancesDistinct=true"]
    for index, role in enumerate(verify.NODE_DATA_PATH_ROLES, 1):
        yields = 5 if role.startswith("driver-") else 20
        runner_selected = not role.startswith("driver-") or role == "driver-shared"
        configuration = (f"BackoffIdleStrategy{{alias=backoff,maxSpins=10,maxYields={yields},"
                         f"minParkPeriodNs=1000,maxParkPeriodNs={maximum}}}")
        result.append(f"VECTOR_NODE_DATA_PATH_IDLE node={node} role={role} instanceId={index} runnerSelected={str(runner_selected).lower()} "
                      f"strategyClass=org.agrona.concurrent.BackoffIdleStrategy configuration={configuration}")
    return "\n".join(result) + "\n"


class NodeDataPathConfigurationTest(unittest.TestCase):
    def launcher(self, changes=None, role="node"):
        settings = {"VECTOR_CLUSTER_HOSTS": "10.0.0.1,10.0.0.2,10.0.0.3", "VECTOR_CLIENT_EGRESS_HOST": "10.0.0.4",
                    **(changes or {})}
        with patch.dict(os.environ, settings, clear=True), \
                patch.object(remote, "distribution", return_value=Path("/bundle/dist/cluster")), \
                patch.object(remote, "java", return_value="/jdk/bin/java"):
            return remote.command(role, 0 if role == "node" else None, Path("/state/node-0"), "start")

    def test_unset_argv_and_historical_fingerprint_are_unchanged(self):
        arguments, environment = self.launcher()
        self.assertFalse(any(PROPERTY in value for value in arguments))
        historical = {"version": 1, "role": "node", "settings": {name: environment.get(name)
                      for name in remote.CONFIGURATION_KEYS["node"]}}
        expected = hashlib.sha256(json.dumps(historical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(expected, remote.configuration_fingerprint("node", environment))

    def test_explicit_default_and_tuned_values_add_one_node_jvm_flag_only(self):
        original, old_environment = self.launcher()
        identities = {remote.configuration_fingerprint("node", old_environment)}
        for maximum in ("1000", "100000", "1000000"):
            args, environment = self.launcher({ENV: maximum})
            flag = f"-D{PROPERTY}={maximum}"
            self.assertEqual([flag], [value for value in args if PROPERTY in value])
            self.assertLess(args.index(flag), args.index("-cp"))
            self.assertEqual(original, [value for value in args if value != flag])
            identities.add(remote.configuration_fingerprint("node", environment))
            gateway, gateway_environment = self.launcher({ENV: maximum}, "gateway")
            self.assertFalse(any(PROPERTY in value for value in gateway))
            self.assertEqual(remote.configuration_fingerprint("gateway", old_environment),
                             remote.configuration_fingerprint("gateway", gateway_environment))
        self.assertEqual(4, len(identities))

    def test_invalid_canonical_values_and_hidden_jvm_environment_are_rejected(self):
        for value in ("", "999", "1000001", "+1000", "01000", "1e5", "100us", "1000 ", " 1000", "1_000", "9" * 400):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.launcher({ENV: value})
        for name in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
            for option in (f"-D{PROPERTY}=100000", "-Dhidden=vectormatch.node.dataPathMaxParkNs=100000"):
                for maximum in (None, "100000"):
                    with self.subTest(name=name, option=option, maximum=maximum), self.assertRaises(ValueError):
                        self.launcher({name: option, **({ENV: maximum} if maximum else {})})
            with self.assertRaises(ValueError):
                self.launcher({ENV: "100000", name: "-Daeron.cluster.idle.strategy=spin"})
        # Existing non-profile JVM idle properties keep their historical path.
        self.launcher({"JAVA_TOOL_OPTIONS": "-Daeron.cluster.idle.strategy=backoff"})

    def test_node_property_is_optional_typed_exact_once_and_before_classpath(self):
        self.assertIsNone(verify.node_data_path_max_park({}))
        verify.verify_node_data_path_jvm_arguments(["java", "-cp", "/lib/*", "Main"], {})
        for value in (True, "100000", 100000.0, None, 999, 1000001):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                verify.node_data_path_max_park({"nodeDataPathMaxParkNs": value})
        fixed = {"nodeDataPathMaxParkNs": 100000}
        flag = f"-D{PROPERTY}=100000"
        verify.verify_node_data_path_jvm_arguments(["java", flag, "-cp", "/lib/*", "Main"], fixed)
        for args in (["java", "-cp", "/lib/*", "Main", flag], ["java", flag],
                     ["java", flag, flag, "-cp", "/lib/*", "Main"],
                     ["java", f"-D{PROPERTY}=0100000", "-cp", "/lib/*", "Main"],
                     ["java", f"-Dhidden={flag}", "-cp", "/lib/*", "Main"]):
            with self.subTest(args=args), self.assertRaises(AssertionError):
                verify.verify_node_data_path_jvm_arguments(args, fixed)
        with self.assertRaises(AssertionError):
            verify.verify_node_data_path_jvm_arguments(["java", flag, "-cp", "/lib/*", "Main"], {})

    def test_runtime_evidence_covers_actual_parameters_and_distinct_instances(self):
        for maximum in (100000, 1000000):
            fixed = {"nodeDataPathMaxParkNs": maximum, "driverThreadingArgument": "SHARED"}
            verify.verify_node_data_path_startup(fixed, evidence(maximum), 0)
        fixed = {"nodeDataPathMaxParkNs": 100000}
        valid = evidence()
        invalid = [valid.replace("role=service", "role=unknown"), valid.replace("instanceId=8", "instanceId=7"),
                   valid.replace("maxYields=20", "maxYields=5"), valid.replace("minParkPeriodNs=1000", "minParkPeriodNs=100"),
                   valid.replace("role=driver-sender instanceId=2 runnerSelected=false", "role=driver-sender instanceId=2 runnerSelected=true"),
                   valid.replace("nodeDataPathMaxParkNs=100000", "nodeDataPathMaxParkNs=1000000"),
                   valid.replace("role=service instanceId=8", "role=service role=service instanceId=8"),
                   "\n".join(valid.splitlines()[:-1]) + "\n"]
        for value in invalid:
            with self.subTest(value=value[-150:]), self.assertRaises(AssertionError):
                verify.verify_node_data_path_startup(fixed, value, 0)
        with self.assertRaises(AssertionError):
            verify.verify_node_data_path_startup(fixed, valid, 1)
        with self.assertRaises(AssertionError):
            verify.verify_node_data_path_startup({}, valid, 0)
        verify.verify_node_data_path_startup({}, "legacy log without opt-in")
        # Suppliers may create several independent instances for one role.
        verify.verify_node_data_path_startup(fixed, valid + valid.splitlines()[-1].replace("instanceId=8", "instanceId=9") + "\n", 0)

    def fixture(self, root, maximum):
        helper = fixtures.CapacityConfigTest()
        directory = helper.terminal_unknown_fixture(root)
        campaign_path = root / "campaign.json"
        campaign = json.loads(campaign_path.read_text())
        campaign["fixed"].update(nodeDataPathMaxParkNs=maximum, driverIdleMaxParkNs=maximum)
        campaign_path.write_text(json.dumps(campaign))
        for node in range(3):
            path = directory / f"node{node}/process.json"
            record = json.loads(path.read_text())
            record["arguments"].insert(record["arguments"].index("-cp"), f"-D{PROPERTY}={maximum}")
            record["commandSha256"] = verify.command_sha256(record["arguments"])
            path.write_text(json.dumps(record))
            log = directory / f"node{node}/process.log"
            started = next(line for line in log.read_text().splitlines() if line.startswith("VECTOR_CLUSTER_STARTED "))
            started = started.replace("driverIdleMaxParkNs=1000000", f"driverIdleMaxParkNs={maximum}")
            log.write_text(evidence(maximum, node, started))
        return directory

    def test_explicit_factor_enters_real_annotation_and_retains_failed_scope(self):
        identities = set()
        for maximum in (100000, 1000000):
            with self.subTest(maximum=maximum), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = self.fixture(root, maximum)
                with contextlib.redirect_stdout(io.StringIO()):
                    verify.main(root, include_failed_unknown=True)
                trial = json.loads((directory / "trial.json").read_text())
                fixed = trial["fixedNodeConfiguration"]
                self.assertEqual(maximum, fixed["nodeDataPathMaxParkNs"])
                self.assertEqual(20, fixed["nodeDataPathIdleAgentMaxYields"])
                self.assertEqual(5, fixed["driverIdleMaxYields"])
                self.assertEqual(maximum, fixed["driverIdleMaxParkNs"])
                identities.add(hashlib.sha256(json.dumps(fixed, sort_keys=True).encode()).hexdigest())
                receipt = json.loads((directory / "configuration-verification.json").read_text())
                self.assertTrue(receipt["configurationOnly"])
                self.assertFalse(receipt["businessCorrectnessVerified"])
                self.assertFalse((directory / "result.json").exists())
                self.assertIn("node0/process.log", receipt["rawSha256"])
        self.assertEqual(2, len(identities))

    def test_mismatched_actual_agent_evidence_fails_before_annotation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.fixture(root, 100000)
            before = (directory / "trial.json").read_bytes()
            log = directory / "node2/process.log"
            log.write_text(log.read_text().replace("maxYields=20", "maxYields=5"))
            with self.assertRaises(AssertionError):
                verify.main(root, include_failed_unknown=True)
            self.assertEqual(before, (directory / "trial.json").read_bytes())
            self.assertFalse((directory / "configuration-verification.json").exists())

    def test_node_tuning_cannot_be_added_to_load_generator_flags(self):
        trial = {"workers": 128, "loadGeneratorJvmArguments": [f"-D{PROPERTY}=100000"]}
        with self.assertRaisesRegex(AssertionError, "Disallowed load-generator JVM"):
            verify.load_generator_jvm_arguments(trial, {}, {"nodeDataPathMaxParkNs": 100000})


if __name__ == "__main__":
    unittest.main()
