"""In-memory only: no ss, /proc or project process is contacted."""
import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location("owned_socket_buffer", Path(__file__).with_name("owned-socket-buffer.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class DiagnosticTest(unittest.TestCase):
    def test_empty_diagnostic_is_clean_success(self):
        self.assertEqual({"diagnosticCodes": [], "diagnosticLineCount": 0}, probe.ss_diagnostics(b"", 0))

    def test_exact_observed_warning_is_counted_without_raw_text(self):
        for count in (1, 2, 3):
            with self.subTest(count=count):
                self.assertEqual({"diagnosticCodes": ["SS_CGROUP2_MOUNT_METADATA_WARNING"],
                                  "diagnosticLineCount": count},
                                 probe.ss_diagnostics(probe.CGROUP2_WARNING * count, 0))

    def test_nonzero_exit_is_never_excused(self):
        for code in (-9, 1, 2):
            for stderr in (b"", probe.CGROUP2_WARNING):
                with self.subTest(code=code, stderr=stderr), self.assertRaisesRegex(ValueError, "^ss-error-or-diagnostic$"):
                    probe.ss_diagnostics(stderr, code)

    def test_near_match_blank_line_and_malformed_bytes_are_rejected(self):
        for stderr in (probe.CGROUP2_WARNING.rstrip(b"\n"), b" " + probe.CGROUP2_WARNING,
                       probe.CGROUP2_WARNING.replace(b"mount", b"mount "),
                       probe.CGROUP2_WARNING.replace(b"\n", b"\r\n"), b"\n", b"\xff\n"):
            with self.subTest(stderr=stderr), self.assertRaisesRegex(ValueError, "^ss-error-or-diagnostic$"):
                probe.ss_diagnostics(stderr, 0)

    def test_other_diagnostics_never_escape_in_error_text(self):
        private_text = b"sensitive-token-must-not-be-serialized\n"
        for stderr in (private_text, probe.CGROUP2_WARNING + private_text):
            with self.subTest(stderr=stderr):
                with self.assertRaises(ValueError) as error:
                    probe.ss_diagnostics(stderr, 0)
                self.assertEqual("ss-error-or-diagnostic", str(error.exception))


if __name__ == "__main__":
    unittest.main()
