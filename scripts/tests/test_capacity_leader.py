import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("capacity_leader", ROOT / "scripts/check-capacity-leader.py")
leader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(leader)


class CapacityLeaderTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        # Actual official ClusterTool list-members output from the earlier cloud run.
        raw = json.loads((Path(__file__).resolve().parent / "fixtures/historical/2026-10-23/runpod-cluster/before-cold-restart/node0.json").read_text())
        self.members = raw["list-members"]
        self.assertIn("leadershipTermId=3", self.members["stdout"])
        for name in ("pre-members.json", "post-members.json"):
            (self.directory / name).write_text(json.dumps(self.members))
        self.rows = {}
        for node in range(3):
            def sample(index):
                counters = []
                for slot, (name, (kind, label)) in enumerate(leader.COUNTERS.items()):
                    value = {"term": 3, "moduleState": 1, "role": 2 if node == 0 else 0}[name]
                    counters.append({"counterId": slot + 20, "registrationId": slot + 100,
                                     "typeId": kind, "label": label, "value": value})
                counters.extend([
                    {"counterId": 50, "typeId": 207, "label": "Cluster election state - clusterId=0", "value": 17},
                    {"counterId": 51, "typeId": 238, "label": "Cluster election count - clusterId=0", "value": 1},
                    {"counterId": 1, "typeId": 0, "label": "unrelated cumulative counter", "value": 1234 + index},
                ])
                return {"kind": "sample", "sample": index, "elapsedNanos": index * 1_000_000_000 + 10,
                        "counters": counters}
            self.rows[node] = [{"kind": "metadata", "readOnlyMapping": True}, sample(0), sample(1),
                               {"kind": "complete", "samples": 2}]
        self.save()

    def save(self):
        for node, rows in self.rows.items():
            (self.directory / f"node{node}-counters.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))

    def change(self, node, index, kind, **values):
        counter = next(c for c in self.rows[node][index]["counters"] if c["typeId"] == kind)
        counter.update(values)
        self.save()

    def check_failure(self, text):
        result = leader.check_trial(self.directory)
        self.assertFalse(result["passed"])
        self.assertTrue(any(text in error for error in result["errors"]), result["errors"])
        return result

    def test_actual_official_members_output_and_stable_counters_pass(self):
        result = leader.check_trial(self.directory)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual([3], result["observedTerms"])
        self.assertEqual({"0": [2], "1": [0], "2": [0]}, result["observedRoles"])

    def test_same_leader_with_new_term_is_rejected(self):
        after = copy.deepcopy(self.members)
        after["stdout"] = after["stdout"].replace("leadershipTermId=3", "leadershipTermId=4")
        (self.directory / "post-members.json").write_text(json.dumps(after))
        self.check_failure("leadership term changed")

    def test_term_transition_with_matching_pre_post_is_not_hidden(self):
        self.change(2, 2, 239, value=4)
        self.check_failure("term=4, expected 3")

    def test_candidate_or_second_leader_is_rejected(self):
        self.change(1, 2, 201, value=1)
        self.check_failure("role=1, expected 0")

    def test_non_active_module_is_rejected(self):
        self.change(0, 1, 200, value=2)
        self.check_failure("moduleState=2, expected 1")

    def test_missing_or_wrong_cluster_counter_cannot_pass(self):
        self.change(0, 1, 239, label="Cluster leadership term id - clusterId=1")
        self.check_failure("expected one term counter")

    def test_duplicate_role_counter_is_ambiguous(self):
        duplicate = copy.deepcopy(next(c for c in self.rows[1][1]["counters"] if c["typeId"] == 201))
        duplicate["counterId"] = 999
        self.rows[1][1]["counters"].append(duplicate)
        self.save()
        self.check_failure("found 2")

    def test_missing_file_is_unverified(self):
        (self.directory / "node2-counters.jsonl").unlink()
        self.check_failure("node2-counters.jsonl")

    def test_truncated_collection_cannot_pass(self):
        self.rows[0].pop()
        self.save()
        self.check_failure("missing completion record")

    def test_counter_re_registration_is_not_silently_joined(self):
        self.change(0, 2, 239, registrationId=9999)
        self.check_failure("term counter identity changed")

    def test_election_counter_change_or_open_election_invalidates_fixed_period(self):
        self.change(1, 2, 238, value=2)
        self.check_failure("election count changed")
        self.change(1, 1, 207, value=1)
        self.check_failure("electionState=1, expected 17")

    def test_collector_failure_and_invalid_json_are_reported(self):
        self.rows[2].insert(3, {"kind": "failure", "errorType": "IOException", "error": "CnC replaced"})
        self.save()
        self.check_failure("collector failure")
        with (self.directory / "node1-counters.jsonl").open("a") as stream:
            stream.write("{broken\n")
        self.check_failure("Expecting property name")

    def test_official_command_error_is_rejected_even_with_plausible_stdout(self):
        before = copy.deepcopy(self.members)
        before["returncode"] = 1
        (self.directory / "pre-members.json").write_text(json.dumps(before))
        self.check_failure("nonzero returncode")

    def test_cli_writes_reviewable_result_and_failure_exit_code(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, leader.main([str(self.directory)]))
        result = json.loads((self.directory / "fixed-leader-check.json").read_text())
        self.assertTrue(result["passed"])
        self.change(0, 1, 201, value=0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, leader.main([str(self.directory)]))
        self.assertFalse(json.loads((self.directory / "fixed-leader-check.json").read_text())["passed"])


if __name__ == "__main__":
    unittest.main()
