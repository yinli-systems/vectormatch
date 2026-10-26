import gzip
import hashlib
import importlib.util
import io
import struct
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("anchored_samples", Path(__file__).parents[1] / "audit-anchored-samples.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def blob(data):
    return struct.pack(">i", len(data)) + data


def text(value):
    raw = value.encode("ascii")
    return struct.pack(">H", len(raw)) + raw


def frame(kind, raw):
    compressed = gzip.compress(raw)
    return struct.pack(">iii", kind, len(raw), len(compressed)) + hashlib.sha256(raw).digest() + compressed


def fixture(sequences=(1, 2, 3, 4, 5), durations=(999999, 888888, 10, 20, 30)):
    raw = struct.pack(">ii", 0x564D5034, 1)
    raw += frame(1, text("test") + text("a" * 64) + text("0" * 64) + struct.pack(">q", 3) + blob(b"initial"))
    body = struct.pack(">q", 1) + blob(b"ack") + blob(b"archive") + blob(b"outbox") + struct.pack(">i", len(sequences))
    body += b"".join(struct.pack(">qq", c, t) for c, t in zip(sequences, durations))
    raw += frame(2, body) + frame(3, b"journal replay belongs to Java auditor")
    raw += frame(4, struct.pack(">q", 1) + blob(b"checkpoint") + struct.pack(">10q", *([1] * 10)))
    raw += frame(5, blob(b"final") + struct.pack(">q", 100))
    return raw


class AnchoredSampleAuditTests(unittest.TestCase):
    def test_deposits_are_excluded_from_exact_order_quantiles(self):
        result, histogram = audit.read_pack(io.BytesIO(fixture()))
        self.assertEqual({10: 1, 20: 1, 30: 1}, dict(histogram))
        self.assertEqual(3, result["samples"])
        self.assertEqual(20, result["p50Ns"])
        self.assertEqual(30, result["p99Ns"])
        self.assertEqual(1, result["firstCommand"])
        self.assertEqual(5, result["lastCommand"])

    def test_duplicate_and_missing_absolute_command_samples_fail(self):
        for values in [(1, 2, 3, 3, 5), (1, 2, 3, 5, 6)]:
            with self.assertRaisesRegex(ValueError, "gap/duplicate"):
                audit.read_pack(io.BytesIO(fixture(values)))

    def test_truncation_and_changed_digest_fail(self):
        raw = fixture()
        with self.assertRaises(ValueError):
            audit.read_pack(io.BytesIO(raw[:-1]))
        changed = bytearray(raw)
        changed[20] ^= 1
        with self.assertRaisesRegex(ValueError, "digest"):
            audit.read_pack(io.BytesIO(changed))

    def test_oversized_compressed_frame_is_rejected_before_read(self):
        raw = bytearray(fixture())
        struct.pack_into(">i", raw, 16, 2**31 - 1)
        with self.assertRaisesRegex(ValueError, "frame bound"):
            audit.read_pack(io.BytesIO(raw))


if __name__ == "__main__":
    unittest.main()
