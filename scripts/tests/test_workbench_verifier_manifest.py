import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "verify-replicated-workbench.py"
spec = importlib.util.spec_from_file_location("workbench_verifier_test", SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def cloud_manifest():
    return {"scope": "Runpod 3 Pods private UDP through a loopback SSH tunnel",
            "clusterMemberCount": 3, "clusterPrivateIps": ["10.0.212.169", "10.1.60.60", "10.2.3.4"],
            "physicalHostIsolationVerified": False, "gatewaySharesClusterMember": True,
            "postgresSharesClusterMember": True, "networkEvidencePath": "evidence/udp-pairs/index.json"}


def http_responses(mode="CLUSTER_REPLICATED"):
    account = {"id": 1, "quoteAvailable": 100, "quoteReserved": 0}
    placed = {"code": "ACCEPTED", "orderId": 42, "tradeCount": 0}
    return [{"health": {"mode": mode, "status": "UP"}, "accounts": [account]},
            {"enabled": False}, {"result": placed}, {"replayed": True, "result": placed},
            {"result": {"code": "IDEMPOTENCY_CONFLICT"}},
            {"result": {"code": "ACCEPTED"}, "events": [{"eventSeq": 111}]},
            {"consistent": True},
            {"accounts": [account], "projection": {"status": "OBSERVED", "cursor": 111}}]


class WorkbenchDeploymentManifestTest(unittest.TestCase):
    def test_default_keeps_original_local_scope_and_limitation(self):
        metadata = verifier.deployment_metadata(None)
        self.assertFalse(metadata["independentMachines"])
        self.assertEqual(verifier.SUMMARY_SCOPE, metadata["scope"])
        self.assertIn("Three cluster processes, gateway and PostgreSQL share one host.", metadata["limitations"])
        self.assertNotIn("deploymentManifest", metadata)

    def test_declared_isolation_does_not_become_a_verified_independent_machine_claim(self):
        manifest = {**cloud_manifest(), "physicalHostIsolationVerified": True}
        metadata = verifier.deployment_metadata(manifest)
        self.assertIsNone(metadata["independentMachines"])
        self.assertTrue(metadata["deploymentManifest"]["physicalHostIsolationVerified"])
        self.assertEqual("NOT_PERFORMED_BY_HTTP_VERIFIER", metadata["hostIsolationVerification"])
        self.assertIn("Caller-supplied layout", metadata["scope"])
        self.assertIn("not independently verified", metadata["deploymentMetadataProvenance"])
        self.assertFalse(any("share one host" in value for value in metadata["limitations"]))

    def test_manifest_schema_rejects_wrong_types_unknown_fields_and_unusable_ip_claims(self):
        invalid = [
            {**cloud_manifest(), "extra": "field"},
            {**cloud_manifest(), "clusterMemberCount": True},
            {**cloud_manifest(), "clusterMemberCount": 2},
            {**cloud_manifest(), "physicalHostIsolationVerified": "false"},
            {**cloud_manifest(), "clusterPrivateIps": ["10.0.0.1", "10.0.0.1", "10.0.0.3"]},
            {**cloud_manifest(), "clusterPrivateIps": ["10.0.0.1", "8.8.8.8", "10.0.0.3"]},
            {**cloud_manifest(), "scope": ""},
            {**cloud_manifest(), "networkEvidencePath": 42},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            for manifest in invalid:
                with self.subTest(manifest=manifest):
                    path.write_text(json.dumps(manifest))
                    with self.assertRaises(ValueError):
                        verifier.load_deployment_manifest(path)
            manifest = cloud_manifest()
            path.write_text(json.dumps(manifest))
            self.assertEqual(manifest, verifier.load_deployment_manifest(path))

    def test_cloud_summary_preserves_http_checks_trace_and_metadata_provenance(self):
        responses = http_responses()
        def urlopen(request, timeout):
            self.assertEqual(35, timeout)
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            manifest_path, output = directory / "manifest.json", directory / "result"
            manifest_path.write_text(json.dumps(cloud_manifest()))
            with patch.object(verifier.urllib.request, "urlopen", side_effect=urlopen), contextlib.redirect_stdout(io.StringIO()):
                verifier.main(["http://127.0.0.1:18001", str(output), str(manifest_path)])
            summary = json.loads((output / "summary.json").read_text())
            trace = json.loads((output / "trace.json").read_text())
            self.assertTrue(summary["passed"])
            self.assertIsNone(summary["independentMachines"])
            self.assertEqual(cloud_manifest(), summary["deploymentManifest"])
            self.assertTrue(summary["idempotentReplayVerified"])
            self.assertTrue(summary["payloadConflictVerified"])
            self.assertTrue(summary["replicatedSnapshotVerified"])
            self.assertEqual(111, summary["confirmedEventSeq"])
            self.assertEqual(8, len(trace))
            self.assertEqual([], responses)

    def test_manifest_cannot_override_actual_nonreplicated_http_backend(self):
        initial = http_responses("LOCAL_JOURNALED")[0]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            manifest_path, output = directory / "manifest.json", directory / "result"
            manifest_path.write_text(json.dumps(cloud_manifest()))
            with patch.object(verifier.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(initial).encode())):
                with self.assertRaisesRegex(AssertionError, "actual replicated backend"):
                    verifier.main(["http://127.0.0.1:18001", str(output), str(manifest_path)])
            self.assertFalse((output / "summary.json").exists())
            trace = json.loads((output / "trace.json").read_text())
            self.assertEqual("LOCAL_JOURNALED", trace[0]["response"]["health"]["mode"])


if __name__ == "__main__":
    unittest.main()
