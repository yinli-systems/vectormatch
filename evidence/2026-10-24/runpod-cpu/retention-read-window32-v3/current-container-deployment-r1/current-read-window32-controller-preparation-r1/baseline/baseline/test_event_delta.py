"""Pure candidate rejection guards; synthetic declarations do not qualify a business run."""
import ast, copy, json
from pathlib import Path
import unittest
from unittest import mock
import cpu_event_fetch_abab as p

HERE=Path(__file__).resolve().parent

def fixture():
    r=json.loads((HERE/'release.template.json').read_text())
    r.update(releaseReady=True,controllerSha256='f'*64)
    for key,row in r['evidenceReferences'].items():
        if row['sha256'] is None:row.update(bytes=128,sha256='a'*64)
    return r

def prerequisites():
    r=fixture()
    v={key:json.loads((HERE/'fixtures'/name).read_text()) for key,name in {
        'linuxMetadataObservation':'actual-linux-distribution-observation.json',
        'linuxMetadataReceipt':'remote-receipt.json',
        'eventFetchRawParserFreeze':'event-fetch-parser-source-freeze.json'}.items()}
    v['campaignQualificationPolicy']=p.qualification_policy()
    v['rootEvidenceReview']=dict(scope='ROOT_REVIEWED_EVENT_FETCH_CLOUD_PREREQUISITES',passed=True,
        sourceCommit=r['sourceCommit'],codeFingerprint=r['codeFingerprint'],profileFingerprint=r['profileFingerprint'],
        controllerSha256=r['controllerSha256'],ownerPollValidatorSha256=r['ownerPollValidatorSha256'],
        proofBindings={k:{x:row[x] for x in ('bytes','sha256')} for k,row in r['evidenceReferences'].items() if k!='rootEvidenceReview'},
        parserSourceFreezeSha256=p.PARSER_FREEZE_SHA,firstCloudArmQualifiesNewArtifactFunctional=True,
        newNativeBusinessQualifiedBeforeArm1=False,guardsPassed=True,strictCpuSchedulerRequired=True,noNewResources=True,
        prerequisiteReviewInputs={k:dict(bytes=100,sha256='1'*64) for k in ('unitCompletion','unitRootReview','independentSourceReview')})
    return v,r

def registration(r):
    return dict(arrivals=33792,rate=500,batchCap=4,archiveChunkBytes=6144,readWindow=8,
        eventFetchCount=p.selected_event_page(),commonEventFetchEnvelope=True,commonChunkEnvelope=False,
        commonReadWindowEnvelope=True,appointedLeader=0,sync=2,profileSha256=r['profileFingerprint'],codeSha256=r['codeFingerprint'],
        retentionIdleSelection=p.selection(),ownerPollSelection=p.expected_owner_selection(1000000),ports=42000,
        lineage='capacity-pilot-synthetic-schema-only',workloadPreset='long-cuts-33792-v1',expectedFullCommandCuts=11,
        expectedTrailingCommands=3,equivalentFullLoadCutNumbers=list(range(2,12)))

def summary():
    return dict(scheduledArrivals=33792,releasedArrivals=33792,ratePerSecond=500,batchCap=4,archiveChunkBytes=6144,
        readWindow=8,arrivalClockPausedForMaintenance=False,unknownFinal=0,unknownObserved=0,maintenanceCycles=12,
        schedulerTimingValid=True,schedulerLatenessOver20ms=0,confirmedAcceptedUniqueOrders=33792,notSent=0,serverRejected=0,
        duplicateOrOutOfRangeAcceptedOrderIds=0,completedLogicalReplies=33792)

def prior_gate(r):
    return dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION',collectionComplete=True,
        arm=p.ARM-1,eventFetchCount=p.EVENT_PAGE_ORDER[p.ARM-2],ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,
        frozenReleaseSha256=p.FROZEN_RELEASE_SHA,controllerSha256=r['controllerSha256'],codeFingerprint=r['codeFingerprint'],
        localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,allRawInputsAndFailuresRetained=True,
        strictSchedulerTimingAdmission=True,sameNewArtifactFunctionalQualified=True,allOriginalRawCanonicalAndThreeSnapshotsVerified=True,
        independentLocalCollectionReceiptSha256='b'*64,closedArchiveSha256='c'*64,closedNativeInventorySha256='d'*64,privatePushReceiptSha256='e'*64)

class EventDelta(unittest.TestCase):
    def tearDown(self):p.configure_arm(1);p.FROZEN_RELEASE_SHA=None;p.PRIOR_GATE_SHA=None

    def test_false_ready_and_unresolved_root_cannot_self_qualify(self):
        draft=json.loads((HERE/'release.template.json').read_text())
        with self.assertRaisesRegex(RuntimeError,'unfrozen draft'):p.validate_release(draft)
        draft.update(releaseReady=True,controllerSha256='f'*64)
        with self.assertRaisesRegex(RuntimeError,'pending prerequisite'):p.validate_release(draft)
        self.assertTrue(p.validate_release(fixture()))

    def test_fixed_four_manual_pages_and_owner_driver(self):
        for arm,page in enumerate((16,32,16,32),1):
            p.configure_arm(arm)
            self.assertEqual((p.selected_event_page(),p.selected_owner_park_ns(),p.selected_park_ns()),(page,1000000,100000))
            self.assertEqual(p.PAIR,p.PREP/('arm-%d/idle-arm'%arm))
        for n in (0,5,True,'1'):
            with self.subTest(n=n),self.assertRaises(RuntimeError):p.configure_arm(n)
        c=p.fixed_configuration();c['eventFetchCountOrder'][0]=32
        self.assertEqual(p.fixed_configuration()['eventFetchCountOrder'],[16,32,16,32])

    def test_exact_new_cli_parent_only_owner_and_unchanged_children(self):
        r=fixture()
        for arm in (1,2,3,4):
            p.configure_arm(arm);args=p.parent_argv(r)
            self.assertEqual(args[-3:],['event-fetch-page-long-cuts',str(p.selected_event_page()),'42000'])
            self.assertEqual([a for a in args if p.OWNER_PROPERTY in a],['-D'+p.OWNER_PROPERTY+'=1000000'])
            self.assertEqual([a for a in args if p.PROPERTY in a],['-D'+p.PROPERTY+'=100000'])
            for node in (0,1,2):
                child=p.node_argv(r,8,node,registration(r))
                self.assertFalse(any(p.OWNER_PROPERTY in a for a in child))
                self.assertEqual([a for a in child if p.PROPERTY in a],['-D'+p.PROPERTY+'=100000'])
                self.assertIn('-Daeron.cluster.appointed.leader.id=0',child)

    def test_selected_registration_refuses_other_page_or_missing_envelope(self):
        for arm in (1,2,3,4):
            p.configure_arm(arm);r=fixture();reg=registration(r);p.validate_registration(r,8,reg)
            for key,value in [('eventFetchCount',32 if p.selected_event_page()==16 else 16),('commonEventFetchEnvelope',False),
                ('ownerPollSelection',p.expected_owner_selection(100000)),('ports',42001),('sync',0)]:
                bad=copy.deepcopy(reg);bad[key]=value
                with self.subTest(arm=arm,key=key),self.assertRaises(RuntimeError):p.validate_registration(r,8,bad)

    def test_two_actual_plans_select_correct_rpc_bounds_same_storage_envelope(self):
        r=fixture();self.assertTrue(p.validate_common_plans(r))
        for arm in (1,2,3,4):
            p.configure_arm(arm);plan=p.selected_plan(r)
            self.assertEqual(plan['eventFetchCount'],p.selected_event_page())
            self.assertEqual(plan['selectedMaximumEventFetchRpcs'],4225 if arm%2 else 2113)
            self.assertEqual(plan['selectedMaximumLogicalMaintenanceRpcs'],7243 if arm%2 else 5131)
            self.assertEqual(p.allocation_limit(r)+p.GIB+p.MAX_ARCHIVE,2116076873)
        for key,value in [('maximumRawTraceBytes',3*p.GIB),('maximumAllocatedGrowthBytes',3*p.GIB),('maximumPhysicalOffersPerRpc',5),('selectedMaximumEventFetchRpcs',4225)]:
            bad=fixture();bad['derivedPlans']['32'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_common_plans(bad)

    def test_release_configuration_and_artifact_cannot_change_another_factor(self):
        for key,value in [('arrivals',6400),('ratePerSecond',1000),('readWindow',1),('batchCap',8),('archiveChunkBytes',3072),
            ('ownerPollMaximumParkNsOrder',[100000]*4),('serverDriverMaximumParkNs',1000000),('eventFetchCountOrder',[32]*4),
            ('commonEventFetchEnvelope',False),('cleanupEnabled',True)]:
            r=fixture();r['configuration'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)
        for key,value in [('sourceCommit','977197616ade0283174f2ea6ddfaa700547f6d15'),('codeFingerprint','0'*64),('ownerPollValidatorSha256','0'*64)]:
            r=fixture();r[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)
        r=fixture();r['artifacts'][r['classPath'][0]]['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_release(r)

    def test_actual_linux_new_schema_and_full_four_jars_pass(self):
        v,r=prerequisites();self.assertTrue(p.validate_linux_metadata(v['linuxMetadataObservation'],v['linuxMetadataReceipt'],r))

    def test_linux_pid_argv_helper_and_strict_exit_drift_rejected(self):
        v,r=prerequisites();o=v['linuxMetadataObservation'];receipt=v['linuxMetadataReceipt']
        for path,value in [(('observationSha256',),'0'*64),(('execution','ownedParentPid'),99),
            (('execution','strictOwnedPidAbsentAfterWait'),False),(('execution','processIdentityObservationGap'),True),
            (('execution','actualProcessIdentity','commandSha256'),'0'*64),(('execution','actualProcessIdentity','actualExecutable'),'/tmp/java')]:
            bad=copy.deepcopy(receipt);target=bad
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)
        for name in ('EventFetchDistributionObservation.java','classes/io/vectormatch/cluster/EventFetchDistributionObservation.class'):
            bad=copy.deepcopy(receipt);bad['stagedFiles'][name]['sha256']='0'*64
            with self.subTest(name=name),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)

    def test_linux_both_containers_plans_and_intent_scope_are_enforced(self):
        v,r=prerequisites();o=v['linuxMetadataObservation'];receipt=v['linuxMetadataReceipt']
        for key in ('ownerConstructed','driverConstructed','cliExecuted','nativeUdpOrBusinessSessionStarted','performanceEvidence'):
            bad=copy.deepcopy(o);bad[key]=True
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)
        bad=copy.deepcopy(o);bad['distributionJars']['agrona-2.6.1.jar']['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)
        bad=copy.deepcopy(o);bad['actualCodeSources'][0]['path']='/tmp/cluster.jar'
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)
        bad=copy.deepcopy(o);bad['plans']['32']['plan']['selectedMaximumEventFetchRpcs']=4225
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,receipt,r)

    def test_parser_exact_new_source_and_staged12_bodies_required(self):
        v,r=prerequisites();f=v['eventFetchRawParserFreeze'];self.assertTrue(p.validate_parser_freeze(f,r))
        for key,value in [('actualPureGuardMethods',33),('scope','OWNER_POLL_RAW_AUDIT_SOURCE_CLOSURE'),('defaultCpuSchedulerStrict',False),('runtimeOrPerformanceClaimed',True)]:
            bad=copy.deepcopy(f);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_parser_freeze(bad,r)
        original_digest=p.digest
        with mock.patch.object(p,'digest',side_effect=lambda path:'0'*64 if Path(path).name=='audit_raw.py' else original_digest(path)):
            with self.assertRaises(RuntimeError):p.validate_parser_freeze(f,r)

    def test_no_prior_native_success_is_invented_by_policy(self):
        r=fixture();q=p.qualification_policy();self.assertTrue(p.validate_qualification_policy(q,r))
        self.assertIs(q['newNativeBusinessQualifiedBeforeArm1'],False)
        self.assertNotIn('passed',q)
        for key,value in [('newNativeBusinessQualifiedBeforeArm1',True),('firstCloudEventFetchCount',32),
            ('continuationRequiresIndependentFullRawCanonicalThreeSnapshots',False),('continuationRequiresStrictScheduler',False),('configurationOnly',False)]:
            bad=copy.deepcopy(q);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_qualification_policy(bad,r)

    def test_root_review_requires_actual_source_unit_receipts_and_policy(self):
        v,r=prerequisites();self.assertTrue(p.validate_prerequisite_proofs(v,r))
        for key,value in [('scope','ROOT_REVIEWED_OWNER_POLL_CLOUD_PREREQUISITES'),('controllerSha256','0'*64),
            ('newNativeBusinessQualifiedBeforeArm1',True),('firstCloudArmQualifiesNewArtifactFunctional',False),('strictCpuSchedulerRequired',False)]:
            bad=copy.deepcopy(v);bad['rootEvidenceReview'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)
        for name in ('unitCompletion','unitRootReview','independentSourceReview'):
            bad=copy.deepcopy(v);del bad['rootEvidenceReview']['prerequisiteReviewInputs'][name]
            with self.subTest(name=name),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)
        bad=copy.deepcopy(v);bad['rootEvidenceReview']['proofBindings']['linuxMetadataReceipt']['sha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,r)

    def test_original_summary_strict_scheduler_unknown_and_order_gates_unchanged(self):
        self.assertTrue(p.validate_long_summary(summary(),8))
        for key,value in [('schedulerTimingValid',False),('schedulerLatenessOver20ms',1),('unknownObserved',1),('unknownFinal',1),('notSent',1),('serverRejected',1),('maintenanceCycles',3)]:
            bad=summary();bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_long_summary(bad,8)

    def test_all_six_runtime_selected_page_metadata_and_coordinator_agree(self):
        r=fixture()
        for arm in (1,2):
            p.configure_arm(arm);small=dict(eventFetchCount=p.selected_event_page(),commonEventFetchEnvelope=True)
            cfg=dict(small,readWindow=8,batchCap=4,archiveChunkBytes=6144)
            s=dict(cfg,maintenanceRpcMetrics=dict(eventFetchCount=p.selected_event_page()))
            args=[r,dict(small),cfg,s,copy.deepcopy(p.selected_plan(r)),dict(small),dict(small)]
            self.assertTrue(p.validate_selected_page_observations(*args))
            for index in range(1,7):
                bad=copy.deepcopy(args);bad[index]['eventFetchCount']=32 if p.selected_event_page()==16 else 16
                with self.subTest(arm=arm,index=index),self.assertRaises(RuntimeError):p.validate_selected_page_observations(*bad)
            bad=copy.deepcopy(args);bad[3]['maintenanceRpcMetrics']['eventFetchCount']=33
            with self.assertRaises(RuntimeError):p.validate_selected_page_observations(*bad)

    def test_prior_gate_requires_new_artifact_full_raw_canonical_snapshots_and_private_push(self):
        r=fixture();p.FROZEN_RELEASE_SHA='a'*64
        for arm in (2,3,4):
            p.configure_arm(arm);g=prior_gate(r);self.assertTrue(p.validate_prior_gate(g,r,arm-1))
            for key,value in [('scope','ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION'),('eventFetchCount',33),
                ('ownerPollMaximumParkNs',100000),('sameNewArtifactFunctionalQualified',False),
                ('allOriginalRawCanonicalAndThreeSnapshotsVerified',False),('strictSchedulerTimingAdmission',False),
                ('codeFingerprint','23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'),('privatePushReceiptSha256',None)]:
                bad=copy.deepcopy(g);bad[key]=value
                with self.subTest(arm=arm,key=key),self.assertRaises(RuntimeError):p.validate_prior_gate(bad,r,arm-1)

    def test_private_push_still_binds_complete_previous_archive(self):
        p.configure_arm(2);g=prior_gate(fixture())
        push=dict(schemaVersion=1,scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH',repository='yinli-systems/vectormatch',visibility='private',
            pushCompleted=True,remoteCommitVerified=True,commit='a'*40,fullOriginalEvidencePushed=True,evidenceManifestSha256='b'*64,
            closedArchiveSha256=g['closedArchiveSha256'],closedNativeInventorySha256=g['closedNativeInventorySha256'])
        self.assertTrue(p.validate_private_push(push,g))
        for key,value in [('fullOriginalEvidencePushed',False),('visibility','public'),('closedArchiveSha256','0'*64)]:
            bad=copy.deepcopy(push);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_private_push(bad,g)

    def test_no_implicit_start_invalid_next_gate_before_ownership_import(self):
        with mock.patch.object(p,'load_base',side_effect=AssertionError('Invalid gate must reject before ownership import')):
            for argv in (['--arm','2'],['--arm','3'],['--arm','4'],['--arm','1','--prior-collection-sha256','a'*64]):
                with self.subTest(argv=argv),self.assertRaises(RuntimeError):p.main(argv)
        with self.assertRaises(SystemExit):p.main(['--arm','1','--auto-next'])
        r=fixture();base=object()
        with mock.patch.object(p,'load_base',return_value=base),mock.patch.object(p,'runtime_manifest',return_value=r),mock.patch.object(p,'preflight',return_value={'noJavaStarted':True}) as pre,mock.patch.object(p,'execute',side_effect=AssertionError('No implicit execution')):
            p.main(['--arm','1','--release-sha256','a'*64]);pre.assert_called_once_with(base,r)

    def test_lineage_and_resource_lifecycle_caps_unchanged(self):
        p.configure_arm(4);reg=registration(fixture())
        with mock.patch.object(p,'json_bounded',return_value={'registration':dict(reg,lineage='prior-fixture')}) as read:
            self.assertTrue(p.validate_fresh_lineage(object(),reg));self.assertEqual(read.call_count,3)
        with mock.patch.object(p,'json_bounded',return_value={'registration':reg}),self.assertRaises(RuntimeError):p.validate_fresh_lineage(object(),reg)
        self.assertEqual((p.MAX_ARCHIVE,p.MAX_LOG,p.MAX_PATHS,p.MAX_LOGICAL),(256*1024**2,4*1024**2,8192,12*p.GIB))
        self.assertEqual((p.EXECUTE_SECONDS,p.TOTAL_SECONDS,p.METRIC_SAMPLE_CAP,p.METRIC_BYTES_CAP),(240,360,512,8*1024**2))

    def test_owned_process_pidfd_normal_stop_protection_and_budget_functions_unchanged(self):
        def functions(path):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        old=functions(HERE/'baseline/cpu_owner_poll_abab.py');new=functions(HERE/'cpu_event_fetch_abab.py')
        for name in ('Registry','owned_metrics','global_metrics','Telemetry','protected_state','allocated_scan','allocation_limit','strict_idle',
            'verify_archive_members','clean_all','validate_egress','validate_egress_progress','collect_stopped','monitor',
            'runtime_manifest','kernel_record_from_json','json_bounded','validate_long_summary','validate_private_push','node_argv'):
            self.assertEqual(old[name],new[name],name)
        self.assertEqual(p.BASE_SHA,'8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87')
        self.assertEqual(fixture()['protectedOriginalState']['manifestSha256'],'6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753')
        source=(HERE/'cpu_event_fetch_abab.py').read_text()
        for forbidden in ('shutil.rmtree','os.remove(','unlink(','--allow-invalid-scheduler','--auto-next'):
            self.assertNotIn(forbidden,source)

if __name__=='__main__':unittest.main()
