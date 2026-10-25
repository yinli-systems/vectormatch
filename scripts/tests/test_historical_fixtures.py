"""Historical regression inputs must keep the exact archived bytes and provenance."""
import hashlib
import json
from pathlib import Path
import unittest


class HistoricalFixtureTest(unittest.TestCase):
    def test_recorded_receipts_are_complete_and_unchanged(self):
        root = Path(__file__).resolve().parent / "fixtures/historical"
        manifest = json.loads((root / "MANIFEST.json").read_text())
        self.assertEqual("38d4ecf582eb4d06127d0ba89fd339c5e0b6dbf6", manifest["sourceRevision"])
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        self.assertEqual(set(manifest["files"]) | {"MANIFEST.json"}, actual)
        for name, pin in manifest["files"].items():
            with self.subTest(name=name):
                body = (root / name).read_bytes()
                self.assertEqual(pin["sourcePath"], "evidence/" + name)
                self.assertEqual(pin["bytes"], len(body))
                self.assertEqual(pin["sha256"], hashlib.sha256(body).hexdigest())
                self.assertEqual(pin["gitBlob"], hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest())
