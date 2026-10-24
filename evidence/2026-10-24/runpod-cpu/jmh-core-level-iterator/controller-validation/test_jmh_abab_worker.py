"""Offline evidence and ownership guards; never launches Java or a subprocess."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("jmh_abab_worker_offline", HERE / "jmh-abab-worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)

A_REVISION = "987f6526b8a0b3c3516ee668a239990cc79fbd8f"
B_REVISION = "7a4cf09be5055fa48c4246b21679d9038bbbfd5f"
ENGINE = "io/vectormatch/core/MatchingEngine.class"
CORE = "lib/core-0.1.0-SNAPSHOT.jar"
BENCH = "lib/vectormatch-core-jmh-0.1.0-SNAPSHOT.jar"
JMH = "lib/jmh-core-1.37.jar"
JARS = (CORE, BENCH, JMH, "lib/jopt-simple-5.0.4.jar", "lib/commons-math3-3.6.1.jar")
REJECTION = (AssertionError, ValueError, RuntimeError)


def valid_rows():
    """Independent 15-case matrix, with 30 finite, positive batch means per case."""
    common = {
        "jmhVersion": "1.37", "mode": "ss", "threads": 1, "forks": 3,
        "jvm": "/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java",
        "jvmArgs": ["-Xms2g", "-Xmx2g"], "jdkVersion": "21.0.13",
        "vmName": "OpenJDK 64-Bit Server VM", "vmVersion": "21.0.13+9-LTS",
        "warmupIterations": 500, "warmupTime": "single-shot", "warmupBatchSize": 1,
        "measurementIterations": 10, "measurementTime": "single-shot", "measurementBatchSize": 1,
        "primaryMetric": {"score": 1.0, "scoreError": 0.0,
                          "scoreConfidence": [1.0, 1.0], "scorePercentiles": {"50.0": 1.0},
                          "scoreUnit": "us/op", "rawData": [[1.0] * 10 for _ in range(3)]},
        "secondaryMetrics": {},
    }
    rows = []
    for depth in ("1", "100", "10000"):
        for trades in ("1", "10", "100"):
            row = copy.deepcopy(common)
            row.update(benchmark="io.vectormatch.bench.jmh.FreshMatchingBenchmark.matchBatch",
                       params={"initialPriceLevels": depth, "tradesPerCommand": trades})
            rows.append(row)
    for action in ("PLACE", "CANCEL"):
        for depth in ("1", "100", "10000"):
            row = copy.deepcopy(common)
            row.update(benchmark="io.vectormatch.bench.jmh.FreshPlaceCancelBenchmark.lifecycleBatch",
                       params={"action": action, "initialPriceLevels": depth})
            rows.append(row)
    return rows


def write_jar(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def jar_entries(path):
    with zipfile.ZipFile(path) as archive:
        return {entry.filename: archive.read(entry) for entry in archive.infolist()}


class RowsGuards(unittest.TestCase):
    def reject(self, rows):
        with self.assertRaises(REJECTION):
            WORKER.verify_rows(rows)

    def test_complete_fresh_matrix_is_valid(self):
        WORKER.verify_rows(valid_rows())

    def test_order_does_not_change_case_identity(self):
        WORKER.verify_rows(list(reversed(valid_rows())))

    def test_missing_and_duplicate_case_rejected(self):
        rows = valid_rows()
        self.reject(rows[:-1])
        rows[-1] = copy.deepcopy(rows[0])
        self.reject(rows)

    def test_extra_case_rejected(self):
        self.reject(valid_rows() + [copy.deepcopy(valid_rows()[0])])

    def test_wrong_benchmark_and_parameters_rejected(self):
        mutations = [
            ("benchmark", "io.vectormatch.bench.jmh.CachedRetryBenchmark.retryBatch"),
            ("params", {"initialPriceLevels": "2", "tradesPerCommand": "1"}),
            ("params", {"initialPriceLevels": "1", "tradesPerCommand": "1", "extra": "x"}),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                rows = valid_rows(); rows[0][key] = value; self.reject(rows)

    def test_exact_metadata_rejected_when_changed(self):
        mutations = {
            "jmhVersion": "1.36", "mode": "avgt", "threads": 2, "forks": 2,
            "jdkVersion": "21.0.12", "warmupIterations": 100,
            "measurementIterations": 9, "warmupBatchSize": 2, "measurementBatchSize": 2,
            "jvmArgs": ["-Xms1g", "-Xmx1g"],
        }
        for key, value in mutations.items():
            with self.subTest(key=key):
                rows = valid_rows(); rows[0][key] = value; self.reject(rows)
        rows = valid_rows(); rows[0]["primaryMetric"]["scoreUnit"] = "ns/op"; self.reject(rows)

    def test_raw_samples_must_be_finite_and_positive(self):
        for value in (math.nan, math.inf, -math.inf, 0.0, -1.0):
            with self.subTest(value=value):
                rows = valid_rows(); rows[0]["primaryMetric"]["rawData"][0][0] = value; self.reject(rows)

    def test_score_must_be_finite_positive_and_match_raw_mean(self):
        for value in (math.nan, math.inf, -math.inf, 0.0, -1.0, 1.01):
            with self.subTest(value=value):
                rows = valid_rows(); rows[0]["primaryMetric"]["score"] = value; self.reject(rows)

    def test_three_forks_ten_samples_each_required(self):
        for raw in ([[1.0] * 10] * 2, [[1.0] * 9] * 3, [[1.0] * 11] * 3):
            rows = valid_rows(); rows[0]["primaryMetric"]["rawData"] = raw; self.reject(rows)

    def test_unbalanced_raw_samples_still_use_actual_mean(self):
        rows = valid_rows()
        rows[0]["primaryMetric"]["rawData"] = [[1.0] * 10, [2.0] * 10, [6.0] * 10]
        rows[0]["primaryMetric"]["score"] = 3.0
        WORKER.verify_rows(rows)


class ArtifactGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jmh-abab-offline-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan = {"distributions": {}}
        for group, revision in (("A", A_REVISION), ("B", B_REVISION)):
            root = self.root / group
            for name in JARS:
                entries = {"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n",
                           "unchanged.class": (name + " shared content").encode()}
                if name == CORE:
                    entries = {"META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n",
                               ENGINE: (group + " engine implementation").encode(),
                               "io/vectormatch/core/MatchingEngine$Order.class": b"same nested class",
                               "io/vectormatch/core/CommandCodec.class": b"same unrelated class"}
                if name == BENCH:
                    entries.update({"META-INF/BenchmarkList": b"fresh matching and lifecycle",
                                    "META-INF/CompilerHints": b"same compiler hints",
                                    "io/vectormatch/bench/jmh/jmh_generated/fixture.class": b"same generated harness"})
                write_jar(root / name, entries)
            self.plan["distributions"][group] = {"root": str(root), "revision": revision,
                                                "files": {name: self.digest(root / name) for name in JARS}}

    @staticmethod
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def path(self, group, name):
        return Path(self.plan["distributions"][group]["root"]) / name

    def rewrite(self, group, name, mutate, rehash=True):
        path = self.path(group, name)
        entries = jar_entries(path); mutate(entries); write_jar(path, entries)
        if rehash:
            self.plan["distributions"][group]["files"][name] = self.digest(path)

    def reject(self):
        with self.assertRaises(REJECTION):
            WORKER.audit_artifacts(self.plan)

    def test_only_engine_entry_changes_is_valid(self):
        WORKER.audit_artifacts(self.plan)

    def test_wrong_registered_file_sha_rejected(self):
        self.plan["distributions"]["B"]["files"][CORE] = "0" * 64
        self.reject()

    def test_rehashed_unrelated_core_entry_rejected(self):
        self.rewrite("B", CORE, lambda entries: entries.__setitem__("io/vectormatch/core/CommandCodec.class", b"tampered"))
        self.reject()

    def test_rehashed_nested_engine_entry_rejected(self):
        self.rewrite("B", CORE, lambda entries: entries.__setitem__("io/vectormatch/core/MatchingEngine$Order.class", b"tampered"))
        self.reject()

    def test_rehashed_added_or_removed_core_entry_rejected(self):
        for operation in ("add", "remove"):
            with self.subTest(operation=operation):
                original = self.path("B", CORE).read_bytes()
                if operation == "add":
                    self.rewrite("B", CORE, lambda entries: entries.__setitem__("unexpected.class", b"new"))
                else:
                    self.rewrite("B", CORE, lambda entries: entries.pop("io/vectormatch/core/CommandCodec.class"))
                self.reject()
                self.path("B", CORE).write_bytes(original)
                self.plan["distributions"]["B"]["files"][CORE] = self.digest(self.path("B", CORE))

    def test_rehashed_benchmark_or_dependency_change_rejected(self):
        for name in (BENCH, JMH, "lib/jopt-simple-5.0.4.jar", "lib/commons-math3-3.6.1.jar"):
            with self.subTest(name=name):
                original = self.path("B", name).read_bytes()
                self.rewrite("B", name, lambda entries: entries.__setitem__("unchanged.class", b"tampered"))
                self.reject()
                self.path("B", name).write_bytes(original)
                self.plan["distributions"]["B"]["files"][name] = self.digest(self.path("B", name))

    def test_extra_unregistered_jar_rejected(self):
        write_jar(self.path("B", "lib/surprise.jar"), {"x": b"x"})
        self.reject()

    def test_extra_registered_jar_rejected(self):
        name = "lib/surprise.jar"
        write_jar(self.path("B", name), {"x": b"x"})
        self.plan["distributions"]["B"]["files"][name] = self.digest(self.path("B", name))
        self.reject()

    def test_missing_registered_jar_rejected(self):
        self.path("B", JMH).unlink()
        self.reject()

    def test_missing_manifest_member_rejected(self):
        del self.plan["distributions"]["B"]["files"][JMH]
        self.reject()

    def test_jar_symlink_rejected_even_when_sha_matches(self):
        path = self.path("B", JMH); outside = self.root / "outside.jar"
        path.replace(outside); path.symlink_to(outside)
        self.reject()

    def test_lib_directory_symlink_rejected(self):
        root = Path(self.plan["distributions"]["B"]["root"])
        (root / "lib").rename(root / "actual-lib"); (root / "lib").symlink_to(root / "actual-lib", target_is_directory=True)
        self.reject()

    def test_root_symlink_rejected(self):
        root = Path(self.plan["distributions"]["B"]["root"])
        link = self.root / "B-link"; link.symlink_to(root, target_is_directory=True)
        self.plan["distributions"]["B"]["root"] = str(link)
        self.reject()

    def test_wrong_or_swapped_revision_rejected(self):
        for group, value in (("A", B_REVISION), ("B", A_REVISION)):
            with self.subTest(group=group):
                prior = self.plan["distributions"][group]["revision"]
                self.plan["distributions"][group]["revision"] = value; self.reject()
                self.plan["distributions"][group]["revision"] = prior

    def test_duplicate_zip_entry_rejected(self):
        path = self.path("B", CORE)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "a") as archive:
                archive.writestr(ENGINE, b"duplicate engine")
        self.plan["distributions"]["B"]["files"][CORE] = self.digest(path)
        self.reject()


def process_record(pid, parent, arguments, start=None, session=100):
    return {"pid": pid, "startTicks": start if start is not None else pid * 10,
            "commandSha256": WORKER.command_sha(arguments), "arguments": list(arguments),
            "parentPid": parent, "processGroupId": session, "sessionId": session}


class FakeProc:
    """An explicit owned process tree. Reading it cannot enumerate real processes."""
    def __init__(self, identities=None, children=None):
        self.identities = dict(identities or {})
        self.child_map = dict(children or {})
        self.reads = []
        self.sequences = {}

    def identity(self, pid):
        self.reads.append(("identity", pid))
        sequence = self.sequences.get(pid)
        if sequence:
            value = sequence.pop(0)
        else:
            value = self.identities.get(pid)
        return copy.deepcopy(value)

    def children(self, pid):
        self.reads.append(("children", pid))
        return list(self.child_map.get(pid, []))


class FakeClock:
    def __init__(self):
        self.value = 0.0
        self.sleeps = 0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds
        self.sleeps += 1
        if self.sleeps > 100:
            raise AssertionError("Cleanup exceeded the bounded fake-clock wait")


class OwnershipGuards(unittest.TestCase):
    def setUp(self):
        self.java = "/offline/cpu/java"
        self.classpath = ["/offline/distribution/" + name for name in sorted(JARS)]
        self.runner = process_record(100, 50, [self.java, "-cp", "/offline/distribution/lib/*", "org.openjdk.jmh.Main"])
        self.fork = process_record(101, 100, [self.java, "-Xms2g", "-Xmx2g", "-cp",
                                           os.pathsep.join(self.classpath), WORKER.FORK_MAIN, "127.0.0.1", "12345"])
        self.reader = FakeProc({100: self.runner, 101: self.fork}, {100: [101]})

    def tracker(self):
        return WORKER.OwnedTracker(self.reader, self.runner, self.java, self.classpath)

    def pidfd_mocks(self):
        stack = __import__("contextlib").ExitStack()
        opened = stack.enter_context(mock.patch.object(WORKER.os, "pidfd_open", return_value=99, create=True))
        sent = stack.enter_context(mock.patch.object(WORKER.signal, "pidfd_send_signal", create=True))
        closed = stack.enter_context(mock.patch.object(WORKER.os, "close"))
        self.addCleanup(stack.close)
        return opened, sent, closed

    def test_pid_reuse_before_pidfd_never_signals(self):
        changed = copy.deepcopy(self.runner); changed["startTicks"] += 1
        self.reader.identities[100] = changed
        opened, sent, closed = self.pidfd_mocks()
        with self.assertRaises(REJECTION):
            WORKER.safe_signal(self.runner, self.reader, signal.SIGTERM)
        opened.assert_not_called(); sent.assert_not_called(); closed.assert_not_called()

    def test_pid_reuse_after_pidfd_closes_without_signal(self):
        changed = copy.deepcopy(self.runner); changed["commandSha256"] = "0" * 64
        self.reader.sequences[100] = [self.runner, changed]
        opened, sent, closed = self.pidfd_mocks()
        with self.assertRaises(REJECTION):
            WORKER.safe_signal(self.runner, self.reader, signal.SIGTERM)
        opened.assert_called_once_with(100); sent.assert_not_called(); closed.assert_called_once_with(99)

    def test_gone_after_pidfd_closes_without_signal(self):
        self.reader.sequences[100] = [self.runner, None]
        opened, sent, closed = self.pidfd_mocks()
        result = WORKER.safe_signal(self.runner, self.reader, signal.SIGTERM)
        self.assertTrue(result["alreadyStopped"])
        opened.assert_called_once_with(100); sent.assert_not_called(); closed.assert_called_once_with(99)

    def test_exact_identity_signals_only_bound_descriptor(self):
        opened, sent, closed = self.pidfd_mocks()
        result = WORKER.safe_signal(self.runner, self.reader, signal.SIGTERM)
        self.assertTrue(result["pidfdBound"])
        self.assertEqual(len(result["identityChecks"]), 2)
        opened.assert_called_once_with(100); sent.assert_called_once_with(99, signal.SIGTERM)
        closed.assert_called_once_with(99)

    def test_unrelated_forked_main_is_never_discovered(self):
        unrelated = process_record(777, 700, self.fork["arguments"], session=700)
        self.reader.identities[777] = unrelated
        tracker = self.tracker(); tracker.sample()
        self.assertEqual(set(tracker.records), {100, 101})
        self.assertFalse(any(pid == 777 for _, pid in self.reader.reads))

    def test_fork_discovery_requires_parent_session_java_heap_and_classpath(self):
        mutations = [
            lambda p: p.update(parentPid=999),
            lambda p: p.update(sessionId=999),
            lambda p: p.update(processGroupId=999),
            lambda p: p["arguments"].__setitem__(0, "/different/java"),
            lambda p: p["arguments"].__setitem__(1, "-Xms1g"),
            lambda p: p["arguments"].__setitem__(4, "/unexpected/lib.jar"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(self.fork); mutation(candidate)
                candidate["commandSha256"] = WORKER.command_sha(candidate["arguments"])
                self.reader.identities[101] = candidate
                tracker = self.tracker(); tracker.sample()
                self.assertNotIn(101, tracker.records)
                self.assertIn(101, tracker.candidates)

    def test_nested_fork_only_follows_already_verified_parent(self):
        grandchild = process_record(102, 101, self.fork["arguments"])
        self.reader.identities[102] = grandchild; self.reader.child_map[101] = [102]
        tracker = self.tracker(); tracker.sample(); tracker.sample()
        self.assertEqual(set(tracker.records), {100, 101, 102})
        self.assertEqual(tracker.summary()["forkIdentitiesObserved"], 2)

    def test_discovery_identity_reuse_fails_closed(self):
        changed = copy.deepcopy(self.fork); changed["startTicks"] += 1
        self.reader.sequences[101] = [self.fork, changed]
        tracker = self.tracker()
        with self.assertRaises(REJECTION):
            tracker.sample()
        self.assertNotIn(101, tracker.records)

    def test_unresolved_discovery_cannot_be_clean_when_runner_exits(self):
        changed = copy.deepcopy(self.fork); changed["startTicks"] += 1
        self.reader.sequences[101] = [self.fork, changed]
        tracker = self.tracker()
        with self.assertRaises(REJECTION):
            tracker.sample()
        self.reader.identities[100] = None; self.reader.child_map[100] = []
        changed["parentPid"] = 1; self.reader.identities[101] = changed
        with mock.patch.object(WORKER, "safe_signal") as sent:
            result = tracker.cleanup(term_seconds=0, kill_seconds=0)
        self.assertFalse(result["passed"])
        sent.assert_not_called()

    def test_known_child_pid_reappearing_with_new_identity_rejected(self):
        tracker = self.tracker(); tracker.sample()
        self.reader.identities[101] = None; self.reader.child_map[100] = []; tracker.sample()
        changed = copy.deepcopy(self.fork); changed["startTicks"] += 1
        self.reader.identities[101] = changed; self.reader.child_map[100] = [101]
        with self.assertRaises(REJECTION):
            tracker.sample()

    def test_candidate_pid_reuse_rejected(self):
        self.reader.identities[101] = process_record(101, 100, ["/bin/unknown-child"])
        tracker = self.tracker(); tracker.sample()
        self.reader.identities[101]["startTicks"] += 1
        with self.assertRaises(REJECTION):
            tracker.sample()

    def test_candidate_population_is_bounded(self):
        self.reader.identities[101] = process_record(101, 100, ["/bin/unknown-one"])
        self.reader.identities[102] = process_record(102, 100, ["/bin/unknown-two"])
        self.reader.child_map[100] = [101, 102]
        tracker = self.tracker()
        with mock.patch.object(WORKER, "MAX_OWNED", 2), self.assertRaises(REJECTION):
            tracker.sample()

    def test_full_ipv6_loopback_fork_is_recognized(self):
        self.fork["arguments"][-2] = "0:0:0:0:0:0:0:1"
        self.fork["commandSha256"] = WORKER.command_sha(self.fork["arguments"])
        self.reader.identities[101] = self.fork
        tracker = self.tracker(); tracker.sample()
        self.assertIn(101, tracker.records)

    def test_unverified_descendant_not_signalled_and_cleanup_not_claimed(self):
        self.reader.identities[101] = process_record(101, 100, ["/bin/unknown-child"])
        tracker = self.tracker(); tracker.sample()
        clock = FakeClock(); signalled = []
        def fake_signal(record, reader, signum):
            signalled.append(record["pid"])
            reader.identities[record["pid"]] = None
            reader.child_map[record["pid"]] = []
            return {"pid": record["pid"], "signal": int(signum)}
        with mock.patch.object(WORKER, "safe_signal", side_effect=fake_signal), \
                mock.patch.object(WORKER.time, "monotonic", side_effect=clock.monotonic), \
                mock.patch.object(WORKER.time, "sleep", side_effect=clock.sleep):
            result = tracker.cleanup(term_seconds=.03, kill_seconds=.03)
        self.assertFalse(result["passed"])
        self.assertNotIn(101, signalled)
        self.assertTrue(result["processes"]["unverifiedCandidates"])

    def test_cleanup_still_alive_is_bounded_and_fails(self):
        tracker = self.tracker(); tracker.sample()
        clock = FakeClock()
        with mock.patch.object(WORKER, "safe_signal", return_value={"mockOnly": True}) as sent, \
                mock.patch.object(WORKER.time, "monotonic", side_effect=clock.monotonic), \
                mock.patch.object(WORKER.time, "sleep", side_effect=clock.sleep):
            result = tracker.cleanup(term_seconds=.03, kill_seconds=.03)
        self.assertFalse(result["passed"])
        self.assertLessEqual(clock.value, .09)
        self.assertLess(clock.sleeps, 20)
        self.assertEqual(sent.call_count, 4)
        self.assertEqual(sent.call_args_list[0].args[0]["pid"], 100)

    def test_cleanup_all_verified_owned_processes_stopped(self):
        tracker = self.tracker(); tracker.sample()
        clock = FakeClock(); signalled = []
        def fake_signal(record, reader, signum):
            signalled.append(record["pid"])
            reader.identities[record["pid"]] = None
            reader.child_map[record["pid"]] = []
            return {"pid": record["pid"], "signal": int(signum)}
        with mock.patch.object(WORKER, "safe_signal", side_effect=fake_signal), \
                mock.patch.object(WORKER.time, "monotonic", side_effect=clock.monotonic), \
                mock.patch.object(WORKER.time, "sleep", side_effect=clock.sleep):
            result = tracker.cleanup(term_seconds=.03, kill_seconds=.03)
        self.assertTrue(result["passed"])
        self.assertEqual(signalled, [100, 101])
        self.assertTrue(all(record["stopped"] for record in result["processes"]["records"]))

    def test_proc_reader_handles_comm_spaces_parentheses_and_zombie(self):
        with tempfile.TemporaryDirectory(prefix="jmh-proc-offline-") as directory:
            root = Path(directory); path = root / "123"; path.mkdir()
            # Index19 after comm is /proc stat field22 (starttime).
            fields = ["S", "50", "123", "123"] + ["0"] * 15 + ["4567"]
            (path / "stat").write_text("123 (name with (parentheses)) " + " ".join(fields))
            (path / "cmdline").write_bytes(b"/offline/java\0main\0")
            task = path / "task" / "123"; task.mkdir(parents=True); (task / "children").write_text("124 125\n")
            reader = WORKER.ProcReader(root)
            actual = reader.identity(123)
            self.assertEqual((actual["startTicks"], actual["parentPid"]), (4567, 50))
            self.assertEqual(actual["arguments"], ["/offline/java", "main"])
            self.assertEqual(reader.children(123), [124, 125])
            fields[0] = "Z"; (path / "stat").write_text("123 (zombie) " + " ".join(fields))
            self.assertIsNone(reader.identity(123))
            self.assertIsNone(reader.identity(999)); self.assertEqual(reader.children(999), [])


class StageGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jmh-stage-offline-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan = {"jobId": "offline-abab-guard", "hostname": "ed6c0673f5cb",
                     "distributions": {"A": {"root": "/offline/A"}, "B": {"root": "/offline/B"}},
                     "stages": [{"id": name, "group": name[0], "expectedCases": 15,
                                 "forks": 3, "warmup": 500, "measurement": 10}
                                for name in ("A1", "B1", "A2", "B2")]}

    def test_validate_plan_rejects_wrong_sequence_or_fewer_samples(self):
        WORKER.validate_plan(self.plan)
        for key, value in (("forks", 2), ("warmup", 100), ("measurement", 9), ("expectedCases", 14)):
            plan = copy.deepcopy(self.plan); plan["stages"][0][key] = value
            with self.subTest(key=key), self.assertRaises(REJECTION):
                WORKER.validate_plan(plan)
        plan = copy.deepcopy(self.plan); plan["stages"][1]["group"] = "A"
        with self.assertRaises(REJECTION): WORKER.validate_plan(plan)

    def test_no_next_stage_after_stage_failure(self):
        with mock.patch.object(WORKER, "audit_artifacts", return_value={"passed": True}), \
                mock.patch.object(WORKER, "run_stage", side_effect=ValueError("offline stage failure")) as run:
            result = WORKER.run_stages(self.plan, self.root, {"signal": None})
        self.assertFalse(result["passed"]); self.assertEqual(run.call_count, 1)
        self.assertEqual(json.loads((self.root / "receipt.json").read_text())["activeStage"], "A1")

    def test_no_next_stage_after_cleanup_failure(self):
        with mock.patch.object(WORKER, "audit_artifacts", return_value={"passed": True}), \
                mock.patch.object(WORKER, "run_stage", return_value={"passed": True, "cleanup": {"passed": False}}) as run:
            result = WORKER.run_stages(self.plan, self.root, {"signal": None})
        self.assertFalse(result["passed"]); self.assertEqual(run.call_count, 1)

    def test_registered_signal_prevents_any_launch(self):
        with mock.patch.object(WORKER, "audit_artifacts") as audit, mock.patch.object(WORKER, "run_stage") as run:
            result = WORKER.run_stages(self.plan, self.root, {"signal": int(signal.SIGTERM)})
        self.assertFalse(result["passed"]); audit.assert_not_called(); run.assert_not_called()

    def test_pair_is_reaudited_before_and_after_every_stage(self):
        order = []
        def audit_pair(plan):
            order.append("audit")
            return {"passed": True}
        def completed_stage(stage, dist, root, stop):
            order.append(stage["id"])
            return {"passed": True, "cleanup": {"passed": True}}
        with mock.patch.object(WORKER, "audit_artifacts", side_effect=audit_pair) as audit, \
                mock.patch.object(WORKER, "run_stage", side_effect=completed_stage) as run:
            result = WORKER.run_stages(self.plan, self.root, {"signal": None})
        self.assertTrue(result["passed"]); self.assertEqual(audit.call_count, 8)
        self.assertEqual([call.args[0]["id"] for call in run.call_args_list], ["A1", "B1", "A2", "B2"])
        self.assertEqual(order, ["audit", "A1", "audit", "audit", "B1", "audit",
                                 "audit", "A2", "audit", "audit", "B2", "audit"])

    def test_changed_post_stage_artifact_prevents_next_stage(self):
        before = {"passed": True, "digest": "registered"}
        after = {"passed": True, "digest": "unexpected change"}
        with mock.patch.object(WORKER, "audit_artifacts", side_effect=[before, after]) as audit, \
                mock.patch.object(WORKER, "run_stage", return_value={"passed": True, "cleanup": {"passed": True}}) as run:
            result = WORKER.run_stages(self.plan, self.root, {"signal": None})
        self.assertFalse(result["passed"]); self.assertEqual(audit.call_count, 2)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["activeStage"], "A1")

    def test_failed_post_stage_audit_prevents_next_stage(self):
        with mock.patch.object(WORKER, "audit_artifacts", side_effect=[{"passed": True}, ValueError("changed JAR")]) as audit, \
                mock.patch.object(WORKER, "run_stage", return_value={"passed": True, "cleanup": {"passed": True}}) as run:
            result = WORKER.run_stages(self.plan, self.root, {"signal": None})
        self.assertFalse(result["passed"]); self.assertEqual(audit.call_count, 2)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["activeStage"], "A1")

    def test_signal_arriving_after_first_stage_prevents_next_launch(self):
        stop = {"signal": None}
        def interrupted_stage(stage, dist, root, mutable_stop):
            mutable_stop["signal"] = int(signal.SIGINT)
            return {"passed": True, "cleanup": {"passed": True}}
        with mock.patch.object(WORKER, "audit_artifacts", return_value={"passed": True}) as audit, \
                mock.patch.object(WORKER, "run_stage", side_effect=interrupted_stage) as run:
            result = WORKER.run_stages(self.plan, self.root, stop)
        self.assertFalse(result["passed"]); self.assertEqual(run.call_count, 1)
        self.assertEqual(result["interruptedSignal"], int(signal.SIGINT))


if __name__ == "__main__":
    unittest.main()
