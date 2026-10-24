"""Pure fixture guards; no real stage, raw workload, remote access or resource mutation."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common
import closed_bindings as bindings
import frozen_parser
import audit_raw
import finalize_local_collection as finalize
import collect_and_audit as runner
import cpu_long_cuts as controller

class Guards(unittest.TestCase):
    def test_long_tape_over32m_explicit_only(self):
        size=35_578_188;plan={'maximumRawTraceBytes':185_514_924}
        self.assertTrue(bindings.materialize('job/idle-arm/load/physical-replies.bin',size,plan))
        self.assertFalse(bindings.materialize('job/unrelated.bin',size,plan))
        self.assertFalse(bindings.materialize('job/node/aeron.rec',100,plan))

    def test_overbudget_preserves_archive_not_raw_admission(self):
        plan={'maximumRawTraceBytes':185_514_924}
        rows={name:{'bytes':60_000_000}for name in bindings.TAPES}
        result=bindings.validate_tape_budget(rows,plan)
        self.assertFalse(result['passed']);self.assertEqual(result['totalOriginalTapeBytes'],240_000_000)
        self.assertIn('retain complete outer/nested TAR',result['failurePolicy'])
        self.assertTrue(all(not bindings.materialize(k,v['bytes'],plan,allow_tapes=result['passed'])for k,v in rows.items()))
        self.assertFalse(bindings.materialize(next(iter(rows)),185_514_925,plan))
        with self.assertRaises(AssertionError):bindings.materialize(next(iter(rows)),1,{'maximumRawTraceBytes':999_999_999})

    def projection_fixture(self,root):
        collection=Path(root).resolve();name='job/idle-arm/load/arrivals.csv';path=collection/'raw-files'/name
        path.parent.mkdir(parents=True);path.write_bytes(b'synthetic,only\n')
        outer={'files':{name:{'bytes':path.stat().st_size,'sha256':common.sha(path),'mode':0o600,'uid':123456,'gid':123456}}}
        (collection/'remote-inventory.stdout.json').write_text(json.dumps(outer))
        receipt={'passed':True,'allOuterFileFullShaSizeModeOwnerAndEmptyDirClosureVerified':True,
            'outerInventorySha256':common.sha(collection/'remote-inventory.stdout.json'),'rawTapeMaterializationBudget':{'passed':True}}
        native={'passed':True,'allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified':True,'allNestedFilesExactlyBoundToOuterArchive':True}
        return collection,path,outer,receipt,native

    def test_projection_separates_original_owner_from_local(self):
        with tempfile.TemporaryDirectory()as t:
            collection,path,outer,receipt,native=self.projection_fixture(t)
            rows,links=bindings.project(collection,outer,receipt,native);key='raw-files/job/idle-arm/load/arrivals.csv'
            self.assertEqual(rows[key]['uid'],os.geteuid())
            self.assertEqual(links[key]['originalArchiveMetadata']['uid'],123456)
            self.assertTrue(links[key]['archiveOwnerIsNotLocalOwnerClaim'])
            self.assertEqual(rows[key]['sha256'],outer['files'][key[len('raw-files/'):]]['sha256'])

    def test_projection_rejects_payload_change(self):
        with tempfile.TemporaryDirectory()as t:
            c,p,o,r,n=self.projection_fixture(t);p.write_bytes(b'changed')
            with self.assertRaises(AssertionError):bindings.project(c,o,r,n)

    def test_projection_rejects_symlink(self):
        with tempfile.TemporaryDirectory()as t:
            c,p,o,r,n=self.projection_fixture(t);target=p.with_name('target');p.rename(target);p.symlink_to(target.name)
            with self.assertRaises(AssertionError):bindings.project(c,o,r,n)

    def test_projection_requires_all_closures_and_tape_admission(self):
        with tempfile.TemporaryDirectory()as t:
            c,p,o,r,n=self.projection_fixture(t)
            for target,key in [(r,'allOuterFileFullShaSizeModeOwnerAndEmptyDirClosureVerified'),(n,'allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'),(n,'allNestedFilesExactlyBoundToOuterArchive')]:
                old=target[key];target[key]=False
                with self.assertRaises(AssertionError):bindings.project(c,o,r,n)
                target[key]=old
            r['rawTapeMaterializationBudget']['passed']=False
            with self.assertRaises(AssertionError):bindings.project(c,o,r,n)
            r['rawTapeMaterializationBudget']['passed']=True;r['outerInventorySha256']='0'*64
            with self.assertRaises(AssertionError):bindings.project(c,o,r,n)

    def test_frozen_loader_restores_alias_and_strict_default(self):
        previous=sys.modules['common'];mods=frozen_parser.load()
        self.assertIs(sys.modules['common'],previous)
        self.assertIs(mods['audit_raw'].audit_arm.__kwdefaults__['local_functional_only'],False)
        self.assertEqual(mods['workload_contract'].LONG.arrivals,33792)

    def test_frozen_loader_rejects_source_change_and_restores_alias(self):
        previous=sys.modules['common']
        with tempfile.TemporaryDirectory()as t:
            root=Path(t)/'long_parser';shutil.copytree(HERE/'long_parser',root)
            p=root/'source/audit_raw.py';p.write_bytes(p.read_bytes()+b'\n# unexpected\n')
            with self.assertRaises(AssertionError):frozen_parser.load(root)
            self.assertIs(sys.modules['common'],previous)

    def test_strict_adapter_never_passes_diagnostic_optin(self):
        calls=[]
        parser=types.SimpleNamespace(audit_arm=lambda *a,**k:calls.append((a,k))or{'passed':True})
        self.assertTrue(audit_raw.strict_arm(parser,'long','arm')['passed'])
        self.assertEqual(calls,[((8,'arm'),{'workload':'long'})])

    def test_finalizer_denies_local_diagnostic_wrong_source_and_overbudget(self):
        reports={'nativeResult':{'sourceCommit':'source','frozenCodeFingerprintIndependentlyRecomputed':'code'},
            'rawResult':{'sourceCommit':'source','strictSchedulerTimingAdmission':True,'localFunctionalDiagnosticOptIn':False},
            'collectionReceipt':{'rawTapeMaterializationBudget':{'passed':True}}}
        finalize.strict_long_reports(reports,'source','code')
        for target,key,value in [(reports['rawResult'],'strictSchedulerTimingAdmission',False),
            (reports['rawResult'],'localFunctionalDiagnosticOptIn',True),
            (reports['nativeResult'],'sourceCommit','wrong'),
            (reports['nativeResult'],'frozenCodeFingerprintIndependentlyRecomputed','wrong'),
            (reports['collectionReceipt']['rawTapeMaterializationBudget'],'passed',False)]:
            old=target[key];target[key]=value
            with self.assertRaises(AssertionError):finalize.strict_long_reports(reports,'source','code')
            target[key]=old

    def config_fixture(self,t):
        root=Path(t).resolve();prep='/opt/vectormatch-cpu/preparation/cpu-long-cuts-cloud-r1'
        protected=root/'protected.json';protected.write_text('{}\n')
        release={'host':'ed6c0673f5cb','controllerSha256':common.sha(HERE/'cpu_long_cuts.py'),
            'arms':{'1':{'job':prep+'/arm-1','armRoot':prep+'/arm-1/idle-arm','maximumParkNs':100000}},
            'protectedOriginalState':{'manifestSha256':common.sha(protected)}}
        rp=root/'release.json';rp.write_text(json.dumps(release));rh=common.sha(rp)
        files={'release/release.json':{'bytes':rp.stat().st_size,'sha256':rh},
            'cpu_long_cuts.py':{'bytes':(HERE/'cpu_long_cuts.py').stat().st_size,'sha256':common.sha(HERE/'cpu_long_cuts.py')}}
        for name in ['owned_linux_base_8eeb.py','idle_attestation.py','shutdown_warning.py','common.py','long_parser/source/audit_raw.py','long_parser/source/read_phase_audit.py']:
            path=HERE/name;files[name]={'bytes':path.stat().st_size,'sha256':common.sha(path)}
        stage=root/'stage.json';stage.write_text(json.dumps({'passed':True,'stagedFiles':files,'releaseSha256':rh,
            'controllerSha256':release['controllerSha256'],'applicationStarted':False,'resourceCreated':False}))
        c={'schemaVersion':3,'experiment':'retention-long-cuts-v1','arm':1,'remotePrep':prep,'host':release['host'],
            'releaseLocal':str(rp),'releaseSha256':rh,'stagingReceipt':str(stage),'stagingReceiptSha256':common.sha(stage),
            'protectedReference':str(protected),'protectedReferenceSha256':common.sha(protected),
            'maximumParkNs':100000,'workloadPreset':'long-cuts-33792-v1','priorGates':{},
            'executionMetadata':['arm-1-execution-register.json','arm-1-execution.stdout','arm-1-execution.stderr']}
        cp=root/'config.json';cp.write_text(json.dumps(c));return cp,c,stage

    def test_config_allowlist_fixture_only(self):
        # This isolates collector-schema gates, not a real release/artifact readiness assertion.
        with tempfile.TemporaryDirectory()as t,patch.object(controller,'validate_release',side_effect=lambda r:r):
            p,c,s=self.config_fixture(t);actual,release,rows,allow=common.load_config(p)
            self.assertEqual(len(allow),len(rows)+3);self.assertEqual(actual['arm'],1)
            self.assertNotIn('arm-1/idle-arm',allow)

    def test_config_wrong_arm_preset_prior_metadata_and_stage(self):
        with tempfile.TemporaryDirectory()as t,patch.object(controller,'validate_release',side_effect=lambda r:r):
            p,c,s=self.config_fixture(t)
            for key,value in [('arm',2),('workloadPreset','idle-6400'),('priorGates',{'1':{}}),
                ('executionMetadata',['../bad']),('stagingReceiptSha256','0'*64)]:
                changed=copy.deepcopy(c);changed[key]=value;p.write_text(json.dumps(changed))
                with self.assertRaises(AssertionError):common.load_config(p)

    def test_closed_proof_exact_long_scope_and_release(self):
        with tempfile.TemporaryDirectory()as t:
            p=Path(t).resolve()/'closed.json';c={'arm':1,'maximumParkNs':100000,'releaseSha256':'a'*64,'remotePrep':str(controller.PREP)};r={'controllerSha256':'b'*64}
            v={'schemaVersion':2,'scope':'ROOT_VERIFIED_CLOSED_CPU_LONG_CUTS_CONTROLLER','rootVerified':True,'arm':1,
                'maximumParkNs':100000,'frozenReleaseSha256':'a'*64,'controllerSha256':'b'*64,'job':str(controller.PREP)+'/arm-1',
                'controllerIdentityGone':True,'allOwnedStopped':True,'inspectionSha256':'c'*64,'inspectionSourceSha256':'d'*64}
            p.write_text(json.dumps(v));runner.closed_proof(p,common.sha(p),c,r)
            for key,value in [('scope','ROOT_VERIFIED_CLOSED_CPU_IDLE_CONTROLLER'),('arm',2),('allOwnedStopped',False),('controllerIdentityGone',False),('frozenReleaseSha256','e'*64)]:
                changed=copy.deepcopy(v);changed[key]=value;p.write_text(json.dumps(changed))
                with self.assertRaises(AssertionError):runner.closed_proof(p,common.sha(p),c,r)

if __name__=='__main__':unittest.main()
