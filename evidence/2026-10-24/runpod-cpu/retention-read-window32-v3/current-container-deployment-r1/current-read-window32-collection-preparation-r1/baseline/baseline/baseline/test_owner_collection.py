"""Pure synthetic adapter guards. No actual stage/raw/network/JVM; fixtures never authorize execution."""
import copy,json,os,shutil,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as c
import cpu_owner_poll_abab as controller
import build_config
import collect_and_audit as runner
import closed_bindings as bindings
import frozen_parser
import audit_raw
import audit_native_artifacts as native
import owner_bundle
import finalize_local_collection as finalize

def write(p,v):p.write_text(json.dumps(v));return c.sha(p)

def release_fixture():
    r=json.loads((HERE/'fixtures/release.template.json').read_text());r.update(releaseReady=True,controllerSha256=c.sha(HERE/'cpu_owner_poll_abab.py'))
    for k,row in r['evidenceReferences'].items():
        if k not in controller.PREREQUISITE_PINS:row.update(bytes=128,sha256='a'*64)
    return r

def prior_fixture(n,release_sha,release):
    push=dict(schemaVersion=1,scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH',repository='yinli-systems/vectormatch',visibility='private',
        pushCompleted=True,remoteCommitVerified=True,commit='d'*40,fullOriginalEvidencePushed=True,evidenceManifestSha256='e'*64,
        closedArchiveSha256='b'*64,closedNativeInventorySha256='c'*64)
    gate=dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION',collectionComplete=True,arm=n,
        ownerPollMaximumParkNs=controller.OWNER_PARK_ORDER[n-1],serverDriverMaximumParkNs=100000,
        frozenReleaseSha256=release_sha,controllerSha256=release['controllerSha256'],codeFingerprint=release['codeFingerprint'],
        localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,allRawInputsAndFailuresRetained=True,strictSchedulerTimingAdmission=True,
        independentLocalCollectionReceiptSha256='f'*64,closedArchiveSha256='b'*64,closedNativeInventorySha256='c'*64)
    return gate,push

class Guards(unittest.TestCase):
    def config(self,root,arm):
        root=Path(root).resolve();protected=root/'protected.json';write(protected,{})
        r=release_fixture();r['protectedOriginalState']['manifestSha256']=c.sha(protected)
        rp=root/'release.json';rh=write(rp,r)
        author=json.loads((HERE/'controller-preparation-frozen.json').read_text())['files'];rows=copy.deepcopy(author)
        rows['LOCAL_PREPARATION_FROZEN.json']={'bytes':(HERE/'controller-preparation-frozen.json').stat().st_size,'sha256':c.sha(HERE/'controller-preparation-frozen.json')}
        rows['release/release.json']={'bytes':rp.stat().st_size,'sha256':rh}
        rows['release/current-stopped-original-state.json']={'bytes':protected.stat().st_size,'sha256':c.sha(protected)}
        rows.update({'release/lib/'+Path(k).name:copy.deepcopy(v)for k,v in r['artifacts'].items()})
        rows.update({'release/proofs/'+k+'.json':{x:v[x]for x in('bytes','sha256')}for k,v in r['evidenceReferences'].items()})
        self.assertEqual(39,len(rows));stage=root/'stage.json'
        write(stage,dict(passed=True,stagedFiles=rows,releaseSha256=rh,controllerSha256=r['controllerSha256'],applicationStarted=False,resourceCreated=False))
        gates={}
        for n in range(1,arm):
            gate,push=prior_fixture(n,rh,r);pp=root/('push%d.json'%n);ph=write(pp,push);gate['privatePushReceiptSha256']=ph
            gp=root/('gate%d.json'%n);gh=write(gp,gate);gates[str(n)]=dict(local=str(gp),sha256=gh,privatePushLocal=str(pp),privatePushSha256=ph)
        value=dict(schemaVersion=4,experiment='retention-owner-poll-long-v1',workloadPreset='long-cuts-33792-v1',arm=arm,
            maximumParkNs=100000,serverDriverMaximumParkNs=100000,ownerPollMaximumParkNs=controller.OWNER_PARK_ORDER[arm-1],
            remotePrep=str(controller.PREP),host='ed6c0673f5cb',releaseLocal=str(rp),releaseSha256=rh,stagingReceipt=str(stage),stagingReceiptSha256=c.sha(stage),
            protectedReference=str(protected),protectedReferenceSha256=c.sha(protected),priorGates=gates,
            executionMetadata=['arm-%d-execution-register.json'%arm,'arm-%d-execution.stdout'%arm,'arm-%d-execution.stderr'%arm])
        path=root/'config.json';write(path,value);return path,value,stage,r
    def load(self,p):
        # Schema fixtures use synthetic protected bytes. Production release validation remains mandatory, separately checked below.
        with patch.object(controller,'validate_release',side_effect=lambda r:r):return c.load_config(p)
    def test_real_release_validator_same_new_artifact_and_draft_denied(self):
        r=release_fixture();self.assertIs(controller.validate_release(r),r)
        for key,v in [('releaseReady',False),('sourceCommit','bcf49c10b77a14708b53d3fc6c115a6a3b834408'),('codeFingerprint','0'*64)]:
            x=copy.deepcopy(r);x[key]=v
            with self.subTest(key=key),self.assertRaises(RuntimeError):controller.validate_release(x)
    def test_four_manual_arm_schemas_exact39_plus_prefix_pairs_plus3(self):
        for arm in(1,2,3,4):
            with self.subTest(arm=arm),tempfile.TemporaryDirectory()as t:
                p,x,s,r=self.config(t,arm);actual,_,rows,allow=self.load(p)
                self.assertEqual(39+2*(arm-1),len(rows));self.assertEqual(len(rows)+3,len(allow));self.assertEqual(arm,actual['arm'])
                self.assertEqual(controller.OWNER_PARK_ORDER[arm-1],actual['ownerPollMaximumParkNs'])
    def test_wrong_cap_driver_arm_metadata_or_missing_prefix_denied(self):
        with tempfile.TemporaryDirectory()as t:
            p,x,s,r=self.config(t,2)
            for key,v in [('arm',0),('arm',True),('ownerPollMaximumParkNs',1000000),('serverDriverMaximumParkNs',1000000),
                ('maximumParkNs',1000000),('priorGates',{}),('workloadPreset','short'),('executionMetadata',['arm-1-execution-register.json'])]:
                y=copy.deepcopy(x);y[key]=v;write(p,y)
                with self.subTest(key=key),self.assertRaises((AssertionError,KeyError)):self.load(p)
    def test_prior_gate_cannot_relabel_wrong_owner_or_unpushed_archive(self):
        with tempfile.TemporaryDirectory()as t:
            p,x,s,r=self.config(t,2);row=x['priorGates']['1'];gp=Path(row['local']);orig=json.loads(gp.read_text())
            for key,v in [('ownerPollMaximumParkNs',100000),('strictSchedulerTimingAdmission',False),('codeFingerprint','0'*64),('privatePushReceiptSha256','0'*64)]:
                y=copy.deepcopy(orig);y[key]=v;row['sha256']=write(gp,y);write(p,x)
                with self.subTest(key=key),self.assertRaises((AssertionError,RuntimeError)):self.load(p)
            row['sha256']=write(gp,orig);pp=Path(row['privatePushLocal']);push=json.loads(pp.read_text());push['remoteCommitVerified']=False
            row['privatePushSha256']=write(pp,push);orig['privatePushReceiptSha256']=row['privatePushSha256'];row['sha256']=write(gp,orig);write(p,x)
            with self.assertRaises(RuntimeError):self.load(p)
    def test_staged_names_or_unique_validator_mutation_denied(self):
        with tempfile.TemporaryDirectory()as t:
            p,x,s,r=self.config(t,1);original=json.loads(s.read_text())
            for kind in('missing','substitute','ownerhash','controllerhash'):
                y=copy.deepcopy(original)
                if kind=='missing':y['stagedFiles'].pop('owner_poll_attestation.py')
                elif kind=='substitute':y['stagedFiles']['unrelated.py']=y['stagedFiles'].pop('PLAN.md')
                else:y['stagedFiles']['owner_poll_attestation.py'if kind=='ownerhash'else'cpu_owner_poll_abab.py']['sha256']='0'*64
                x['stagingReceiptSha256']=write(s,y);write(p,x)
                with self.subTest(kind=kind),self.assertRaises(AssertionError):self.load(p)
    def test_builder_create_new_and_explicit_prefix_pairs(self):
        with tempfile.TemporaryDirectory()as t:
            root=Path(t).resolve();p,x,s,r=self.config(root,1);out=root/'new-config'
            with patch.object(controller,'validate_release',side_effect=lambda r:r):
                result=build_config.build(1,Path(x['releaseLocal']),x['releaseSha256'],s,x['stagingReceiptSha256'],Path(x['protectedReference']),x['protectedReferenceSha256'],{},x['executionMetadata'],out)
                self.assertTrue(result.is_file())
                with self.assertRaises(AssertionError):build_config.build(1,Path(x['releaseLocal']),x['releaseSha256'],s,x['stagingReceiptSha256'],Path(x['protectedReference']),x['protectedReferenceSha256'],{},x['executionMetadata'],out)
    def test_owner_wrapper_uses_same_validator_all_actual_evidence_and_exact_argv(self):
        for arm in(1,2,3,4):
            controller.configure_arm(arm);r=release_fixture();root=controller.PAIR
            ids={'pilot-parent':{'pid':100,'arguments':controller.parent_argv(r)}}
            reg={'lineage':'capacity-pilot-synthetic','ports':42000}
            ids.update({'window-8-node-'+str(n):{'pid':101+n,'arguments':controller.node_argv(r,8,n,reg)}for n in(0,1,2)})
            values={'registration.json':reg,'configuration.json':{'synthetic':'configuration'},'load-result.json':{'physicalOfferTape':{'lastActualTransportObservation':{'retentionIdlePolicy':{'last':'actual'}}}},
                'transport-observations.json':[{'retentionIdlePolicy':{'sample':'actual'}}],'owner-before-close.json':{'alive':True},'owner-after-close.json':{'alive':False}}
            for n in(0,1,2):values['node-'+str(n)]={'node':n}
            seen=[]
            def read(path):
                seen.append(str(path));return values['node-'+path.parts[-3].split('-')[-1]]if path.name=='idle-000.actual.json'else values[path.name]
            with patch.object(owner_bundle,'validate_owner_bundle',return_value={'passed':True})as sole:
                result=owner_bundle.verify(dict(arm=arm,serverDriverMaximumParkNs=100000,ownerPollMaximumParkNs=controller.OWNER_PARK_ORDER[arm-1]),r,root,read,ids)
                self.assertTrue(result['passed']);kw=sole.call_args.kwargs
                self.assertEqual(ids['pilot-parent']['arguments'],kw['expected_parent_arguments']);self.assertEqual(3,len(kw['node_idle_actuals']))
                self.assertEqual([{'sample':'actual'},{'last':'actual'}],kw['parent_idle_actuals']);self.assertIn(str(root/'load/owner-after-close.json'),seen)
                self.assertEqual(controller.OWNER_PARK_ORDER[arm-1],kw['expected_owner_cap'])
    def test_owner_wrapper_wrong_arm_cap_never_calls_validator(self):
        with patch.object(owner_bundle,'validate_owner_bundle')as sole:
            with self.assertRaises(AssertionError):owner_bundle.verify(dict(arm=2,serverDriverMaximumParkNs=100000,ownerPollMaximumParkNs=1000000),release_fixture(),Path('/synthetic'),lambda p:{},{})
            sole.assert_not_called()
    def test_strict_parser_default_unchanged_and_alias_restored(self):
        before=sys.modules['common'];m=frozen_parser.load();self.assertIs(sys.modules['common'],before)
        self.assertIs(m['audit_raw'].audit_arm.__kwdefaults__['local_functional_only'],False);self.assertEqual(33792,m['workload_contract'].LONG.arrivals)
        calls=[];fake=types.SimpleNamespace(audit_arm=lambda *a,**k:calls.append((a,k))or{'passed':True});audit_raw.strict_arm(fake,'long','arm')
        self.assertEqual([((8,'arm'),{'workload':'long'})],calls)
    def test_parser_byte_change_refused_and_alias_restored(self):
        old=sys.modules['common']
        with tempfile.TemporaryDirectory()as t:
            root=Path(t)/'parser';shutil.copytree(HERE/'long_parser',root);p=root/'source/audit_raw.py';p.write_bytes(p.read_bytes()+b'\n# forbidden\n')
            with self.assertRaises(AssertionError):frozen_parser.load(root)
        self.assertIs(sys.modules['common'],old)
    def test_exact_tapes_over32m_and_overbudget_diagnostics(self):
        plan={'maximumRawTraceBytes':185514924};self.assertTrue(bindings.materialize('job/idle-arm/load/physical-replies.bin',35578188,plan));self.assertFalse(bindings.materialize('job/unrelated.bin',35578188,plan))
        rows={name:{'bytes':60000000}for name in bindings.TAPES};v=bindings.validate_tape_budget(rows,plan);self.assertFalse(v['passed']);self.assertIn('retain complete outer/nested TAR',v['failurePolicy'])
        self.assertTrue(all(not bindings.materialize(k,v['bytes'],plan,allow_tapes=False)for k,v in rows.items()))
    def test_owner_finalizer_cannot_accept_intent_only_timing_invalid_or_drift(self):
        owner=dict(passed=True,ownerPollMaximumParkNs=100000,serverDriverMaximumParkNs=100000,selectionIntentAndConstructedOwnerSnapshotReconciled=True,
            exactRegisteredParentAndThreeNodeArgumentsVerified=True,ownerPropertyParentOnly=True,actualConfiguredIdleFactoryCreations=22)
        v={'nativeResult':{'sourceCommit':'source','frozenCodeFingerprintIndependentlyRecomputed':'code','ownerPollAttestation':copy.deepcopy(owner)},
            'rawResult':{'sourceCommit':'source','strictSchedulerTimingAdmission':True,'localFunctionalDiagnosticOptIn':False,'ownerPollAttestation':copy.deepcopy(owner)},'collectionReceipt':{'rawTapeMaterializationBudget':{'passed':True}}}
        finalize.strict_long_reports(v,'source','code',100000)
        for path,key,value in [('rawResult','strictSchedulerTimingAdmission',False),('rawResult','localFunctionalDiagnosticOptIn',True),('nativeResult','ownerPollAttestation',{}),('nativeResult','sourceCommit','old')]:
            x=copy.deepcopy(v);x[path][key]=value
            with self.subTest(key=key),self.assertRaises((AssertionError,KeyError)):finalize.strict_long_reports(x,'source','code',100000)
        with self.assertRaises(AssertionError):finalize.strict_long_reports(v,'source','code',1000000)
    def test_native_audit_entry_dispatches_to_actual_controller_before_io(self):
        class DispatchReached(Exception):pass
        def configure(arm):
            self.assertEqual(arm,1);raise DispatchReached()
        with patch.object(native,'controller',types.SimpleNamespace(configure_arm=configure)):
            with self.assertRaises(DispatchReached):native.audit(object(),{'arm':1},{})
    def test_driver_report_preserves_historical_scope_without_repeating_it_as_current(self):
        report={'passed':True,'scope':'owner loop remains unchanged at up to1ms','actualFactoryCreations':22}
        result=native.driver_only_idle_report(report)
        self.assertEqual(report['scope'],result['historicalValidatorScope']);self.assertEqual(22,result['actualFactoryCreations'])
        self.assertEqual('owner loop remains unchanged at up to1ms',report['scope'])
        self.assertIn('MediaDriver strategies only',result['scope']);self.assertNotIn('1ms',result['scope'])
    def test_closed_receipt_rejects_other_valid_hex_source_not_only_malformed_sha(self):
        with tempfile.TemporaryDirectory()as t:
            path=Path(t).resolve()/'closed.json';cfg=dict(arm=1,ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,releaseSha256='a'*64,remotePrep=str(controller.PREP));release=dict(controllerSha256='b'*64)
            receipt=dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_CONTROLLER',rootVerified=True,arm=1,ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,
                frozenReleaseSha256='a'*64,controllerSha256='b'*64,job=str(controller.PREP)+'/arm-1',controllerIdentityGone=True,allOwnedStopped=True,inspectionSha256='c'*64,executedSourceSha256=runner.CLOSE_SOURCE_SHA)
            write(path,receipt);self.assertIsNotNone(runner.closed_proof(path,c.sha(path),cfg,release))
            for wrong in ('f'*64,'d'*64,'852546a1525b015df1baf38bb43d16e6ab68d2717fb57be648775de7bae0f51f'):
                bad=dict(receipt,executedSourceSha256=wrong);write(path,bad)
                with self.subTest(wrong=wrong),self.assertRaises(AssertionError):runner.closed_proof(path,c.sha(path),cfg,release)
    def test_closed_receipt_exact_owner_driver_scope_and_source(self):
        with tempfile.TemporaryDirectory()as t:
            p=Path(t).resolve()/'closed.json';cfg=dict(arm=2,ownerPollMaximumParkNs=100000,serverDriverMaximumParkNs=100000,releaseSha256='a'*64,remotePrep=str(controller.PREP));release=dict(controllerSha256='b'*64)
            x=dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_CONTROLLER',rootVerified=True,arm=2,ownerPollMaximumParkNs=100000,serverDriverMaximumParkNs=100000,
                frozenReleaseSha256='a'*64,controllerSha256='b'*64,job=str(controller.PREP)+'/arm-2',controllerIdentityGone=True,allOwnedStopped=True,inspectionSha256='c'*64,executedSourceSha256=runner.CLOSE_SOURCE_SHA)
            write(p,x);runner.closed_proof(p,c.sha(p),cfg,release)
            for key,value in [('scope','ROOT_VERIFIED_CLOSED_CPU_LONG_CUTS_CONTROLLER'),('ownerPollMaximumParkNs',1000000),('serverDriverMaximumParkNs',1000000),('allOwnedStopped',False),('controllerIdentityGone',False),('executedSourceSha256',''),('arm',1)]:
                y=copy.deepcopy(x);y[key]=value;write(p,y)
                with self.subTest(key=key),self.assertRaises(AssertionError):runner.closed_proof(p,c.sha(p),cfg,release)

if __name__=='__main__':unittest.main(verbosity=2)
