import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("arrival_archive", ROOT / "scripts/archive-capacity-arrivals.py")
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)


class CapacityArrivalArchiveTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.data = b"index,status,latency_ns\n0,ACCEPTED,123\n1,CLIENT_QUEUE_FULL,\n2,UNKNOWN,\n" * 32
        self.raw = self.directory / archive.RAW
        self.raw.write_bytes(self.data)
        self.digest = hashlib.sha256(self.data).hexdigest()

    def compress(self):
        return archive.archive(self.directory, self.digest)

    def manifest(self):
        return json.loads((self.directory / archive.MANIFEST).read_text())

    def replace_manifest(self, **changes):
        (self.directory / archive.MANIFEST).write_text(json.dumps({**self.manifest(), **changes}))

    def assert_no_temporary(self):
        self.assertFalse(list(self.directory.glob(".arrivals-archive-*.tmp")))

    def test_round_trip_preserves_every_row_and_original_csv(self):
        before = self.raw.stat()
        result = self.compress()
        after = self.raw.stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_size),
                         (after.st_ino, after.st_mtime_ns, after.st_size))
        self.assertEqual(self.data, self.raw.read_bytes())
        self.assertEqual(self.digest, result["rawSha256"])
        self.assertEqual(len(self.data), result["rawBytes"])
        self.assertEqual(self.data, gzip.decompress((self.directory / archive.ARCHIVE).read_bytes()))
        self.raw.unlink()  # The caller, never the archiver, removes the independent test fixture.
        restored = archive.restore(self.directory)
        self.assertEqual("restored", restored["status"])
        self.assertEqual(self.data, self.raw.read_bytes())
        self.assert_no_temporary()

    def test_gzip_and_manifest_are_deterministic_without_timestamp_or_filename(self):
        self.compress()
        packed = (self.directory / archive.ARCHIVE).read_bytes()
        self.assertEqual(b"\x00\x00\x00\x00", packed[4:8])
        self.assertEqual(0, packed[3] & 8, "FNAME must be absent")
        other = self.directory / "other"
        other.mkdir()
        (other / archive.RAW).write_bytes(self.data)
        archive.archive(other, self.digest)
        self.assertEqual(packed, (other / archive.ARCHIVE).read_bytes())
        self.assertEqual((self.directory / archive.MANIFEST).read_bytes(), (other / archive.MANIFEST).read_bytes())

    def test_archive_requires_expected_sha_and_never_publishes_mismatched_evidence(self):
        for digest in ("0" * 64, "bad", self.digest.upper(), None):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                archive.archive(self.directory, digest)
            self.assertFalse((self.directory / archive.ARCHIVE).exists())
            self.assertFalse((self.directory / archive.MANIFEST).exists())
            self.assertEqual(self.data, self.raw.read_bytes())
            self.assert_no_temporary()

    def test_archive_never_overwrites_either_existing_output(self):
        for name in (archive.ARCHIVE, archive.MANIFEST):
            path = self.directory / name
            path.write_bytes(b"original existing evidence")
            with self.subTest(name=name), self.assertRaises(FileExistsError):
                self.compress()
            self.assertEqual(b"original existing evidence", path.read_bytes())
            self.assertEqual(self.data, self.raw.read_bytes())
            path.unlink()
        self.assert_no_temporary()

    def test_restore_verifies_existing_csv_without_modifying_it(self):
        self.compress()
        before = self.raw.stat()
        result = archive.restore(self.directory)
        self.assertEqual("already-present-verified", result["status"])
        after = self.raw.stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
        self.raw.write_bytes(b"different existing evidence")
        with self.assertRaisesRegex(ValueError, "refusing overwrite"):
            archive.restore(self.directory)
        self.assertEqual(b"different existing evidence", self.raw.read_bytes())
        self.assert_no_temporary()

    def test_concurrent_csv_creation_wins_without_being_overwritten_or_cleaned(self):
        self.compress()
        self.raw.unlink()
        original_publish = archive.publish

        def create_before_publish(descriptor, temporary_name, name):
            self.assertEqual(archive.RAW, name)
            self.raw.write_bytes(b"created concurrently")
            original_publish(descriptor, temporary_name, name)

        with patch.object(archive, "publish", create_before_publish), self.assertRaises(FileExistsError):
            archive.restore(self.directory)
        self.assertEqual(b"created concurrently", self.raw.read_bytes())
        self.assert_no_temporary()

    def test_compressed_tamper_is_rejected_before_any_csv_is_published(self):
        self.compress()
        self.raw.unlink()
        packed = self.directory / archive.ARCHIVE
        content = bytearray(packed.read_bytes())
        content[len(content) // 2] ^= 1
        packed.write_bytes(content)
        with self.assertRaisesRegex(ValueError, "Compressed SHA-256"):
            archive.restore(self.directory)
        self.assertFalse(self.raw.exists())
        self.assert_no_temporary()

    def test_updated_compressed_digest_does_not_hide_truncated_gzip(self):
        self.compress()
        self.raw.unlink()
        packed = self.directory / archive.ARCHIVE
        content = packed.read_bytes()[:-6]
        packed.write_bytes(content)
        self.replace_manifest(compressedBytes=len(content), compressedSha256=hashlib.sha256(content).hexdigest())
        with self.assertRaises((OSError, EOFError, ValueError)):
            archive.restore(self.directory)
        self.assertFalse(self.raw.exists())
        self.assert_no_temporary()

    def test_raw_hash_and_byte_count_are_independently_verified(self):
        self.compress()
        self.raw.unlink()
        original = (self.directory / archive.MANIFEST).read_bytes()
        for changes in ({"rawSha256": "0" * 64}, {"rawBytes": len(self.data) - 1}):
            self.replace_manifest(**changes)
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "Decoded CSV"):
                archive.restore(self.directory)
            self.assertFalse(self.raw.exists())
            self.assert_no_temporary()
            (self.directory / archive.MANIFEST).write_bytes(original)

    def test_decoded_size_limit_cannot_be_bypassed_by_false_manifest_size(self):
        self.compress()
        self.raw.unlink()
        content = gzip.compress(b"A" * 128, mtime=0)
        (self.directory / archive.ARCHIVE).write_bytes(content)
        self.replace_manifest(rawBytes=10, rawSha256=hashlib.sha256(b"A" * 128).hexdigest(),
                              compressedBytes=len(content), compressedSha256=hashlib.sha256(content).hexdigest())
        with patch.object(archive, "MAX_RAW_BYTES", 64), self.assertRaisesRegex(ValueError, "Decoded CSV exceeds"):
            archive.restore(self.directory)
        self.assertFalse(self.raw.exists())
        self.assert_no_temporary()

    def test_declared_sizes_and_manifest_names_are_bounded_and_fixed(self):
        self.compress()
        self.raw.unlink()
        original = (self.directory / archive.MANIFEST).read_bytes()
        for changes in ({"rawBytes": archive.MAX_RAW_BYTES + 1}, {"rawBytes": True},
                        {"compressedBytes": -1}, {"compressedBytes": 1.0},
                        {"rawFile": "../arrivals.csv"}, {"archiveFile": "other.gz"}):
            self.replace_manifest(**changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                archive.restore(self.directory)
            self.assertFalse(self.raw.exists())
            self.assert_no_temporary()
            (self.directory / archive.MANIFEST).write_bytes(original)

    def test_symlink_inputs_outputs_manifest_and_directory_are_rejected(self):
        target = self.directory / "target.csv"
        target.write_bytes(self.data)
        self.raw.unlink()
        self.raw.symlink_to(target)
        with self.assertRaises(OSError):
            self.compress()
        self.raw.unlink()
        self.raw.write_bytes(self.data)
        for name in (archive.ARCHIVE, archive.MANIFEST):
            path = self.directory / name
            path.symlink_to(target)
            with self.subTest(name=name), self.assertRaises(FileExistsError):
                self.compress()
            path.unlink()
        self.compress()
        self.raw.unlink()
        for name in (archive.ARCHIVE, archive.MANIFEST):
            path = self.directory / name
            saved = path.read_bytes()
            path.unlink()
            path.symlink_to(target)
            with self.subTest(name=name), self.assertRaises(OSError):
                archive.restore(self.directory)
            path.unlink()
            path.write_bytes(saved)
        self.raw.symlink_to(target)
        with self.assertRaises(ValueError):
            archive.restore(self.directory)
        linked_directory = self.directory / "linked-directory"
        linked_directory.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaises(OSError):
            archive.restore(linked_directory)
        self.assertEqual(self.data, target.read_bytes())
        self.assert_no_temporary()

    def test_mutating_input_is_detected_and_only_owned_temporary_files_are_cleaned(self):
        sentinel = self.directory / ".arrivals-archive-existing.tmp"
        sentinel.write_bytes(b"not owned by this invocation")
        original_write = gzip.GzipFile.write
        changed = False

        def write_and_change(stream, chunk):
            nonlocal changed
            result = original_write(stream, chunk)
            if not changed:
                changed = True
                self.raw.write_bytes(self.data + b"new row\n")
            return result

        with patch.object(gzip.GzipFile, "write", write_and_change), self.assertRaisesRegex(ValueError, "changed|differs"):
            self.compress()
        self.assertFalse((self.directory / archive.ARCHIVE).exists())
        self.assertFalse((self.directory / archive.MANIFEST).exists())
        self.assertEqual(b"not owned by this invocation", sentinel.read_bytes())
        self.assertEqual([sentinel], list(self.directory.glob(".arrivals-archive-*.tmp")))


if __name__ == "__main__":
    unittest.main()
