import copy
import gzip
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("chain", Path(__file__).parents[1] / "audit-anchored-chain.py")
chain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chain)


class AnchoredChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = dict(lineage="one", firstCommand=1, lastCommand=5, acceptedTotal=3, samples=3,
                          parentPackSha256="0" * 64, initialSnapshotSha256="a" * 64,
                          finalSnapshotSha256="b" * 64, member="first/raw.pack")
        self.second = dict(lineage="one", firstCommand=6, lastCommand=8, acceptedTotal=6, samples=3,
                           parentPackSha256="1" * 64, initialSnapshotSha256="b" * 64,
                           finalSnapshotSha256="c" * 64, member="second/raw.pack")

    def cohort(self, name, pack, asset, raw_hash, histogram):
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        values = {
            "PRIVATE_ASSET_VERIFIED.json": dict(assetId=asset, sha256="f" * 64,
                allOriginalMembersVerified=True, authenticatedFullDownloadVerified=True, nativeRunsAndAuditsExited=True),
            "MEMBER_MANIFEST.json": {"files": {pack["member"]: {"sha256": raw_hash}}},
            "EXACT_SERVICE_SAMPLES.json": dict(replicated=False, allArrivalLatencyProven=False,
                packs=[pack], freshOrderSamples=chain.samples.quantiles(histogram))}
        for file, value in values.items():
            (folder / file).write_text(json.dumps(value))
        with gzip.open(folder / "exact-service-frequency.csv.gz", "wt") as stream:
            stream.write("duration_ns,count\n")
            for duration, count in histogram.items():
                stream.write(f"{duration},{count}\n")

    def setup_chain(self, second=None):
        self.cohort("a", self.first, 1, "1" * 64, {10: 2, 100: 1})
        self.cohort("b", second or self.second, 2, "2" * 64, {20: 3})

    def test_exact_union_not_average_of_percentiles(self):
        self.setup_chain()
        result = chain.audit(self.root, 6)
        self.assertEqual(20, result["exactFreshOrderServiceNs"]["p50Ns"])
        self.assertEqual(100, result["exactFreshOrderServiceNs"]["p99Ns"])
        self.assertEqual(1, result["separateColdContinuationBoundaries"])
        self.assertFalse(result["allArrivalLatencyProven"])

    def test_altered_parent_snapshot_and_lineage_are_rejected(self):
        for field in ["parentPackSha256", "initialSnapshotSha256", "lineage"]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.second)
                changed[field] = "changed"
                self.setup_chain(changed)
                with self.assertRaises(ValueError):
                    chain.audit(self.root, 6)

    def test_gap_duplicate_and_premature_target_are_rejected(self):
        for first in [5, 7]:
            changed = dict(self.second, firstCommand=first)
            self.setup_chain(changed)
            with self.assertRaises(ValueError):
                chain.audit(self.root, 6)
        self.setup_chain()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            chain.audit(self.root, 100_000_000)

    def test_unverified_asset_and_altered_histogram_are_rejected(self):
        self.setup_chain()
        receipt = self.root / "a/PRIVATE_ASSET_VERIFIED.json"
        value = json.loads(receipt.read_text())
        value["authenticatedFullDownloadVerified"] = False
        receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "receipt"):
            chain.audit(self.root, 6)
        self.setup_chain()
        with gzip.open(self.root / "a/exact-service-frequency.csv.gz", "wt") as stream:
            stream.write("duration_ns,count\n1,3\n")
        with self.assertRaisesRegex(ValueError, "quantiles"):
            chain.audit(self.root, 6)


if __name__ == "__main__":
    unittest.main()
