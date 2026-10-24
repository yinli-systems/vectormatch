from pathlib import Path
import importlib.util
import signal
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('pg18_tools_build', Path(__file__).with_name('build-pg18-tools.py'))
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class FakeProcess:
    pid = 43210

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.returncode = None

    def wait(self, timeout):
        value = self.outcomes.pop(0)
        if isinstance(value, BaseException):
            raise value
        self.returncode = value
        return value


class BuildGuards(unittest.TestCase):
    def tearDown(self):
        MOD.CANCEL_SIGNAL = None

    def item(self, name, kind=tarfile.REGTYPE):
        member = tarfile.TarInfo(name)
        member.type = kind
        member.mode = 0o755 if kind == tarfile.DIRTYPE else 0o644
        return member

    def test_default_format_exact(self):
        text = '\n'.join('#define ' + k + ' ' + v for k, v in MOD.FORMAT_MACROS.items())
        self.assertEqual(MOD.verify_format(text), MOD.FORMAT_MACROS)

    def test_nondefault_blocksize_rejected(self):
        text = '\n'.join('#define ' + k + ' ' + v for k, v in MOD.FORMAT_MACROS.items())
        with self.assertRaisesRegex(ValueError, 'BLCKSZ'):
            MOD.verify_format(text.replace('#define BLCKSZ 8192', '#define BLCKSZ 16384'))

    def test_wrong_major_rejected(self):
        text = '\n'.join('#define ' + k + ' ' + v for k, v in MOD.FORMAT_MACROS.items())
        with self.assertRaisesRegex(ValueError, 'PG_VERSION'):
            MOD.verify_format(text.replace('"18.6"', '"17.6"'))

    def test_version_floors(self):
        valid = {'make': 'GNU Make 4.2.1', 'bison': 'bison (GNU Bison) 3.5.1',
                 'perl': 'v5.30.0\n', 'flex': 'flex 2.6.4'}
        self.assertEqual(MOD.verify_versions(valid)['make'], [4, 2, 1])
        for name, value in [('make', 'GNU Make 3.80'), ('bison', 'bison (GNU Bison) 2.2'),
                            ('perl', 'v5.12.0')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                MOD.verify_versions(dict(valid, **{name: value}))

    def test_tool_version_formats_are_distinct(self):
        MOD.verify_tool_version('pg_config', 'PostgreSQL 18.6\n')
        MOD.verify_tool_version('pg_controldata', 'pg_controldata (PostgreSQL) 18.6\n')
        with self.assertRaises(ValueError):
            MOD.verify_tool_version('pg_config', 'pg_config (PostgreSQL) 18.6')

    def test_work_dir_escape_rejected(self):
        for path in ['/workspace/build', '/opt/vectormatch-cpu/tool-builds/../escape',
                     '/opt/vectormatch-cpu/tool-builds/x/child', 'relative']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                MOD.validate_work_dir(path)

    def test_existing_work_dir_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            (base / 'existing').mkdir()
            (base / 'link').symlink_to(base / 'existing', target_is_directory=True)
            with mock.patch.object(MOD, 'WORK_BASE', base):
                for name in ['existing', 'link']:
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        MOD.validate_work_dir(base / name)
                self.assertEqual(MOD.validate_work_dir(base / 'new'), base / 'new')

    def test_tar_traversal_and_wrong_root(self):
        for name in ['../escape', '/etc/escape', 'other-root/file', 'postgresql-18.6/../escape']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                MOD.validate_members([self.item(name)])

    def test_tar_links_devices_duplicates_rejected(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE]:
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                MOD.validate_members([self.item('postgresql-18.6/x', kind)])
        with self.assertRaises(ValueError):
            MOD.validate_members([self.item('postgresql-18.6/x'), self.item('postgresql-18.6/x')])

    def test_tar_nondirectory_parent_rejected(self):
        with self.assertRaises(ValueError):
            MOD.validate_members([self.item('postgresql-18.6/x'), self.item('postgresql-18.6/x/y')])

    def test_tar_size_and_setuid_rejected(self):
        member = self.item('postgresql-18.6/x')
        member.size = MOD.MAX_MEMBER_BYTES + 1
        with self.assertRaises(ValueError):
            MOD.validate_members([member])
        member.size = 0
        member.mode = 0o4755
        with self.assertRaises(ValueError):
            MOD.validate_members([member])

    def test_benchmark_probe_does_not_return_full_args(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            (proc / '123').mkdir()
            (proc / '123/cmdline').write_bytes(b'java\x00org.openjdk.jmh.Main\x00secret-irrelevant-argument')
            found = MOD.benchmark_processes(proc)
            self.assertEqual(found, [{'pid': 123, 'markers': ['org.openjdk.jmh.']}])
            self.assertNotIn('secret', str(found))

    def test_execute_without_idle_confirmation_never_spawns(self):
        with mock.patch.object(MOD.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'idle'):
                MOD.execute({}, False)
            popen.assert_not_called()

    def test_wrong_os_never_spawns(self):
        with mock.patch.object(MOD.platform, 'system', return_value='Darwin'), \
             mock.patch.object(MOD.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'Linux'):
                MOD.execute({}, True)
            popen.assert_not_called()

    def test_only_two_leaf_targets_fixed_jobs(self):
        source = Path(__file__).with_name('postgresql-18.6.tar.bz2')
        value = MOD.plan(source, '/opt/vectormatch-cpu/tool-builds/pg18-tools-guards')
        self.assertEqual(value['jobs'], 2)
        self.assertEqual(value['makeTargets'], [
            ['make', '-j2', '-C', 'src/bin/pg_controldata', 'all'],
            ['make', '-j2', '-C', 'src/bin/pg_config', 'all']])
        self.assertTrue(value['doesNotDescribeOriginalZonkyBuild'])
        self.assertFalse(value['networkOrPackageInstallCommands'])

    def test_source_checksum_failure_no_workdir(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bad.tar.bz2'
            source.write_bytes(b'wrong source')
            with self.assertRaisesRegex(ValueError, 'SHA'):
                MOD.plan(source, '/opt/vectormatch-cpu/tool-builds/pg18-tools-invalid')

    def test_timeout_kills_only_new_owned_group_and_records_failure(self):
        process = FakeProcess([-9])
        records = []
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MOD.subprocess, 'Popen', return_value=process) as popen, \
             mock.patch.object(MOD.os, 'killpg') as kill, \
             mock.patch.object(MOD, 'group_members', return_value=[]):
            with self.assertRaises(RuntimeError):
                MOD.run_step('bounded', ['make', '-j2'], Path(directory), {},
                             Path(directory), records, timeout=0)
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            kill.assert_called_once_with(process.pid, signal.SIGKILL)
            self.assertTrue(records[0]['timedOut'])
            self.assertEqual(records[0]['exitCode'], -9)
            self.assertEqual(records[0]['remainingProcessGroupMembers'], [])

    def test_interruption_stops_owned_group_and_records_failure(self):
        process = FakeProcess([KeyboardInterrupt(), -9])
        records = []
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MOD.subprocess, 'Popen', return_value=process), \
             mock.patch.object(MOD.os, 'killpg') as kill, \
             mock.patch.object(MOD, 'group_members', return_value=[]):
            with self.assertRaises(RuntimeError):
                MOD.run_step('interrupted', ['make', '-j2'], Path(directory), {},
                             Path(directory), records, timeout=10)
            kill.assert_called_once_with(process.pid, signal.SIGKILL)
            self.assertTrue(records[0]['interrupted'])

    def test_remaining_group_is_not_claimed_stopped(self):
        process = FakeProcess([0])
        records = []
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MOD.subprocess, 'Popen', return_value=process), \
             mock.patch.object(MOD.os, 'killpg') as kill, \
             mock.patch.object(MOD, 'group_members', return_value=[{'pid': 56789, 'startTicks': 22}]), \
             mock.patch.object(MOD.time, 'monotonic', side_effect=[0, 0, 0, 4]):
            with self.assertRaises(RuntimeError):
                MOD.run_step('orphan', ['make', '-j2'], Path(directory), {},
                             Path(directory), records, timeout=10)
            kill.assert_not_called()
            self.assertEqual(records[0]['remainingProcessGroupMembers'][0]['pid'], 56789)

    def test_cli_cancellation_is_flag_only_and_never_spawns_next_command(self):
        MOD.request_cancel(signal.SIGTERM, None)
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(MOD.subprocess, 'Popen') as popen:
            with self.assertRaises(MOD.BuildCancelled):
                MOD.run_step('cancelled', ['make', '-j2'], Path(directory), {},
                             Path(directory), [], timeout=10)
            popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
