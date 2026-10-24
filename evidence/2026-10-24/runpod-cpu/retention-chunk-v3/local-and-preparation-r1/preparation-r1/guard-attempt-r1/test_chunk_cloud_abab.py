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
spec = importlib.util.spec_from_file_location('pilot', str(HERE / 'chunk_cloud_abab.py'))
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def release():
    data = json.loads((HERE / 'release.template.json').read_text())
    data.update(releaseReady=True, sourceCommit='a' * 40, codeFingerprint='b' * 64,
                profileFingerprint='c' * 64, javaExecutableSha256='d' * 64,
                jdkReleaseSha256='e' * 64, controllerSha256='2' * 64, profileId='fixture-only-not-an-artifact')
    paths = [str(pilot.PREP / 'release/lib' / name) for name in ['cluster.jar', 'core.jar', 'aeron.jar']]
    data['classPath'], data['nodeClassPath'] = paths, paths[:]
    data['artifacts'] = {p: {'bytes': 128, 'sha256': 'f' * 64} for p in paths}
    data['protectedOriginalState']['manifestSha256'] = '1' * 64
    data['derivedPlans'] = {str(c): {'arrivals': 6400, 'batchCap': 4, 'archiveChunkBytes': c, 'commonChunkEnvelope': True,
        'eventFetchCount': 16, 'maximumSupportedArchiveChunkBytes': 6144,
        'maximumEncodedChunkReplyBytes': 6919, 'admitted': True,
        'admissionRejections': [], 'minimumFreeRuntimeBytes': pilot.GIB,
        'maximumAllocatedGrowthBytes': 64 * 1024**2} for c in pilot.CHUNKS}
    return data


def registration(cap=3072):
    return {'arrivals': 6400, 'rate': 500, 'batchCap': 4, 'archiveChunkBytes': cap, 'eventFetchCount': 16, 'commonChunkEnvelope': True, 'appointedLeader': 0, 'sync': 2,
            'profileSha256': 'c' * 64, 'codeSha256': 'b' * 64, 'ports': 42000,
            'lineage': 'capacity-pilot-fixture-' + str(cap)}


def egress():
    return {'requiredApplicationReplyBytes': 6919, 'aeronSessionHeaderBytes': 32,
        'requiredCompleteMessageBytes': 6951, 'minimumActualDerivedMaxMessageLength': 8192,
        'actualImageObservations': 2, 'replyHeaderImageAssociations': 8,
        'defaultMetadataSubstituted': False, 'sameOwnerThreadRequired': True,
        'images': [{'imageCorrelationId': 10, 'publicationSessionId': 20, 'streamId': 101,
            'actualTermBufferLength': 65536, 'actualMtuLength': 1248, 'derivedMaxMessageLength': 8192,
            'associatedApplicationReplies': 8, 'largestObservedApplicationReplyBytes': 6919}]}


def identity(args, pid=122, ticks=999):
    raw = b''.join(a.encode() + b'\0' for a in args)
    return {'pid': pid, 'startTicks': ticks, 'commandSha256': hashlib.sha256(raw).hexdigest(), 'arguments': args}


class ReleaseGuards(unittest.TestCase):
    def test_draft_never_executable(self):
        with self.assertRaisesRegex(RuntimeError, 'unfrozen draft'):
            pilot.validate_release(json.loads((HERE / 'release.template.json').read_text()))

    def test_complete_fixture_contract_only(self):
        data = release()
        self.assertIs(pilot.validate_release(data), data)

    def test_configuration_changes_rejected(self):
        for field, value in [('sync', 0), ('appointedLeader', 1), ('arrivals', 6401), ('ratePerSecond', 501),
                             ('archiveChunkBytesOrder', [6144, 3072, 6144, 3072]), ('workers', 64), ('queuePerWorker', 65), ('mtu', 1408),
                             ('preparedArchiveCache', False), ('samePortsAcrossArms', False)]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data['configuration'][field] = value; pilot.validate_release(data)

    def test_host_or_attempt_change_rejected(self):
        for field in ['host']:
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
        self.assertIn(':'.join(data['nodeClassPath']), pilot.node_argv(data, 3072, 0, registration()))

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
        for field, value in [('admitted', False), ('arrivals', 350000), ('batchCap', 1),
                             ('admissionRejections', ['raw cap']), ('minimumFreeRuntimeBytes', 0),
                             ('maximumAllocatedGrowthBytes', 3 * pilot.GIB)]:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                data = release(); data['derivedPlans']['3072'][field] = value; pilot.validate_release(data)

    def test_parent_flags_are_fixed(self):
        data = release(); data['parentJvmArguments'].append('-Daeron.archive.file.sync.level=0')
        with self.assertRaises(RuntimeError): pilot.validate_release(data)

    def test_pair_bound_is_sum_plus_explicit_monitor_budget(self):
        self.assertEqual(pilot.allocation_limit(release()), 144 * 1024**2)

    def test_explicit_frozen_manifest_sha_required(self):
        base = pilot.load_base()
        with self.assertRaisesRegex(RuntimeError, 'Explicit root-frozen'):
            pilot.runtime_manifest(base, '/tmp/arbitrary.json', None)
        with self.assertRaisesRegex(RuntimeError, 'fixed frozen release path'):
            pilot.runtime_manifest(base, '/tmp/arbitrary.json', 'a' * 64)


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

    def put_registration(self, cap=3072, **changes):
        root = self.pair / ('chunk-' + str(cap)); root.mkdir(exist_ok=True)
        row = registration(cap); row.update(changes)
        (root / 'registration.json').write_text(json.dumps(row))
        return root, row

    def test_untrusted_observation_does_not_become_owned(self):
        self.registry.observe(identity(['/foreign']), 'candidate', 'unvalidated')
        self.assertFalse(self.registry.records)
        self.assertEqual(len(list(self.job.glob('identity-observation-*'))), 1)

    def test_recover_live_node_before_json_write(self):
        _, reg = self.put_registration(); args = pilot.node_argv(self.data, 3072, 0, reg)
        (self.proc / '122').mkdir(); actual = identity(args)
        with mock.patch.object(self.base, 'process_identity', return_value=actual):
            self.registry.discover()
        self.assertEqual(next(iter(self.registry.records.values()))['identity'], actual)

    def test_live_json_kernel_mismatch_persisted_but_not_owned(self):
        arm, reg = self.put_registration(); args = pilot.node_argv(self.data, 3072, 0, reg); claimed = identity(args)
        (arm / 'node-0-identity.json').write_text(json.dumps({'pid': 122, 'linuxStartTicks': 999,
            'linuxCommandSha256': claimed['commandSha256'], 'command': args[0], 'arguments': args[1:]}))
        with mock.patch.object(self.base, 'process_identity', return_value=identity(['/foreign'])):
            with self.assertRaisesRegex(RuntimeError, 'JSON/kernel'): self.registry.discover()
        self.assertFalse(self.registry.records)
        self.assertEqual(len(list(self.job.glob('identity-observation-*'))), 1)

    def test_template_mismatch_not_owned(self):
        _, reg = self.put_registration(); args = pilot.node_argv(self.data, 3072, 0, reg); args[-1] = 'uncached'
        (self.proc / '122').mkdir()
        with mock.patch.object(self.base, 'process_identity', return_value=identity(args)):
            with self.assertRaisesRegex(RuntimeError, 'exact template'): self.registry.discover()
        self.assertFalse(self.registry.records)

    def test_already_exited_json_record_retained(self):
        arm, reg = self.put_registration(); args = pilot.node_argv(self.data, 3072, 0, reg); item = identity(args)
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
        self.registry.record(node_record, 'chunk-3072-node-0', 'fixture')
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
             mock.patch.object(pilot, 'strict_idle', return_value={}), \
             mock.patch.object(self.registry, 'discover', side_effect=lambda: order.append('post-parent-discover')):
            result = pilot.clean_all(self.base, self.registry, parent, parent_record['arguments'], pilot.time.monotonic() + 120)
        self.assertTrue(result['allOwnedStopped'])
        self.assertEqual(order, ['stop-100', 'parent-wait', 'post-parent-discover', 'stop-101'])

    def test_other_java_vm_or_pg_blocks_without_signal(self):
        (self.proc / '122').mkdir()
        for command in ['/unrelated/tool/bin/java', '/bin/postgres', '/bin/postmaster']:
            with self.subTest(command=command), mock.patch.object(self.base, 'process_identity', return_value=identity([command, 'unrelated'])), \
                 mock.patch.object(self.base, 'stop_owned') as stopping:
                with self.assertRaisesRegex(RuntimeError, 'Unowned Java VM or Postgres'):
                    pilot.strict_idle(self.base)
                stopping.assert_not_called()

    def functional_jsons(self):
        self.registry.registrations = {c: registration(c) for c in pilot.CHUNKS}
        self.registry.records = {(100, 1): {'role': 'pilot-parent', 'identity': {}}}
        for cap in pilot.CHUNKS:
            arm = self.pair / ('chunk-' + str(cap)); arm.mkdir(exist_ok=True)
            for member in range(3):
                pid = cap * 100 + member
                self.registry.records[(pid, 2)] = {'role': 'chunk-%d-node-%d' % (cap, member), 'identity': {'pid': pid}}
                (arm / ('node-%d.log' % member)).write_text('VECTOR_V3_ROLE role=' + ('LEADER' if member == 0 else 'FOLLOWER')
                    + '\nVECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s\npreparedArchiveCacheEnabled=true' % (
                        member, pid, self.data['profileFingerprint'], registration(cap)['lineage'], self.data['codeFingerprint']))
        def value(base, path, maximum=1024**2):
            if path.name == 'pair-completion.json': return {'passed': True, 'archiveChunkBytes': pilot.CHUNKS, 'fixedBusinessBatchCap': 4}
            cap = int(next(p.name[6:] for p in path.parents if p.name.startswith('chunk-')))
            if path.name == 'completion.json': return {'passed': True, 'allOwnedStopped': True, 'fixedLeader': 0}
            if path.name == 'owned-stop.json': return {'allOwnedStopped': True}
            if path.name == 'functional-result.json': return {'passed': True, 'noCapacityPromotion': True, 'actualEgressBounds': egress(),
                'actualSourceSummary': {'scheduledArrivals': 6400, 'releasedArrivals': 6400, 'ratePerSecond': 500,
                    'batchCap': 4, 'archiveChunkBytes': cap, 'physicalOfferTape': {'recordedReplies': 8}, 'arrivalClockPausedForMaintenance': False, 'unknownFinal': 0, 'maintenanceCycles': 3}}
            if path.name == 'artifact-inventory.json': return {'codeFingerprint': 'b' * 64,
                'actualFiles': [dict(path=p, **row) for p, row in self.data['artifacts'].items()]}
            if path.name == 'admission-plan.json': return self.data['derivedPlans'][str(cap)]
            if path.name == 'transport-observations.json': return [{'leaderMemberId': 0,
                'profileSha256': 'c' * 64, 'lineageId': registration(cap)['lineage'],
                'maintenanceEnabled': True, 'mtuLength': 1248, 'archiveChunkBytes': cap, 'actualEgressBounds': egress(), 'newLeaderEvents': []}]
            raise AssertionError(path)
        return value

    def test_result_requires_actual_loaded_artifacts_and_codec_plan(self):
        values = self.functional_jsons()
        with mock.patch.object(self.registry, 'discover'), mock.patch.object(pilot, 'json_bounded', side_effect=values):
            self.assertTrue(pilot.validate_result(self.base, self.registry, self.data)['passed'])
        def changed(base, path, maximum=1024**2):
            actual = values(base, path, maximum)
            if path.name == 'artifact-inventory.json': actual['actualFiles'][0]['sha256'] = '0' * 64
            return actual
        with mock.patch.object(self.registry, 'discover'), mock.patch.object(pilot, 'json_bounded', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'loaded JAR bytes'): pilot.validate_result(self.base, self.registry, self.data)

    def test_during_load_foreign_leader_rejected(self):
        values = self.functional_jsons()
        def changed(base, path, maximum=1024**2):
            actual = values(base, path, maximum)
            if path.name == 'transport-observations.json': actual[0]['newLeaderEvents'] = [{'leaderMemberId': 2}]
            return actual
        with mock.patch.object(self.registry, 'discover'), mock.patch.object(pilot, 'json_bounded', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'leadership change'): pilot.validate_result(self.base, self.registry, self.data)

    def test_actual_finite_plan_change_rejected(self):
        values = self.functional_jsons()
        def changed(base, path, maximum=1024**2):
            actual = copy.deepcopy(values(base, path, maximum))
            if path.name == 'admission-plan.json': actual['maximumAllocatedGrowthBytes'] += 1
            return actual
        with mock.patch.object(self.registry, 'discover'), mock.patch.object(pilot, 'json_bounded', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'codec-derived plan'): pilot.validate_result(self.base, self.registry, self.data)


class TelemetryGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name).resolve()
        self.base = pilot.load_base(); self.folder = self.root / '122'; self.folder.mkdir()
        self.record = identity(['/java', 'node'])
        self.row = {'role': 'chunk-3072-node-0', 'identity': self.record}
        self.proc_patch = mock.patch.object(self.base, 'PROC', self.root); self.proc_patch.start()
        fields = ['S'] + ['0'] * 24; fields[11] = '101'; fields[12] = '7'; fields[19] = '999'; fields[21] = '100'
        (self.folder / 'stat').write_text('122 (node) ' + ' '.join(fields))
        (self.folder / 'status').write_text('Name:\tsecret-not-collected\nVmRSS:\t400 kB\nRssAnon:\t300 kB\nRssFile:\t100 kB\nThreads:\t7\n')
        (self.folder / 'io').write_text('read_bytes: 1024\nwrite_bytes: 2048\nsyscr: 3\nsyscw: 4\n')
        (self.root / 'stat').write_text('cpu 1 2 3 4 5 6 7 8\ncpu0 1 2\nctxt 12\nprocesses 42\nprocs_running 3\nprocs_blocked 1\n')

    def tearDown(self):
        self.proc_patch.stop(); self.temp.cleanup()

    def test_cpu_rss_io_exact_typed_counters_and_double_identity_check(self):
        with mock.patch.object(self.base, 'matching_identity', return_value=self.record) as check:
            result = pilot.owned_metrics(self.base, self.row)
        self.assertEqual(check.call_count, 2); self.assertTrue(result['available'])
        self.assertEqual((result['userTicks'], result['systemTicks']), (101, 7))
        self.assertEqual(result['status']['VmRSSBytes'], 409600)
        self.assertEqual(result['io'], {'read_bytes': 1024, 'write_bytes': 2048, 'syscr': 3, 'syscw': 4})
        self.assertNotIn('secret-not-collected', json.dumps(result))

    def test_io_permission_or_missing_field_is_explicit_partial_failure(self):
        (self.folder / 'io').write_text('read_bytes: 1024\n')
        with mock.patch.object(self.base, 'matching_identity', return_value=self.record):
            result = pilot.owned_metrics(self.base, self.row)
        self.assertFalse(result['available']); self.assertTrue(result['partialCountersMayBePresent'])
        self.assertIn('IO metric closure', result['reason']); self.assertNotIn('io', result)

    def test_process_exit_during_metrics_does_not_get_valid_label(self):
        with mock.patch.object(self.base, 'matching_identity', side_effect=[self.record, None]):
            result = pilot.owned_metrics(self.base, self.row)
        self.assertFalse(result['available']); self.assertIn('exited during', result['reason'])

    def test_global_aggregate_only_no_per_cpu_or_process_details(self):
        result = pilot.global_metrics(self.base)
        self.assertTrue(result['available']); self.assertEqual(result['ctxt'], 12)
        self.assertEqual(result['aggregateCpuTicks'], list(range(1, 9))); self.assertNotIn('cpu0', result)

    def test_1hz_bounded_timestamped_raw_flush_without_load_fsync(self):
        registry = types.SimpleNamespace(records={(122, 999): self.row}, registrations={3072: registration()})
        with mock.patch.object(self.base, 'matching_identity', return_value=self.record), \
             mock.patch.object(pilot.os, 'fsync') as syncing:
            telemetry = pilot.Telemetry(self.base, self.root, pilot.time.monotonic())
            telemetry.sample(registry); telemetry.sample(registry)
            self.assertEqual(telemetry.samples, 1); syncing.assert_not_called()
            receipt = telemetry.close(True); syncing.assert_called_once()
        raw = json.loads(telemetry.path.read_text()); self.assertIn('atUtc', raw); self.assertIn('monotonicNs', raw)
        self.assertEqual(raw['activeArmsFromSuccessfulMetricSamples'], [3072]); self.assertEqual(receipt['samples'], 1)

    def test_finite_byte_cap_and_unconfirmed_stop_skip_force(self):
        registry = types.SimpleNamespace(records={}, registrations={})
        telemetry = pilot.Telemetry(self.base, self.root, pilot.time.monotonic())
        telemetry.bytes = pilot.METRIC_BYTES_CAP
        with self.assertRaisesRegex(RuntimeError, '8MiB'): telemetry.sample(registry)
        with mock.patch.object(pilot.os, 'fsync') as syncing:
            receipt = telemetry.close(False); syncing.assert_not_called()
        self.assertTrue(receipt['fsyncSkippedBecauseOwnedStopUnconfirmed'])

    def test_signal_interruption_not_swallowed_by_metric_collection(self):
        with mock.patch.object(self.base, 'matching_identity', side_effect=InterruptedError('controller signal')):
            with self.assertRaises(InterruptedError): pilot.owned_metrics(self.base, self.row)


if __name__ == '__main__':
    unittest.main(verbosity=2)
