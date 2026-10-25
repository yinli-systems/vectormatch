import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "owned_process_identity.py"
SPEC = importlib.util.spec_from_file_location("owned_process_identity", SOURCE)
identity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(identity)


def stat(pid=123, state="R", start=456, flags=0):
    # state is field3;starttime is field22,not a whitespace split of comm.
    fields = [state] + ["0"] * 18 + [str(start)]
    fields[6] = str(flags)
    return (str(pid) + " (name with ) space) " + " ".join(fields)).encode()


class IdentityFixtureTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.process = self.root / "123"
        self.process.mkdir()
        (self.process / "stat").write_bytes(stat())
        (self.process / "cmdline").write_bytes(b"java\0-cp\0example\0\0\xff\0")

    def test_complete_arguments_preserve_bytes_empty_values_and_start_time(self):
        raw = (self.process / "cmdline").read_bytes()
        result = identity.read_identity(123, self.root)
        self.assertEqual(123, result["pid"])
        self.assertEqual(456, result["startTicks"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["commandSha256"])
        self.assertEqual(raw, b"".join(os.fsencode(v) + b"\0" for v in result["arguments"]))

    def test_absent_process_is_absent(self):
        self.assertIsNone(identity.read_identity(124, self.root))

    def test_zombie_never_needs_command_line(self):
        (self.process / "stat").write_bytes(stat(state="Z"))
        (self.process / "cmdline").unlink()
        self.assertIsNone(identity.read_identity(123, self.root))

    def test_exit_between_stat_and_empty_command_line_is_proven_by_second_stat(self):
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", stat(state="Z")]) as reads:
            self.assertIsNone(identity.read_identity(123, self.root))
        self.assertEqual(["stat", "cmdline", "stat"], [c.args[1] for c in reads.call_args_list])

    def test_live_empty_command_line_is_refused_after_bounded_retry(self):
        (self.process / "cmdline").write_bytes(b"")
        with patch.object(identity.time, "sleep") as sleep:
            with self.assertRaisesRegex(identity.IdentityReadError, "pid=123.*argvBytes=0"):
                identity.read_identity(123, self.root)
        self.assertEqual(2, sleep.call_count)

    def test_transient_live_empty_command_line_can_become_complete_without_absence(self):
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", stat(), stat(), b"java\0", stat()]), patch.object(identity.time, "sleep"):
            result = identity.read_identity(123, self.root)
        self.assertEqual(["java"], result["arguments"])

    def test_exiting_empty_command_line_waits_beyond_old_retry_before_terminal_proof(self):
        exiting = stat(flags=identity.PF_EXITING)
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", exiting] + [exiting] * 20 + [stat(state="Z")]), patch.object(identity.time, "sleep") as sleep:
            self.assertIsNone(identity.read_identity(123, self.root))
        self.assertEqual(20, sleep.call_count)

    def test_exiting_flag_alone_never_proves_absence_and_wait_is_read_bounded(self):
        (self.process / "stat").write_bytes(stat(flags=identity.PF_EXITING))
        (self.process / "cmdline").write_bytes(b"")
        with patch.object(identity.time, "sleep") as sleep, patch.object(identity.time, "monotonic", return_value=0):
            with self.assertRaisesRegex(identity.IdentityReadError, "Unproven process exit pid=123"):
                identity.read_identity(123, self.root)
        self.assertEqual(identity.EXIT_WAIT_READS, sleep.call_count)

    def test_exiting_wait_also_obeys_monotonic_deadline(self):
        (self.process / "stat").write_bytes(stat(flags=identity.PF_EXITING))
        (self.process / "cmdline").write_bytes(b"")
        with patch.object(identity.time, "sleep") as sleep, patch.object(identity.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(identity.IdentityReadError, "phase=exit-wait"):
                identity.read_identity(123, self.root)
        sleep.assert_not_called()

    def test_exiting_wait_cannot_accept_a_different_birth_even_if_zombie(self):
        exiting = stat(flags=identity.PF_EXITING)
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", exiting, stat(state="Z", start=999)]):
            with self.assertRaisesRegex(identity.IdentityReadError, "startTicks=456->999"):
                identity.read_identity(123, self.root)

    def test_exiting_wait_permission_failure_is_not_absence(self):
        exiting = stat(flags=identity.PF_EXITING)
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", exiting, PermissionError(13, "denied")]):
            with self.assertRaises(PermissionError):
                identity.read_identity(123, self.root)

    def test_exiting_wait_disappearance_is_proven_absence(self):
        exiting = stat(flags=identity.PF_EXITING)
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", exiting, ProcessLookupError(3, "exited")]):
            self.assertIsNone(identity.read_identity(123, self.root))

    def test_exiting_flag_disappearing_while_live_is_refused(self):
        exiting = stat(flags=identity.PF_EXITING)
        with patch.object(identity, "_read_at", side_effect=[stat(), b"", exiting, stat()]):
            with self.assertRaisesRegex(identity.IdentityReadError, "Unproven process exit"):
                identity.read_identity(123, self.root)

    def test_live_partial_arguments_are_refused_without_exposing_their_bytes(self):
        (self.process / "cmdline").write_bytes(b"do-not-log-this-secret")
        with patch.object(identity.time, "sleep"):
            with self.assertRaises(identity.IdentityReadError) as caught:
                identity.read_identity(123, self.root)
        self.assertNotIn("do-not-log-this-secret", str(caught.exception))
        self.assertIn("pid=123", str(caught.exception))

    def test_empty_executable_is_not_an_identity(self):
        (self.process / "cmdline").write_bytes(b"\0argument\0")
        with patch.object(identity.time, "sleep"):
            with self.assertRaises(identity.IdentityReadError):
                identity.read_identity(123, self.root)

    def test_changed_start_time_is_refused_even_with_complete_arguments(self):
        with patch.object(identity, "_read_at", side_effect=[stat(), b"java\0", stat(start=999)]):
            with self.assertRaisesRegex(identity.IdentityReadError, "pid=123 startTicks=456->999"):
                identity.read_identity(123, self.root)

    def test_malformed_stat_is_refused_before_arguments(self):
        (self.process / "stat").write_bytes(b"123 (short) R")
        with self.assertRaisesRegex(identity.IdentityReadError, "pid=123 phase=before"):
            identity.read_identity(123, self.root)

    def test_wrong_pid_in_stat_is_refused(self):
        (self.process / "stat").write_bytes(stat(pid=124))
        with self.assertRaises(identity.IdentityReadError):
            identity.read_identity(123, self.root)

    def test_permission_failure_is_never_reported_as_absence(self):
        with patch.object(identity.os, "open", side_effect=PermissionError(13, "denied")):
            with self.assertRaises(PermissionError):
                identity.read_identity(123, self.root)

    def test_symlink_process_directory_is_refused(self):
        (self.root / "124").symlink_to(self.process, target_is_directory=True)
        with self.assertRaises(OSError):
            identity.read_identity(124, self.root)

    def test_open_directory_cannot_switch_to_a_reused_path(self):
        read = identity._read_at
        first = True
        descriptors = []

        def replace_path_after_stat(fd, name, maximum):
            nonlocal first
            descriptors.append(fd)
            body = read(fd, name, maximum)
            if first:
                first = False
                self.process.rename(self.root / "retired-process")
                self.process.mkdir()
                (self.process / "stat").write_bytes(stat(start=999))
                (self.process / "cmdline").write_bytes(b"foreign-process\0")
            return body

        with patch.object(identity, "_read_at", side_effect=replace_path_after_stat):
            result = identity.read_identity(123, self.root)
        self.assertEqual(456, result["startTicks"])
        self.assertEqual("java", result["arguments"][0])
        with self.assertRaises(OSError):
            os.fstat(descriptors[0])

    def test_oversized_arguments_are_bounded_and_refused(self):
        (self.process / "cmdline").write_bytes(b"x" * 262145)
        with self.assertRaisesRegex(identity.IdentityReadError, "pid=123.*bounded cmdline"):
            identity.read_identity(123, self.root)

    def test_invalid_pid_types_are_refused(self):
        for pid in (True, False, 0, -1, "123", None):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                identity.read_identity(pid, self.root)


@unittest.skipUnless(sys.platform.startswith("linux"), "actual /proc semantics require Linux")
class LinuxProcessTest(unittest.TestCase):
    def test_owned_large_memory_natural_exit_keeps_proven_exit_semantics(self):
        code = ("import mmap,os,sys; "
                "m=mmap.mmap(-1,512*1024*1024,flags=mmap.MAP_PRIVATE|mmap.MAP_ANONYMOUS); "
                "m.madvise(mmap.MADV_NOHUGEPAGE); "
                "m[::4096]=b'x'*(len(m)//4096); "
                "print('READY',flush=True); "
                "assert sys.stdin.buffer.read(1)==b'x'; os._exit(0)")
        for _ in range(6):
            with subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
                self.assertEqual(b"READY\n", child.stdout.readline())
                before = identity.read_identity(child.pid)
                self.assertIsNotNone(before)
                child.stdin.write(b"x")
                child.stdin.flush()
                deadline = time.monotonic() + 3
                while child.poll() is None and time.monotonic() < deadline:
                    result = identity.read_identity(child.pid)
                    if result is None:
                        self.assertEqual(0, child.wait(timeout=2))
                    else:
                        self.assertEqual(before, result)
                self.assertEqual(0, child.wait(timeout=2))
                self.assertEqual(b"", child.stderr.read())
            self.assertFalse(Path("/proc", str(child.pid)).exists())

    def test_live_self_has_a_complete_stable_birth_and_command(self):
        first = identity.read_identity(os.getpid())
        second = identity.read_identity(os.getpid())
        self.assertEqual(first, second)
        self.assertEqual(os.getpid(), first["pid"])

    def test_owned_short_lived_children_exit_without_unproven_live_absence(self):
        for _ in range(30):
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.002)"])
            try:
                deadline = time.monotonic() + 2
                while child.poll() is None and time.monotonic() < deadline:
                    result = identity.read_identity(child.pid)
                    if result is None:
                        self.assertIsNotNone(child.poll())
                    else:
                        self.assertEqual(child.pid, result["pid"])
                        self.assertEqual(child.args, result["arguments"])
                self.assertEqual(0, child.wait(timeout=2))
            finally:
                if child.poll() is None:
                    child.wait(timeout=2)


if __name__ == "__main__":
    unittest.main()
