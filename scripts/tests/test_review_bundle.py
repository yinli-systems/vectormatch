import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC = importlib.util.spec_from_file_location("review_bundle", Path(__file__).parents[1] / "create-review-bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class ReviewBundleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        for name, value in {"README.md": "original\n", "gradlew": "#!/bin/sh\n",
                            "core/src/example.java": "class Example {}\n",
                            "evidence/index.json": "{}\n", "evidence/raw.bin": "excluded",
                            "runtime/credential-fixture.txt": "must not export"}.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        (self.repo / "gradlew").chmod(0o755)
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, stderr=subprocess.DEVNULL).decode().strip()

    def test_pinned_objects_exclude_raw_history_and_ignore_dirty_worktree(self):
        (self.repo / "README.md").write_text("uncommitted change")
        (self.repo / "core/untracked.txt").write_text("untracked")
        first = bundle.export(self.repo, "HEAD", self.root / "first")
        second = bundle.export(self.repo, "HEAD", self.root / "second")
        self.assertEqual(first, second)
        self.assertFalse(first["buildOrFunctionalTestsRun"])
        with zipfile.ZipFile(self.root / "first/source.zip") as archive:
            self.assertEqual(set(archive.namelist()), {"README.md", "gradlew", "core/src/example.java",
                                                       "evidence/index.json", "SOURCE_MANIFEST.json"})
            self.assertEqual(archive.read("README.md"), b"original\n")
            self.assertEqual(archive.getinfo("gradlew").external_attr >> 16, 0o100755)
            manifest = json.loads(archive.read("SOURCE_MANIFEST.json"))
            self.assertEqual(manifest["sourceCommit"], self.git("rev-parse", "HEAD"))

    def test_symlink_is_refused_without_reading_its_target(self):
        (self.repo / "core/link").symlink_to("../runtime/credential-fixture.txt")
        self.git("add", "core/link")
        self.git("commit", "-qm", "symlink fixture")
        with self.assertRaisesRegex(ValueError, "non-regular"):
            bundle.export(self.repo, "HEAD", self.root / "refused")
        self.assertFalse((self.root / "refused").exists())

    def test_per_file_and_total_bounds_stop_export(self):
        with patch.object(bundle, "MAX_FILE", 3), self.assertRaisesRegex(ValueError, "size bound"):
            bundle.export(self.repo, "HEAD", self.root / "file-bound")
        with patch.object(bundle, "MAX_TOTAL", 3), self.assertRaisesRegex(ValueError, "size bound"):
            bundle.export(self.repo, "HEAD", self.root / "total-bound")

    def test_unknown_revision_and_existing_output_fail_closed(self):
        with self.assertRaises(subprocess.CalledProcessError):
            bundle.export(self.repo, "missing-fixture-revision", self.root / "unknown")
        self.assertFalse((self.root / "unknown").exists())
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "keep").write_text("unchanged")
        with self.assertRaises(ValueError):
            bundle.export(self.repo, "HEAD", occupied)
        self.assertEqual((occupied / "keep").read_text(), "unchanged")


if __name__ == "__main__":
    unittest.main()
