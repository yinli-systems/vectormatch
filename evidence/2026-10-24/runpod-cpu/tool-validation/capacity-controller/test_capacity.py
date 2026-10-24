"""Offline guard tests only: no SSH, JVM, remote workload, registration or mutation of frozen tools."""
import copy
import ast
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("cpu_capacity_under_test", Path(__file__).with_name("capacity.py"))
C = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = C
SPEC.loader.exec_module(C)


def plan():
    return C.draft_plan("cpu-pilot-offline-guard")


class CapacityGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = plan()

    def test_exact_plan_and_cpu_argv_are_pinned(self):
        p = copy.deepcopy(self.original)
        self.assertIs(C.validate_plan(p), p)
        args = C.load_arguments(p)
        self.assertEqual(args[0], "/opt/vectormatch-cpu/tools/jdk/bin/java")
        self.assertEqual(args[args.index("io.vectormatch.cluster.RemoteCapacityExperiment") + 1], p["paths"]["trial"])
        self.assertEqual(args[-10:], ["23000", "10000", "350000", "128", "64", "2000", "30000", "0", "20", "extended-350k-256"])

    def test_invalid_ids_cannot_escape_owned_directory(self):
        for ident in ("../x", "cpu-pilot-../x", "cpu-pilot-X", "cpu-pilot-a;echo", "cpu-pilot-", "gpu-pilot-1"):
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                C.paths(ident)

    def test_updated_hash_cannot_authorize_changed_pilot_scope_or_configuration(self):
        changes = (("scope", "THREE_HOSTS"), ("sourceRevision", "0" * 40), ("hostname", "other"),
                   ("minimumLiveFreeBytes", 0), ("expectedPreparedSnapshotSha256", "0" * 64))
        for name, value in changes:
            p = copy.deepcopy(self.original)
            p[name] = value
            p["planSha256"] = C.plan_identity(p)
            with self.subTest(name=name), self.assertRaises(ValueError):
                C.validate_plan(p)
        for name, value in (("rate", 20000), ("workers", 256), ("arrivals", 1)):
            p = copy.deepcopy(self.original)
            p["task"][name] = value
            p["planSha256"] = C.plan_identity(p)
            with self.assertRaises(ValueError):
                C.validate_plan(p)

    def test_source_archive_and_plan_digest_fail_closed(self):
        for mutation in (lambda p: p["tools"][C.TOOLS[0]].update(source="bad"),
                         lambda p: p.update(controllerSha256="0" * 64),
                         lambda p: p["analysisIdentity"].update(scope="changed")):
            p = copy.deepcopy(self.original)
            mutation(p)
            p["planSha256"] = C.plan_identity(p)
            with self.assertRaises(ValueError):
                C.validate_plan(p)
        p = copy.deepcopy(self.original)
        p["registeredAtUtc"] = "changed"
        with self.assertRaises(ValueError):
            C.validate_plan(p)

    def passing_metrics(self):
        result = {name: True for name in ("passed", "measurementValid", "canonicalSnapshotBytesVerified", "fixedLeaderVerified")}
        result["leaderChanged"] = False
        load = {name: 0 for name in C.ZERO_COUNTS}
        load.update(scheduledArrivals=350000, confirmedAcceptedCommands=350000, generatorTimingInvalid=False)
        configuration = {"workers": 128, "maxServiceRequestsInFlight": 128, "clientPendingCapacity": 128,
                         "clientDriverCount": 1, "clientSessionCount": 1, "clientTransportMode": "multiplexed",
                         "clientDriverMode": "shared", "clientAeronMode": "one-session-one-network-owner",
                         "preparedSnapshotSha256": C.PREPARED_SHA}
        return result, load, configuration

    def test_strict_pilot_requires_every_typed_zero_and_all350k(self):
        result, load, config = self.passing_metrics()
        self.assertTrue(C.strict_pilot(result, load, config)["passed"])
        for name in C.ZERO_COUNTS:
            for value in (None, False, "0", 1):
                modified = dict(load)
                modified[name] = value
                with self.subTest(name=name, value=value):
                    self.assertFalse(C.strict_pilot(result, modified, config)["passed"])
        modified = dict(load)
        modified["confirmedAcceptedCommands"] = 349999
        self.assertFalse(C.strict_pilot(result, modified, config)["passed"])

    def test_pending_capacity_and_full_canonical_checks_are_not_optional(self):
        result, load, config = self.passing_metrics()
        for key in ("clientPendingCapacity", "workers", "clientSessionCount"):
            modified = dict(config)
            modified.pop(key)
            self.assertFalse(C.strict_pilot(result, load, modified)["passed"])
        result["canonicalSnapshotBytesVerified"] = False
        self.assertFalse(C.strict_pilot(result, load, config)["passed"])

    def test_fuse_state_is_not_mislabelled_as_local_overlay(self):
        text = "1 0 0:1 / / rw - overlay overlay rw\n2 1 0:2 / /workspace rw - fuse.test remote rw\n"
        self.assertEqual(C.mount_for("/opt/vectormatch-cpu", text)["filesystem"], "overlay")
        self.assertEqual(C.mount_for("/workspace/jobs", text)["filesystem"], "fuse.test")

    def test_changed_pid_identity_never_receives_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / "process.json"
            record.write_text("{}")
            svc = Mock()
            svc.record_state.return_value = ("identity-mismatch", {"pid": 42})
            with self.assertRaises(ValueError):
                C.stop_owned(svc, record)
            svc.stop.assert_not_called()

    def test_python38_pidfd_compatibility_keeps_fd_bound_syscalls_and_signal_zero_probe(self):
        libc = Mock()
        libc.syscall.side_effect = [7, 0]
        with patch.object(C.platform, "system", return_value="Linux"), patch.object(C.platform, "machine", return_value="x86_64"), \
             patch.object(C.os, "pidfd_open", None, create=True), patch.object(C.signal, "pidfd_send_signal", None, create=True), \
             patch.object(C.ctypes, "CDLL", return_value=libc), patch.object(C.os, "close") as close, \
             patch.object(C.os, "set_inheritable"):
            result = C.enable_pidfd()
        self.assertEqual(result["mode"], "linux-x86_64-syscall-python38")
        calls = libc.syscall.call_args_list
        self.assertEqual(calls[0].args[0].value, 434)
        self.assertEqual(calls[1].args[0].value, 424)
        self.assertEqual(calls[1].args[2].value, 0)
        close.assert_called_once_with(7)

    def test_python38_pidfd_adapter_refuses_other_abi(self):
        with patch.object(C.os, "pidfd_open", None, create=True), patch.object(C.signal, "pidfd_send_signal", None, create=True), \
             patch.object(C.platform, "machine", return_value="aarch64"), self.assertRaises(ValueError):
            C.enable_pidfd()

    def test_archive_preserves_failed_unknown_raw_and_original_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "job"
            root.mkdir()
            (root / "state.bin").write_bytes(b"state\0" * 200)
            (root / "failure.json").write_text(json.dumps({"passed": False, "unknownUnresolved": 2}))
            (root / "arrivals.csv").write_text("index,outcome\n0,UNKNOWN_UNRESOLVED\n")
            archive = Path(temp) / "full.tar.gz"
            result = C.archive_all(root, archive)
            self.assertTrue(result["verifiedAllEntries"])
            self.assertTrue((root / "state.bin").exists())
            target = Path(temp) / "extracted"
            C.safe_extract(archive, target)
            self.assertEqual((target / "arrivals.csv").read_bytes(), (root / "arrivals.csv").read_bytes())
            with self.assertRaises(ValueError):
                C.archive_all(root, archive)

    def test_symlink_and_tar_traversal_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "job"
            root.mkdir()
            (root / "escape").symlink_to(Path(temp))
            with self.assertRaises(ValueError):
                C.archive_all(root, Path(temp) / "bad.tar.gz")
            archive = Path(temp) / "traversal.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                member = tarfile.TarInfo("../outside")
                out.addfile(member)
            with self.assertRaises(ValueError):
                C.safe_extract(archive, Path(temp) / "extracted")

    def test_import_and_draft_never_contact_remote(self):
        with patch.object(C, "remote_module", side_effect=AssertionError("network forbidden")):
            p = C.draft_plan("cpu-pilot-offline-draft")
            self.assertEqual(p["scope"], C.SCOPE)

    def test_detached_submission_payload_is_valid_python38_and_uses_same_job(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "plan.json"
            C.save_new(source, self.original)
            remote = Mock()
            remote.run.return_value = Mock(returncode=0, stdout="{}", stderr="")
            remote.upload.return_value = Mock(returncode=0)
            with patch.object(C, "remote_module", return_value=remote), patch("builtins.print"):
                C.execute(source)
            self.assertEqual(remote.run.call_count, 2)
            for call in remote.run.call_args_list:
                ast.parse(call.kwargs["input"], feature_version=(3, 8))
                self.assertIn(self.original["jobId"], call.kwargs["input"])

    def test_existing_control_job_never_uploads_or_reissues(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "plan.json"
            C.save_new(source, self.original)
            remote = Mock()
            remote.run.return_value = Mock(returncode=1, stdout="", stderr="already exists")
            with patch.object(C, "remote_module", return_value=remote), self.assertRaises(ValueError):
                C.execute(source)
            self.assertEqual(remote.run.call_count, 1)
            remote.upload.assert_not_called()

    def test_post_load_wait_requires_all_cnc_and_telemetry_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            watch = Path(temp)
            before = "2026-10-24T01:00:00.000000000Z"
            completed = "2026-10-24T01:00:01.123456+00:00"
            after = "2026-10-24T01:00:02.123456789Z"
            def write_samples(timestamp):
                for node in range(3):
                    (watch / ("node" + str(node) + "-counters.jsonl")).write_text(json.dumps({"kind": "sample", "timestamp": timestamp}) + "\n")
                (watch / "telemetry.jsonl").write_text(json.dumps({"type": "sample", "wallTimeUtc": timestamp}) + "\n")
            write_samples(before)
            sleeps = []
            def sleep(seconds):
                sleeps.append(seconds)
                write_samples(after)
            result = C.wait_post_samples(watch, completed, clock=lambda: 0, sleep=sleep)
            self.assertTrue(result["passed"])
            self.assertEqual(len(sleeps), 1)
            self.assertEqual(set(result["postSampleWallTimes"]), {"node0", "node1", "node2", "telemetry"})
            self.assertEqual(C.utc_datetime(after).microsecond, 123456)

    def test_post_load_wait_times_out_instead_of_treating_missing_observer_as_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            ticks = iter([0, 5])
            with self.assertRaisesRegex(ValueError, "within5s"):
                C.wait_post_samples(temp, "2026-10-24T01:00:01+00:00", clock=lambda: next(ticks),
                                    sleep=lambda _: self.fail("deadline must fail immediately"))

    def test_java_output_directory_is_not_precreated_by_observer_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            watch = root / "watch"
            watch.mkdir(parents=True)
            output = root / "evidence/runs/cpu-pilot-offline-guard"
            staging = {"root": root, "trial": output}
            (watch / "pre-members.json").write_text("{}")
            self.assertFalse(output.exists())
            output.mkdir(parents=True)  # Model Java's CREATE_NEW output ownership.
            (output / "configuration.json").write_text("{\"java\":true}")
            with patch.object(C, "paths", return_value=staging):
                C.merge_watch(self.original)
            self.assertTrue((output / "pre-members.json").exists())
            self.assertEqual((output / "configuration.json").read_text(), '{"java":true}')

    def test_preflight_failure_still_archives_original_failure_without_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "job"
            control = Path(temp).resolve() / "control"
            control.mkdir()
            plan_path = control / "plan.json"
            plan_path.write_text("{}")
            p = {"root": root, "state": root / "state", "evidence": root / "evidence",
                 "trial": root / "evidence/runs/cpu-pilot-offline-guard", "control": control,
                 "archive": Path(temp) / "failed.tar.gz"}
            with patch.object(C, "validate_plan", return_value=self.original), patch.object(C, "paths", return_value=p), \
                 patch.object(C, "preflight", side_effect=ValueError("insufficient overlay")), \
                 patch.object(C, "spawn_owned", side_effect=AssertionError("must never start")), \
                 patch("builtins.print"):
                self.assertEqual(C.worker(plan_path), 1)
            completion = json.loads((control / "completion.json").read_text())
            self.assertFalse(completion["strictPilotPassed"])
            self.assertFalse(completion["workloadLaunched"])
            self.assertTrue(completion["archiveComplete"])
            self.assertIn("insufficient overlay", (root / "receipt.json").read_text())

    def test_original_verifier_attests_cpu_schema_and_rejects_wrong_actual_load_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            tools = temp / "tools"
            source = self.original["tools"]["scripts/verify-capacity-config.py"]
            script = tools / "scripts/verify-capacity-config.py"
            script.parent.mkdir(parents=True)
            script.write_text(source["source"])
            verifier = C.import_file("cpu_config_test_original", script)
            p = copy.deepcopy(self.original)
            evidence = temp / "evidence"
            trial = evidence / "runs" / p["jobId"]
            trial.mkdir(parents=True)
            p["paths"]["evidence"] = str(evidence)
            p["paths"]["trial"] = str(trial)
            state = p["paths"]["state"]
            C.save_new(evidence / "campaign.json", {"fixed": C.FIXED})
            C.save_new(evidence / "deployment.json", p["deployment"])
            metadata = {**p["task"], "state": state, "release": str(C.RELEASE), "profile": C.FIXED["capacityProfile"],
                        "loadGeneratorRelease": str(C.RELEASE), "loadGeneratorJvmArguments": C.LOAD_FLAGS}
            C.save_new(trial / "trial.json", metadata)
            (trial / "prepared-snapshot.bin").write_bytes(b"synthetic exact prepared bytes")
            config = {"aeronMtuLength": 1248, "expectedLeader": 0, "queueCapacityPerWorker": 64,
                      "declaredOutboxCapacity": 800000, "profile": C.FIXED["capacityProfile"],
                      "expectedStateProfile": "capacity-350k-v1", "fullCheckpointMaximumBytes": 536870912,
                      "expectedCoreLimits": {"maxAccounts": 10000, "maxProducers": 10000,
                                             "maxRetainedOrders": 360000, "maxCachedResults": 100000},
                      "requestTimeoutMs": 2000, "drainTimeoutMs": 30000, "schedulerLatenessLimitMs": 20,
                      "portBase": 23000, "memberHosts": ["127.0.0.1"] * 3,
                      "preparedSnapshotSha256": C.sha(trial / "prepared-snapshot.bin"),
                      "clientTransportMode": "multiplexed", "clientSessionCount": 1,
                      "clientDriverMode": "shared", "clientDriverCount": 1,
                      "clientAeronMode": "one-session-one-network-owner", "clientNakUnicastDelayNs": 1000,
                      "clientNakUnicastRetryDelayRatio": 100, "clientPendingCapacity": 128,
                      "workers": 128, "maxServiceRequestsInFlight": 128}
            C.save_new(trial / "configuration.json", config)
            C.save_new(trial / "result.json", {"passed": True})
            for node in range(3):
                target = trial / ("node" + str(node))
                target.mkdir()
                argv = [str(C.JAVA), *C.OPENS, "-Xmx2g", "-Daeron.cluster.appointed.leader.id=0",
                        "-Daeron.cluster.max.sessions=256", "-Daeron.nak.unicast.delay=1000",
                        "-Dvectormatch.node.dataPathMaxParkNs=1000000", "-cp", str(C.RELEASE / "dist/cluster/lib/*"),
                        "io.vectormatch.cluster.ClusterNodeMain", *verifier.node_arguments(metadata, C.FIXED, node, ",".join(config["memberHosts"]))]
                C.save_new(target / "process.json", {"arguments": argv})
                startup = (f"VECTOR_CLUSTER_STARTED node={node} profile=capacity-350k-v1 outbox=800000 "
                           "checkpointMaxBytes=536870912 maxRetainedOrders=360000 resultCachePerProducer=1024 "
                           "requestedSocketReceiveBufferBytes=131072 driverThreading=SHARED driverIdleMaxSpins=10 "
                           "driverIdleMaxYields=5 driverIdleMinParkNs=1000 driverIdleMaxParkNs=1000000 "
                           "nakUnicastDelayNs=1000 nakUnicastRetryDelayRatio=100 nodeDataPathIdlePolicyVersion=1 "
                           "nodeDataPathMaxParkNs=1000000 nodeDataPathIdleInstancesDistinct=true\n")
                for index, role in enumerate(verifier.NODE_DATA_PATH_ROLES):
                    yields = 5 if role.startswith("driver-") else 20
                    selected = not role.startswith("driver-") or role == "driver-shared"
                    startup += (f"VECTOR_NODE_DATA_PATH_IDLE node={node} role={role} instanceId={index+1} "
                                f"runnerSelected={str(selected).lower()} strategyClass=org.agrona.concurrent.BackoffIdleStrategy "
                                f"configuration=BackoffIdleStrategy{{alias=backoff,maxSpins=10,maxYields={yields},minParkPeriodNs=1000,maxParkPeriodNs=1000000}}\n")
                (target / "process.log").write_text(startup)
            load_record = trial / "load-process.json"
            C.save_new(load_record, {"commandSha256": verifier.command_sha256(C.load_arguments(p))})
            with patch("builtins.print"):
                C.cpu_configuration_check(p, tools)
            self.assertTrue(C.read(trial / "cpu-configuration-adapter.json")["passed"])
            load_record.write_text(json.dumps({"commandSha256": "0" * 64}))
            with patch("builtins.print"), self.assertRaises(AssertionError):
                C.cpu_configuration_check(p, tools)


if __name__ == "__main__":
    unittest.main()
