"""Pure synthetic protocol/negative guards only. Never real stage, raw audit, SSH or JVM."""
import copy
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as c
import cpu_read_window32_abab as controller
import build_config
import collect_and_audit as runner
import closed_bindings as bindings
import frozen_parser
import audit_raw
import audit_native_artifacts as native
import owner_bundle
import finalize_local_collection as finalize


def write(path,value):
    path.write_text(json.dumps(value));return c.sha(path)


def release_fixture():
    value=json.loads((HERE/'fixtures/release.template.json').read_text())
    value.update(releaseReady=True,controllerSha256=c.sha(HERE/'cpu_read_window32_abab.py'))
    for key,row in value['evidenceReferences'].items():
        if key not in controller.PREREQUISITE_PINS:row.update(bytes=128,sha256='a'*64)
    return value


def prior_fixture(number,release_sha,release):
    push=dict(schemaVersion=1,scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH',repository='yinli-systems/vectormatch',visibility='private',
        pushCompleted=True,remoteCommitVerified=True,commit='d'*40,fullOriginalEvidencePushed=True,evidenceManifestSha256='e'*64,
        closedArchiveSha256='b'*64,closedNativeInventorySha256='c'*64)
    gate=dict(schemaVersion=3,scope='ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_ARM_COLLECTION',collectionComplete=True,
        arm=number,eventFetchCount=32,readWindow=controller.READ_WINDOW_ORDER[number-1],commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,
        sameNewArtifactFunctionalQualified=True,allOriginalRawCanonicalAndThreeSnapshotsVerified=True,
        ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,frozenReleaseSha256=release_sha,
        controllerSha256=release['controllerSha256'],codeFingerprint=release['codeFingerprint'],
        localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,allRawInputsAndFailuresRetained=True,strictSchedulerTimingAdmission=True,
        independentLocalCollectionReceiptSha256='f'*64,closedArchiveSha256='b'*64,closedNativeInventorySha256='c'*64)
    return gate,push


class Guards(unittest.TestCase):
    def tearDown(self):controller.configure_arm(1)

    def config(self,root,arm):
        root=Path(root).resolve();protected=root/'protected.json';write(protected,{})
        value=release_fixture();value['protectedOriginalState']['manifestSha256']=c.sha(protected)
        release=root/'release.json';release_sha=write(release,value)
        rows=copy.deepcopy(json.loads((HERE/'controller-preparation-frozen.json').read_text())['files'])
        rows['LOCAL_PREPARATION_FROZEN.json']=dict(bytes=(HERE/'controller-preparation-frozen.json').stat().st_size,sha256=c.sha(HERE/'controller-preparation-frozen.json'))
        rows['release/release.json']=dict(bytes=release.stat().st_size,sha256=release_sha)
        rows['release/current-container-baseline.json']=dict(bytes=protected.stat().st_size,sha256=c.sha(protected))
        rows.update({'release/lib/'+Path(k).name:copy.deepcopy(row)for k,row in value['artifacts'].items()})
        rows.update({'release/proofs/'+k+'.json':{x:row[x]for x in('bytes','sha256')}for k,row in value['evidenceReferences'].items()})
        stage=root/'stage.json';write(stage,dict(passed=True,stagedFiles=rows,releaseSha256=release_sha,
            controllerSha256=value['controllerSha256'],applicationStarted=False,resourceCreated=False))
        gates={}
        for n in range(1,arm):
            gate,push=prior_fixture(n,release_sha,value);pp=root/('push%d.json'%n);ph=write(pp,push);gate['privatePushReceiptSha256']=ph
            gp=root/('gate%d.json'%n);gh=write(gp,gate);gates[str(n)]=dict(local=str(gp),sha256=gh,privatePushLocal=str(pp),privatePushSha256=ph)
        cfg=dict(schemaVersion=6,experiment='retention-read-window32-long-v1',workloadPreset='long-cuts-33792-v1',arm=arm,
            maximumParkNs=100000,serverDriverMaximumParkNs=100000,ownerPollMaximumParkNs=1000000,eventFetchCount=32,
            readWindow=controller.READ_WINDOW_ORDER[arm-1],remotePrep=str(controller.PREP),host='33ace3d92505',
            releaseLocal=str(release),releaseSha256=release_sha,stagingReceipt=str(stage),stagingReceiptSha256=c.sha(stage),
            protectedReference=str(protected),protectedReferenceSha256=c.sha(protected),priorGates=gates,
            executionMetadata=['arm-%d-execution-register.json'%arm,'arm-%d-execution.stdout'%arm,'arm-%d-execution.stderr'%arm])
        config=root/'config.json';write(config,cfg);return config,cfg,stage,value

    def load(self,path):
        # Explicit synthetic protected bytes are not actual release witnesses.
        with patch.object(controller,'validate_release',side_effect=lambda value:value):return c.load_config(path)

    def metadata(self):
        return (json.loads((HERE/'fixtures/actual-linux-distribution-observation.json').read_text()),
                json.loads((HERE/'fixtures/actual-local-distribution-observation.json').read_text()))

    def test_real_release_requires_new_artifact_schema_and_unmodified_threshold(self):
        value=release_fixture();self.assertIs(controller.validate_release(value),value)
        self.assertEqual(2116076873,controller.MINIMUM_INITIAL_FREE_BYTES)
        for key,bad in [('releaseReady',False),('schemaVersion',2),('sourceCommit','d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'),('codeFingerprint','0'*64)]:
            other=copy.deepcopy(value);other[key]=bad
            with self.subTest(key=key),self.assertRaises(RuntimeError):controller.validate_release(other)

    def test_four_arm_config_schema_exact_source_sets_and_all_prior_pairs(self):
        for arm in(1,2,3,4):
            with self.subTest(arm=arm),tempfile.TemporaryDirectory()as temp:
                path,cfg,stage,r=self.config(temp,arm);actual,_,rows,allow=self.load(path)
                self.assertEqual(controller.READ_WINDOW_ORDER[arm-1],actual['readWindow'])
                self.assertEqual(len(json.loads(stage.read_text())['stagedFiles'])+2*(arm-1),len(rows))
                self.assertEqual(len(rows)+3,len(allow));self.assertEqual(32,actual['eventFetchCount'])

    def test_old_namespace_schema_wrong_selected_window_and_diagnostic_metadata_denied(self):
        with tempfile.TemporaryDirectory()as temp:
            path,cfg,stage,r=self.config(temp,2)
            for key,value in [('schemaVersion',5),('experiment','retention-event-fetch-long-v1'),('readWindow',8),('readWindow',True),
                ('eventFetchCount',16),('remotePrep','/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1'),
                ('ownerPollMaximumParkNs',100000),('serverDriverMaximumParkNs',1000000),('priorGates',{}),('executionMetadata',['foreign.json'])]:
                bad=copy.deepcopy(cfg);bad[key]=value;write(path,bad)
                with self.subTest(key=key),self.assertRaises((AssertionError,RuntimeError,KeyError)):self.load(path)

    def test_prior_pair_cannot_relabel_wrong_window_envelope_or_unpushed_state(self):
        with tempfile.TemporaryDirectory()as temp:
            path,cfg,stage,r=self.config(temp,2);row=cfg['priorGates']['1'];gp=Path(row['local']);original=json.loads(gp.read_text())
            for key,value in [('readWindow',32),('eventFetchCount',16),('commonReadWindow32Envelope',False),('commonEventFetchEnvelope',True),
                ('strictSchedulerTimingAdmission',False),('codeFingerprint','0'*64)]:
                bad=copy.deepcopy(original);bad[key]=value;row['sha256']=write(gp,bad);write(path,cfg)
                with self.subTest(key=key),self.assertRaises((AssertionError,RuntimeError)):self.load(path)
            row['sha256']=write(gp,original);pp=Path(row['privatePushLocal']);push=json.loads(pp.read_text());push['remoteCommitVerified']=False
            row['privatePushSha256']=write(pp,push);original['privatePushReceiptSha256']=row['privatePushSha256'];row['sha256']=write(gp,original);write(path,cfg)
            with self.assertRaises(RuntimeError):self.load(path)

    def test_staged_files_need_exact_reviewed_names_and_controller_validator_hash(self):
        with tempfile.TemporaryDirectory()as temp:
            path,cfg,stage,r=self.config(temp,1);original=json.loads(stage.read_text())
            for name in ['owner_poll_attestation.py','cpu_read_window32_abab.py','release/release.json']:
                bad=copy.deepcopy(original);bad['stagedFiles'][name]['sha256']='0'*64;cfg['stagingReceiptSha256']=write(stage,bad);write(path,cfg)
                with self.subTest(name=name),self.assertRaises(AssertionError):self.load(path)
            bad=copy.deepcopy(original);bad['stagedFiles']['unrelated.py']=bad['stagedFiles'].pop('PLAN.md');cfg['stagingReceiptSha256']=write(stage,bad);write(path,cfg)
            with self.assertRaises(AssertionError):self.load(path)

    def test_builder_only_fresh_config_and_complete_explicit_prefix(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp).resolve();path,cfg,stage,r=self.config(root,1);out=root/'fresh'
            with patch.object(controller,'validate_release',side_effect=lambda value:value):
                result=build_config.build(1,Path(cfg['releaseLocal']),cfg['releaseSha256'],stage,cfg['stagingReceiptSha256'],
                    Path(cfg['protectedReference']),cfg['protectedReferenceSha256'],{},cfg['executionMetadata'],out)
                self.assertTrue(result.is_file())
                with self.assertRaises(AssertionError):build_config.build(1,Path(cfg['releaseLocal']),cfg['releaseSha256'],stage,
                    cfg['stagingReceiptSha256'],Path(cfg['protectedReference']),cfg['protectedReferenceSha256'],{},cfg['executionMetadata'],out)

    def test_frozen_read32_parser_is_byte_exact_strict_and_all_aliases_restored(self):
        previous={n:sys.modules.get(n)for n in frozen_parser.MODULES};modules=frozen_parser.load()
        self.assertEqual(previous,{n:sys.modules.get(n)for n in frozen_parser.MODULES})
        self.assertIs(modules['audit_raw'].audit_read_window32_arm.__kwdefaults__['local_functional_only'],False)
        self.assertEqual(33792,modules['workload_contract'].LONG.arrivals)
        self.assertEqual('766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad',frozen_parser.FREEZE_SHA)

    def test_parser_mutated_body_refused_without_module_alias_leak(self):
        before=sys.modules['common']
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp)/'parser';shutil.copytree(HERE/'long_parser',root);path=root/'source/read_window32_contract.py';path.write_bytes(path.read_bytes()+b'\n# forbidden\n')
            with self.assertRaises(AssertionError):frozen_parser.load(root)
        self.assertIs(sys.modules['common'],before)

    def test_strict_entry_requires_both_explicit_selections_and_no_timing_opt_in(self):
        calls=[];fake=types.SimpleNamespace(audit_read_window32_arm=lambda *args,**kw:calls.append((args,kw))or{})
        for window in(8,32):audit_raw.strict_arm(fake,'LONG','synthetic',selected_window=window,event_fetch_count=32)
        self.assertEqual([8,32],[a[0]for a,kw in calls]);self.assertTrue(all('local_functional_only'not in kw for a,kw in calls))
        for window in(None,True,0,16,33):
            with self.subTest(window=window),self.assertRaises(AssertionError):audit_raw.strict_arm(fake,'LONG','synthetic',selected_window=window,event_fetch_count=32)
        with self.assertRaises(TypeError):audit_raw.strict_arm(fake,'LONG','synthetic',event_fetch_count=32)
        with self.assertRaises(AssertionError):audit_raw.strict_arm(fake,'LONG','synthetic',selected_window=8,event_fetch_count=16)

    def test_real_linux_two_plans_compare_to_actual_local_four_before_parser(self):
        linux,local=self.metadata();contract=frozen_parser.load()['workload_contract']
        for window in(8,32):
            report=audit_raw.validate_actual_plan_sources(linux,local,local['plans']['page32-window%d'%window]['plan'],
                linux['actualCodeFingerprint'],selected_window=window,event_fetch_count=32,contract=contract)
            self.assertTrue(report['passed']);self.assertEqual(window,report['selectedReadWindow'])

    def test_never_fabricates_four_linux_plans_or_passes_linux_to_local_four_parser(self):
        linux,local=self.metadata();seen=[];fake=types.SimpleNamespace(validate_actual_plan_observation=lambda *a,**k:seen.append((a,k))or{})
        audit_raw.validate_actual_plan_sources(linux,local,local['plans']['page32-window8']['plan'],linux['actualCodeFingerprint'],selected_window=8,event_fetch_count=32,contract=fake)
        self.assertIs(local,seen[0][0][0]);self.assertEqual({'8','32'},set(linux['plans']))
        bad=copy.deepcopy(linux);bad['plans']=copy.deepcopy(local['plans'])
        with self.assertRaises(AssertionError):audit_raw.validate_actual_plan_sources(bad,local,{},linux['actualCodeFingerprint'],selected_window=8,event_fetch_count=32,contract=fake)
        self.assertEqual(1,len(seen))

    def test_linux_full_plan_configuration_or_identity_drift_blocks_before_parser(self):
        linux,local=self.metadata();fake=types.SimpleNamespace(validate_actual_plan_observation=lambda *a,**k:self.fail('Parser reached before actual local/Linux equality'))
        for key in ['plan','configuration']:
            bad=copy.deepcopy(linux);bad['plans']['32'][key]['readWindow'if key=='configuration'else'requestedReadWindow']=8
            with self.subTest(key=key),self.assertRaises(AssertionError):audit_raw.validate_actual_plan_sources(bad,local,{},linux['actualCodeFingerprint'],selected_window=8,event_fetch_count=32,contract=fake)
        bad=copy.deepcopy(linux);bad['sourceCommit']='old'
        with self.assertRaises(AssertionError):audit_raw.validate_actual_plan_sources(bad,local,{},linux['actualCodeFingerprint'],selected_window=8,event_fetch_count=32,contract=fake)

    def test_full_tapes_and_new_actual_trace_bound_preserved_on_overbudget(self):
        plan={'maximumRawTraceBytes':182433396};self.assertTrue(bindings.materialize('job/idle-arm/load/physical-replies.bin',40*1024**2,plan))
        self.assertFalse(bindings.materialize('job/foreign.bin',40*1024**2,plan))
        rows={name:{'bytes':60000000}for name in bindings.TAPES};budget=bindings.validate_tape_budget(rows,plan)
        self.assertFalse(budget['passed']);self.assertIn('retain complete outer/nested TAR',budget['failurePolicy'])
        self.assertTrue(all(not bindings.materialize(name,row['bytes'],plan,allow_tapes=False)for name,row in rows.items()))
        with self.assertRaises(AssertionError):bindings.validate_tape_budget(rows,{'maximumRawTraceBytes':185514924})

    def test_raw_qualification_requires_all_arrivals24_phases3canonical_logs(self):
        final={'combinedSha256':'h'};terminal=dict(rows=33792,acceptedUniqueOrders=33792,duplicateOrOutOfRangeAcceptedOrderIds=0)
        for window in(8,32):
            report=dict(eventFetchCount=32,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,readWindow=window,batchCap=4,
                cycles=[{}]*12,readPhaseBindings={'readPhases':[{}]*24},schedulerTimingValidFromRaw=True,
                nodeLogs=[dict(member=n,finalCheckpointSha256='h')for n in(0,1,2)])
            self.assertTrue(audit_raw.qualify_new_artifact(report,terminal,final,32,window))
            for key,value in [('readWindow',32 if window==8 else 8),('commonReadWindow32Envelope',False),('commonEventFetchEnvelope',True),
                ('schedulerTimingValidFromRaw',False),('cycles',[{}]*11),('readPhaseBindings',{'readPhases':[{}]*23}),('nodeLogs',report['nodeLogs'][:2])]:
                bad=copy.deepcopy(report);bad[key]=value
                with self.subTest(window=window,key=key),self.assertRaises(AssertionError):audit_raw.qualify_new_artifact(bad,terminal,final,32,window)
            bad=copy.deepcopy(terminal);bad['acceptedUniqueOrders']=33791
            with self.assertRaises(AssertionError):audit_raw.qualify_new_artifact(report,bad,final,32,window)

    def closed(self,arm):
        cfg=dict(arm=arm,eventFetchCount=32,readWindow=controller.READ_WINDOW_ORDER[arm-1],ownerPollMaximumParkNs=1000000,
            serverDriverMaximumParkNs=100000,releaseSha256='a'*64,remotePrep=str(controller.PREP))
        receipt=dict(schemaVersion=3,scope='ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_CONTROLLER',rootVerified=True,
            **{k:cfg[k]for k in('arm','eventFetchCount','readWindow','ownerPollMaximumParkNs','serverDriverMaximumParkNs')},
            commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,frozenReleaseSha256='a'*64,
            controllerSha256='b'*64,job=str(controller.PREP)+'/arm-'+str(arm),controllerIdentityGone=True,allOwnedStopped=True,
            inspectionSha256='c'*64,executedSourceSha256=runner.CLOSE_SOURCE_SHA)
        return cfg,receipt

    def test_actual_new_close_pin_required_not_old_event_or_other_hex(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp).resolve()/'closed.json';cfg,receipt=self.closed(1);write(path,receipt)
            self.assertTrue(c.hexsha(runner.CLOSE_SOURCE_SHA));runner.closed_proof(path,c.sha(path),cfg,dict(controllerSha256='b'*64))
            for value in ['67fcfe5bd15efb8bdc488d25b156534b34878ce6584e5cb2ec3cf95ebeb2b5f2','f'*64,'']:
                bad=dict(receipt,executedSourceSha256=value);write(path,bad)
                with self.subTest(value=value),self.assertRaises(AssertionError):runner.closed_proof(path,c.sha(path),cfg,dict(controllerSha256='b'*64))

    def test_closed_scope_schema_window_envelopes_and_all_pid_closure_required(self):
        with tempfile.TemporaryDirectory()as temp:
            path=Path(temp).resolve()/'closed.json';cfg,receipt=self.closed(2)
            for key,value in [('schemaVersion',2),('scope','ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_CONTROLLER'),('readWindow',8),
                ('commonReadWindow32Envelope',False),('commonEventFetchEnvelope',True),('eventFetchCount',16),
                ('allOwnedStopped',False),('controllerIdentityGone',False),('serverDriverMaximumParkNs',1000000)]:
                bad=dict(receipt,**{key:value});write(path,bad)
                with self.subTest(key=key),self.assertRaises(AssertionError):runner.closed_proof(path,c.sha(path),cfg,dict(controllerSha256='b'*64))

    def test_native_dispatches_actual_selected_controller_before_io(self):
        class Reached(Exception):pass
        def configure(arm):self.assertEqual(2,arm);raise Reached()
        with patch.object(native,'controller',types.SimpleNamespace(configure_arm=configure)):
            with self.assertRaises(Reached):native.audit(object(),dict(arm=2),{})

    def test_owner_bundle_binds_selected_node_roles_exact_parent_argv_and_same_validator(self):
        for arm in(1,2,3,4):
            controller.configure_arm(arm);window=controller.selected_read_window();release=release_fixture();root=controller.PAIR
            envelope=dict(eventFetchCount=32,readWindow=window,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False)
            geometry=dict(envelope,batchCap=4,archiveChunkBytes=6144)
            registration=dict(envelope,lineage='capacity-pilot-synthetic',ports=42000)
            identities={'pilot-parent':dict(pid=100,arguments=controller.parent_argv(release))}
            identities.update({'window-%d-node-%d'%(window,n):dict(pid=101+n,arguments=controller.node_argv(release,window,n,registration))for n in(0,1,2)})
            summary=dict(geometry,maintenanceRpcMetrics=dict(eventFetchCount=32,readWindow=window,commonReadWindow32Envelope=True),
                         physicalOfferTape={'lastActualTransportObservation':{'retentionIdlePolicy':{'last':'actual'}}})
            values={'registration.json':registration,'configuration.json':dict(geometry),'load-result.json':summary,
                'admission-plan.json':controller.selected_plan(release),'completion.json':dict(envelope),'functional-result.json':dict(envelope),
                'transport-observations.json':[{'retentionIdlePolicy':{'sample':'actual'}}],
                'owner-before-close.json':{'alive':True},'owner-after-close.json':{'alive':False}}
            def read(path):
                return {'node':int(path.parts[-3].split('-')[-1])}if path.name=='idle-000.actual.json'else values[path.name]
            cfg=dict(arm=arm,eventFetchCount=32,readWindow=window,ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000)
            with patch.object(owner_bundle,'validate_owner_bundle',return_value={'passed':True})as sole:
                self.assertTrue(owner_bundle.verify(cfg,release,root,read,identities)['passed'])
                actual=sole.call_args.kwargs
                self.assertEqual({n:identities['window-%d-node-%d'%(window,n)]for n in(0,1,2)},actual['nodes'])
                self.assertEqual(controller.parent_argv(release),actual['expected_parent_arguments'])
                self.assertEqual([{'sample':'actual'},{'last':'actual'}],actual['parent_idle_actuals'])
                self.assertEqual(1000000,actual['expected_owner_cap'])

    def test_failed_native_or_raw_retains_partials_and_refuses_finalization(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp).resolve();proof=root/'proof';proof.write_bytes(b'SYNTHETIC ONLY');cfg=dict(arm=2,eventFetchCount=32,readWindow=32,serverDriverMaximumParkNs=100000,ownerPollMaximumParkNs=1000000)
            output=root/'attempt';calls=[]
            def invoke(args,dest,label):
                calls.append(label)
                if label=='strict-raw':(dest/'partial.guard').write_bytes(b'partial synthetic evidence')
                return dict(exitCode=1 if label in('strict-native','strict-raw')else 0)
            with patch.object(runner,'preparation',return_value={}),patch.object(runner,'checked_config',return_value=(cfg,{},[])),patch.object(runner,'closed_proof',return_value={}),\
                patch.object(runner.b,'reference',side_effect=lambda path,h:path),patch.object(runner,'invoke',side_effect=invoke):
                report=runner.execute(root/'config','a'*64,output,proof,'b'*64,'c'*64,root/'remote')
            self.assertFalse(report['passed']);self.assertFalse(report['nextArmAuthorized']);self.assertFalse(report['rootGateCreated'])
            self.assertEqual(['collect-readonly','full-native-byte-closure','strict-native','strict-raw'],calls)
            self.assertTrue((output/'partial.guard').exists());self.assertTrue((output/'DIAGNOSTICS_ONLY.json').exists())

    def test_finalizer_requires_same_window_raw_canonical_and_strict_scheduler(self):
        owner=dict(passed=True,ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,selectionIntentAndConstructedOwnerSnapshotReconciled=True,
            exactRegisteredParentAndThreeNodeArgumentsVerified=True,ownerPropertyParentOnly=True,actualConfiguredIdleFactoryCreations=22)
        native_report=dict(sourceCommit='source',frozenCodeFingerprintIndependentlyRecomputed='code',eventFetchCount=32,readWindow=32,
            commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,ownerPollAttestation=owner)
        raw=dict(sourceCommit='source',eventFetchCount=32,readWindow=32,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,
            strictSchedulerTimingAdmission=True,localFunctionalDiagnosticOptIn=False,ownerPollAttestation=owner,
            sameNewArtifactFunctionalQualified=True,allOriginalRawCanonicalAndThreeSnapshotsVerified=True)
        reports=dict(nativeResult=native_report,rawResult=raw,collectionReceipt={'rawTapeMaterializationBudget':{'passed':True}})
        finalize.strict_long_reports(reports,'source','code',1000000,event_fetch_count=32,selected_window=32)
        for key,value in [('readWindow',8),('strictSchedulerTimingAdmission',False),('localFunctionalDiagnosticOptIn',True),
            ('sameNewArtifactFunctionalQualified',False),('allOriginalRawCanonicalAndThreeSnapshotsVerified',False),('commonReadWindow32Envelope',False)]:
            bad=copy.deepcopy(reports);bad['rawResult'][key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):finalize.strict_long_reports(bad,'source','code',1000000,event_fetch_count=32,selected_window=32)


if __name__=='__main__':unittest.main(verbosity=2)
