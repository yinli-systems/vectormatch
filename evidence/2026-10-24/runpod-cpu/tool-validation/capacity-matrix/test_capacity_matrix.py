"""Local guards for the fixed CPU matrix. No SSH, JVM, registration or cloud work."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cpu_capacity_matrix_guard", BASE / "capacity_matrix.py")
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)


class MatrixGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.draft_matrix(prerequisite={"jobId": C.PILOT_ID, "ready": False})

    def test_exact_order_independent_states_and_v2_provenance(self):
        self.assertEqual([row["rate"] for row in C.matrix_tasks()], [13000, 18000, 26000, 13000, 18000, 26000])
        self.assertEqual([row["repetition"] for row in C.matrix_tasks()], [1, 1, 1, 2, 2, 2])
        paths = [row["paths"]["state"] for row in self.plan["trialPlans"]]
        self.assertEqual(len(set(paths)), 6)
        self.assertEqual(C.sha(BASE / "capacity_v2.py"), C.BASE_V2_SHA256)
        for plan in self.plan["trialPlans"]:
            C.validate_plan(plan)
            self.assertEqual(plan["baseControllerSha256"], C.BASE_V2_SHA256)
            self.assertEqual(plan["fixed"], C.FIXED)
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
        p["pilotPrerequisite"] = {"jobId": C.PILOT_ID, "ready": True, "closure": "checked"}
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

    def test_sequential_matrix_waits_exports_and_analyzes_all_six_points(self):
        code, calls, result = self.execute_mocked()
        self.assertEqual(code, 0)
        self.assertEqual(calls, [13000, 18000, 26000, 13000, 18000, 26000])
        self.assertTrue(result["completed"])
        self.assertEqual(result["unlaunchedIds"], [])

    def test_unknown_stops_remaining_points_without_reissue(self):
        code, calls, result = self.execute_mocked(unknown_at=1)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [13000, 18000])
        self.assertEqual(len(result["unlaunchedIds"]), 4)
        self.assertEqual(result["points"][1]["continuation"]["passed"], False)

    def test_low_space_keeps_archived_point_and_stops_without_prune(self):
        code, calls, result = self.execute_mocked(low_space_after=0)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [13000])
        self.assertIn("below3GiB", result["error"])
        self.assertEqual(len(result["unlaunchedIds"]), 5)

    def test_ambiguous_launch_timeout_never_resubmits_or_starts_next_point(self):
        code, calls, result = self.execute_mocked(transport_failure_at=0)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [13000])
        self.assertEqual(result["errorType"], "TimeoutError")
        self.assertEqual(len(result["unlaunchedIds"]), 5)

    def test_no_default_draft_network_and_python38_grammar(self):
        with patch.object(C, "remote_module", side_effect=AssertionError("network forbidden")):
            C.draft_matrix(prerequisite={"jobId": C.PILOT_ID, "ready": False})
        ast.parse((BASE / "capacity_matrix.py").read_text(), feature_version=(3, 8))
        self.assertEqual(C.sha(BASE / "capacity_v2.py"), C.BASE_V2_SHA256)


if __name__ == "__main__":
    unittest.main()
