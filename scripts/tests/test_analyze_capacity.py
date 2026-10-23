import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "analyze-capacity.py"
SPEC = importlib.util.spec_from_file_location("analyze_capacity_test", SCRIPT)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class CapacityAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def fixture(self, name="trial", outcomes=None, latencies_ms=None, result=True):
        directory = self.root / name
        directory.mkdir()
        outcomes = outcomes or ["CONFIRMED_ACCEPTED"] * 100
        count = len(outcomes)
        latencies_ms = latencies_ms or [10] * count
        result_json = {"scheduledArrivals": count, "targetArrivalRatePerSecond": count / 10,
                       "workers": 4, "queueCapacityPerWorker": 16, "arrivalWindowSeconds": 10,
                       "passed": True, "measurementValid": True, "canonicalSnapshotBytesVerified": True,
                       "fixedLeaderVerified": True, "leaderChanged": False, "generatorTimingInvalid": False,
                       "schedulerLatenessAboveLimitCount": 0}
        (directory / ("result.json" if result else "load-result.json")).write_text(json.dumps(result_json))
        (directory / "trial.json").write_text(json.dumps({
            "id": name, "phase": "curve", "repetition": 1,
            "release": "/opt/vectormatch/releases/" + "a" * 40,
            "deploymentBundleSha256": "b" * 64,
            "fixedNodeConfiguration": {"archiveFileSyncLevel": 2, "maxHeap": "1g", "outboxCapacity": 65536,
                                       "appointedLeaderId": 0},
        }))
        (directory / "configuration.json").write_text(json.dumps({"preparedSnapshotSha256": "c" * 64}))
        (directory / "fixed-leader-check.json").write_text(json.dumps({"passed": True, "preTerm": 0, "postTerm": 0, "observedTerms": [0, 0], "observedRoles": ["LEADER"]}))
        columns = ["index", "outcome", "confirmed_offset_ns", "scheduled_to_confirmed_ns", "initial_execute_rtt_ns",
                   "queue_delay_ns", "scheduler_lateness_ns", "unknown_at_initial_deadline"]
        with (directory / "arrivals.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, columns)
            writer.writeheader()
            for index, (outcome, latency) in enumerate(zip(outcomes, latencies_ms)):
                confirmed = outcome in ("CONFIRMED_ACCEPTED", "BUSINESS_REJECTED", "SERVER_ERROR", "INVALID_REPLY")
                writer.writerow({"index": index, "outcome": outcome,
                                 "confirmed_offset_ns": int(index * 10e9 / count + latency * 1e6) if confirmed else "",
                                 "scheduled_to_confirmed_ns": int(latency * 1e6) if confirmed else "",
                                 "initial_execute_rtt_ns": int(latency * 1e6) if confirmed else "",
                                 "queue_delay_ns": 0 if confirmed else "", "scheduler_lateness_ns": 0,
                                 "unknown_at_initial_deadline": "false"})
        with (directory / "backlog.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, ["offset_ns", "queue_depth", "in_flight"])
            writer.writeheader()
            for second in range(11):
                writer.writerow({"offset_ns": second * 1_000_000_000, "queue_depth": 0, "in_flight": 1})
        return directory

    def test_stable_finite_trial_is_recomputed_without_latency_sla(self):
        directory = self.fixture(latencies_ms=[200] * 100)
        trial = analysis.analyze_trial(directory)
        self.assertTrue(trial["measurementValid"])
        self.assertTrue(trial["observedStableWindow"], "200 ms p99 is not an implicit latency SLA")
        self.assertEqual(200, trial["derived"]["allOfferedAcceptedP99Millis"])
        self.assertEqual(9.9, trial["derived"]["arrivalWindowGoodputPerSecond"])
        self.assertIsNone(trial["latencyTargetMet"])
        targeted = analysis.analyze_trial(directory, {"latencyTargetP99Millis": 100})
        self.assertFalse(targeted["latencyTargetMet"])
        self.assertTrue(targeted["observedStableWindow"])

    def test_drops_keep_conditional_p99_but_remove_all_offered_finite_p99(self):
        directory = self.fixture(outcomes=["CONFIRMED_ACCEPTED"] * 90 + ["CLIENT_QUEUE_FULL_NOT_SENT"] * 10)
        trial = analysis.analyze_trial(directory)
        self.assertTrue(trial["measurementValid"])
        self.assertFalse(trial["observedStableWindow"])
        self.assertEqual(10, trial["derived"]["latency"]["conditionalAccepted"]["p99Millis"])
        self.assertFalse(trial["derived"]["allOfferedAcceptedFinite"])
        self.assertIsNone(trial["derived"]["allOfferedAcceptedP99Millis"])
        self.assertEqual(10, trial["derived"]["clientQueueFullNotSent"])
        self.assertEqual(0, trial["derived"]["businessRejected"])

    def test_unknown_server_rejection_and_unsent_are_separate(self):
        directory = self.fixture(outcomes=["CONFIRMED_ACCEPTED"] * 96 + ["BUSINESS_REJECTED", "SERVER_ERROR", "UNKNOWN_UNRESOLVED", "WORKER_BLOCKED_UNKNOWN_NOT_SENT"])
        trial = analysis.analyze_trial(directory)
        derived = trial["derived"]
        self.assertEqual(1, derived["businessRejected"])
        self.assertEqual(1, derived["serverErrors"])
        self.assertEqual(1, derived["unknownUnresolved"])
        self.assertEqual(1, derived["clientNotSent"])
        self.assertEqual(98, derived["latency"]["conditionalReply"]["count"])

    def test_failure_artifact_and_missing_final_result_never_mark_stable(self):
        for name, final in (("failed", True), ("partial", False)):
            directory = self.fixture(name, result=final)
            if final:
                (directory / "failure.json").write_text('{"passed":false}')
            trial = analysis.analyze_trial(directory)
            self.assertFalse(trial["measurementValid"])
            self.assertFalse(trial["observedStableWindow"])
            self.assertEqual(100, trial["derived"]["confirmedAccepted"])

    def test_scheduler_invalid_term_change_or_csv_count_mismatch_invalidates_measurement(self):
        directory = self.fixture()
        source = directory / "result.json"
        raw = json.loads(source.read_text())
        raw["generatorTimingInvalid"] = True
        source.write_text(json.dumps(raw))
        self.assertFalse(analysis.analyze_trial(directory)["measurementValid"])
        raw["generatorTimingInvalid"] = False
        raw["confirmedAcceptedCommands"] = 99
        source.write_text(json.dumps(raw))
        self.assertEqual(1, len(analysis.analyze_trial(directory)["countMismatches"]))
        raw.pop("confirmedAcceptedCommands")
        source.write_text(json.dumps(raw))
        (directory / "fixed-leader-check.json").write_text('{"passed":true,"preTerm":0,"postTerm":1,"observedTerms":[0,1]}')
        self.assertFalse(analysis.analyze_trial(directory)["validationChecks"]["fixedLeaderTermEvidence"])

    def test_drain_is_not_counted_as_arrival_window_goodput(self):
        directory = self.fixture(latencies_ms=[2000] * 100)
        trial = analysis.analyze_trial(directory)
        self.assertEqual(81, trial["derived"]["confirmedWithinArrivalWindow"])
        self.assertGreater(trial["derived"]["confirmedIncludingDrainPerSecond"], trial["derived"]["arrivalWindowGoodputPerSecond"])
        self.assertFalse(trial["stabilityChecks"]["boundedDrain"])

    def test_backlog_uses_second_half_window_and_excludes_drain(self):
        rows = [{"offset_ns": str(second * 1_000_000_000), "queue_depth": str(second * 2), "in_flight": "4"} for second in range(11)]
        rows += [{"offset_ns": "11000000000", "queue_depth": "0", "in_flight": "0"}]
        result = analysis.analyze_backlog(rows, 10)
        self.assertEqual(6, result["secondHalfWindowSamples"])
        self.assertEqual(2, result["secondHalfOutstandingTrendCommandsPerSecond"])
        self.assertEqual(10, result["secondHalfFittedGrowthCommands"])

    def test_all_repetitions_retained_and_mixed_rate_not_claimed_stable(self):
        good = analysis.analyze_trial(self.fixture("good"))
        bad = analysis.analyze_trial(self.fixture("bad", outcomes=["CONFIRMED_ACCEPTED"] * 99 + ["CLIENT_QUEUE_FULL_NOT_SENT"]))
        group = analysis.summarize_groups([good, bad])[0]
        self.assertEqual(2, group["points"][0]["trials"])
        self.assertFalse(group["points"][0]["allReplicationsObservedStable"])
        self.assertIsNone(group["highestAllReplicationsStableObservedRate"])

    def test_short_window_and_missing_backlog_observations_are_not_instability_proof(self):
        directory = self.fixture()
        trial = analysis.analyze_trial(directory, {"minArrivalWindowSeconds": 20})
        self.assertTrue(trial["measurementValid"])
        self.assertEqual("INSUFFICIENT_WINDOW_OBSERVATIONS", trial["classification"])
        self.assertIsNone(analysis.summarize_groups([trial])[0]["lowestHigherValidNonstableObservedRate"])

    def test_different_request_timeout_is_not_merged_into_same_capacity_group(self):
        first, second = self.fixture("first"), self.fixture("second")
        for directory, timeout in ((first, 1000), (second, 2000)):
            path = directory / "configuration.json"
            configuration = json.loads(path.read_text())
            configuration["requestTimeoutMs"] = timeout
            path.write_text(json.dumps(configuration))
        groups = analysis.summarize_groups([analysis.analyze_trial(first), analysis.analyze_trial(second)])
        self.assertEqual(2, len(groups))

    def test_release_commit_is_derived_and_different_release_is_not_merged(self):
        first, second = self.fixture("first"), self.fixture("second")
        path = second / "trial.json"
        trial = json.loads(path.read_text())
        trial["release"] = "/opt/vectormatch/releases/" + "d" * 40
        path.write_text(json.dumps(trial))
        observations = [analysis.analyze_trial(first), analysis.analyze_trial(second)]
        self.assertTrue(all(row["measurementValid"] for row in observations))
        self.assertEqual("a" * 40, observations[0]["comparisonConfiguration"]["sourceRevision"])
        self.assertEqual("d" * 40, observations[1]["comparisonConfiguration"]["sourceRevision"])
        self.assertEqual(2, len(analysis.summarize_groups(observations)))

    def test_different_prepared_state_bundle_and_node_settings_are_separate_groups(self):
        for changed in ("preparedSnapshotSha256", "deploymentBundleSha256", "fixedNodeConfiguration"):
            with self.subTest(changed=changed):
                first, second = self.fixture("first-" + changed), self.fixture("second-" + changed)
                path = second / ("configuration.json" if changed == "preparedSnapshotSha256" else "trial.json")
                document = json.loads(path.read_text())
                document[changed] = ({"archiveFileSyncLevel": 0, "maxHeap": "1g"}
                                     if changed == "fixedNodeConfiguration" else "e" * 64)
                path.write_text(json.dumps(document))
                observations = [analysis.analyze_trial(first), analysis.analyze_trial(second)]
                self.assertTrue(all(row["measurementValid"] for row in observations))
                self.assertEqual(2, len(analysis.summarize_groups(observations)))

    def test_missing_identity_is_explicitly_unverified_not_stable(self):
        directory = self.fixture()
        path = directory / "trial.json"
        document = json.loads(path.read_text())
        del document["deploymentBundleSha256"]
        path.write_text(json.dumps(document))
        result = analysis.analyze_trial(directory)
        self.assertFalse(result["measurementValid"])
        self.assertFalse(result["observedStableWindow"])
        self.assertFalse(result["validationChecks"]["configurationIdentityVerified"])
        self.assertTrue(any("deploymentBundleSha256 missing" in issue for issue in result["configurationIdentityIssues"]))

    def test_disagreeing_explicit_source_revision_and_release_is_unverified(self):
        directory = self.fixture()
        path = directory / "trial.json"
        document = json.loads(path.read_text())
        document["sourceRevision"] = "f" * 40
        path.write_text(json.dumps(document))
        result = analysis.analyze_trial(directory)
        self.assertFalse(result["measurementValid"])
        self.assertIn("source revision declarations disagree", result["configurationIdentityIssues"])

    def test_source_alias_and_rate_worker_metadata_do_not_change_effective_identity(self):
        configuration = {"preparedSnapshotSha256": "c" * 64, "ratePerSecond": 100, "workers": 4}
        trial = {"release": "/opt/releases/" + "a" * 40, "deploymentBundleSha256": "b" * 64,
                 "fixedNodeConfiguration": {"syncLevel": 2}}
        before, errors = analysis.comparison_identity(configuration, trial)
        self.assertFalse(errors)
        configuration.update({"ratePerSecond": 200, "workers": 16})
        trial["sourceRevision"] = "a" * 40
        after, errors = analysis.comparison_identity(configuration, trial)
        self.assertFalse(errors)
        self.assertEqual(before, after)

    def test_malformed_arrival_index_is_retained_as_invalid_not_tool_crash(self):
        directory = self.fixture()
        path = directory / "arrivals.csv"
        lines = path.read_text().splitlines()
        lines[1] = lines[1].replace("0,", ",", 1)
        path.write_text("\n".join(lines) + "\n")
        trial = analysis.analyze_trial(directory)
        self.assertFalse(trial["measurementValid"])
        self.assertTrue(trial["derived"]["validationIssues"])

    def test_cli_writes_all_trials_json_csv_and_explicit_no_plot_status(self):
        runs = self.root / "runs"
        runs.mkdir()
        original_root = self.root
        self.root = runs
        self.fixture("a")
        self.fixture("b", result=False)
        self.root = original_root
        output = self.root / "analysis"
        analysis.main(["--runs-dir", str(runs), "--output-dir", str(output)])
        summary = json.loads((output / "summary.json").read_text())
        self.assertEqual(2, summary["counts"]["trials"])
        self.assertEqual("not-requested", summary["plots"]["status"])
        with (output / "capacity.csv").open() as handle:
            self.assertEqual(2, len(list(csv.DictReader(handle))))


if __name__ == "__main__":
    unittest.main()
