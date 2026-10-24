"""Local guards for node-only maxPark ABAB draft; no SSH/JVM/registration/cloud work."""
import ast
import copy
import importlib.util
import json
import inspect
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cpu_capacity_idle_guard", BASE / "capacity_idle.py")
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)


def ready_declaration():
    return {"jobId": C.PILOT_ID, "ready": True, "closure": "offline fixture only",
            "baselines13000": [{"jobId": ident, "ready": True, "sourceRevision": C.REVISION,
                                 "controllerSha256": C.BASE_MATRIX_SHA256,
                                 "completionContentSha256": "a" * 64, "archiveSha256": "b" * 64}
                                for ident in C.BASELINE_IDS]}


class MatrixGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.draft_matrix(prerequisite={"jobId": C.PILOT_ID, "ready": False})

    def test_exact_order_independent_states_and_v2_provenance(self):
        self.assertEqual([row["rate"] for row in C.matrix_tasks()], [18000, 18000, 18000, 18000])
        self.assertEqual([row["repetition"] for row in C.matrix_tasks()], [1, 1, 2, 2])
        paths = [row["paths"]["state"] for row in self.plan["trialPlans"]]
        self.assertEqual(len(set(paths)), 4)
        self.assertEqual(C.sha(BASE / "capacity_v2.py"), C.BASE_V2_SHA256)
        for plan in self.plan["trialPlans"]:
            C.validate_plan(plan)
            self.assertEqual(plan["baseControllerSha256"], C.BASE_V2_SHA256)
            self.assertEqual(plan["fixed"], C.fixed_for_task(plan["task"]))
            self.assertEqual(plan["archiveCompressionLevel"], 1)

    def test_reordered_or_changed_arrival_concurrency_or_rate_is_rejected(self):
        p = copy.deepcopy(self.plan)
        p["order"].reverse()
        p["matrixPlanSha256"] = C.matrix_identity(p)
        with self.assertRaises(ValueError):
            C.validate_matrix(p)
        for key, value in (("rate", 10000), ("workers", 256), ("arrivals", 190000)):
            p = copy.deepcopy(self.plan["trialPlans"][0])
            p["task"][key] = value
            p["planSha256"] = C.plan_identity(p)
            with self.assertRaises(ValueError):
                C.validate_plan(p)

    def metrics(self, accepted=350000, dropped=0):
        raw = {name: True for name in ("passed", "measurementValid", "canonicalSnapshotBytesVerified", "fixedLeaderVerified")}
        raw["leaderChanged"] = False
        load = {name: 0 for name in C.ZERO_COUNTS}
        load.update(scheduledArrivals=350000, confirmedAcceptedCommands=accepted, clientNotSentCommands=dropped,
                    generatorTimingInvalid=False)
        config = {"workers": 128, "maxServiceRequestsInFlight": 128, "clientPendingCapacity": 128,
                  "clientDriverCount": 1, "clientSessionCount": 1, "clientTransportMode": "multiplexed",
                  "clientDriverMode": "shared", "clientAeronMode": "one-session-one-network-owner",
                  "preparedSnapshotSha256": C.PREPARED_SHA}
        return raw, load, config

    def test_canonical_overload_is_valid_for_matrix_without_claiming_strict_pilot(self):
        raw, load, config = self.metrics(280000, 70000)
        checked = C.matrix_trial_check(raw, load, config)
        self.assertTrue(checked["passed"])
        self.assertIn("overload allowed", checked["scope"])
        load["clientNotSentCommands"] = 69999
        self.assertFalse(C.matrix_trial_check(raw, load, config)["passed"])

    def test_initial_or_final_unknown_and_invalid_scheduler_fail_closed(self):
        raw, load, config = self.metrics()
        for key in ("unknownAtInitialDeadline", "unresolvedFinal", "schedulerLatenessAboveLimitCount"):
            changed = dict(load)
            changed[key] = 1
            self.assertFalse(C.matrix_trial_check(raw, changed, config)["passed"])
        for key in C.ZERO_COUNTS:
            changed = dict(load)
            changed[key] = None
            self.assertFalse(C.matrix_trial_check(raw, changed, config)["passed"])

    def test_independent_analysis_and_cleanup_must_close_before_next_point(self):
        receipt = {"matrixTrialPassed": True, "allOwnedProcessesStopped": True, "archiveComplete": True, "loadExitCode": 0}
        summary = {"trials": [{"measurementValid": True, "classification": "OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT",
                               "derived": {"unknownAtInitialDeadline": 0, "unknownUnresolved": 0}}]}
        self.assertTrue(C.continuation_check(receipt, summary)["passed"])
        for key in ("matrixTrialPassed", "allOwnedProcessesStopped", "archiveComplete"):
            modified = dict(receipt)
            modified[key] = False
            self.assertFalse(C.continuation_check(modified, summary)["passed"])
        for key in ("unknownAtInitialDeadline", "unknownUnresolved"):
            changed = copy.deepcopy(summary)
            changed["trials"][0]["derived"][key] = 1
            self.assertFalse(C.continuation_check(receipt, changed)["passed"])
        changed = copy.deepcopy(summary)
        changed["trials"][0]["measurementValid"] = False
        self.assertFalse(C.continuation_check(receipt, changed)["passed"])

    def test_missing_full_pilot_closure_blocks_execution_without_network(self):
        with tempfile.TemporaryDirectory() as temp:
            prior = C.pilot_prerequisite(Path(temp))
            self.assertFalse(prior["ready"])
            with self.assertRaises(ValueError):
                C.pilot_prerequisite(Path(temp), required=True)
            path = Path(temp) / "matrix.json"
            C.save_new(path, self.plan)
            with patch.object(C, "remote_module", side_effect=AssertionError("network forbidden")), self.assertRaises(ValueError):
                C.execute_matrix(path)

    def execute_mocked(self, *, unknown_at=None, low_space_after=None, transport_failure_at=None):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(root))
        p = copy.deepcopy(self.plan)
        p["pilotPrerequisite"] = ready_declaration()
        for trial in p["trialPlans"]:
            trial["pilotPrerequisite"] = p["pilotPrerequisite"]
            trial["planSha256"] = C.plan_identity(trial)
        p["matrixPlanSha256"] = C.matrix_identity(p)
        plan_path = root / "registered.json"
        C.save_new(plan_path, p)
        calls = []
        current = {"index": -1, "spaceCalls": 0}
        def execute(path):
            current["index"] += 1
            calls.append(C.read(path)["task"]["rate"])
            if current["index"] == transport_failure_at:
                raise TimeoutError("ambiguous launch; query same ID")
        def completion(plan):
            return {"matrixTrialPassed": True, "allOwnedProcessesStopped": True, "archiveComplete": True, "loadExitCode": 0,
                    "planSha256": plan["planSha256"]}
        def collect(path):
            plan = C.read(path)
            local = root / plan["jobId"]
            (local / "analysis").mkdir(parents=True)
            unknown = 1 if current["index"] == unknown_at else 0
            summary = {"trials": [{"measurementValid": True, "derived": {"unknownAtInitialDeadline": unknown, "unknownUnresolved": 0}}]}
            C.save_new(local / "analysis/summary.json", summary)
            return {"directory": str(local), "summary": summary}
        def space():
            current["spaceCalls"] += 1
            low = low_space_after is not None and current["index"] >= low_space_after
            return {"nextPointEligible": not low, "freeBytes": 2*1024**3 if low else 4*1024**3}
        with patch.object(C, "REPO", root), patch.object(C, "pilot_prerequisite", return_value=p["pilotPrerequisite"]), \
             patch.object(C, "execute", side_effect=execute), patch.object(C, "wait_completion", side_effect=completion), \
             patch.object(C, "collect", side_effect=collect), patch.object(C, "overlay_space", side_effect=space), patch("builtins.print"):
            code = C.execute_matrix(plan_path)
        result = C.read(root / "evidence/2026-10-24/runpod-cpu/matrices" / C.MATRIX_ID / "matrix-summary.json")
        return code, calls, result

    def test_sequential_idle_abab_waits_exports_and_analyzes_all_four_points(self):
        code, calls, result = self.execute_mocked()
        self.assertEqual(code, 0)
        self.assertEqual(calls, [18000, 18000, 18000, 18000])
        self.assertTrue(result["completed"])
        self.assertEqual(result["unlaunchedIds"], [])

    def test_unknown_stops_remaining_points_without_reissue(self):
        code, calls, result = self.execute_mocked(unknown_at=1)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [18000, 18000])
        self.assertEqual(len(result["unlaunchedIds"]), 2)
        self.assertEqual(result["points"][1]["continuation"]["passed"], False)

    def test_low_space_keeps_archived_point_and_stops_without_prune(self):
        code, calls, result = self.execute_mocked(low_space_after=0)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [18000])
        self.assertIn("below3GiB", result["error"])
        self.assertEqual(len(result["unlaunchedIds"]), 3)

    def test_ambiguous_launch_timeout_never_resubmits_or_starts_next_point(self):
        code, calls, result = self.execute_mocked(transport_failure_at=0)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [18000])
        self.assertEqual(result["errorType"], "TimeoutError")
        self.assertEqual(len(result["unlaunchedIds"]), 3)

    def test_no_default_draft_network_and_python38_grammar(self):
        with patch.object(C, "remote_module", side_effect=AssertionError("network forbidden")):
            C.draft_matrix(prerequisite={"jobId": C.PILOT_ID, "ready": False})
        ast.parse((BASE / "capacity_idle.py").read_text(), feature_version=(3, 8))
        self.assertEqual(C.sha(BASE / "capacity_v2.py"), C.BASE_V2_SHA256)

    def test_only_three_consistent_node_idle_fields_differ_between_groups(self):
        self.assertEqual([t["stage"] for t in C.matrix_tasks()], ["A1", "B1", "A2", "B2"])
        self.assertEqual([t["nodeMaxParkNs"] for t in C.matrix_tasks()], [1000000, 100000, 1000000, 100000])
        a, b = [p["fixed"] for p in self.plan["trialPlans"][:2]]
        self.assertEqual({key for key in a if a[key] != b[key]}, set(C.VARIABLE_FIXED_FIELDS))
        self.assertEqual(self.plan["fixedAcrossPoints"], C.common_fixed())
        for child in self.plan["trialPlans"]:
            for key in C.common_fixed(): self.assertEqual(child["fixed"][key], C.FIXED[key])

    def test_crossed_fixed_mapping_or_undeclared_client_change_rejected(self):
        for key, value in (("driverIdleMaxParkNs", 1000000), ("clientNakUnicastDelayNs", 100000),
                           ("driverIdleMaxSpins", 100), ("nodeDataPathIdleMinParkNs", 100)):
            plan = copy.deepcopy(self.plan["trialPlans"][1]); plan["fixed"][key] = value
            plan["planSha256"] = C.plan_identity(plan)
            with self.subTest(key=key), self.assertRaises(ValueError): C.validate_plan(plan)

    def test_load_argv_and_environment_identical_except_independent_output_state(self):
        arguments = []
        environments = []
        with patch.dict(C.os.environ, {}, clear=True):
            for child in self.plan["trialPlans"]:
                args = C.load_arguments(child)
                args[args.index("io.vectormatch.cluster.RemoteCapacityExperiment") + 1] = "<independent-trial>"
                arguments.append(args)
                env = C.clean_environment(child)
                self.assertEqual(env["VECTOR_DATA_PATH_MAX_PARK_NS"], str(child["task"]["nodeMaxParkNs"]))
                load_env = C.client_environment(child, env)
                self.assertEqual(load_env["VECTOR_DATA_PATH_MAX_PARK_NS"], "1000000")
                load_env["VECTOR_STATE_DIR"] = "<independent-state>"
                environments.append(load_env)
        self.assertTrue(all(a == arguments[0] for a in arguments))
        self.assertTrue(all(e == environments[0] for e in environments))
        self.assertFalse(any("vectormatch.node.dataPath" in arg for arg in arguments[0]))

    def test_missing_either_original_13k_baseline_blocks_ready_declaration(self):
        for rows in ([], ready_declaration()["baselines13000"][:1]):
            prior = ready_declaration(); prior["baselines13000"] = rows
            with self.assertRaises(ValueError): C.validate_prerequisite_declaration(prior)
        prior = ready_declaration(); prior["baselines13000"][0]["controllerSha256"] = "0" * 64
        with self.assertRaises(ValueError): C.validate_prerequisite_declaration(prior)
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(C.baseline_13000_prerequisite(C.BASELINE_IDS[0], Path(directory))["ready"])
            with self.assertRaises(ValueError): C.baseline_13000_prerequisite(C.BASELINE_IDS[0], Path(directory), required=True)

    def test_frozen_ownership_export_analysis_helpers_are_byte_identical(self):
        old = C.import_file("idle_guard_frozen_matrix", BASE / "capacity_matrix.py")
        self.assertEqual(C.sha(BASE / "capacity_matrix.py"), C.BASE_MATRIX_SHA256)
        names = ("cpu_loopback_network_environment", "install_launcher_adapter", "start_cpu_node", "enable_pidfd",
                 "checked_record", "spawn_owned", "stop_owned", "wait_post_samples", "counter_identity_check",
                 "archive_all", "safe_extract", "load_arguments", "matrix_trial_check", "continuation_check",
                 "collect", "execute", "status", "wait_completion", "overlay_space", "merge_watch", "copy_node_records")
        for name in names:
            with self.subTest(name=name): self.assertEqual(inspect.getsource(getattr(C, name)), inspect.getsource(getattr(old, name)))


class IdleStartupGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.draft_matrix(prerequisite={"jobId": C.PILOT_ID, "ready": False})["trialPlans"][1]

    def fixture(self, directory, corrupt=None):
        trial = Path(directory) / "trial"; trial.mkdir()
        C.save_new(trial / "trial.json", {"fixedNodeConfiguration": self.plan["fixed"]})
        for node in range(3):
            folder = trial / ("node" + str(node)); folder.mkdir()
            maximum = self.plan["task"]["nodeMaxParkNs"]
            C.save_new(folder / "process.json", {"arguments": ["java", "-Dvectormatch.node.dataPathMaxParkNs=" + str(maximum), "-cp", "lib/*", "Main"]})
            rows = []
            for index, role in enumerate(C.NODE_IDLE_ROLES, 1):
                selected = role in ("driver-shared", "archive-shared", "consensus", "service")
                yields = 5 if role.startswith("driver-") else 20
                rows.append("VECTOR_NODE_DATA_PATH_IDLE node=%d role=%s instanceId=%d runnerSelected=%s strategyClass=org.agrona.concurrent.BackoffIdleStrategy configuration=BackoffIdleStrategy{alias=backoff,maxSpins=10,maxYields=%d,minParkPeriodNs=1000,maxParkPeriodNs=%d}" % (node, role, index, str(selected).lower(), yields, maximum))
            rows.append("VECTOR_CLUSTER_STARTED node=%d driverThreading=SHARED driverIdleMaxSpins=10 driverIdleMaxYields=5 driverIdleMinParkNs=1000 driverIdleMaxParkNs=%d nodeDataPathIdlePolicyVersion=1 nodeDataPathMaxParkNs=%d nodeDataPathIdleInstancesDistinct=true" % (node, maximum, maximum))
            if node == 1 and corrupt == "one-role-maximum": rows[0] = rows[0].replace("maxParkPeriodNs=100000}", "maxParkPeriodNs=1000000}")
            if node == 1 and corrupt == "missing-role": rows.pop(0)
            if node == 1 and corrupt == "duplicate-instance": rows[1] = rows[1].replace("instanceId=2", "instanceId=1")
            (folder / "process.log").write_text("\n".join(rows) + "\n")
        verifier_path = Path(directory) / "pinned-verifier.py"
        verifier_path.write_text(self.plan["tools"]["scripts/verify-capacity-config.py"]["source"])
        return trial, C.import_file("idle_guard_actual_pinned_verifier", verifier_path)

    def test_all_eight_actual_role_classes_and_property_must_match_b_variant(self):
        with tempfile.TemporaryDirectory() as directory:
            trial, verifier = self.fixture(directory)
            result = C.actual_idle_check(self.plan, verifier, trial)
        self.assertTrue(result["passed"]); self.assertEqual(result["nodeMaxParkNs"], 100000)
        self.assertEqual([n["roleClassCount"] for n in result["nodes"]], [8, 8, 8])

    def test_wrong_role_park_missing_role_or_shared_instance_rejected(self):
        for corrupt in ("one-role-maximum", "missing-role", "duplicate-instance"):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory:
                trial, verifier = self.fixture(directory, corrupt)
                with self.assertRaises((AssertionError, ValueError)): C.actual_idle_check(self.plan, verifier, trial)


class ExplicitContinuationGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.draft_matrix(prerequisite=ready_declaration())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan_path = self.root / "registered.json"; C.save_new(self.plan_path, self.plan)
        self.destination = self.root / "evidence/2026-10-24/runpod-cpu/matrices" / C.MATRIX_ID

    def test_low_space_before_attempt_allows_only_same_unlaunched_stage_after_manual_space_fix(self):
        with patch.object(C, "REPO", self.root), patch.object(C, "pilot_prerequisite", return_value=self.plan["pilotPrerequisite"]), \
             patch.object(C, "overlay_space", return_value={"nextPointEligible": False}), patch.object(C, "execute") as launch:
            with self.assertRaises(ValueError): C.execute_registered_point(self.plan_path, "A1")
        launch.assert_not_called()
        self.assertFalse((self.destination / "point-executions").exists())

    def test_attempted_ambiguous_identity_cannot_be_resubmitted(self):
        with patch.object(C, "REPO", self.root), patch.object(C, "pilot_prerequisite", return_value=self.plan["pilotPrerequisite"]), \
             patch.object(C, "overlay_space", return_value={"nextPointEligible": True}), \
             patch.object(C, "execute", side_effect=TimeoutError("ambiguous launch")) as launch, patch("builtins.print"):
            self.assertEqual(C.execute_registered_point(self.plan_path, "A1"), 1)
            with self.assertRaises(ValueError): C.execute_registered_point(self.plan_path, "A1")
        self.assertEqual(launch.call_count, 1)

    def test_next_stage_without_valid_completed_prefix_cannot_launch(self):
        with patch.object(C, "REPO", self.root), patch.object(C, "pilot_prerequisite", return_value=self.plan["pilotPrerequisite"]), patch.object(C, "execute") as launch:
            with self.assertRaises((ValueError, OSError)): C.execute_registered_point(self.plan_path, "B1")
        launch.assert_not_called()

    def test_invalid_previous_point_cannot_be_bypassed(self):
        child = self.plan["trialPlans"][0]
        local = self.root / "first-point"; (local / "analysis").mkdir(parents=True)
        summary = {"trials": [{"measurementValid": False}]}; C.save_new(local / "analysis/summary.json", summary)
        point = {"id": child["jobId"], "task": child["task"], "analysisDirectory": str(local),
                 "analysisSummarySha256": C.sha(local / "analysis/summary.json"),
                 "completion": {"planSha256": child["planSha256"], "matrixTrialPassed": False,
                                "allOwnedProcessesStopped": True, "archiveComplete": True, "loadExitCode": 0},
                 "continuation": {"passed": False}}
        C.save_new(self.destination / "points" / (child["jobId"] + ".json"), point)
        with self.assertRaises(ValueError): C.completed_prefix(self.destination, self.plan, 1)

    def valid_prefix_fixture(self):
        C.save_new(self.destination / "plan.json", self.plan)
        for item in self.plan["trialPlans"]: C.save_new(self.destination / "trial-plans" / (item["jobId"] + ".json"), item)
        child = self.plan["trialPlans"][0]
        local = self.root / "first-valid-point"
        native = local / (child["jobId"] + ".tar.gz"); native.parent.mkdir(); native.write_bytes(b"already verified complete native archive fixture")
        C.save_new(local / "raw/full-state-manifest.json", {"files": {"fixture": "complete-at-collection"}})
        raw = local / "raw/evidence/runs" / child["jobId"] / "load-result.json"; C.save_new(raw, {"frozen": "raw input"})
        summary = {"trials": [{"measurementValid": True, "derived": {"unknownAtInitialDeadline": 0, "unknownUnresolved": 0},
                               "inputSha256": {"load-result.json": C.sha(raw)}}]}
        C.save_new(local / "analysis/summary.json", summary)
        C.save_new(local / "postprocess.json", {"exitCode": 0, "analysisIdentitySha256": C.ANALYSIS_ID})
        completion = {"planSha256": child["planSha256"], "matrixTrialPassed": True, "allOwnedProcessesStopped": True,
                      "archiveComplete": True, "loadExitCode": 0,
                      "archive": {"sha256": C.sha(native), "fullStateManifestSha256": C.sha(local / "raw/full-state-manifest.json")}}
        C.save_new(self.destination / "points" / (child["jobId"] + ".json"),
                   {"id": child["jobId"], "task": child["task"], "analysisDirectory": str(local),
                    "analysisSummarySha256": C.sha(local / "analysis/summary.json"), "completion": completion,
                    "continuation": {"passed": True}})
        return local, summary

    def test_explicit_next_point_after_valid_prefix_never_reissues_previous_identity(self):
        local, summary = self.valid_prefix_fixture()
        self.assertEqual(len(C.completed_prefix(self.destination, self.plan, 1)), 1)
        next_child = self.plan["trialPlans"][1]
        completion = {"planSha256": next_child["planSha256"], "matrixTrialPassed": True,
                      "allOwnedProcessesStopped": True, "archiveComplete": True, "loadExitCode": 0}
        with patch.object(C, "REPO", self.root), patch.object(C, "pilot_prerequisite", return_value=self.plan["pilotPrerequisite"]), \
             patch.object(C, "overlay_space", side_effect=[{"nextPointEligible": True}, {"nextPointEligible": False}]), \
             patch.object(C, "execute") as launch, patch.object(C, "wait_completion", return_value=completion), \
             patch.object(C, "collect", return_value={"directory": str(local), "summary": summary}), patch("builtins.print"):
            self.assertEqual(C.execute_registered_point(self.plan_path, "B1"), 0)
        self.assertEqual(launch.call_count, 1)
        self.assertEqual(C.read(launch.call_args.args[0])["task"]["stage"], "B1")
        saved = C.read(self.destination / "points" / (next_child["jobId"] + ".json"))
        self.assertFalse(saved["spaceAfter"]["nextPointEligible"])
        self.assertTrue(saved["continuation"]["passed"])

    def test_previous_archive_tampering_blocks_continuation(self):
        local, _ = self.valid_prefix_fixture()
        (local / (self.plan["trialPlans"][0]["jobId"] + ".tar.gz")).write_bytes(b"changed")
        with self.assertRaises(ValueError): C.completed_prefix(self.destination, self.plan, 1)


if __name__ == "__main__":
    unittest.main()
