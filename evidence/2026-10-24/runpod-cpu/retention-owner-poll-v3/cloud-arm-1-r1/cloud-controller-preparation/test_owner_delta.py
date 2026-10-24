"""Pure local rejection/actual-metadata guards. Synthetic proofs never authorize a run."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import cpu_owner_poll_abab as p

HERE=Path(__file__).resolve().parent

def fixture():
    value=json.loads((HERE/'release.template.json').read_text())
    value.update(releaseReady=True,controllerSha256='f'*64)
    for key,row in value['evidenceReferences'].items():
        if key not in p.PREREQUISITE_PINS:row.update(bytes=128,sha256='a'*64)
    return value

def native_fixture(release):
    # Deliberately synthetic schema values; no fixture is written as a release/proof.
    return dict(schemaVersion=1,scope='OWNER_POLL_NEW_ARTIFACT_FUNCTIONAL_PAIR',passed=True,
        sourceCommit=release['sourceCommit'],codeFingerprint=release['codeFingerprint'],
        profileSha256=release['profileFingerprint'],sameNewArtifact=True,
        localPerformanceClaimed=False,allInputsUnchanged=True,
        arms=[dict(ownerPollMaximumParkNs=maximum,serverDriverMaximumParkNs=100000,
            arrivals=6400,accepted=6400,rawFunctionalPassed=True,ownerActualAttestationPassed=True,
            schedulerTimingValid=(maximum==1000000),fullNativeArchiveSha256='b'*64,inventorySha256='c'*64)
            for maximum in (1000000,100000)],
        fullAuditResult=dict(path='synthetic/full-result.json',bytes=100,sha256='d'*64),
        sourceFreeze=dict(path='synthetic/SOURCE_FROZEN.json',bytes=100,sha256='e'*64))

def parser_fixture(release):
    rows={'long-parser/'+name:dict(row)for name,row in p.LONG_PARSER_BASELINE_ROWS.items()}
    rows['short-parser/audit_raw.py']=dict(bytes=1,sha256='801475c4c4769e9da68db08440717efe39b140dd7cf9ac3fd6699ebb48a7ade8') # synthetic size; no fixture written as actual source
    rows['owner_poll_attestation.py']=dict(bytes=5686,sha256=release['ownerPollValidatorSha256'])
    return dict(schemaVersion=1,scope='OWNER_POLL_RAW_AUDIT_SOURCE_CLOSURE',
        sourceCommit=release['sourceCommit'],codeFingerprint=release['codeFingerprint'],
        shortBaselineParserSha256='801475c4c4769e9da68db08440717efe39b140dd7cf9ac3fd6699ebb48a7ade8',
        longBaselineFreezeSha256='1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3',
        guardCount=14,sourceFiles=rows)

def prerequisites():
    release=fixture()
    values={key:json.loads((HERE/'fixtures'/name).read_text())for key,name in {
        'linuxMetadataObservation':'actual-linux-distribution-observation.json',
        'linuxMetadataReceipt':'actual-linux-metadata-receipt.json'}.items()}
    values['ownerPollNativeAudit']=native_fixture(release)
    values['ownerPollRawParserFreeze']=parser_fixture(release)
    values['rootEvidenceReview']=dict(scope='ROOT_REVIEWED_OWNER_POLL_CLOUD_PREREQUISITES',passed=True,
        sourceCommit=release['sourceCommit'],codeFingerprint=release['codeFingerprint'],
        profileFingerprint=release['profileFingerprint'],controllerSha256=release['controllerSha256'],
        ownerPollValidatorSha256=release['ownerPollValidatorSha256'],
        proofBindings={key:{k:row[k]for k in ('bytes','sha256')}for key,row in release['evidenceReferences'].items()if key!='rootEvidenceReview'},
        nativeFullAuditResultSha256=values['ownerPollNativeAudit']['fullAuditResult']['sha256'],
        nativeSourceFreezeSha256=values['ownerPollNativeAudit']['sourceFreeze']['sha256'],
        prerequisiteReviewInputs={key:dict(bytes=128,sha256='1'*64)for key in ('unitCompletion','unitRootReview','independentSourceReview')},
        guardsPassed=True,strictCpuSchedulerRequired=True,noNewResources=True)
    return values,release

def registration(release):
    return dict(arrivals=33792,rate=500,batchCap=4,archiveChunkBytes=6144,readWindow=8,eventFetchCount=16,
        commonChunkEnvelope=False,commonReadWindowEnvelope=True,appointedLeader=0,sync=2,
        profileSha256=release['profileFingerprint'],codeSha256=release['codeFingerprint'],
        retentionIdleSelection=p.selection(),ownerPollSelection=p.expected_owner_selection(p.selected_owner_park_ns()),
        ports=42000,lineage='capacity-pilot-fixture',workloadPreset='long-cuts-33792-v1',expectedFullCommandCuts=11,
        expectedTrailingCommands=3,equivalentFullLoadCutNumbers=list(range(2,12)))

def summary():
    return dict(scheduledArrivals=33792,releasedArrivals=33792,ratePerSecond=500,batchCap=4,
        archiveChunkBytes=6144,readWindow=8,arrivalClockPausedForMaintenance=False,unknownFinal=0,
        unknownObserved=0,maintenanceCycles=12,schedulerTimingValid=True,schedulerLatenessOver20ms=0,
        confirmedAcceptedUniqueOrders=33792,notSent=0,serverRejected=0,
        duplicateOrOutOfRangeAcceptedOrderIds=0,completedLogicalReplies=33792)

def prior_gate(release):
    return dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION',collectionComplete=True,
        arm=p.ARM-1,ownerPollMaximumParkNs=p.OWNER_PARK_ORDER[p.ARM-2],serverDriverMaximumParkNs=100000,
        frozenReleaseSha256=p.FROZEN_RELEASE_SHA,controllerSha256=release['controllerSha256'],
        codeFingerprint=release['codeFingerprint'],localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,
        allRawInputsAndFailuresRetained=True,strictSchedulerTimingAdmission=True,
        independentLocalCollectionReceiptSha256='b'*64,closedArchiveSha256='c'*64,
        closedNativeInventorySha256='d'*64,privatePushReceiptSha256='e'*64)

def push_receipt(gate):
    return dict(schemaVersion=1,scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH',repository='yinli-systems/vectormatch',
        visibility='private',pushCompleted=True,remoteCommitVerified=True,commit='a'*40,
        fullOriginalEvidencePushed=True,evidenceManifestSha256='b'*64,
        closedArchiveSha256=gate['closedArchiveSha256'],closedNativeInventorySha256=gate['closedNativeInventorySha256'])

class OwnerDelta(unittest.TestCase):
    def tearDown(self):
        p.configure_arm(1);p.FROZEN_RELEASE_SHA=None;p.PRIOR_GATE_SHA=None

    def test_actual_false_ready_template_cannot_self_release(self):
        r=json.loads((HERE/'release.template.json').read_text())
        with self.assertRaisesRegex(RuntimeError,'unfrozen draft'):p.validate_release(r)
        r['releaseReady']=True;r['controllerSha256']='f'*64
        with self.assertRaisesRegex(RuntimeError,'pending prerequisite'):p.validate_release(r)
        self.assertTrue(p.validate_release(fixture()))

    def test_exact_four_manual_modes_and_defensive_configuration(self):
        for arm,maximum in enumerate((1000000,100000,1000000,100000),1):
            p.configure_arm(arm)
            self.assertEqual(p.selected_owner_park_ns(),maximum);self.assertEqual(p.selected_park_ns(),100000)
            self.assertEqual(p.PAIR,p.PREP/('arm-%d/idle-arm'%arm))
        for arm in (0,5,True,'1'):
            with self.subTest(arm=arm),self.assertRaises(RuntimeError):p.configure_arm(arm)
        c=p.fixed_configuration();c['ownerPollMaximumParkNsOrder'][0]=7
        self.assertEqual(p.fixed_configuration()['ownerPollMaximumParkNsOrder'][0],1000000)

    def test_parent_alone_selects_owner_and_all_nodes_keep100us(self):
        r=fixture()
        for arm in (1,2,3,4):
            p.configure_arm(arm);parent=p.parent_argv(r)
            self.assertEqual([x for x in parent if p.OWNER_PROPERTY in x],['-D'+p.OWNER_PROPERTY+'='+str(p.OWNER_PARK_ORDER[arm-1])])
            self.assertEqual([x for x in parent if p.PROPERTY in x],['-D'+p.PROPERTY+'=100000'])
            self.assertEqual(parent[-2:],['idle-window8-long-cuts','42000'])
            for member in (0,1,2):
                node=p.node_argv(r,8,member,registration(r))
                self.assertFalse(any(p.OWNER_PROPERTY in x for x in node))
                self.assertEqual([x for x in node if p.PROPERTY in x],['-D'+p.PROPERTY+'=100000'])
                self.assertIn('-Daeron.cluster.appointed.leader.id=0',node)

    def test_driver_selection_schema_stays_byte_semantically_unchanged(self):
        self.assertEqual(p.selection(),dict(schema='retention-idle-selection-v1',property=p.PROPERTY,
            maximumParkNs=100000,factor='maximum requested park only'))
        for arm in (1,2,3,4):
            p.configure_arm(arm);reg=registration(fixture());p.validate_registration(fixture(),8,reg)
            reg['ownerPollSelection']=p.expected_owner_selection(100000 if p.selected_owner_park_ns()==1000000 else 1000000)
            with self.assertRaises(RuntimeError):p.validate_registration(fixture(),8,reg)

    def test_only_new_actual_artifacts_and_same_fixed_long_plan(self):
        r=fixture();o=json.loads((HERE/'fixtures/actual-linux-distribution-observation.json').read_text())
        self.assertEqual(r['derivedPlan'],o['workloads']['LONG_CUTS']['plan']);self.assertEqual(r['codeFingerprint'],o['actualCodeFingerprint'])
        self.assertEqual(r['sourceCommit'],'977197616ade0283174f2ea6ddfaa700547f6d15')
        self.assertEqual(len(r['artifacts']),4);self.assertEqual(r['derivedPlan']['maximumLogicalMaintenanceRpcs'],7243)
        for key,value in [('sourceCommit','bcf49c10b77a14708b53d3fc6c115a6a3b834408'),('codeFingerprint','0'*64),('profileFingerprint','0'*64),('ownerPollValidatorSha256','0'*64)]:
            bad=copy.deepcopy(r);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(bad)
        bad=copy.deepcopy(r);bad['artifacts'][r['classPath'][0]]['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_release(bad)

    def test_fixed_config_cannot_lower_protection_or_factors(self):
        for key,value in [('arrivals',6400),('ratePerSecond',1000),('readWindow',1),('batchCap',8),
            ('archiveChunkBytes',3072),('eventFetchCount',64),('sync',0),('fixedBasePorts',42001),
            ('cleanupEnabled',True),('serverDriverMaximumParkNs',1000000),('ownerPollMaximumParkNsOrder',[100000]*4)]:
            bad=fixture();bad['configuration'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(bad)
        for key,value in [('maximumRawTraceBytes',3*p.GIB),('maximumAllocatedGrowthBytes',3*p.GIB),('maximumJournalRecords',1024),('maximumPhysicalOffersPerRpc',5)]:
            bad=fixture();bad['derivedPlan'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(bad)
        self.assertEqual(p.allocation_limit(fixture())+p.GIB+p.MAX_ARCHIVE,2116076873)

    def test_classpath_order_and_exact_node_closure(self):
        for key in ('classPath','nodeClassPath'):
            r=fixture();r[key]=list(reversed(r[key]))
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)

    def test_real_linux_closed_metadata_passes_without_a_new_jvm(self):
        values,r=prerequisites()
        self.assertTrue(p.validate_linux_metadata(values['linuxMetadataObservation'],values['linuxMetadataReceipt'],r))
        self.assertEqual(len(values['linuxMetadataObservation']['actualCodeSources']),7)

    def test_linux_observation_and_owned_pid_are_crossbound(self):
        values,r=prerequisites();o=values['linuxMetadataObservation'];receipt=values['linuxMetadataReceipt']
        for path,value in [(('observationSha256',),'0'*64),(('execution','ownedParentPid'),99),
            (('execution','processIdentityObservationGap'),True),(('execution','metadataJvmExited'),False),
            (('execution','allInputsUnchanged'),False),(('execution','actualProcessIdentity','commandSha256'),'0'*64)]:
            bad=copy.deepcopy(receipt);target=bad
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)

    def test_linux_must_not_pretend_owner_was_constructed(self):
        values,r=prerequisites();receipt=values['linuxMetadataReceipt']
        for key,value in [('ownerConstructed',True),('ownerRuntimeObservationAvailable',True),('ownerPollAbsentEffectiveMaximumParkNs',100000),('ownerPollSelections',{})]:
            bad=copy.deepcopy(values['linuxMetadataObservation']);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)

    def test_linux_source_class_plan_and_helper_drift_rejected(self):
        values,r=prerequisites();o=values['linuxMetadataObservation'];receipt=values['linuxMetadataReceipt']
        bad=copy.deepcopy(o);bad['actualCodeSources'].pop()
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)
        bad=copy.deepcopy(o);bad['workloads']['LONG_CUTS']['plan']['maximumRawTraceBytes']+=1
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)
        bad=copy.deepcopy(o);bad['actualCodeSources'][0]['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)
        for name in ('OwnerPollDistributionObservation.java','classes/io/vectormatch/cluster/OwnerPollDistributionObservation.class'):
            bad=copy.deepcopy(receipt);bad['stagedFiles'][name]['sha256']='0'*64
            with self.subTest(name=name),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)

    def test_native_functional_schema_preserves_actual_invalid_timing(self):
        r=fixture();n=native_fixture(r);self.assertTrue(p.validate_native_proof(n,r))
        self.assertIs(n['arms'][1]['schedulerTimingValid'],False)
        for key,value in [('scope','PRE_RAW_AUDIT'),('sameNewArtifact',False),('passed',False),('localPerformanceClaimed',True),('allInputsUnchanged',False)]:
            bad=copy.deepcopy(n);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_native_proof(bad,r)
        for key,value in [('arrivals',33792),('accepted',6399),('ownerPollMaximumParkNs',1000000),('serverDriverMaximumParkNs',1000000),('schedulerTimingValid','false'),('fullNativeArchiveSha256',None),('ownerActualAttestationPassed',False)]:
            bad=copy.deepcopy(n);bad['arms'][1][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_native_proof(bad,r)

    def test_native_full_audit_and_source_closure_required(self):
        for key in ('fullAuditResult','sourceFreeze'):
            n=native_fixture(fixture());n[key]['sha256']=None
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_native_proof(n,fixture())

    def test_parser_uses_actual_short_and_long_and_single_owner_validator(self):
        r=fixture();f=parser_fixture(r);self.assertTrue(p.validate_parser_freeze(f,r))
        for key,value in [('shortBaselineParserSha256','0'*64),('longBaselineFreezeSha256','0'*64),('guardCount',0),('codeFingerprint','0'*64)]:
            bad=copy.deepcopy(f);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_parser_freeze(bad,r)
        bad=copy.deepcopy(f);bad['sourceFiles']['owner_poll_attestation.py']['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_parser_freeze(bad,r)
        bad=copy.deepcopy(f);bad['sourceFiles']['../escape.py']=dict(bytes=1,sha256='a'*64)
        with self.assertRaises(RuntimeError):p.validate_parser_freeze(bad,r)
        for name in p.LONG_PARSER_BASELINE_ROWS:
            bad=copy.deepcopy(f);del bad['sourceFiles']['long-parser/'+name]
            with self.subTest(name=name),self.assertRaises(RuntimeError):p.validate_parser_freeze(bad,r)
        bad=copy.deepcopy(f);del bad['sourceFiles']['short-parser/audit_raw.py']
        with self.assertRaises(RuntimeError):p.validate_parser_freeze(bad,r)

    def test_all_proofs_need_actual_root_review_not_only_true_declarations(self):
        values,r=prerequisites();self.assertTrue(p.validate_prerequisite_proofs(values,r))
        for key in values:
            bad=copy.deepcopy(values);bad[key]={}
            with self.subTest(key=key),self.assertRaises((RuntimeError,KeyError)):p.validate_prerequisite_proofs(bad,r)
        for key,value in [('scope','OLD_LONG_REVIEW'),('controllerSha256','0'*64),('strictCpuSchedulerRequired',False),('nativeFullAuditResultSha256','0'*64),('ownerPollValidatorSha256','0'*64),('passed',False)]:
            bad=copy.deepcopy(values);bad['rootEvidenceReview'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)
        bad=copy.deepcopy(values);bad['rootEvidenceReview']['proofBindings']['linuxMetadataReceipt']['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)

    def test_source_unit_receipts_are_required_in_root_review(self):
        values,r=prerequisites()
        for key in ('unitCompletion','unitRootReview','independentSourceReview'):
            bad=copy.deepcopy(values);del bad['rootEvidenceReview']['prerequisiteReviewInputs'][key]
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)
            for field,value in (('bytes',0),('sha256',None)):
                bad=copy.deepcopy(values);bad['rootEvidenceReview']['prerequisiteReviewInputs'][key][field]=value
                with self.subTest(key=key,field=field),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)

    def test_cpu_scheduler_gate_stays_strict_even_native_diagnostic_allowed(self):
        self.assertTrue(p.validate_long_summary(summary(),8))
        for key,value in [('schedulerTimingValid',False),('schedulerLatenessOver20ms',1),('unknownObserved',1),('notSent',1),('serverRejected',1),('maintenanceCycles',3)]:
            bad=summary();bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_long_summary(bad,8)

    def test_previous_gate_exact_arm_artifact_scheduler_and_full_closure(self):
        r=fixture();p.FROZEN_RELEASE_SHA='a'*64
        for arm in (2,3,4):
            p.configure_arm(arm);g=prior_gate(r);self.assertTrue(p.validate_prior_gate(g,r,arm-1))
            for key,value in [('arm',arm),('ownerPollMaximumParkNs',7),('frozenReleaseSha256','b'*64),('codeFingerprint','0'*64),('strictSchedulerTimingAdmission',False),('allRawInputsAndFailuresRetained',False),('privatePushReceiptSha256',None)]:
                bad=copy.deepcopy(g);bad[key]=value
                with self.subTest(arm=arm,key=key),self.assertRaises(RuntimeError):p.validate_prior_gate(bad,r,arm-1)

    def test_private_push_is_bound_to_the_full_previous_archive(self):
        p.configure_arm(2);g=prior_gate(fixture());push=push_receipt(g);self.assertTrue(p.validate_private_push(push,g))
        for key,value in [('visibility','public'),('repository','wrong/repo'),('pushCompleted',False),('remoteCommitVerified',False),('commit','x'*40),('fullOriginalEvidencePushed',False),('closedArchiveSha256','0'*64),('closedNativeInventorySha256','0'*64)]:
            bad=copy.deepcopy(push);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_private_push(bad,g)

    def test_cli_cannot_omit_previous_gate_or_auto_run_next(self):
        with mock.patch.object(p,'load_base',side_effect=AssertionError('No ownership import for invalid gate')):
            for argv in (['--arm','2'],['--arm','3'],['--arm','4'],['--arm','1','--prior-collection-sha256','a'*64]):
                with self.subTest(argv=argv),self.assertRaises(RuntimeError):p.main(argv)
        with self.assertRaises(SystemExit):p.main(['--arm','1','--auto-next'])

    def test_default_cli_only_preflights(self):
        r=fixture();base=object()
        with mock.patch.object(p,'load_base',return_value=base),mock.patch.object(p,'runtime_manifest',return_value=r),mock.patch.object(p,'preflight',return_value={'noJavaStarted':True}) as preflight,mock.patch.object(p,'execute',side_effect=AssertionError('Implicit benchmark forbidden')):
            p.main(['--arm','1','--release-sha256','a'*64]);preflight.assert_called_once_with(base,r)

    def test_lineage_freshness_in_every_arm(self):
        p.configure_arm(4);reg=registration(fixture())
        prior={'registration':dict(reg,lineage='capacity-pilot-prior')}
        with mock.patch.object(p,'json_bounded',return_value=prior) as read:
            self.assertTrue(p.validate_fresh_lineage(object(),reg));self.assertEqual(read.call_count,3)
        with mock.patch.object(p,'json_bounded',return_value={'registration':reg}),self.assertRaises(RuntimeError):p.validate_fresh_lineage(object(),reg)

    def test_process_ownership_and_no_kill_escalation_unchanged(self):
        old=ast.parse((HERE/'baseline/cpu_long_cuts.py').read_text());new=ast.parse((HERE/'cpu_owner_poll_abab.py').read_text())
        a={n.name:ast.dump(n,include_attributes=False)for n in old.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        b={n.name:ast.dump(n,include_attributes=False)for n in new.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        for name in ('owned_metrics','global_metrics','Telemetry','protected_state','allocated_scan','allocation_limit','strict_idle','verify_archive_members','clean_all','validate_egress','validate_egress_progress','collect_stopped','monitor','runtime_manifest','kernel_record_from_json','json_bounded'):
            self.assertEqual(a[name],b[name],name)
        self.assertEqual(p.BASE_SHA,'8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87')

    def test_source_has_explicit_actual_owner_evidence_calls(self):
        source=(HERE/'cpu_owner_poll_abab.py').read_text();tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='validate_result')
        calls=[n for n in ast.walk(fn)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='validate_owner_bundle']
        self.assertEqual(len(calls),1)
        self.assertEqual({x.arg for x in calls[0].keywords},{'registration','configuration','summary','before','after','parent','nodes','expected_owner_cap','expected_parent_arguments','expected_node_arguments','node_idle_actuals','parent_idle_actuals'})
        self.assertIn('historicalValidatorScope',source)

    def test_retained_bounds_protection_and_no_cleanup_function(self):
        self.assertEqual((p.EXECUTE_SECONDS,p.TOTAL_SECONDS,p.METRIC_SAMPLE_CAP,p.METRIC_BYTES_CAP),(240,360,512,8*1024**2))
        self.assertEqual((p.MAX_ARCHIVE,p.MAX_LOG,p.MAX_PATHS,p.MAX_LOGICAL),(256*1024**2,4*1024**2,8192,12*p.GIB))
        r=fixture();self.assertEqual(r['protectedOriginalState']['manifestSha256'],'6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753')
        r['protectedOriginalState']['manifestSha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_release(r)
        source=(HERE/'cpu_owner_poll_abab.py').read_text()
        for forbidden in ('shutil.rmtree','os.remove(','unlink(','--allow-invalid-scheduler','--auto-next'):
            self.assertNotIn(forbidden,source)

if __name__=='__main__':unittest.main()
