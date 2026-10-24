#!/usr/bin/env python3
"""Pure contract/fixture tests. No SSH, JVM, PG, real process signals, or cloud mutation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import tarfile
import io
import ast
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
    data['derivedPlans'] = {}
    for c in pilot.CHUNKS:
        plan = {key: 1 for key in pilot.PLAN_KEYS}
        plan.update(arrivals=6400,batchCap=4,archiveChunkBytes=c,commonChunkEnvelope=True,eventFetchCount=16,
            maximumSupportedArchiveChunkBytes=6144,maximumEncodedChunkReplyBytes=6919,admitted=True,
            admissionRejections=[],minimumFreeRuntimeBytes=pilot.GIB,maximumAllocatedGrowthBytes=64*1024**2,
            maximumPhysicalOffersPerRpc=4,maximumBusinessFrames=6400,maximumEvents=12803,maximumMaintenanceCycles=4,
            maximumWriterPayloadFiles=8,maximumWriterFilesIncludingReceipts=16,maximumJournalRecords=32,
            maximumEventFetchRpcs=20,selectedMaximumArchiveChunkRpcs=100 if c==3072 else 50,
            selectedMaximumLogicalMaintenanceRpcs=132 if c==3072 else 82,
            maximumArchiveChunkRpcs=100,maximumLogicalMaintenanceRpcs=132,largestReplyBytes=6919,
            witness='fixture only',scope='fixture only')
        data['derivedPlans'][str(c)] = plan
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
        self.put_registration(6144, ports=42001)
        with self.assertRaisesRegex(RuntimeError, 'port range differs'): self.registry.discover()

    def test_same_lineage_across_arms_refused(self):
        self.put_registration(); self.put_registration(6144, lineage=registration(3072)['lineage'])
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
                    'confirmedAcceptedUniqueOrders':6400,'notSent':0,'serverRejected':0,
                    'duplicateOrOutOfRangeAcceptedOrderIds':0,'completedLogicalReplies':6400,
                    'batchCap': 4, 'archiveChunkBytes': cap, 'physicalOfferTape': {'recordedReplies': 8}, 'arrivalClockPausedForMaintenance': False, 'unknownFinal': 0, 'maintenanceCycles': 3}}
            if path.name == 'artifact-inventory.json': return {'codeFingerprint': 'b' * 64,
                'actualFiles': [dict(path=p, **row) for p, row in self.data['artifacts'].items()]}
            if path.name == 'admission-plan.json': return self.data['derivedPlans'][str(cap)]
            if path.name == 'transport-observations.json': return [{'leaderMemberId': 0, 'leadershipTermId': 0,
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
            if path.name == 'transport-observations.json': actual[0]['newLeaderEvents'] = [{'leaderMemberId': 2, 'leadershipTermId': 0}]
            return actual
        with mock.patch.object(self.registry, 'discover'), mock.patch.object(pilot, 'json_bounded', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'leadership member/term change'): pilot.validate_result(self.base, self.registry, self.data)


    def test_same_leader_term_drift_or_callback_term_refused(self):
        values=self.functional_jsons()
        for callback in [False,True]:
            def changed(base,path,maximum=1024**2):
                actual=values(base,path,maximum)
                if path.name=='transport-observations.json':
                    if callback:actual[0]['newLeaderEvents']=[{'leaderMemberId':0,'leadershipTermId':1}]
                    else:
                        actual.append(copy.deepcopy(actual[0]));actual[-1]['leadershipTermId']=1
                return actual
            with self.subTest(callback=callback),mock.patch.object(self.registry,'discover'),mock.patch.object(pilot,'json_bounded',side_effect=changed):
                with self.assertRaisesRegex(RuntimeError,'term change|changed leadership term'):pilot.validate_result(self.base,self.registry,self.data)

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



class ChunkAndRoundGuards(unittest.TestCase):
    def tearDown(self):
        pilot.configure_round(1)
        pilot.FROZEN_RELEASE_SHA = None
        pilot.PRIOR_GATE_SHA = None

    def test_fixed_chunk_cli_exact_order_and_ports(self):
        args = pilot.parent_argv(release())
        self.assertEqual(args[-3:], [str(pilot.PAIR), 'archive-chunks', '42000'])
        self.assertEqual(args[-4], pilot.MAIN)
        self.assertEqual(args.count('archive-chunks'), 1)

    def test_round_roots_fixed_distinct_same_release(self):
        data = release(); pilot.validate_release(data)
        first = pilot.JOB
        pilot.configure_round(2)
        self.assertNotEqual(first, pilot.JOB)
        self.assertEqual(pilot.JOB, pilot.PREP / 'round-2')
        self.assertEqual(pilot.PAIR, pilot.JOB / 'chunk-pair')
        pilot.validate_release(data)

    def test_unknown_round_and_boolean_refused(self):
        for value in [0, 3, True, '1']:
            with self.subTest(value=value), self.assertRaises(RuntimeError): pilot.configure_round(value)

    def test_release_round_path_or_count_change_refused(self):
        for key in ['1', '2']:
            data = release(); data['rounds'][key]['job'] += '-other'
            with self.subTest(key=key), self.assertRaises(RuntimeError): pilot.validate_release(data)
        data = release(); data['rounds']['3'] = data['rounds']['1']
        with self.assertRaises(RuntimeError): pilot.validate_release(data)

    def test_common_operational_bound_change_refused(self):
        data = release(); data['derivedPlans']['6144']['maximumAllocatedGrowthBytes'] += 1
        with self.assertRaisesRegex(RuntimeError, 'operational envelopes'): pilot.validate_release(data)

    def test_only_selected_rpc_estimates_may_differ(self):
        data = release()
        for chunk in pilot.CHUNKS:
            data['derivedPlans'][str(chunk)]['selectedMaximumArchiveChunkRpcs'] = 100 if chunk == 3072 else 50
            data['derivedPlans'][str(chunk)]['selectedMaximumLogicalMaintenanceRpcs'] = 132 if chunk == 3072 else 82
        pilot.validate_release(data)

    def test_chunk_common_reply_policy_changes_refused(self):
        for field,value in [('commonChunkEnvelope',False),('eventFetchCount',32),
                            ('maximumSupportedArchiveChunkBytes',8192),('maximumEncodedChunkReplyBytes',6920)]:
            data = release(); data['derivedPlans']['6144'][field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError): pilot.validate_release(data)


    def test_unknown_release_artifact_plan_protected_keys_refused(self):
        changes=[lambda d:d.update(unreviewedKnob=True),
                 lambda d:d['artifacts'][d['classPath'][0]].update(extra=True),
                 lambda d:d['protectedOriginalState'].update(extra=True),
                 lambda d:[row.update(extra=True) for row in d['derivedPlans'].values()]]
        for change in changes:
            data=release();change(data)
            with self.subTest(change=change),self.assertRaises(RuntimeError):pilot.validate_release(data)

    def test_selected_rpc_chunk_witness_mismatch_refused(self):
        for key,value in [('selectedMaximumLogicalMaintenanceRpcs',999),('selectedMaximumArchiveChunkRpcs',0),
                          ('maximumArchiveChunkRpcs',999),('maximumPhysicalOffersPerRpc',5)]:
            data=release()
            for row in data['derivedPlans'].values():row[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):pilot.validate_release(data)

    def test_round2_gate_sha_required_before_reading_any_path(self):
        pilot.configure_round(2); base=pilot.load_base()
        with mock.patch.object(pilot,'digest') as hashing:
            with self.assertRaisesRegex(RuntimeError,'explicit independently frozen'): pilot.verify_prior_round_gate(base,release())
            hashing.assert_not_called()

    def test_gate_wrong_sha_refused(self):
        pilot.configure_round(2); pilot.PRIOR_GATE_SHA='1'*64; base=pilot.load_base()
        with mock.patch.object(pilot,'digest',return_value='2'*64):
            with self.assertRaisesRegex(RuntimeError,'gate differs'): pilot.verify_prior_round_gate(base,release())

    def test_gate_draft_or_other_release_refused(self):
        pilot.configure_round(2); pilot.PRIOR_GATE_SHA='1'*64;pilot.FROZEN_RELEASE_SHA='3'*64
        gate=json.loads((HERE/'round-1-collection-gate.template.json').read_text()); base=pilot.load_base()
        with mock.patch.object(pilot,'digest',return_value='1'*64),mock.patch.object(pilot,'json_bounded',return_value=gate):
            with self.assertRaisesRegex(RuntimeError,'incomplete or from a different'): pilot.verify_prior_round_gate(base,release())

    def test_no_delete_or_network_or_numeric_pid_signal_code(self):
        tree=ast.parse((HERE/'chunk_cloud_abab.py').read_text())
        calls=[node.func for node in ast.walk(tree) if isinstance(node,ast.Call)]
        banned={'unlink','rmtree','remove','kill','killpg','connect','create_connection'}
        self.assertFalse([node.attr for node in calls if isinstance(node,ast.Attribute) and node.attr in banned])


class ActualEgressGuards(unittest.TestCase):
    def test_actual_geometry_and_header_counts(self):
        self.assertEqual(pilot.validate_egress(egress())[10]['actualTermBufferLength'],65536)

    def test_missing_actual_image_or_default_fallback_refused(self):
        for field,value in [('images',[]),('defaultMetadataSubstituted',True),('sameOwnerThreadRequired',False),
                            ('requiredApplicationReplyBytes',6144),('requiredCompleteMessageBytes',6919),
                            ('replyHeaderImageAssociations',7),('minimumActualDerivedMaxMessageLength',65536)]:
            row=egress();row[field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):pilot.validate_egress(row)

    def test_actual_image_term_mtu_limit_or_duplicate_refused(self):
        for field,value in [('actualTermBufferLength',65535),('actualTermBufferLength',32768),
                            ('actualMtuLength',1408),('derivedMaxMessageLength',65536),
                            ('largestObservedApplicationReplyBytes',8161),('imageCorrelationId',-1)]:
            row=egress();row['images'][0][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):pilot.validate_egress(row)
        row=egress();row['images'].append(copy.deepcopy(row['images'][0]))
        with self.assertRaisesRegex(RuntimeError,'duplicate'):pilot.validate_egress(row)


class ArchiveReadbackGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.archive=self.root/'closed.tar.gz'
        self.payload=b'synthetic evidence\n'
        self.inventory={'files':{'raw.bin':{'bytes':len(self.payload),'sha256':hashlib.sha256(self.payload).hexdigest(),'mode':0o600,'uid':1,'gid':2}},
            'directories':{'.':{'mode':0o700,'uid':1,'gid':2},'empty':{'mode':0o700,'uid':1,'gid':2}},'logicalBytes':len(self.payload)}

    def tearDown(self):
        self.temp.cleanup();pilot.configure_round(1);pilot.FROZEN_RELEASE_SHA=None;pilot.PRIOR_GATE_SHA=None

    def write_archive(self,payload=None,extra=None,omit_empty=False):
        with tarfile.open(self.archive,'w:gz') as archive:
            for name in ['chunk-pair','chunk-pair/empty']:
                if omit_empty and name.endswith('/empty'):continue
                row=tarfile.TarInfo(name);row.type=tarfile.DIRTYPE;row.mode=0o700;row.uid=1;row.gid=2;archive.addfile(row)
            data=self.payload if payload is None else payload
            row=tarfile.TarInfo('chunk-pair/raw.bin');row.mode=0o600;row.uid=1;row.gid=2;row.size=len(data);archive.addfile(row,io.BytesIO(data))
            if extra is not None:archive.addfile(extra)


    def prior_gate_fixture(self,native_present=False):
        previous=self.root/'round-1';previous.mkdir()
        archive=previous/'pilot-after-clean-stop.tar.gz'
        self.write_archive();self.archive.rename(archive)
        gate=json.loads((HERE/'round-1-collection-gate.template.json').read_text())
        gate.update(collectionComplete=True,frozenReleaseSha256='3'*64,controllerSha256='2'*64,
            independentLocalCollectionReceiptSha256='4'*64,localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,
            allRawInputsAndFailuresRetained=True,closedArchiveSha256=pilot.digest(archive),
            closedNativeInventorySha256=hashlib.sha256(json.dumps(self.inventory,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            rootReviewedExactOwnedNativeRemoval=not native_present)
        after={'archive':{'archive':{'path':str(archive),'bytes':archive.stat().st_size,'sha256':pilot.digest(archive)},'inventory':self.inventory}}
        complete={'passed':True,'allOwnedStopped':True,'round':1,'frozenReleaseSha256':'3'*64}
        def value(base,path,maximum=1024**2):
            return {'round-1-collection-gate.json':gate,'completion.json':complete,'python-owned-stop.json':{'allOwnedStopped':True},'after-clean-stop.json':after}[path.name]
        return gate,value,archive

    def test_second_round_full_closed_archive_gate_success_without_deletion(self):
        gate,value,archive=self.prior_gate_fixture();base=pilot.load_base()
        pilot.configure_round(2);pilot.FROZEN_RELEASE_SHA='3'*64;pilot.PRIOR_GATE_SHA='1'*64
        actual_digest=pilot.digest
        def hashed(path):return '1'*64 if Path(path).name=='round-1-collection-gate.json' else actual_digest(path)
        with mock.patch.object(pilot,'PREP',self.root),mock.patch.object(pilot,'json_bounded',side_effect=value),mock.patch.object(pilot,'digest',side_effect=hashed):
            result=pilot.verify_prior_round_gate(base,release())
        self.assertTrue(result['passed']);self.assertTrue(archive.exists());self.assertFalse(result['controllerDeletesAnyFile'])
        self.assertFalse(result['retainedNativeStillPresent'])

    def test_missing_prior_native_requires_explicit_root_review(self):
        gate,value,archive=self.prior_gate_fixture();gate['rootReviewedExactOwnedNativeRemoval']=False;base=pilot.load_base()
        pilot.configure_round(2);pilot.FROZEN_RELEASE_SHA='3'*64;pilot.PRIOR_GATE_SHA='1'*64
        actual_digest=pilot.digest
        def hashed(path):return '1'*64 if Path(path).name=='round-1-collection-gate.json' else actual_digest(path)
        with mock.patch.object(pilot,'PREP',self.root),mock.patch.object(pilot,'json_bounded',side_effect=value),mock.patch.object(pilot,'digest',side_effect=hashed):
            with self.assertRaisesRegex(RuntimeError,'Missing prior owned native'):pilot.verify_prior_round_gate(base,release())

    def test_archive_closure_digest_mutation_or_failed_stop_refused(self):
        gate,value,archive=self.prior_gate_fixture();gate['closedNativeInventorySha256']='0'*64;base=pilot.load_base()
        pilot.configure_round(2);pilot.FROZEN_RELEASE_SHA='3'*64;pilot.PRIOR_GATE_SHA='1'*64
        actual_digest=pilot.digest
        def hashed(path):return '1'*64 if Path(path).name=='round-1-collection-gate.json' else actual_digest(path)
        with mock.patch.object(pilot,'PREP',self.root),mock.patch.object(pilot,'json_bounded',side_effect=value),mock.patch.object(pilot,'digest',side_effect=hashed):
            with self.assertRaisesRegex(RuntimeError,'native inventory differs'):pilot.verify_prior_round_gate(base,release())

    def test_stream_all_file_sha_owner_mode_empty_directory_closure(self):
        self.write_archive();result=pilot.verify_archive_members(self.archive,self.inventory)
        self.assertTrue(result['passed']);self.assertEqual(result['files'],1);self.assertEqual(result['directories'],2)
        self.assertTrue(result['noExtraction']);self.assertFalse((self.root/'chunk-pair').exists())

    def test_payload_mutation_or_missing_empty_dir_refused(self):
        self.write_archive(payload=b'bad'+self.payload[3:])
        with self.assertRaisesRegex(RuntimeError,'payload SHA'):pilot.verify_archive_members(self.archive,self.inventory)
        self.write_archive(omit_empty=True)
        with self.assertRaisesRegex(RuntimeError,'closure differs'):pilot.verify_archive_members(self.archive,self.inventory)

    def test_link_special_traversal_or_duplicate_refused(self):
        for name,kind in [('chunk-pair/link',tarfile.SYMTYPE),('chunk-pair/../escape',tarfile.REGTYPE),
                          ('chunk-pair/raw.bin',tarfile.REGTYPE),('outside',tarfile.REGTYPE)]:
            row=tarfile.TarInfo(name);row.type=kind
            self.write_archive(extra=row)
            with self.subTest(name=name),self.assertRaises(RuntimeError):pilot.verify_archive_members(self.archive,self.inventory)

if __name__ == '__main__':
    unittest.main(verbosity=2)
