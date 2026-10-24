#!/usr/bin/env python3
"""Pure contract/fixture tests. No SSH, JVM, PG, real process signals, or cloud mutation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pilot', str(HERE / 'capacity_cloud_pilot.py'))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def release():
    data = json.loads((HERE / 'release.template.json').read_text())
    data.update(releaseReady=True, sourceCommit='a' * 40, codeFingerprint='b' * 64,
                profileFingerprint='c' * 64, javaExecutableSha256='d' * 64,
                jdkReleaseSha256='e' * 64, profileId='fixture-only-not-an-artifact')
    paths = [str(pilot.PREP / 'release/lib' / name) for name in ['cluster.jar', 'core.jar', 'aeron.jar']]
    data['classPath'], data['nodeClassPath'] = paths, paths[:]
    data['artifacts'] = {p: {'bytes': 128, 'sha256': 'f' * 64} for p in paths}
    data['protectedOriginalState']['manifestSha256'] = '1' * 64
    data['derivedPlans'] = {str(c): {'arrivals': 6400, 'batchCap': c, 'admitted': True,
        'admissionRejections': [], 'minimumFreeRuntimeBytes': pilot.GIB,
        'maximumAllocatedGrowthBytes': 64 * 1024**2} for c in [1, 4]}
    return data


def registration(cap=1):
    return {'arrivals': 6400, 'rate': 500, 'batchCap': cap, 'appointedLeader': 0, 'sync': 2,
            'profileSha256': 'c' * 64, 'codeSha256': 'b' * 64, 'ports': 42000,
            'lineage': 'capacity-pilot-fixture-' + str(cap)}


def identity(args, pid=122, ticks=999):
    raw = b''.join(a.encode() + b'\0' for a in args)
    return {'pid': pid, 'startTicks': ticks, 'commandSha256': hashlib.sha256(raw).hexdigest(), 'arguments': args}


class ReleaseGuards(unittest.TestCase):
    def test_draft_never_executable(self):
        with self.assertRaisesRegex(RuntimeError, 'unfrozen draft'):
            pilot.validate_release(json.loads((HERE / 'release.template.json').read_text()))

    def test_complete_fixture_contract_only(self):
        self.assertIs(pilot.validate_release(self.data := release()), self.data)

    def test_configuration_changes_rejected(self):
        for field, value in [('sync', 0), ('appointedLeader', 1), ('arrivals', 6401), ('ratePerSecond', 501),
                             ('batchCaps', [4, 1]), ('workers', 64), ('queuePerWorker', 65), ('mtu', 1408),
                             ('preparedArchiveCache', False), ('samePortsAcrossArms', False)]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data['configuration'][field] = value; pilot.validate_release(data)

    def test_host_or_attempt_change_rejected(self):
        for field in ['host', 'job', 'pairRoot']:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data[field] += '-other'; pilot.validate_release(data)

    def test_missing_actual_fingerprint_rejected(self):
        for field in ['codeFingerprint', 'profileFingerprint', 'javaExecutableSha256', 'jdkReleaseSha256']:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data[field] = None; pilot.validate_release(data)

    def test_noncommit_and_noncanonical_java_rejected(self):
        for field, value in [('sourceCommit', 'main'), ('sourceCommit', 'z' * 40), ('java', '/usr/bin/java')]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data[field] = value; pilot.validate_release(data)

    def test_node_classpath_not_assumed_equal_to_parent(self):
        data = release(); extra = str(pilot.PREP / 'release/lib/agrona.jar')
        data['classPath'].append(extra); data['artifacts'][extra] = {'bytes': 128, 'sha256': 'f' * 64}
        pilot.validate_release(data)
        self.assertNotEqual(data['classPath'], data['nodeClassPath'])
        self.assertIn(':'.join(data['nodeClassPath']), pilot.node_argv(data, 1, 0, registration()))

    def test_unknown_or_duplicate_class_source_rejected(self):
        for paths in [['/tmp/unknown.jar'] * 3, ['/tmp/one.jar', '/tmp/two.jar', '/tmp/three.jar']]:
            with self.subTest(paths=paths), self.assertRaises(RuntimeError):
                data = release(); data['nodeClassPath'] = paths; pilot.validate_release(data)

    def test_artifact_closure_and_path_guard(self):
        data = release(); data['artifacts']['/tmp/escape.jar'] = {'bytes': 1, 'sha256': 'f' * 64}
        with self.assertRaises(RuntimeError): pilot.validate_release(data)
        data = release(); path = data['classPath'][0]; data['artifacts'][path]['bytes'] = 0
        with self.assertRaises(RuntimeError): pilot.validate_release(data)

    def test_rejected_or_wrong_derived_plan_refused(self):
        for field, value in [('admitted', False), ('arrivals', 350000), ('batchCap', 4),
                             ('admissionRejections', ['raw cap']), ('minimumFreeRuntimeBytes', 0),
                             ('maximumAllocatedGrowthBytes', 3 * pilot.GIB)]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data['derivedPlans']['1'][field] = value; pilot.validate_release(data)

    def test_parent_flags_are_fixed(self):
        data = release(); data['parentJvmArguments'].append('-Daeron.archive.file.sync.level=0')
        with self.assertRaises(RuntimeError): pilot.validate_release(data)

    def test_pair_bound_is_sum_plus_explicit_monitor_budget(self):
        self.assertEqual(pilot.allocation_limit(release()), 144 * 1024**2)


class IdentityGuards(unittest.TestCase):
    def setUp(self):
        self.base = pilot.load_base()

    def test_exact_base_source_sha_checked(self):
        self.assertEqual(pilot.digest(HERE / 'owned_linux_base_8eeb.py'), pilot.BASE_SHA)

    def test_raw_argv_includes_executable_and_nul_boundaries(self):
        args = ['/java', 'a b', 'c']
        self.assertNotEqual(self.base.argv_digest(args), self.base.argv_digest(['/java', 'a', 'b c']))
        expected = identity(args)
        row = {'pid': 122, 'linuxStartTicks': 999, 'linuxCommandSha256': expected['commandSha256'],
               'command': '/java', 'arguments': ['a b', 'c']}
        self.assertEqual(pilot.kernel_record_from_json(self.base, row, args), expected)

    def test_json_start_ticks_sha_and_full_argv_required(self):
        args = ['/java', 'main']; item = identity(args)
        row = {'pid': 122, 'linuxStartTicks': 999, 'linuxCommandSha256': item['commandSha256'],
               'command': '/java', 'arguments': ['main']}
        for field, value in [('linuxStartTicks', 0), ('pid', True), ('linuxCommandSha256', '0' * 64),
                             ('arguments', ['other'])]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                changed = copy.deepcopy(row); changed[field] = value
                pilot.kernel_record_from_json(self.base, changed, args)

    def test_foreign_or_reused_process_no_signal(self):
        expected = identity(['/java', 'main'])
        for field, value in [('pid', 123), ('startTicks', 1000), ('arguments', ['/java', 'other']),
                             ('commandSha256', '0' * 64)]:
            changed = copy.deepcopy(expected); changed[field] = value
            with self.subTest(field=field), mock.patch.object(self.base, 'process_identity', return_value=changed), \
                 mock.patch.object(self.base.os, 'pidfd_open', create=True) as opening:
                with self.assertRaises(RuntimeError): self.base.stop_owned(expected, 1)
                opening.assert_not_called()

    def test_absent_process_never_signalled(self):
        with mock.patch.object(self.base, 'process_identity', return_value=None), \
             mock.patch.object(self.base.os, 'pidfd_open', create=True) as opening:
            self.assertTrue(self.base.stop_owned(identity(['/java']), 1)['alreadyExited'])
            opening.assert_not_called()

    def test_pidfd_identity_rechecked_before_signal(self):
        expected = identity(['/java']); foreign = identity(['/java'], ticks=1000)
        with mock.patch.object(self.base, 'process_identity', side_effect=[expected, foreign]), \
             mock.patch.object(self.base.os, 'pidfd_open', create=True, return_value=88), \
             mock.patch.object(self.base.os, 'close') as closing, \
             mock.patch.object(self.base.signal, 'pidfd_send_signal', create=True) as sending:
            with self.assertRaises(RuntimeError): self.base.stop_owned(expected, 1)
            sending.assert_not_called(); closing.assert_called_once_with(88)

    def test_timeout_never_escalates(self):
        expected = identity(['/java'])
        with mock.patch.object(self.base, 'process_identity', return_value=expected), \
             mock.patch.object(self.base.os, 'pidfd_open', create=True, return_value=88), \
             mock.patch.object(self.base.os, 'close'), \
             mock.patch.object(self.base.select, 'select', return_value=([], [], [])), \
             mock.patch.object(self.base.signal, 'pidfd_send_signal', create=True) as sending:
            with self.assertRaisesRegex(RuntimeError, 'no forced kill'): self.base.stop_owned(expected, 1)
            sending.assert_called_once_with(88, self.base.signal.SIGTERM)

    def test_linux_stat_start_time_parenthesized_comm(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); proc = root / '122'; proc.mkdir()
            fields = ['S'] + ['0'] * 18 + ['987654'] + ['0'] * 5
            (proc / 'stat').write_text('122 (name with ) parens) ' + ' '.join(fields))
            (proc / 'cmdline').write_bytes(b'/java\0main\0')
            with mock.patch.object(self.base, 'PROC', root):
                self.assertEqual(self.base.process_identity(122)['startTicks'], 987654)
                self.assertEqual(self.base.process_identity(122)['arguments'], ['/java', 'main'])


class RegistryGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.base = pilot.load_base(); self.data = release(); self.proc = self.root / 'proc'; self.proc.mkdir()
        self.pair = self.root / 'pilot-pair'; self.pair.mkdir(); self.job = self.root / 'job'; self.job.mkdir()
        self.pair_patch = mock.patch.object(pilot, 'PAIR', self.pair); self.pair_patch.start()
        self.proc_patch = mock.patch.object(self.base, 'PROC', self.proc); self.proc_patch.start()
        self.registry = pilot.Registry(self.base, self.data, self.job)

    def tearDown(self):
        self.proc_patch.stop(); self.pair_patch.stop(); self.temp.cleanup()

    def put_registration(self, cap=1, **changes):
        root = self.pair / ('cap-' + str(cap)); root.mkdir(exist_ok=True)
        row = registration(cap); row.update(changes)
        (root / 'registration.json').write_text(json.dumps(row))
        return root, row

    def test_untrusted_observation_does_not_become_owned(self):
        self.registry.observe(identity(['/foreign']), 'candidate', 'unvalidated')
        self.assertFalse(self.registry.records)
        self.assertEqual(len(list(self.job.glob('identity-observation-*'))), 1)

    def test_recover_live_node_before_json_write(self):
        _, reg = self.put_registration(); args = pilot.node_argv(self.data, 1, 0, reg)
        (self.proc / '122').mkdir(); actual = identity(args)
        with mock.patch.object(self.base, 'process_identity', return_value=actual):
            self.registry.discover()
        self.assertEqual(next(iter(self.registry.records.values()))['identity'], actual)

    def test_live_json_kernel_mismatch_persisted_but_not_owned(self):
        arm, reg = self.put_registration(); args = pilot.node_argv(self.data, 1, 0, reg); claimed = identity(args)
        (arm / 'node-0-identity.json').write_text(json.dumps({'pid': 122, 'linuxStartTicks': 999,
            'linuxCommandSha256': claimed['commandSha256'], 'command': args[0], 'arguments': args[1:]}))
        with mock.patch.object(self.base, 'process_identity', return_value=identity(['/foreign'])):
            with self.assertRaisesRegex(RuntimeError, 'JSON/kernel'): self.registry.discover()
        self.assertFalse(self.registry.records)
        self.assertEqual(len(list(self.job.glob('identity-observation-*'))), 1)

    def test_template_mismatch_not_owned(self):
        _, reg = self.put_registration(); args = pilot.node_argv(self.data, 1, 0, reg); args[-1] = 'uncached'
        (self.proc / '122').mkdir()
        with mock.patch.object(self.base, 'process_identity', return_value=identity(args)):
            with self.assertRaisesRegex(RuntimeError, 'exact template'): self.registry.discover()
        self.assertFalse(self.registry.records)

    def test_already_exited_json_record_retained(self):
        arm, reg = self.put_registration(); args = pilot.node_argv(self.data, 1, 0, reg); item = identity(args)
        (arm / 'node-0-identity.json').write_text(json.dumps({'pid': 122, 'linuxStartTicks': 999,
            'linuxCommandSha256': item['commandSha256'], 'command': args[0], 'arguments': args[1:]}))
        with mock.patch.object(self.base, 'process_identity', return_value=None): self.registry.discover()
        self.assertEqual(next(iter(self.registry.records.values()))['identity'], item)

    def test_registration_mutation_or_different_ports_refused(self):
        self.put_registration(); self.registry.discover()
        self.put_registration(4, ports=42001)
        with self.assertRaisesRegex(RuntimeError, 'changed UDP ports'): self.registry.discover()

    def test_same_lineage_across_arms_refused(self):
        self.put_registration(); self.put_registration(4, lineage=registration(1)['lineage'])
        with self.assertRaisesRegex(RuntimeError, 'distinct fresh lineages'): self.registry.discover()

    def test_evidence_symlink_refused(self):
        outside = self.root / 'outside'; outside.write_text('evidence')
        (self.job / 'escape').symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError, 'Symlink'): pilot.allocated_scan(self.base, self.job)

    def test_oversized_log_refused_by_metadata(self):
        with (self.job / 'node.log').open('wb') as stream: stream.truncate(pilot.MAX_LOG + 1)
        with self.assertRaisesRegex(RuntimeError, 'log cap'): pilot.allocated_scan(self.base, self.job)

    def test_cleanup_parent_before_final_discovery_and_each_node(self):
        parent_record = identity(['/java', 'parent'], pid=100)
        node_record = identity(['/java', 'node'], pid=101)
        self.registry.record(parent_record, 'pilot-parent', 'fixture')
        self.registry.record(node_record, 'cap-1-node-0', 'fixture')
        order = []; state = {'parentExited': False}
        parent = types.SimpleNamespace(pid=100,
            poll=lambda: 0 if state['parentExited'] else None,
            wait=lambda timeout: order.append('parent-wait'))
        def stopping(item, seconds):
            order.append('stop-' + str(item['pid']))
            if item['pid'] == 100: state['parentExited'] = True
            return {'stopped': True}
        with mock.patch.object(self.base, 'process_identity', return_value=parent_record), \
             mock.patch.object(self.base, 'stop_owned', side_effect=stopping), \
             mock.patch.object(self.base, 'matching_identity', return_value=None), \
             mock.patch.object(self.base, 'idle_check', return_value={}), \
             mock.patch.object(self.registry, 'discover', side_effect=lambda: order.append('post-parent-discover')):
            result = pilot.clean_all(self.base, self.registry, parent, parent_record['arguments'], pilot.time.monotonic() + 120)
        self.assertTrue(result['allOwnedStopped'])
        self.assertEqual(order, ['stop-100', 'parent-wait', 'post-parent-discover', 'stop-101'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
