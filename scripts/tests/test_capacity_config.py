import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile


ROOT = Path(__file__).resolve().parents[2]
HISTORICAL = Path(__file__).resolve().parent / "fixtures/historical/2026-10-23"
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
            directory = next(p for p in sorted((HISTORICAL / cohort / "runs").iterdir())
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
            root = HISTORICAL / cohort
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
                    config.verify_maximum_cluster_sessions(arguments, fixed)
                    config.verify_requested_receive_buffer_startup(fixed, "legacy startup without receive buffer field")

    def test_maximum_cluster_sessions_default_is_historical_and_explicit_values_are_strict(self):
        fixed = {}
        self.assertEqual(128, config.maximum_cluster_sessions(fixed))
        self.assertEqual({}, fixed, "Historical absence must not add a new fingerprint field")
        for sessions in (128, 256):
            self.assertEqual(sessions, config.maximum_cluster_sessions({"maxClusterSessions": sessions}))
        for sessions in (None, True, False, 128.0, "128", 0, 64, 129, 255, 257):
            with self.subTest(sessions=sessions), self.assertRaisesRegex(AssertionError, "Invalid fixed"):
                config.maximum_cluster_sessions({"maxClusterSessions": sessions})

    def test_node_sessions_require_one_exact_jvm_property_without_overrides(self):
        for fixed in ({}, {"maxClusterSessions": 128}, {"maxClusterSessions": 256}):
            sessions = config.maximum_cluster_sessions(fixed)
            flag = "-Daeron.cluster.max.sessions=" + str(sessions)
            arguments = ["/jdk/bin/java", "-Xmx2g", flag, "-cp", "/lib/*", "Main"]
            config.verify_maximum_cluster_sessions(arguments, fixed)
            for invalid in ([], [flag, flag], [flag, "-Daeron.cluster.max.sessions=64"],
                            ["-Daeron.cluster.max.sessions=64"], [flag, "-Daeron.cluster.max.sessions"],
                            [flag + " "], ["-Daeron.cluster.max.sessions"]):
                with self.subTest(fixed=fixed, invalid=invalid), self.assertRaisesRegex(AssertionError, "differs or is repeated"):
                    config.verify_maximum_cluster_sessions(["java", *invalid, "Main"], fixed)

    def test_350k_sessions_and_state_profile_have_distinct_exact_argument_digests(self):
        fixed = {"portBase": 23000, "syncLevel": 2, "outboxCapacity": 800000,
                 "stateProfile": "capacity-350k-v1", "maxClusterSessions": 256,
                 "socketReceiveBufferArgumentBytes": 1048576, "driverThreadingArgument": "DEDICATED"}
        trial = {"state": "/state/trial"}
        suffix = ["0", "/state/trial", "23000", "2", "800000", "127.0.0.1",
                  "capacity-350k-v1", "1048576", "DEDICATED"]
        self.assertEqual(suffix, config.node_arguments(trial, fixed, 0, "127.0.0.1"))
        arguments = ["java", "-Daeron.cluster.max.sessions=256", "Main", *suffix]
        config.verify_maximum_cluster_sessions(arguments, fixed)
        self.assertEqual(hashlib.sha256(b"\0".join(arg.encode() for arg in arguments) + b"\0").hexdigest(),
                         config.command_sha256(arguments))
        previous = ["java", "-Daeron.cluster.max.sessions=128", "Main", *suffix]
        self.assertNotEqual(config.command_sha256(arguments), config.command_sha256(previous))
        with self.assertRaises(AssertionError):
            config.verify_maximum_cluster_sessions(previous, fixed)

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

    def test_driver_threading_argument_is_optional_and_strict(self):
        self.assertIsNone(config.driver_threading_argument({}))
        for mode in ("SHARED", "DEDICATED"):
            self.assertEqual(mode, config.driver_threading_argument({"driverThreadingArgument": mode}))
        for value in (None, True, 1, "", "shared", "dedicated", "SHARED_NETWORK", "INVOKER", "DEDICATED "):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, "Invalid explicit"):
                config.driver_threading_argument({"driverThreadingArgument": value})

    def test_driver_mode_fills_profile_and_receive_positions_without_changing_legacy_argv(self):
        fixed = {"portBase": 23000, "syncLevel": 2, "outboxCapacity": 65536}
        trial = {"state": "/state/trial"}
        legacy = ["0", "/state/trial", "23000", "2", "65536", "127.0.0.1"]
        self.assertEqual(legacy, config.node_arguments(trial, fixed, 0, "127.0.0.1"))
        fixed["socketReceiveBufferArgumentBytes"] = 1048576
        receive_only = legacy + ["default", "1048576"]
        self.assertEqual(receive_only, config.node_arguments(trial, fixed, 0, "127.0.0.1"))
        for mode in ("SHARED", "DEDICATED"):
            fixed["driverThreadingArgument"] = mode
            self.assertEqual(receive_only + [mode], config.node_arguments(trial, fixed, 0, "127.0.0.1"))
        del fixed["socketReceiveBufferArgumentBytes"]
        self.assertEqual(legacy + ["default", "131072", "DEDICATED"],
                         config.node_arguments(trial, fixed, 0, "127.0.0.1"))

    def test_explicit_mode_requires_matching_threading_and_exact_idle_policy_startup(self):
        fixed = {"driverThreadingArgument": "DEDICATED"}
        startup = ("VECTOR_CLUSTER_STARTED node=0 driverThreading=DEDICATED driverIdleMaxSpins=10 "
                   "driverIdleMaxYields=5 driverIdleMinParkNs=1000 driverIdleMaxParkNs=1000000\n")
        config.verify_driver_threading_startup(fixed, startup)
        config.verify_driver_threading_startup({}, "legacy startup without threading fields")
        for invalid in (startup.replace("DEDICATED", "SHARED"), startup.replace("MaxYields=5", "MaxYields=20"),
                        startup.replace("MinParkNs=1000", "MinParkNs=10000"),
                        startup.replace("driverIdleMaxSpins=10 ", ""),
                        startup.replace("VECTOR_CLUSTER_STARTED ", "error "), ""):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                config.verify_driver_threading_startup(fixed, invalid)

    def test_node_mode_is_in_nul_delimited_command_digest(self):
        fixed = {"portBase": 23000, "syncLevel": 2, "outboxCapacity": 524288,
                 "stateProfile": "capacity-190k-v1", "socketReceiveBufferArgumentBytes": 1048576}
        trial = {"state": "/state/trial"}
        old = config.node_arguments(trial, fixed, 0, "127.0.0.1")
        expected_old = ["0", "/state/trial", "23000", "2", "524288", "127.0.0.1", "capacity-190k-v1", "1048576"]
        self.assertEqual(config.command_sha256(expected_old), config.command_sha256(old))
        digests = {config.command_sha256(old)}
        for mode in ("SHARED", "DEDICATED"):
            arguments = config.node_arguments(trial, {**fixed, "driverThreadingArgument": mode}, 0, "127.0.0.1")
            self.assertEqual(config.command_sha256(expected_old + [mode]), config.command_sha256(arguments))
            digests.add(config.command_sha256(arguments))
        self.assertEqual(3, len(digests))

    def nak_fixed(self, delay=100000):
        return {"nakUnicastDelayNs": delay, "clientNakUnicastDelayNs": delay,
                "nakUnicastRetryDelayRatio": 100}

    def test_nak_configuration_is_all_or_none_bounded_integer_and_retains_legacy_absence(self):
        legacy = {"syncLevel": 2}
        self.assertIsNone(config.nak_settings(legacy))
        self.assertEqual({"syncLevel": 2}, legacy)
        for delay in (1000, 100000, 1000000):
            self.assertEqual(self.nak_fixed(delay), config.nak_settings(self.nak_fixed(delay)))
        for missing in self.nak_fixed():
            fixed = self.nak_fixed()
            del fixed[missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(AssertionError, "Incomplete"):
                config.nak_settings(fixed)
        for name in ("nakUnicastDelayNs", "clientNakUnicastDelayNs"):
            for invalid in (None, True, "1000", 1000.0, 999, 1000001):
                with self.subTest(name=name, invalid=invalid), self.assertRaises(AssertionError):
                    config.nak_settings({**self.nak_fixed(), name: invalid})
        for ratio in (None, True, "100", 100.0, 1, 99, 101):
            with self.subTest(ratio=ratio), self.assertRaisesRegex(AssertionError, "ratio"):
                config.nak_settings({**self.nak_fixed(), "nakUnicastRetryDelayRatio": ratio})

    def test_nak_properties_are_exactly_once_before_classpath_without_hidden_overrides(self):
        fixed = self.nak_fixed()
        flag = "-Daeron.nak.unicast.delay=100000"
        arguments = ["java", flag, "-cp", "/lib/*", "Main"]
        config.verify_nak_jvm_arguments(arguments, fixed)
        config.verify_nak_jvm_arguments(arguments, fixed, client=True)
        config.verify_nak_jvm_arguments(["java", "Main"], {})
        for invalid in ([], [flag, flag], [flag, "-Daeron.nak.unicast.delay=1000"],
                        ["-Daeron.nak.unicast.delay=100000ns"], [flag, "-Daeron.nak.unicast.retry.delay.ratio=100"],
                        ["-Daeron.nak.unicast.delay"], [flag, "-Daeron.nak.multicast.max.backoff=1"],
                        ["-Dhidden=-Daeron.nak.unicast.delay=100000"]):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(AssertionError, "NAK JVM"):
                config.verify_nak_jvm_arguments(["java", *invalid, "-cp", "/lib/*", "Main"], fixed)
        with self.assertRaisesRegex(AssertionError, "JVM argument"):
            config.verify_nak_jvm_arguments(["java", "-cp", "/lib/*", "Main", flag], fixed)
        with self.assertRaises(AssertionError):
            config.verify_nak_jvm_arguments(arguments, {})

    def test_nak_started_fields_require_actual_effective_value_and_unchanged_ratio(self):
        fixed = self.nak_fixed()
        line = "VECTOR_CLUSTER_STARTED node=0 nakUnicastDelayNs=100000 nakUnicastRetryDelayRatio=100\n"
        config.verify_nak_startup(fixed, line)
        config.verify_nak_startup({}, "legacy")
        for invalid in ("", line.replace("VECTOR_CLUSTER_STARTED", "error"),
                        line.replace("100000", "1000"), line.replace("Ratio=100", "Ratio=101"),
                        line.replace("DelayNs=100000", "DelayNs=100000ns"),
                        line.rstrip() + " nakUnicastDelayNs=100000\n", line + line.replace("100000", "1000")):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(AssertionError, "NAK startup"):
                config.verify_nak_startup(fixed, invalid)

    def test_shared_driver_and_nak_load_flags_are_allowlisted_and_attested_together(self):
        fixed = self.nak_fixed()
        flag = "-Daeron.nak.unicast.delay=100000"
        self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + "shared", flag]
        runtime = self.runtime("shared", clientNakUnicastDelayNs=100000, clientNakUnicastRetryDelayRatio=100)
        flags = config.load_generator_jvm_arguments(self.trial, runtime, fixed)
        self.assertEqual(self.trial["loadGeneratorJvmArguments"], flags)
        args = config.load_generator_arguments(self.trial, self.release, flags)
        self.assertEqual([DRIVER_FLAG + "shared", flag], args[3:5])
        wrong = self.trial.copy()
        wrong["loadGeneratorJvmArguments"] = [DRIVER_FLAG + "shared", "-Daeron.nak.unicast.delay=1000"]
        with self.assertRaises(AssertionError):
            config.load_generator_jvm_arguments(wrong, runtime, fixed)
        for missing in ("clientNakUnicastDelayNs", "clientNakUnicastRetryDelayRatio"):
            partial = runtime.copy()
            del partial[missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(AssertionError, "Incomplete client NAK"):
                config.load_generator_jvm_arguments(self.trial, partial, fixed)
        for changes in ({"clientNakUnicastDelayNs": 1000}, {"clientNakUnicastRetryDelayRatio": 99},
                        {"clientNakUnicastDelayNs": "100000"}, {"clientNakUnicastRetryDelayRatio": 100.0}):
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments(self.trial, {**runtime, **changes}, fixed)
        with self.assertRaises(AssertionError):
            config.load_generator_jvm_arguments(self.trial, runtime)
        legacy_trial = {k: v for k, v in self.trial.items() if k != "loadGeneratorJvmArguments"}
        with self.assertRaisesRegex(AssertionError, "Undeclared nondefault client NAK"):
            config.load_generator_jvm_arguments(legacy_trial, runtime)

    def test_unflagged_actual_runtime_defaults_are_compatible_without_new_fingerprint_settings(self):
        self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + "shared"]
        runtime = self.runtime("shared", clientNakUnicastDelayNs=1000, clientNakUnicastRetryDelayRatio=100)
        fixed = {"syncLevel": 2}
        self.assertEqual([DRIVER_FLAG + "shared"], config.load_generator_jvm_arguments(self.trial, runtime, fixed))
        self.assertEqual({"syncLevel": 2}, fixed)
        self.assertEqual([DRIVER_FLAG + "shared"], config.load_generator_jvm_arguments(self.trial, self.runtime("shared"), fixed))
        for missing in ("clientNakUnicastDelayNs", "clientNakUnicastRetryDelayRatio"):
            partial = runtime.copy()
            del partial[missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(AssertionError, "Incomplete client NAK"):
                config.load_generator_jvm_arguments(self.trial, partial, fixed)
        for changes in ({"clientNakUnicastDelayNs": 100000}, {"clientNakUnicastRetryDelayRatio": 99},
                        {"clientNakUnicastDelayNs": "1000"}, {"clientNakUnicastDelayNs": 1000.0},
                        {"clientNakUnicastRetryDelayRatio": 100.0}, {"clientNakUnicastRetryDelayRatio": True}):
            with self.subTest(changes=changes), self.assertRaisesRegex(AssertionError, "Undeclared nondefault"):
                config.load_generator_jvm_arguments(self.trial, {**runtime, **changes}, fixed)

    def terminal_unknown_fixture(self, root):
        source_root = HISTORICAL / "runpod-optimization/window350k/pilot"
        source = source_root / "runs/w-pilot-10000-w128"
        directory = root / "runs/w-pilot-10000-w128"
        directory.mkdir(parents=True)
        for name in ("campaign.json", "deployment.json"):
            (root / name).write_bytes((source_root / name).read_bytes())
        for name in ("trial.json", "configuration.json", "load-process.json"):
            (directory / name).write_bytes((source / name).read_bytes())
        for node in range(3):
            (directory / f"node{node}").mkdir()
            for name in ("process.json", "process.log"):
                (directory / f"node{node}" / name).write_bytes((source / f"node{node}" / name).read_bytes())
        snapshot = b"test-prepared-bytes"
        (directory / "prepared-snapshot.bin").write_bytes(snapshot)
        runtime = json.loads((directory / "configuration.json").read_text())
        runtime["preparedSnapshotSha256"] = hashlib.sha256(snapshot).hexdigest()
        (directory / "configuration.json").write_text(json.dumps(runtime))
        load = {"unresolvedFinal": 1, "unknownAtInitialDeadline": 1, "scheduledArrivals": 350000}
        failure = {"passed": False, "errorType": "java.lang.IllegalStateException",
                   "error": config.UNKNOWN_GUARD.format(count=1), "loadSummary": load}
        for name, value in (("load-result.json", load), ("failure.json", failure), ("receipt.json", {"exitCode": 1})):
            (directory / name).write_text(json.dumps(value))
        return directory

    def test_exact_terminal_unknown_can_verify_configuration_without_creating_business_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.terminal_unknown_fixture(root)
            original_failure = (directory / "failure.json").read_bytes()
            config.main(root)
            self.assertFalse((directory / "configuration-verification.json").exists(), "Default must still skip failed runs")
            config.main(root, include_failed_unknown=True)
            receipt = json.loads((directory / "configuration-verification.json").read_text())
            self.assertTrue(receipt["passed"])
            self.assertTrue(receipt["configurationOnly"])
            self.assertFalse(receipt["businessCorrectnessVerified"])
            self.assertFalse((directory / "result.json").exists())
            self.assertEqual(original_failure, (directory / "failure.json").read_bytes())
            trial = json.loads((directory / "trial.json").read_text())
            self.assertIn("fixedNodeConfiguration", trial)
            self.assertIn("deploymentBundleSha256", trial)

    def test_terminal_unknown_flag_rejects_other_failures_missing_receipt_and_snapshot_without_annotation(self):
        for damage in ("wrong-guard", "missing-receipt", "wrong-count", "mismatched-summary", "missing-snapshot"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                directory = self.terminal_unknown_fixture(root)
                before = (directory / "trial.json").read_bytes()
                if damage == "missing-receipt":
                    (directory / "receipt.json").unlink()
                elif damage == "missing-snapshot":
                    (directory / "prepared-snapshot.bin").unlink()
                else:
                    failure = json.loads((directory / "failure.json").read_text())
                    if damage == "wrong-guard":
                        failure["error"] = "Per-reply business result differs at arrival 2245"
                    elif damage == "wrong-count":
                        failure["error"] = config.UNKNOWN_GUARD.format(count=2)
                    else:
                        failure["loadSummary"]["scheduledArrivals"] = 1
                    (directory / "failure.json").write_text(json.dumps(failure))
                with self.assertRaises((AssertionError, FileNotFoundError)):
                    config.main(root, include_failed_unknown=True)
                self.assertEqual(before, (directory / "trial.json").read_bytes())
                self.assertFalse((directory / "configuration-verification.json").exists())
                self.assertFalse((directory / "result.json").exists())

    def test_in_progress_unknown_is_skipped_even_with_failed_run_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = self.terminal_unknown_fixture(root)
            trial = json.loads((directory / "trial.json").read_text())
            del trial["completedAt"]
            (directory / "trial.json").write_text(json.dumps(trial))
            before = (directory / "trial.json").read_bytes()
            config.main(root, include_failed_unknown=True)
            self.assertEqual(before, (directory / "trial.json").read_bytes())
            self.assertFalse((directory / "configuration-verification.json").exists())

    def test_client_transport_fixed_fields_are_optional_complete_and_typed(self):
        fixed = {"syncLevel": 2}
        self.assertIsNone(config.transport_settings(fixed))
        self.assertEqual({"syncLevel": 2}, fixed)
        for mode, sessions in (("direct", 128), ("multiplexed", 1)):
            declared = {"clientTransportMode": mode, "clientSessionCount": sessions}
            self.assertEqual(declared, config.transport_settings(declared))
        for invalid in ({"clientTransportMode": "direct"}, {"clientSessionCount": 128},
                        {"clientTransportMode": "shared", "clientSessionCount": 128},
                        {"clientTransportMode": "multiplexed", "clientSessionCount": 128},
                        {"clientTransportMode": "direct", "clientSessionCount": True},
                        {"clientTransportMode": "direct", "clientSessionCount": 128.0}):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                config.transport_settings(invalid)

    def test_unflagged_direct_transport_metadata_preserves_old_argv_and_comparison_identity(self):
        self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + "shared"]
        legacy = self.runtime("shared")
        new = {**legacy, "clientTransportMode": "direct", "clientSessionCount": 128}
        old_flags = config.load_generator_jvm_arguments(self.trial, legacy)
        new_flags = config.load_generator_jvm_arguments(self.trial, new)
        self.assertEqual(old_flags, new_flags)
        self.assertEqual(config.command_sha256(config.load_generator_arguments(self.trial, self.release, old_flags)),
                         config.command_sha256(config.load_generator_arguments(self.trial, self.release, new_flags)))
        for changes in ({"clientTransportMode": "multiplexed"}, {"clientSessionCount": 1},
                        {"clientSessionCount": True}, {"clientSessionCount": "128"}):
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments(self.trial, {**new, **changes})
        for missing in ("clientTransportMode", "clientSessionCount"):
            partial = new.copy()
            del partial[missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(AssertionError, "Incomplete client transport"):
                config.load_generator_jvm_arguments(self.trial, partial)

    def test_explicit_direct_and_multiplexed_flags_match_physical_runtime_and_full_digest(self):
        digests = set()
        for mode, sessions, aeron in (("direct", 128, "one-independent-Aeron-per-client"),
                                      ("multiplexed", 1, "one-session-one-network-owner")):
            fixed = {"clientTransportMode": mode, "clientSessionCount": sessions, **self.nak_fixed(1000)}
            self.trial["loadGeneratorJvmArguments"] = [DRIVER_FLAG + "shared",
                "-Dvectormatch.capacity.client.transport=" + mode, "-Daeron.nak.unicast.delay=1000"]
            runtime = self.runtime("shared", clientTransportMode=mode, clientSessionCount=sessions,
                clientAeronMode=aeron, clientNakUnicastDelayNs=1000, clientNakUnicastRetryDelayRatio=100)
            flags = config.load_generator_jvm_arguments(self.trial, runtime, fixed)
            self.assertEqual(self.trial["loadGeneratorJvmArguments"], flags)
            digests.add(config.command_sha256(config.load_generator_arguments(self.trial, self.release, flags)))
            for changes in ({"clientSessionCount": 2}, {"clientTransportMode": "other"},
                            {"clientAeronMode": "one-shared-Aeron-per-physical-session"}):
                with self.subTest(mode=mode, changes=changes), self.assertRaises(AssertionError):
                    config.load_generator_jvm_arguments(self.trial, {**runtime, **changes}, fixed)
        self.assertEqual(2, len(digests))
        wrong_workers = {**self.trial, "workers": 129}
        with self.assertRaisesRegex(AssertionError, "128 or 256 logical workers"):
            config.load_generator_jvm_arguments(wrong_workers, runtime, fixed)
        isolated = {**self.trial, "loadGeneratorJvmArguments": [DRIVER_FLAG + "isolated",
            "-Dvectormatch.capacity.client.transport=multiplexed", "-Daeron.nak.unicast.delay=1000"]}
        with self.assertRaises(AssertionError):
            config.load_generator_jvm_arguments(isolated, {**runtime, "clientDriverMode": "isolated", "clientDriverCount": 128}, fixed)

    def test_multiplexed_256_requires_true_pending_and_logical_runtime_bounds(self):
        fixed = {"clientTransportMode": "multiplexed", "clientSessionCount": 1}
        trial = {**self.trial, "workers": 256, "profile": "extended-350k-256",
                 "loadGeneratorJvmArguments": [DRIVER_FLAG + "shared", "-Dvectormatch.capacity.client.transport=multiplexed"]}
        runtime = self.runtime("shared", clientTransportMode="multiplexed", clientSessionCount=1,
                               clientAeronMode="one-session-one-network-owner", clientPendingCapacity=256,
                               workers=256, maxServiceRequestsInFlight=256)
        self.assertEqual(trial["loadGeneratorJvmArguments"], config.load_generator_jvm_arguments(trial, runtime, fixed))
        for name in ("clientPendingCapacity", "workers", "maxServiceRequestsInFlight"):
            for invalid in (None, True, 128, 255, 257, 256.0, "256"):
                with self.subTest(name=name, invalid=invalid), self.assertRaises(AssertionError):
                    config.load_generator_jvm_arguments(trial, {**runtime, name: invalid}, fixed)
            missing = runtime.copy(); del missing[name]
            with self.subTest(missing=name), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments(trial, missing, fixed)
        for unsupported in (0, 1, 63, 64, 127, 129, 255, 257, True, "256", 256.0):
            with self.subTest(unsupported=unsupported), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments({**trial, "workers": unsupported}, runtime, fixed)

    def test_pending_capacity_is_optional_for_legacy_128_but_strict_when_present(self):
        fixed = {"clientTransportMode": "multiplexed", "clientSessionCount": 1}
        trial = {**self.trial, "loadGeneratorJvmArguments": [DRIVER_FLAG + "shared",
                 "-Dvectormatch.capacity.client.transport=multiplexed"]}
        runtime = self.runtime("shared", clientTransportMode="multiplexed", clientSessionCount=1,
                               clientAeronMode="one-session-one-network-owner")
        self.assertEqual(trial["loadGeneratorJvmArguments"], config.load_generator_jvm_arguments(trial, runtime, fixed))
        self.assertEqual(trial["loadGeneratorJvmArguments"], config.load_generator_jvm_arguments(
            trial, {**runtime, "clientPendingCapacity": 128}, fixed))
        for invalid in (None, True, 127, 256, 128.0, "128"):
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments(trial, {**runtime, "clientPendingCapacity": invalid}, fixed)

    def test_direct_256_remains_independent_sessions_and_worker_changes_change_argv(self):
        flags = [DRIVER_FLAG + "shared", "-Dvectormatch.capacity.client.transport=direct"]
        trial = {**self.trial, "workers": 256, "profile": "extended-350k-256", "loadGeneratorJvmArguments": flags}
        fixed = {"clientTransportMode": "direct", "clientSessionCount": 256}
        runtime = self.runtime("shared", clientTransportMode="direct", clientSessionCount=256)
        self.assertEqual(flags, config.load_generator_jvm_arguments(trial, runtime, fixed))
        args256 = config.load_generator_arguments(trial, self.release, flags)
        args128 = config.load_generator_arguments({**trial, "workers": 128}, self.release, flags)
        self.assertNotEqual(config.command_sha256(args256), config.command_sha256(args128))
        self.assertNotIn("clientPendingCapacity", runtime)

    def test_transport_flags_reject_duplicates_conflicts_missing_fixed_or_runtime(self):
        fixed = {"clientTransportMode": "multiplexed", "clientSessionCount": 1}
        flag = "-Dvectormatch.capacity.client.transport=multiplexed"
        runtime = self.runtime("shared", clientTransportMode="multiplexed", clientSessionCount=1,
                               clientAeronMode="one-session-one-network-owner")
        for invalid in ([flag, flag], [flag, "-Dvectormatch.capacity.client.transport=direct"],
                        ["-Dvectormatch.capacity.client.transport=shared"], [], [flag + " "],
                        ["-Dvectormatch.capacity.client.transport"], ["-Dother=" + flag]):
            trial = {**self.trial, "loadGeneratorJvmArguments": [DRIVER_FLAG + "shared", *invalid]}
            with self.subTest(invalid=invalid), self.assertRaises(AssertionError):
                config.load_generator_jvm_arguments(trial, runtime, fixed)
        valid = {**self.trial, "loadGeneratorJvmArguments": [DRIVER_FLAG + "shared", flag]}
        with self.assertRaisesRegex(AssertionError, "Undeclared client transport"):
            config.load_generator_jvm_arguments(valid, runtime)
        with self.assertRaisesRegex(AssertionError, "Incomplete client transport"):
            config.load_generator_jvm_arguments(valid, self.runtime("shared"), fixed)

    def test_transport_settings_enter_real_comparison_identity_without_mutating_legacy_fixed(self):
        spec = importlib.util.spec_from_file_location("transport_comparison", ROOT / "scripts/analyze-capacity.py")
        analyzer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyzer)
        trial = {"release": self.release, "deploymentRevision": "a" * 40,
                 "deploymentBundleSha256": "b" * 64, "preparedSnapshotSha256": "c" * 64,
                 "fixedNodeConfiguration": {"syncLevel": 2}}
        original, issues = analyzer.comparison_identity({}, trial)
        self.assertEqual([], issues)
        fingerprints = {json.dumps(original, sort_keys=True)}
        for mode, sessions in (("direct", 128), ("multiplexed", 1)):
            fixed = {**trial["fixedNodeConfiguration"], "clientTransportMode": mode, "clientSessionCount": sessions}
            identity, issues = analyzer.comparison_identity({}, {**trial, "fixedNodeConfiguration": fixed})
            self.assertEqual([], issues)
            fingerprints.add(json.dumps(identity, sort_keys=True))
        self.assertEqual(3, len(fingerprints))
        self.assertEqual({"syncLevel": 2}, trial["fixedNodeConfiguration"])

    def test_optional_nak_values_enter_real_comparison_identity_and_command_hashes(self):
        spec = importlib.util.spec_from_file_location("nak_comparison", ROOT / "scripts/analyze-capacity.py")
        analyzer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyzer)
        trial = {"release": self.release, "deploymentRevision": "a" * 40,
                 "deploymentBundleSha256": "b" * 64, "preparedSnapshotSha256": "c" * 64,
                 "fixedNodeConfiguration": {"syncLevel": 2}}
        original, issues = analyzer.comparison_identity({}, trial)
        self.assertEqual([], issues)
        identities, commands = {json.dumps(original, sort_keys=True)}, {config.command_sha256(["java", "Main"])}
        for delay in (1000, 100000):
            changed = {**trial, "fixedNodeConfiguration": {**trial["fixedNodeConfiguration"], **self.nak_fixed(delay)}}
            identity, issues = analyzer.comparison_identity({}, changed)
            self.assertEqual([], issues)
            self.assertEqual(delay, identity["fixedNodeConfiguration"]["nakUnicastDelayNs"])
            identities.add(json.dumps(identity, sort_keys=True))
            commands.add(config.command_sha256(["java", "-Daeron.nak.unicast.delay=" + str(delay), "Main"]))
        self.assertEqual(3, len(identities))
        self.assertEqual(3, len(commands))


if __name__ == "__main__":
    unittest.main()
