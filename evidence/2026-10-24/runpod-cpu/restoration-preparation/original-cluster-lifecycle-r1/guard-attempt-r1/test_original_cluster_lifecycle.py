import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('lifecycle', HERE / 'original_cluster_lifecycle.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Guards(unittest.TestCase):
    def setUp(self):
        self.plan = m.load_plan()
        self.identity = {'pid': 12345, 'startTicks': 67890, 'arguments': ['/registered/java', '-cp', '/registered/lib', 'io.vectormatch.AnyRole'],
                         'commandSha256': ''}
        self.identity['commandSha256'] = m.argv_digest(self.identity['arguments'])

    def test_default_action_does_not_execute(self):
        with patch.object(m, 'preflight', return_value={'readOnly': True}) as read, patch.object(m, 'execute') as start, patch('builtins.print'):
            m.main([])
        read.assert_called_once()
        start.assert_not_called()

    def test_only_explicit_start_new_calls_execute(self):
        with patch.object(m, 'preflight') as read, patch.object(m, 'execute', return_value={'passed': True}) as start, patch('builtins.print'):
            m.main(['--start-new'])
        read.assert_not_called()
        start.assert_called_once()

    def test_abbreviated_or_old_execute_flags_rejected(self):
        for flag in ['--start', '--execute', '--yes']:
            with patch.object(m, 'execute') as start, patch('sys.stderr'), self.assertRaises(SystemExit):
                m.main([flag])
            start.assert_not_called()

    def test_frozen_plan_and_exact_original_closure(self):
        self.assertEqual(hashlib.sha256((HERE / 'plan.json').read_bytes()).hexdigest(), m.PLAN_SHA)
        self.assertEqual([len(n['files']) for n in self.plan['nodes']], [16, 17, 18])
        self.assertEqual(sum(len(n['files']) for n in self.plan['nodes']), 51)
        self.assertEqual(self.plan['helperJar']['sha256'], 'd83df3e4369d35501dd43aa8404276234a04f21c1861b6026301ec5dfd0d7be6')

    def test_node_arguments_fixed_original_source_and_each_clone(self):
        for n in range(3):
            args = m.node_argv(self.plan, n, '/owned/private/lib')
            start = args.index('io.vectormatch.cluster.ClusterNodeMain')
            self.assertEqual(args[start + 1:], [str(n), str(Path(self.plan['nodes'][n]['base']).parent), '19000', '2', '65536', '127.0.0.1,127.0.0.1,127.0.0.1'])
            self.assertIn('-Xmx1g', args)
            self.assertNotIn('*', args[args.index('-cp') + 1])
            self.assertEqual(len(args[args.index('-cp') + 1].split(':')), 4)

    def test_probe_only_new_tail_aware_r2_class(self):
        args = m.probe_argv(self.plan, '/owned/private')
        self.assertIn('io.vectormatch.cluster.ProbeOriginalRestorationR2', args)
        self.assertNotIn('io.vectormatch.cluster.ProbeOriginalRestoration', args)
        self.assertEqual(args[-1], '/opt/vectormatch-cpu/preparation/original-cluster-probe-r2/result')
        self.assertIn('-Xmx128m', args)

    def test_identity_independent_of_role(self):
        with patch.object(m, 'process_identity', return_value=self.identity):
            self.assertEqual(m.matching_identity(self.identity), self.identity)

    def test_changed_start_ticks_rejected_without_signal(self):
        changed = dict(self.identity, startTicks=1)
        with patch.object(m, 'process_identity', return_value=changed), patch.object(m.signal, 'pidfd_send_signal', create=True) as send:
            with self.assertRaises(RuntimeError):
                m.matching_identity(self.identity)
        send.assert_not_called()

    def test_changed_argv_or_hash_rejected(self):
        for changed in [dict(self.identity, arguments=['other']), dict(self.identity, commandSha256='f' * 64)]:
            with patch.object(m, 'process_identity', return_value=changed), self.assertRaises(RuntimeError):
                m.matching_identity(self.identity)

    def test_stable_pidfd_rechecks_before_signal(self):
        with patch.object(m, 'process_identity', side_effect=[self.identity, self.identity, None]), \
                patch.object(m.os, 'pidfd_open', return_value=7, create=True), \
                patch.object(m.signal, 'pidfd_send_signal', create=True) as send, \
                patch.object(m.select, 'select', return_value=([7], [], [])), patch.object(m.os, 'close') as close:
            result = m.stop_owned(self.identity, 30)
        self.assertTrue(result['stopped'])
        send.assert_called_once_with(7, signal.SIGTERM)
        close.assert_called_once_with(7)

    def test_pid_reuse_after_open_never_signals(self):
        with patch.object(m, 'process_identity', side_effect=[self.identity, dict(self.identity, startTicks=1)]), \
                patch.object(m.os, 'pidfd_open', return_value=7, create=True), \
                patch.object(m.signal, 'pidfd_send_signal', create=True) as send, patch.object(m.os, 'close'):
            with self.assertRaises(RuntimeError):
                m.stop_owned(self.identity, 30)
        send.assert_not_called()

    def test_clean_stop_timeout_never_forces_kill(self):
        with patch.object(m, 'process_identity', return_value=self.identity), \
                patch.object(m.os, 'pidfd_open', return_value=7, create=True), \
                patch.object(m.signal, 'pidfd_send_signal', create=True) as send, \
                patch.object(m.select, 'select', return_value=([], [], [])), patch.object(m.os, 'close'):
            with self.assertRaisesRegex(RuntimeError, 'benchmark blocked'):
                m.stop_owned(self.identity, 30)
        self.assertEqual([call.args[1] for call in send.call_args_list], [signal.SIGTERM])

    def test_already_exited_never_opens_or_signals(self):
        with patch.object(m, 'process_identity', return_value=None), patch.object(m.os, 'pidfd_open', create=True) as opening:
            self.assertTrue(m.stop_owned(self.identity, 30)['alreadyExited'])
        opening.assert_not_called()

    def test_fake_proc_identity_and_zombie(self):
        with tempfile.TemporaryDirectory() as td:
            proc = Path(td); child = proc / '12345'; child.mkdir()
            fields = ['S'] + ['0'] * 18 + ['67890']
            (child / 'stat').write_text('12345 (name with ) spaces) ' + ' '.join(fields))
            (child / 'cmdline').write_bytes(b''.join(x.encode() + b'\0' for x in self.identity['arguments']))
            with patch.object(m, 'PROC', proc):
                self.assertEqual(m.process_identity(12345), self.identity)
                fields[0] = 'Z'; (child / 'stat').write_text('12345 (x) ' + ' '.join(fields))
                self.assertIsNone(m.process_identity(12345))

    def test_scan_refuses_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'data').write_bytes(b'x'); (root / 'link').symlink_to(root / 'data')
            with self.assertRaises(RuntimeError): m.scan(root)
            (root / 'link').unlink(); m.os.link(str(root / 'data'), str(root / 'hard'))
            with self.assertRaises(RuntimeError): m.scan(root)

    def test_scan_complete_files_modes_empty_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'empty').mkdir(); (root / 'data').write_bytes(b'abc')
            result = m.scan(root, True)
            self.assertEqual(set(result['directories']), {'.', 'empty'})
            self.assertEqual(result['files']['data']['sha256'], hashlib.sha256(b'abc').hexdigest())
            self.assertEqual(result['logicalBytes'], 3)

    def test_all_15_udp_ports_checked_and_closed_without_reuse(self):
        made = []
        def fake(*args):
            sock = MagicMock(); made.append(sock); return sock
        with patch.object(m.socket, 'socket', side_effect=fake):
            self.assertEqual(m.port_check()['freshUdpBinds'], 15)
        expected = [('127.0.0.1', 19000 + n * 100 + o) for n in range(3) for o in range(1, 6)]
        self.assertEqual([s.bind.call_args.args[0] for s in made], expected)
        for s in made:
            s.close.assert_called_once(); s.setsockopt.assert_not_called()

    def test_port_conflict_fails_closed_and_closes_prior_sockets(self):
        one, two = MagicMock(), MagicMock(); two.bind.side_effect = OSError('occupied')
        with patch.object(m.socket, 'socket', side_effect=[one, two]), self.assertRaises(OSError):
            m.port_check()
        one.close.assert_called_once(); two.close.assert_called_once()

    def test_capped_archive_rejects_before_overflow_write(self):
        stream = MagicMock(); stream.write.side_effect = len
        wrapper = m.CappedArchive(stream, 3)
        wrapper.write(b'abc')
        with self.assertRaises(RuntimeError): wrapper.write(b'd')
        stream.write.assert_called_once_with(b'abc')

    def test_launch_failure_keeps_direct_child_ownership_for_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td); fake = MagicMock(); fake.pid = 12345; owned = []
            with patch.object(m.subprocess, 'Popen', return_value=fake), patch.object(m, 'process_identity', return_value=None):
                with self.assertRaises(RuntimeError): m.launch(self.plan, 'unit-only', self.identity['arguments'], owned, job)
            self.assertEqual(len(owned), 1); self.assertIs(owned[0]['child'], fake)
            self.assertIsNone(owned[0]['record']); self.assertTrue((job / 'unit-only.log').exists())

    def test_monitor_probe_exit_race_allowed_but_node_exit_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'log'; p.write_text('')
            row = {'role': 'tail-probe-r2', 'record': self.identity, 'log': str(p)}
            with patch.object(m, 'idle_check'), patch.object(m, 'matching_identity', return_value=None), \
                    patch.object(m.shutil, 'disk_usage', return_value=MagicMock(free=10 * 1024**3)), patch.object(m, 'allocated', return_value=0):
                m.monitor(self.plan, [row], 0, ('tail-probe-r2',))
                row['role'] = 'node-0'
                with self.assertRaises(RuntimeError): m.monitor(self.plan, [row], 0, ('tail-probe-r2',))

    def test_runtime_growth_and_free_space_guard(self):
        with patch.object(m, 'idle_check'), patch.object(m.shutil, 'disk_usage', return_value=MagicMock(free=10 * 1024**3)), \
                patch.object(m, 'allocated', return_value=513 * 1024**2), self.assertRaises(RuntimeError):
            m.monitor(self.plan, [], 0)
        with patch.object(m, 'idle_check'), patch.object(m.shutil, 'disk_usage', return_value=MagicMock(free=2 * 1024**3)), \
                patch.object(m, 'allocated', return_value=0), self.assertRaises(RuntimeError):
            m.monitor(self.plan, [], 0)

    def test_linux38_syntax_and_no_numeric_kill_or_delete_or_old_probe(self):
        import ast
        source = (HERE / 'original_cluster_lifecycle.py').read_text()
        ast.parse(source, feature_version=(3, 8))
        for forbidden in ['os.kill(', 'os.killpg(', 'SIGKILL', 'rmtree(', '.unlink(', 'pg_ctl', 'ProbeOriginalRestoration\'']:
            self.assertNotIn(forbidden, source)
        self.assertIn('syscall(434', source); self.assertIn('syscall(424', source)


if __name__ == '__main__':
    unittest.main()
