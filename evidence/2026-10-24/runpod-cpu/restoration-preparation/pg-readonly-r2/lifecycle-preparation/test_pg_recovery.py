#!/usr/bin/env python3
"""Offline guards only: no SSH, accounts, ACLs, chown, server, or SQL connections."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pg_recovery', HERE / 'pg_recovery.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.pg = self.root / 'pg'
        self.pg.mkdir(mode=0o700)
        (self.pg / 'base').mkdir(mode=0o700)
        self.f = self.pg / 'base' / 'file'
        self.f.write_bytes(b'original-synthetic-file\0' * 4)
        self.f.chmod(0o600)
        self.d = {'pgFiles': {'base/file': {'bytes': self.f.stat().st_size, 'sha256': M.sha(self.f), 'mode': 0o600}},
                  'pgDirectories': [{'path': '', 'mode': 0o700}, {'path': 'base', 'mode': 0o700}]}
        self.p = patch.object(M, 'PGDATA', self.pg)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_exact_bytes_inventory_pass_and_no_mutation(self):
        before = self.f.stat()
        self.assertEqual(M.verify_pg(self.d)['files'], 1)
        after = self.f.stat()
        self.assertEqual((before.st_ino, before.st_mode, before.st_uid, before.st_gid, before.st_mtime_ns),
                         (after.st_ino, after.st_mode, after.st_uid, after.st_gid, after.st_mtime_ns))

    def test_same_size_payload_corruption_rejected(self):
        self.f.write_bytes(b'X' * self.f.stat().st_size)
        with self.assertRaisesRegex(RuntimeError, 'baseline differs'): M.verify_pg(self.d)

    def test_missing_file_rejected(self):
        self.f.unlink()
        with self.assertRaisesRegex(RuntimeError, 'inventory differs'): M.verify_pg(self.d)

    def test_extra_file_rejected(self):
        (self.pg / 'postmaster.pid').write_text('12')
        with self.assertRaisesRegex(RuntimeError, 'inventory differs'): M.verify_pg(self.d)

    def test_extra_empty_directory_rejected(self):
        (self.pg / 'extra').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'directory inventory'): M.verify_pg(self.d)

    def test_symlink_file_outside_tree_rejected(self):
        self.f.unlink()
        self.f.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(RuntimeError, 'Non-regular'): M.verify_pg(self.d)

    def test_symlink_directory_outside_tree_rejected(self):
        (self.pg / 'escape').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'symlink'): M.verify_pg(self.d)

    def test_parent_symlink_rejected(self):
        linked = self.root / 'linked'
        linked.symlink_to(self.pg, target_is_directory=True)
        with patch.object(M, 'PGDATA', linked), self.assertRaisesRegex(RuntimeError, 'Symlink'): M.verify_pg(self.d)

    def test_hardlink_outside_tree_rejected(self):
        os.link(str(self.f), str(self.root / 'alias'))
        with self.assertRaisesRegex(RuntimeError, 'hardlinked'): M.verify_pg(self.d)

    def test_fifo_rejected(self):
        self.f.unlink()
        os.mkfifo(str(self.f))
        with self.assertRaisesRegex(RuntimeError, 'Non-regular'): M.verify_pg(self.d)

    def test_mode_change_rejected(self):
        self.f.chmod(0o640)
        with self.assertRaisesRegex(RuntimeError, 'baseline differs'): M.verify_pg(self.d)

    def test_wrong_owner_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'owner differs'): M.verify_pg(self.d, (os.getuid() + 1, os.getgid()))

    def test_ownership_exact_descendants_and_root_last(self):
        targets = M.ownership_targets({'base/file': self.f}, {'','base','base/deeper'})
        self.assertEqual(targets[-1], self.pg)
        self.assertLess(targets.index(self.pg/'base/deeper'), targets.index(self.pg/'base'))
        self.assertTrue(all(x == self.pg or self.pg in x.parents for x in targets))

    def test_ownership_outside_tree_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'escaped'):
            M.ownership_targets({'../outside': self.f}, {''})

    def test_baseline_actual_pinned_post_r1_counts_and_hash(self):
        # Load actual fixed baseline with original paths, no remote access.
        with patch.object(M, 'PGDATA', Path('/opt/vectormatch-cpu/restorations/original-native-r1/node2/runtime/postgres18')):
            d = M.load_baseline()
        self.assertEqual(d['pgFilesCount'], 989)
        self.assertEqual(len(d['pgDirectories']), 27)
        self.assertEqual(len(d['binaryEntries']), 1071)
        self.assertEqual(d['pgSystemIdentifier'], '7699920832388303129')

    def test_corrupted_baseline_refused_before_parse(self):
        p = self.root / 'manifest'
        p.write_text('{}')
        with patch.object(M, 'BASELINE', p), self.assertRaisesRegex(RuntimeError, 'SHA mismatch'): M.load_baseline()

    def missing_accounts(self):
        return patch.multiple(M.pwd, getpwnam=unittest.mock.Mock(side_effect=KeyError), getpwuid=unittest.mock.Mock(side_effect=KeyError))

    def test_unused_identity_proposes_only_fixed_account_commands(self):
        with self.missing_accounts(), patch.multiple(M.grp, getgrnam=unittest.mock.Mock(side_effect=KeyError), getgrgid=unittest.mock.Mock(side_effect=KeyError)):
            p = M.account_plan()
        self.assertFalse(p['exists'])
        self.assertEqual((p['uid'],p['gid']),(963,963))
        args = p['creationCommands'][1]
        self.assertIn('--no-create-home', args)
        self.assertEqual(args[-1], 'vectormatch-pg')
        self.assertNotIn('/bin/bash', args)

    def test_existing_numeric_uid_collision_rejected(self):
        other = SimpleNamespace(pw_name='unrelated', pw_uid=963)
        with patch.object(M.pwd, 'getpwnam', side_effect=KeyError), patch.object(M.pwd, 'getpwuid', return_value=other), \
             patch.object(M.grp, 'getgrnam', side_effect=KeyError), patch.object(M.grp, 'getgrgid', side_effect=KeyError), \
             self.assertRaisesRegex(RuntimeError, 'collision'): M.account_plan()

    def test_existing_group_name_collision_rejected(self):
        with self.missing_accounts(), patch.object(M.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=123)), \
             patch.object(M.grp, 'getgrgid', side_effect=KeyError), self.assertRaisesRegex(RuntimeError, 'collision'): M.account_plan()

    def test_preexisting_wrong_account_rejected(self):
        existing = SimpleNamespace(pw_uid=0, pw_gid=0, pw_dir='/root', pw_shell='/bin/sh')
        with patch.object(M.pwd, 'getpwnam', return_value=existing), patch.object(M.pwd, 'getpwuid', return_value=existing), \
             patch.object(M.grp, 'getgrnam', side_effect=KeyError), patch.object(M.grp, 'getgrgid', side_effect=KeyError), \
             self.assertRaisesRegex(RuntimeError, 'not exact'): M.account_plan()

    def test_argv_pins_durability_readonly_loopback_and_no_initdb(self):
        a = M.argv()
        self.assertEqual(Path(a[0]).name, 'postgres')
        for v in ['listen_addresses=127.0.0.1', 'port=15432', 'fsync=on', 'synchronous_commit=on',
                  'default_transaction_read_only=on', 'shared_preload_libraries=', 'autovacuum=off', 'restore_command=']:
            self.assertIn(v,a)
        self.assertNotIn('initdb', a)

    def test_argv_is_not_user_selectable(self):
        with patch.object(M.sys, 'argv', ['pg_recovery.py','start']), patch.object(M, 'phase') as action, \
             self.assertRaisesRegex(RuntimeError, '--execute'):
            M.main()
        action.assert_not_called()

    def test_default_action_is_readonly_preflight(self):
        with patch.object(M.sys, 'argv', ['pg_recovery.py']), patch.object(M, 'preflight', return_value={'readOnly':True}) as p, \
             patch.object(M, 'phase') as action, patch('builtins.print'):
            M.main()
        p.assert_called_once_with()
        action.assert_not_called()

    def expected_identity(self):
        args = M.argv()
        return {'pid':56789, 'startTicks':1234, 'commandSha256':'f'*64, 'arguments':args}

    def test_pid_reuse_refused_before_pidfd_or_signal(self):
        old = self.expected_identity()
        live = dict(old, startTicks=1235)
        with patch.object(M, 'enable_pidfd'), patch.object(M, 'process_identity', return_value=live), \
             patch.object(M.os, 'pidfd_open', create=True) as opening, self.assertRaisesRegex(RuntimeError, 'mismatch'):
            M.stop_record(old)
        opening.assert_not_called()

    def test_changed_argv_refused_before_pidfd_or_signal(self):
        old = self.expected_identity()
        with patch.object(M, 'enable_pidfd'), patch.object(M, 'process_identity', return_value=dict(old, arguments=['unrelated'])), \
             patch.object(M.os, 'pidfd_open', create=True) as opening, self.assertRaisesRegex(RuntimeError, 'mismatch'):
            M.stop_record(old)
        opening.assert_not_called()

    def test_changed_argv_sha_refused_before_pidfd_or_signal(self):
        old = self.expected_identity()
        with patch.object(M, 'enable_pidfd'), patch.object(M, 'process_identity', return_value=dict(old, commandSha256='0'*64)), \
             patch.object(M.os, 'pidfd_open', create=True) as opening, self.assertRaisesRegex(RuntimeError, 'mismatch'):
            M.stop_record(old)
        opening.assert_not_called()

    def test_already_exited_does_not_signal(self):
        with patch.object(M, 'enable_pidfd'), patch.object(M, 'process_identity', return_value=None), \
             patch.object(M.os, 'pidfd_open', create=True) as opening:
            self.assertTrue(M.stop_record(self.expected_identity())['alreadyExited'])
        opening.assert_not_called()

    def test_second_identity_check_prevents_race_signal(self):
        old = self.expected_identity()
        with patch.object(M, 'enable_pidfd'), patch.object(M, 'process_identity', side_effect=[old,dict(old,startTicks=1235)]), \
             patch.object(M.os, 'pidfd_open', return_value=10, create=True), patch.object(M.os, 'close'), \
             patch.object(M.signal, 'pidfd_send_signal', create=True) as sending, self.assertRaisesRegex(RuntimeError,'mismatch'):
            M.stop_record(old)
        sending.assert_not_called()

    def test_exact_job_acl_passes_but_extra_reader_rejected(self):
        expected = 'user::rwx\nuser:963:--x\ngroup::---\nmask::--x\nother::---\n'
        fake = SimpleNamespace(stat=lambda: SimpleNamespace(st_uid=0,st_gid=0,st_mode=stat.S_IFDIR|0o710))
        with patch.object(M,'JOB',fake), patch.object(M.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=expected)):
            M.job_privacy()
        with patch.object(M,'JOB',fake), patch.object(M.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=expected+'user:964:r-x\n')), \
             self.assertRaisesRegex(RuntimeError,'exact dedicated'): M.job_privacy()

    def test_wrong_host_fails_before_data_actions(self):
        with patch.object(M.platform,'system',return_value='Linux'),patch.object(M.platform,'machine',return_value='x86_64'), \
             patch.object(M.platform,'node',return_value='some-other-host'),self.assertRaisesRegex(RuntimeError,'Wrong fixed'):
            M.host_check()

    def test_stop_phase_does_not_require_free_space(self):
        target = self.root/'control'
        with patch.object(M,'JOB',target),patch.object(M,'host_check') as h,patch.object(M,'job_privacy'):
            M.phase('stop',lambda:{'stopped':True})
        h.assert_called_once_with(require_free=False)

    def test_failed_phase_keeps_intent_and_refuses_retry(self):
        target = self.root/'control'
        with patch.object(M,'JOB',target),patch.object(M,'host_check'),patch.object(M,'job_privacy'):
            with self.assertRaisesRegex(RuntimeError,'synthetic-failure'):
                M.phase('chown',lambda: (_ for _ in ()).throw(RuntimeError('synthetic-failure')))
            self.assertTrue((target/'chown-intent.json').is_file())
            self.assertTrue((target/'chown-failure.json').is_file())
            with self.assertRaises(FileExistsError): M.phase('chown',lambda:{'bad':True})

    def test_python38_parse(self):
        import ast
        ast.parse((HERE/'pg_recovery.py').read_text(), feature_version=(3,8))


if __name__ == '__main__':
    unittest.main(verbosity=2)
