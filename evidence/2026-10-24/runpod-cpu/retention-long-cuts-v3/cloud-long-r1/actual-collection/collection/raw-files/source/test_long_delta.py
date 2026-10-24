"""Pure local schema/ownership-fencing deltas; never deploys, launches Java or selects fake codec witnesses."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import cpu_long_cuts as p

HERE=Path(__file__).resolve().parent

def fixture():
    # Plan and artifact rows are exact copied actual local installed-JAR metadata.
    # Placeholder proof hashes below are explicitly schema fixtures, never a runnable release.
    r=json.loads((HERE/'release.template.json').read_text())
    r.update(releaseReady=True,javaExecutableSha256='d'*64,jdkReleaseSha256='e'*64,controllerSha256='f'*64)
    for row in r['evidenceReferences'].values():row.update(bytes=128,sha256='a'*64)
    for key,row in p.PREREQUISITE_PINS.items():r['evidenceReferences'][key].update(row)
    return r

def summary():
    return dict(scheduledArrivals=33792,releasedArrivals=33792,ratePerSecond=500,batchCap=4,archiveChunkBytes=6144,readWindow=8,
        arrivalClockPausedForMaintenance=False,unknownFinal=0,unknownObserved=0,maintenanceCycles=12,
        schedulerTimingValid=True,schedulerLatenessOver20ms=0,confirmedAcceptedUniqueOrders=33792,notSent=0,
        serverRejected=0,duplicateOrOutOfRangeAcceptedOrderIds=0,completedLogicalReplies=33792)

def linux_fixture(release):
    """Schema fixture only: exact actual codec/JAR rows, synthetic PID and kernel identity for pure guards."""
    root='/opt/vectormatch-cpu/preparation/cpu-long-cuts-release-metadata-r1'
    observation=json.loads((HERE/'fixtures/actual-distribution-observation.json').read_text())
    for row in observation['actualCodeSources']:row['path']=root+'/lib/'+Path(row['path']).name
    rows=json.loads((HERE/'metadata-preparation/metadata-config.json').read_text())['rows']
    command=[release['java'],'-Xmx128m','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',root+'/classes:'+':'.join(root+'/lib/'+Path(x).name for x in release['classPath']),'io.vectormatch.cluster.LongCutsDistributionObservation',root+'/results/actual-distribution-observation.json']
    identity=dict(pid=123,startTicks=456,actualExecutable=release['java'],commandSha256=hashlib.sha256(b'\0'.join(x.encode() for x in command)+b'\0').hexdigest())
    registration=dict(hostname=p.HOST,command=command,javaExecutable=release['java'],actualJavaExecutable=release['java'],javaExecutableSha256=release['javaExecutableSha256'],jdkReleaseSha256=release['jdkReleaseSha256'],inputInventory=rows)
    execution=dict(ownedParentPid=123,actualProcessIdentity=identity,processIdentityObservationGap=False,exitCode=0,timedOut=False,metadataJvmExited=True,allInputsUnchanged=True,javaExecutableSha256After=release['javaExecutableSha256'],jdkReleaseSha256After=release['jdkReleaseSha256'])
    return observation,dict(passed=True,root=root,observationSha256=release['evidenceReferences']['linuxMetadataObservation']['sha256'],registration=registration,execution=execution,stagedFiles=rows)

def prerequisites():
    release=fixture();values={key:json.loads((HERE/'fixtures'/name).read_text()) for key,name in {
        'longRawAudit':'LOCAL_FUNCTIONAL_AUDIT_COMPLETE.json','longRawParserFreeze':'LONG_PARSER_SOURCE_FROZEN.json',
        'linuxMetadataObservation':'actual-linux-distribution-observation.json','linuxMetadataReceipt':'actual-linux-metadata-receipt.json'}.items()}
    release['javaExecutableSha256']=values['linuxMetadataReceipt']['registration']['javaExecutableSha256']
    release['jdkReleaseSha256']=values['linuxMetadataReceipt']['registration']['jdkReleaseSha256']
    # Explicit root-attestation schema fixture only; root creates the actual receipt after final source freeze.
    values['rootEvidenceReview']=dict(scope='ROOT_REVIEWED_LONG_NATIVE_CLOUD_PREREQUISITES',passed=True,
        sourceCommit=release['sourceCommit'],codeFingerprint=release['codeFingerprint'],profileFingerprint=release['profileFingerprint'],controllerSha256=release['controllerSha256'],
        sourceReviewSha256='a9561e676b19892a58590b16fc51b6e63962261aede70858fa0d48b0d8bd23db',
        nativeReviewSha256='55b3bf21ea23dca8a34bb7a1c2baaf7235cce2ddbf6ec38100fe5a0edc0dd49d',
        proofBindings=copy.deepcopy(p.PREREQUISITE_PINS),guardsPassed=True,strictCpuSchedulerRequired=True,noNewResources=True)
    return values,release

class LongDelta(unittest.TestCase):
    def tearDown(self):p.configure_arm(1)

    def test_draft_and_missing_proof_refs_cannot_become_ready(self):
        r=json.loads((HERE/'release.template.json').read_text())
        with self.assertRaisesRegex(RuntimeError,'unfrozen draft'):p.validate_release(r)
        r.update(releaseReady=True,javaExecutableSha256='d'*64,jdkReleaseSha256='e'*64,controllerSha256='f'*64)
        with self.assertRaisesRegex(RuntimeError,'pending prerequisite'):p.validate_release(r)
        r=fixture();self.assertIs(p.validate_release(r),r)

    def test_only_single_manual_arm_and_no_prior_gate_cli(self):
        p.configure_arm(1);self.assertEqual(p.PAIR,p.PREP/'arm-1/idle-arm');self.assertEqual(p.selected_park_ns(),100000)
        for n in [0,2,3,4,True,'1']:
            with self.subTest(n=n),self.assertRaises(RuntimeError):p.configure_arm(n)
        with mock.patch.object(p,'load_base',side_effect=AssertionError('No base must load for invalid CLI')):
            for args in [['--arm','2'],['--arm','1','--prior-collection-sha256','a'*64],['--arm','1','--allow-invalid-scheduler']]:
                with self.subTest(args=args),self.assertRaises(SystemExit):p.main(args)

    def test_actual_long_plan_fixture_is_copied_from_installed_distribution(self):
        r=fixture();actual=json.loads((HERE/'fixtures/actual-distribution-observation.json').read_text())
        self.assertEqual(r['derivedPlan'],actual['workloads']['LONG_CUTS']['plan']);self.assertEqual(r['codeFingerprint'],actual['actualCodeFingerprint'])
        self.assertEqual(r['derivedPlan']['maximumLogicalMaintenanceRpcs'],7243)
        self.assertEqual(r['derivedPlan']['maximumJournalRecords'],96);self.assertEqual(r['derivedPlan']['maximumJournalBytes'],117792)
        self.assertEqual(r['derivedPlan']['maximumRawTraceBytes'],185514924);self.assertEqual(r['derivedPlan']['maximumAllocatedGrowthBytes'],757122377)

    def test_short_or_changed_code_profile_and_budget_fail_before_launch(self):
        actual=json.loads((HERE/'fixtures/actual-distribution-observation.json').read_text())
        mutations=[('sourceCommit','7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23'),('codeFingerprint','0'*64),('profileFingerprint','0'*64),('profileId','different-profile'),('derivedPlan',actual['workloads']['SHORT']['plan'])]
        for key,value in mutations:
            r=fixture();r[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)
        for key,value in [('maximumPhysicalOffersPerRpc',5),('maximumMaintenanceCycles',11),('maximumJournalRecords',1024),('maximumRawTraceBytes',3*p.GIB),('maximumAllocatedGrowthBytes',3*p.GIB)]:
            r=fixture();r['derivedPlan'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)

    def test_parent_and_all_node_argv_forward_one_actual_idle_property(self):
        r=fixture();args=p.parent_argv(r)
        self.assertEqual(args[-3:],[str(p.PAIR),'idle-window8-long-cuts','42000'])
        self.assertEqual(args[1],'-Dvectormatch.retention.idleMaxParkNs=100000')
        for n in range(3):
            argv=p.node_argv(r,8,n,dict(ports=42000,lineage='capacity-pilot-fixture'))
            self.assertEqual(argv[1],args[1]);self.assertEqual(sum(p.PROPERTY in x for x in argv),1)
            self.assertIn('-Daeron.cluster.appointed.leader.id=0',argv);self.assertIn('2',argv)
        self.assertEqual(r['configuration']['ownerLoopMaximumParkNsUnchanged'],1000000)
        self.assertEqual(r['configuration']['exposureNs'],67584000000)
        self.assertEqual(r['configuration']['equivalentFullLoadCutNumbers'],list(range(2,12)))

    def test_configuration_cannot_turn_into_duration_rate_or_idle_experiment(self):
        for key,value in [('arrivals',30720),('ratePerSecond',1000),('exposureNs',61440000000),('maximumRequestedParkNs',1000000),('readWindow',1),('fixedBasePorts',42001),('sync',0)]:
            r=fixture();r['configuration'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)

    def test_registration_requires_actual_long_preset_and_exact_cut_declaration(self):
        r=fixture();reg=dict(arrivals=33792,rate=500,batchCap=4,archiveChunkBytes=6144,readWindow=8,eventFetchCount=16,
            commonChunkEnvelope=False,commonReadWindowEnvelope=True,appointedLeader=0,sync=2,profileSha256=r['profileFingerprint'],codeSha256=r['codeFingerprint'],retentionIdleSelection=p.selection(),ports=42000,lineage='capacity-pilot-fixture',workloadPreset='long-cuts-33792-v1',expectedFullCommandCuts=11,expectedTrailingCommands=3,equivalentFullLoadCutNumbers=list(range(2,12)))
        p.validate_registration(r,8,reg)
        for key,value in [('workloadPreset','short'),('expectedFullCommandCuts',10),('expectedTrailingCommands',0),('equivalentFullLoadCutNumbers',list(range(1,11))),('ports',42001),('arrivals',6400)]:
            bad=copy.deepcopy(reg);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_registration(r,8,bad)

    def test_cpu_summary_has_no_local_diagnostic_scheduler_bypass(self):
        self.assertTrue(p.validate_long_summary(summary(),8))
        for key,value in [('schedulerTimingValid',False),('schedulerLatenessOver20ms',26),('unknownObserved',1),('unknownFinal',1),('notSent',1),('serverRejected',1),('completedLogicalReplies',33791),('maintenanceCycles',3)]:
            bad=summary();bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_long_summary(bad,8)

    def test_original_state_is_exact_previous57_and_pg989_manifest_not_new_baseline(self):
        r=fixture();self.assertEqual(r['protectedOriginalState']['manifestSha256'],'6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753')
        r['protectedOriginalState']['manifestSha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_release(r)

    def test_proof_paths_sizes_and_hashes_are_closed_before_ready(self):
        for key in fixture()['evidenceReferences']:
            for field,value in [('path','/tmp/unbound.json'),('bytes',None),('bytes',2*1024**2),('sha256',None),('sha256','x'*64)]:
                r=fixture();r['evidenceReferences'][key][field]=value
                with self.subTest(key=key,field=field,value=value),self.assertRaises(RuntimeError):p.validate_release(r)

    def test_pid_start_and_full_argv_ownership_contract_is_retained(self):
        args=['/java','-cp','x','Node','0'];sha=hashlib.sha256(b'\0'.join(x.encode() for x in args)+b'\0').hexdigest()
        class Base:
            @staticmethod
            def argv_digest(argv):return hashlib.sha256(b'\0'.join(x.encode() for x in argv)+b'\0').hexdigest()
        row=dict(command=args[0],arguments=args[1:],pid=123,linuxStartTicks=456,linuxCommandSha256=sha)
        result=p.kernel_record_from_json(Base,row,args);self.assertEqual(result['startTicks'],456)
        for key,value in [('linuxStartTicks',0),('linuxCommandSha256','0'*64),('arguments',args[1:]+['wrong'])]:
            bad=copy.deepcopy(row);bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.kernel_record_from_json(Base,bad,args)

    def test_reviewed_ownership_telemetry_transport_and_archive_bodies_unchanged(self):
        old=ast.parse((HERE/'baseline/cpu_idle_abab.py').read_text());new=ast.parse((HERE/'cpu_long_cuts.py').read_text())
        a={n.name:ast.dump(n,include_attributes=False) for n in old.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        b={n.name:ast.dump(n,include_attributes=False) for n in new.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        for name in ['Registry','owned_metrics','global_metrics','Telemetry','protected_state','allocated_scan','allocation_limit','strict_idle','verify_archive_members','clean_all','validate_egress','validate_egress_progress','collect_stopped']:
            self.assertEqual(a[name],b[name],name)
        self.assertNotIn('verify_prior_arm_gate',b);self.assertNotIn('validate_prior_gate',b)

    def test_finite_monitor_archive_and_execution_limits_are_unchanged(self):
        self.assertEqual((p.EXECUTE_SECONDS,p.TOTAL_SECONDS,p.METRIC_SAMPLE_CAP,p.METRIC_BYTES_CAP),(240,360,512,8*1024**2))
        self.assertEqual((p.MAX_ARCHIVE,p.MAX_LOG,p.MAX_PATHS,p.MAX_LOGICAL),(256*1024**2,4*1024**2,8192,12*p.GIB))
        self.assertEqual(p.allocation_limit(fixture()),757122377+16*1024**2)
        self.assertLess(67.584+90,p.EXECUTE_SECONDS)

    def test_linux_proofs_require_observed_exact_pid_start_argv_and_closed_jvm(self):
        r=fixture();o,proof=linux_fixture(r);self.assertTrue(p.validate_linux_metadata(o,proof,r))
        for key,value in [('processIdentityObservationGap',True),('actualProcessIdentity',None),('metadataJvmExited',False),('allInputsUnchanged',False),('timedOut',True),('exitCode',1)]:
            bad=copy.deepcopy(proof);bad['execution'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)
        bad=copy.deepcopy(proof);del bad['execution']['processIdentityObservationGap']
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)
        for key,value in [('pid',0),('startTicks',0),('actualExecutable','/usr/bin/java'),('commandSha256','0'*64)]:
            bad=copy.deepcopy(proof);bad['execution']['actualProcessIdentity'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)
        bad=copy.deepcopy(proof);bad['execution']['ownedParentPid']=999
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)
        bad=copy.deepcopy(proof);bad['observationSha256']='0'*64
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)

    def test_linux_proofs_reject_different_jdk_plan_classpath_or_compiled_helper(self):
        r=fixture();o,proof=linux_fixture(r)
        for key,value in [('javaExecutableSha256After','0'*64),('jdkReleaseSha256After','0'*64)]:
            bad=copy.deepcopy(proof);bad['execution'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)
        bad=copy.deepcopy(o);bad['workloads']['LONG_CUTS']['plan']['maximumRawTraceBytes']+=1
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,proof,r)
        bad=copy.deepcopy(o);bad['actualCodeSources'][-1]['path']=bad['actualCodeSources'][-1]['path'].replace('aeron-all-1.53.3.jar','agrona-2.6.1.jar')
        with self.assertRaises(RuntimeError):p.validate_linux_metadata(bad,proof,r)
        for name in ['LongCutsDistributionObservation.java','classes/io/vectormatch/cluster/LongCutsDistributionObservation.class','lib/cluster-0.1.0-SNAPSHOT.jar']:
            bad=copy.deepcopy(proof);bad['stagedFiles'][name]['sha256']='0'*64
            with self.subTest(name=name),self.assertRaises(RuntimeError):p.validate_linux_metadata(o,bad,r)

    def test_all_five_prerequisites_are_semantically_consumed(self):
        values,release=prerequisites();self.assertTrue(p.validate_prerequisite_proofs(values,release))
        for key in values:
            bad=copy.deepcopy(values);bad[key]={}
            with self.subTest(key=key),self.assertRaises((RuntimeError,KeyError)):p.validate_prerequisite_proofs(bad,release)

    def test_local_qualification_cannot_become_failed_wrong_result_or_cpu_timing_proof(self):
        values,release=prerequisites()
        for key,value in [('readOnlyAuditPassed',False),('scope','CPU_PERFORMANCE_PASS'),('sourceCommit','0'*40),('actualCodeFingerprint','0'*64),('schedulerTimingValid',True),('schedulerLatenessOver20ms',0),('localFunctionalOnly',False),('noCapacityClaim',False),('futureCpuSchedulerGateDefaultStrict',False),('readPhases',8),('consumedInputFiles',79)]:
            bad=copy.deepcopy(values);bad['longRawAudit'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,release)
        for key in ['fullResult','parserFreeze']:
            bad=copy.deepcopy(values);bad['longRawAudit'][key]['sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,release)

    def test_parser_must_bind_exact_closed_source_and_strict_future_default(self):
        values,release=prerequisites()
        for key,value in [('guardTests',31),('defaultImportedSchedulerAdmissionStrict',False),('localFunctionalDiagnosticOptInIsExplicitRunnerOnly',False),('firstFailedAuditPreserved',False),('actualCodeFingerprintUnderAudit','0'*64)]:
            bad=copy.deepcopy(values);bad['longRawParserFreeze'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,release)
        bad=copy.deepcopy(values);del bad['longRawParserFreeze']['sourceFiles']['source/workload_contract.py']
        with self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,release)

    def test_root_review_must_crossbind_every_other_proof_and_final_controller(self):
        values,release=prerequisites()
        for key,value in [('passed',False),('scope','OLD_IDLE_RELEASE'),('controllerSha256','0'*64),('nativeReviewSha256','0'*64),('sourceReviewSha256','0'*64),('strictCpuSchedulerRequired',False),('guardsPassed',False),('noNewResources',False)]:
            bad=copy.deepcopy(values);bad['rootEvidenceReview'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,release)
        for key in p.PREREQUISITE_PINS:
            bad=copy.deepcopy(values);bad['rootEvidenceReview']['proofBindings'][key]['sha256']='0'*64
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prerequisite_proofs(bad,release)

if __name__=='__main__':unittest.main()
