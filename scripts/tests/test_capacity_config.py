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


if __name__ == "__main__":
    unittest.main()
