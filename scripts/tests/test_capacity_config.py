import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("capacity_config", ROOT / "scripts/verify-capacity-config.py")
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)

DRIVER_FLAG = "-Dvectormatch.capacity.client.driver="


class CapacityConfigTest(unittest.TestCase):
    def setUp(self):
        self.trial = {"id": "controlled-mode", "rate": 15000, "arrivals": 190000,
                      "workers": 128, "profile": "extended-190k-128"}
        self.release = "/opt/vectormatch/releases/" + "a" * 40

    def runtime(self, mode="isolated", **changes):
        return {"clientDriverMode": mode, "clientDriverCount": 1 if mode == "shared" else 128,
                "clientAeronMode": "one-independent-Aeron-per-client", **changes}

    def test_historical_cloud_argument_receipts_still_match_exactly(self):
        # Real recorded receipts independently anchor legacy argv and hashing.
        for cohort in ("runpod-capacity", "runpod-capacity-extended", "runpod-capacity-128", "runpod-capacity-long"):
            directory = next(p for p in sorted((ROOT / "evidence/2026-10-23" / cohort / "runs").iterdir())
                             if (p / "load-process.json").exists() and (p / "result.json").exists())
            with self.subTest(cohort=cohort):
                trial = json.loads((directory / "trial.json").read_text())
                runtime = json.loads((directory / "configuration.json").read_text())
                flags = config.load_generator_jvm_arguments(trial, runtime)
                arguments = config.load_generator_arguments(trial, trial["release"], flags)
                receipt = json.loads((directory / "load-process.json").read_text())
                self.assertEqual(receipt["commandSha256"], config.command_sha256(arguments))

    def test_legacy_runtime_absence_and_explicit_empty_flags_pass(self):
        self.assertEqual([], config.load_generator_jvm_arguments(self.trial, {}))
        self.trial["loadGeneratorJvmArguments"] = []
        self.assertEqual([], config.load_generator_jvm_arguments(self.trial, {}))

    def test_new_isolated_default_and_both_explicit_modes_pass(self):
        self.assertEqual([], config.load_generator_jvm_arguments(self.trial, self.runtime()))
        for mode in ("isolated", "shared"):
            with self.subTest(mode=mode):
                self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + mode]
                self.assertEqual([DRIVER_FLAG + mode],
                                 config.load_generator_jvm_arguments(self.trial, self.runtime(mode)))

    def test_flag_and_declared_mode_must_agree(self):
        for flag, mode in (("shared", "isolated"), ("isolated", "shared"), (None, "shared")):
            with self.subTest(flag=flag, mode=mode):
                self.trial["loadGeneratorJvmArguments"] = [] if flag is None else [DRIVER_FLAG + flag]
                with self.assertRaisesRegex(AssertionError, "differs from actual JVM argument"):
                    config.load_generator_jvm_arguments(self.trial, self.runtime(mode))

    def test_driver_count_must_match_mode_and_worker_count(self):
        for mode, count in (("isolated", 1), ("isolated", 64), ("shared", 128),
                            ("shared", True), ("shared", 1.0), ("shared", "1")):
            with self.subTest(mode=mode, count=count):
                self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + mode]
                with self.assertRaisesRegex(AssertionError, "Client driver count differs"):
                    config.load_generator_jvm_arguments(self.trial, self.runtime(mode, clientDriverCount=count))

    def test_partial_runtime_declarations_do_not_fall_back_to_legacy(self):
        for missing in self.runtime():
            with self.subTest(missing=missing):
                runtime = self.runtime()
                del runtime[missing]
                with self.assertRaisesRegex(AssertionError, "Incomplete"):
                    config.load_generator_jvm_arguments(self.trial, runtime)

    def test_any_new_flag_requires_complete_runtime_evidence(self):
        for mode in ("isolated", "shared"):
            self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + mode]
            with self.subTest(mode=mode), self.assertRaisesRegex(AssertionError, "Missing runtime"):
                config.load_generator_jvm_arguments(self.trial, {})

    def test_unknown_modes_and_aeron_ownership_are_rejected(self):
        for runtime in (self.runtime(clientDriverMode="dedicated"),
                        self.runtime(clientAeronMode="shared-Aeron")):
            with self.subTest(runtime=runtime), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments(self.trial, runtime)

    def test_only_a_single_exact_allowlisted_jvm_property_is_allowed(self):
        for flags in (["-Xmx8g"], [DRIVER_FLAG + "other"], [DRIVER_FLAG + "shared "] ,
                      [DRIVER_FLAG + "shared", DRIVER_FLAG + "shared"],
                      [DRIVER_FLAG + "shared", "-Dother=value"], [None], [1],
                      DRIVER_FLAG + "shared", None, (DRIVER_FLAG + "shared",)):
            with self.subTest(flags=flags):
                self.trial["loadGeneratorJvmArguments"] = flags
                with self.assertRaises(AssertionError):
                    config.load_generator_jvm_arguments(self.trial, self.runtime())

    def test_explicit_default_and_shared_properties_change_actual_argument_digest(self):
        results = {}
        for mode in (None, "isolated", "shared"):
            trial = copy.deepcopy(self.trial)
            if mode is not None:
                trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + mode]
            flags = config.load_generator_jvm_arguments(trial, self.runtime(mode or "isolated"))
            args = config.load_generator_arguments(trial, self.release, flags)
            if mode is not None:
                self.assertEqual(args[3], DRIVER_FLAG + mode)
                self.assertLess(args.index(DRIVER_FLAG + mode), args.index("-cp"))
            results[mode] = config.command_sha256(args)
        self.assertEqual(3, len(set(results.values())))

    def test_load_artifact_and_profile_remain_in_expected_argv(self):
        self.trial["loadGeneratorRelease"] = "/opt/vectormatch/releases/" + "b" * 40
        arguments = config.load_generator_arguments(self.trial, self.release, [])
        self.assertEqual(self.trial["loadGeneratorRelease"] + "/dist/cluster/lib/*",
                         arguments[arguments.index("-cp") + 1])
        self.assertEqual("extended-190k-128", arguments[-1])
        self.assertNotIn(self.release + "/dist/cluster/lib/*", arguments)

    def test_digest_preserves_argument_boundaries_and_final_nul(self):
        self.assertEqual(hashlib.sha256(b"ab\0c\0").hexdigest(), config.command_sha256(["ab", "c"]))
        self.assertNotEqual(config.command_sha256(["ab", "c"]), config.command_sha256(["a", "bc"]))
        self.assertNotEqual(hashlib.sha256(b"ab\0c").hexdigest(), config.command_sha256(["ab", "c"]))

    def test_historical_node_argv_is_unchanged_without_new_opt_in(self):
        for cohort in ("runpod-capacity", "runpod-capacity-extended", "runpod-capacity-128", "runpod-capacity-long"):
            root = ROOT / "evidence/2026-10-23" / cohort
            directory = next(p for p in sorted((root / "runs").iterdir())
                             if (p / "load-process.json").exists() and (p / "result.json").exists())
            fixed = json.loads((root / "campaign.json").read_text())["fixed"]
            fixed.setdefault("outboxCapacity", 65536)
            trial = json.loads((directory / "trial.json").read_text())
            hosts = ",".join(json.loads((directory / "configuration.json").read_text())["memberHosts"])
            for node in range(3):
                with self.subTest(cohort=cohort, node=node):
                    arguments = json.loads((directory / f"node{node}" / "process.json").read_text())["arguments"]
                    offset = arguments.index("io.vectormatch.cluster.ClusterNodeMain") + 1
                    self.assertEqual(arguments[offset:], config.node_arguments(trial, fixed, node, hosts))
                    config.verify_requested_receive_buffer_startup(fixed, "legacy startup without receive buffer field")

    def test_new_receive_buffer_keeps_profile_in_seventh_position(self):
        fixed = {"portBase": 23000, "syncLevel": 2, "outboxCapacity": 65536,
                 "socketReceiveBufferArgumentBytes": 1048576}
        trial = {"state": "/state/trial"}
        expected = ["0", "/state/trial", "23000", "2", "65536", "127.0.0.1", "default", "1048576"]
        self.assertEqual(expected, config.node_arguments(trial, fixed, 0, "127.0.0.1"))
        fixed.update(stateProfile="capacity-190k-v1", outboxCapacity=524288)
        arguments = config.node_arguments(trial, fixed, 0, "127.0.0.1")
        self.assertEqual(["capacity-190k-v1", "1048576"], arguments[-2:])
        self.assertEqual("524288", arguments[4])

    def test_receive_buffer_argument_requires_bounded_integer(self):
        for value in (65536, 131072, 1048576, 4194304):
            with self.subTest(value=value):
                self.assertEqual(value, config.socket_receive_buffer_argument({"socketReceiveBufferArgumentBytes": value}))
        for value in (None, True, 131072.0, "131072", 0, -1, 65535, 4194305):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, "Invalid explicit"):
                config.socket_receive_buffer_argument({"socketReceiveBufferArgumentBytes": value})

    def test_explicit_receive_buffer_requires_matching_started_record(self):
        fixed = {"socketReceiveBufferArgumentBytes": 1048576}
        config.verify_requested_receive_buffer_startup(fixed,
            "VECTOR_CLUSTER_STARTED node=0 requestedSocketReceiveBufferBytes=1048576\n")
        for startup in ("VECTOR_CLUSTER_STARTED node=0\n", "",
                        "VECTOR_CLUSTER_STARTED requestedSocketReceiveBufferBytes=131072\n",
                        "error requestedSocketReceiveBufferBytes=1048576\n",
                        "VECTOR_CLUSTER_STARTED requestedSocketReceiveBufferBytes=1048576garbage\n",
                        "VECTOR_CLUSTER_STARTED requestedSocketReceiveBufferBytes=1048576\n"
                        "VECTOR_CLUSTER_STARTED requestedSocketReceiveBufferBytes=131072\n"):
            with self.subTest(startup=startup), self.assertRaisesRegex(AssertionError, "startup evidence"):
                config.verify_requested_receive_buffer_startup(fixed, startup)


if __name__ == "__main__":
    unittest.main()
