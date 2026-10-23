import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "summarize-capacity-repeats.py"
SPEC = importlib.util.spec_from_file_location("capacity_repeats_test", SCRIPT)
repeats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repeats)


def trial(identifier, rate=14000, stable=True, phase="screen", valid=True):
    return {"id": identifier, "phase": phase, "repetition": 1,
            "comparisonFingerprintSha256": "a" * 64, "workers": 128, "queueCapacityPerWorker": 64,
            "targetArrivalRatePerSecond": rate, "scheduledArrivals": 190000,
            "arrivalWindowSeconds": (190000 * 1000000000 // rate) / 1e9,
            "measurementValid": valid, "observedStableWindow": stable,
            "classification": repeats.STABLE if stable else repeats.NONSTABLE,
            "derived": {"clientNotSent": 0, "clientQueueFullNotSent": 0, "unknownAtInitialDeadline": 0,
                        "unknownUnresolved": 0, "businessRejected": 0, "serverErrors": 0, "confirmedAccepted": 190000,
                        "allOfferedAcceptedP99Millis": 10, "latency": {"conditionalAccepted": {"p99Millis": 10}}}}


class CapacityRepeatsTest(unittest.TestCase):
    def summarize(self, *rows):
        return repeats.summarize({"criteria": {"minArrivalWindowSeconds": 10}, "trials": list(rows)}, "f" * 64)

    def test_cross_phase_mixed_retains_every_observation_and_does_not_claim_repeated_stability(self):
        first, second = trial("screen-14k", stable=False), trial("confirm-14k", phase="confirm")
        first["derived"]["latency"]["conditionalAccepted"]["p99Millis"] = 109
        result = self.summarize(first, second)
        self.assertEqual([14000], result["mixedRates"])
        self.assertIsNone(result["highestRepeatedlyStableRate"])
        self.assertIsNone(result["lowestRepeatedlyNonstableRate"])
        group = result["groups"][0]
        self.assertEqual("MIXED", group["repeatVerdict"])
        self.assertEqual(["screen-14k", "confirm-14k"], group["trialIds"])
        self.assertEqual(["confirm", "screen"], group["phases"])
        self.assertEqual(2, len(group["classifications"]))
        self.assertEqual(109, group["conditionalAcceptedP99MillisRange"]["maximum"])

    def test_two_agreeing_cross_phase_trials_establish_repeated_finite_window(self):
        result = self.summarize(trial("a", rate=13000), trial("b", rate=13000, phase="repeat"),
                                trial("c", rate=16000, stable=False), trial("d", rate=16000, stable=False, phase="repeat"))
        self.assertEqual(13000, result["highestRepeatedlyStableRate"])
        self.assertEqual(16000, result["lowestRepeatedlyNonstableRate"])
        self.assertEqual(2, result["groups"][0]["eligibleStableTrials"])

    def test_single_observation_is_not_a_repeat_and_different_windows_remain_separate(self):
        first, second = trial("single"), trial("different-window")
        second["scheduledArrivals"], second["arrivalWindowSeconds"] = 140000, 10
        result = self.summarize(first, second)
        self.assertEqual(2, result["groupCount"])
        self.assertTrue(all(group["repeatVerdict"] == "INSUFFICIENT_REPETITIONS" for group in result["groups"]))
        self.assertIsNone(result["highestRepeatedlyStableRate"])

    def test_invalid_or_short_trials_cannot_be_cherry_picked_into_repeated_result(self):
        first, second = trial("valid"), trial("invalid", valid=False)
        result = self.summarize(first, second)
        self.assertEqual("INCONCLUSIVE", result["groups"][0]["repeatVerdict"])
        self.assertIsNone(result["highestRepeatedlyStableRate"])
        first["arrivalWindowSeconds"] = second["arrivalWindowSeconds"] = 9.9
        second["measurementValid"] = True
        self.assertIsNone(self.summarize(first, second)["highestRepeatedlyStableRate"])

    def test_mixed_fingerprint_is_rejected_even_for_an_invalid_trial(self):
        first, second = trial("a"), trial("b", valid=False)
        second["comparisonFingerprintSha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "Mixed configuration"):
            self.summarize(first, second)

    def test_missing_or_malformed_fingerprint_is_not_silently_grouped(self):
        for fingerprint in (None, "", [], "a" * 63):
            row = trial("missing-identity")
            row["comparisonFingerprintSha256"] = fingerprint
            with self.subTest(fingerprint=fingerprint):
                with self.assertRaisesRegex(ValueError, "requires a configuration fingerprint"):
                    self.summarize(row)

    def test_loss_unknown_totals_are_separate_and_missing_values_are_not_zero(self):
        first, second = trial("a", stable=False), trial("b", stable=False)
        first["derived"].update(clientNotSent=7, clientQueueFullNotSent=7, unknownAtInitialDeadline=2, unknownUnresolved=1,
                                allOfferedAcceptedP99Millis=None)
        second["derived"].pop("serverErrors")
        result = self.summarize(first, second)
        totals = result["totalsAcrossAllTrials"]
        self.assertEqual(7, totals["clientNotSentTotal"])
        self.assertEqual(2, totals["initialUnknownTotal"])
        self.assertEqual(1, totals["unresolvedUnknownTotal"])
        self.assertIsNone(totals["serverErrorsTotal"])
        self.assertEqual(["b"], totals["missingCounterTrialIds"]["serverErrorsTotal"])
        self.assertEqual(["a"], totals["allOfferedAcceptedP99UnavailableTrialIds"])

    def test_duplicate_ids_are_refused_and_worker_counts_are_not_merged(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.summarize(trial("same"), trial("same"))
        first, second = trial("a"), trial("b")
        second["workers"] = 64
        self.assertEqual(2, self.summarize(first, second)["groupCount"])

    def test_cli_records_exact_input_sha_and_refuses_source_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "summary.json", Path(directory) / "repeats.json"
            encoded = json.dumps({"trials": [trial("a"), trial("b", phase="repeat")]}) + "\n"
            source.write_text(encoded)
            repeats.main([str(source), str(output)])
            result = json.loads(output.read_text())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), result["inputSummarySha256"])
            self.assertEqual(2, result["trialCount"])
            self.assertEqual(14000, result["highestRepeatedlyStableRate"])
            with self.assertRaises(SystemExit):
                repeats.main([str(source), str(source)])
            self.assertEqual(encoded, source.read_text())


if __name__ == "__main__":
    unittest.main()
