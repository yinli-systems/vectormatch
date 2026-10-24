"""Focused deltas over frozen122 guards. Fixtures are schema-only, never artifacts."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import cpu_idle_abab as p
import idle_attestation as a
import common
import build_config as builder
import collect_and_audit as collector

HERE = Path(__file__).resolve().parent


def release():
    x = json.loads((HERE / 'release.template.json').read_text())
    x.update(releaseReady=True, sourceCommit=p.SOURCE_COMMIT, codeFingerprint='b'*64,
             profileFingerprint='c'*64, javaExecutableSha256='d'*64, jdkReleaseSha256='e'*64,
             controllerSha256='f'*64, profileId='SCHEMA-FIXTURE-NOT-A-REAL-ARTIFACT')
    jars = [str(p.PREP / 'release/lib' / name) for name in ['cluster.jar','core.jar','aeron.jar','agrona.jar']]
    x['classPath'], x['nodeClassPath'] = jars, jars[:3]
    x['artifacts'] = {q: {'bytes': 128, 'sha256': '1'*64} for q in jars}
    plan = {key: 1 for key in p.PLAN_KEYS}
    plan.update(arrivals=6400,batchCap=4,archiveChunkBytes=6144,requestedReadWindow=8,maxReadOnlyInFlight=8,
                commonReadWindowEnvelope=True,commonChunkEnvelope=False,eventFetchCount=16,admitted=True,
                admissionRejections=[],minimumFreeRuntimeBytes=p.GIB,maximumPhysicalOffersPerRpc=4,
                maximumBusinessFrames=6400,maximumEvents=12803,maximumMaintenanceCycles=4,
                maximumWriterPayloadFiles=8,maximumWriterFilesIncludingReceipts=16,maximumJournalRecords=32,
                selectedMaximumArchiveChunkRpcs=566,maximumEventFetchRpcs=801,
                selectedMaximumLogicalMaintenanceRpcs=1379,maximumArchiveChunkRpcs=566,
                maximumLogicalMaintenanceRpcs=1379,maximumAllocatedGrowthBytes=589327865,
                maximumRawTraceBytes=38033404,readOnlyStagingBytes=1282496,
                readOnlyFailureTraceReserveBytes=1054872,maximumSupportedArchiveChunkBytes=6144,
                maximumEncodedChunkReplyBytes=6919,largestReplyBytes=6791)
    x['derivedPlan'] = plan
    return x


def actual(maximum=1000000, node=0, pid=123):
    rows=[];roles=a.OWNER_ROLES if node==-1 else a.NODE_ROLES
    counts={role:len(a.USES[role]) for role in roles}
    for role,yields in roles.items():
        for consumed,use in enumerate(a.USES[role],1):
            rows.append({'role':role,'instanceOrdinal':len(rows)+1,'roleConsumptionOrdinal':consumed,
                'roleConsumptionBound':counts[role],'strategyClass':'org.agrona.concurrent.BackoffIdleStrategy',
                'strategyDescription':('BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=%d, minParkPeriodNs=1000, maxParkPeriodNs=%d}')%(yields,maximum),
                'maximumSpins':10,'maximumYields':yields,'minimumParkNs':1000,'maximumParkNs':maximum,
                'sourceDerivedIntendedUse':use,'factoryCallerStack':[{'class':'schema.Fixture','method':'factory','classTruncated':False,'methodTruncated':False,'line':1}],
                'factoryCallerFrameLimit':5,'factoryCallerTextByteLimit':256,'factoryCallerTailMayBeOmitted':False,
                'association':'actual installed shared-driver getter object' if 'driver' in role else 'source-ordered factory consumption; private agent field not read back'})
    return {'schema':'retention-idle-actual-v2','node':node,'pid':pid,'selection':a.selection(maximum),
            'instancesDistinct':True,'instances':rows,'selectedLogicalRoles':sorted(roles),
            'expectedConsumptionCounts':counts,'observedConsumptionCounts':counts.copy(),
            'sleepDurationMeasured':False,'hardRealtimeGuaranteed':False,
            'runningAgentThreadCountIndependentlyObserved':False,'associationScope':a.ASSOCIATION}


def gate(n=1):
    return {'schemaVersion':2,'scope':'ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION',
            'collectionComplete':True,'arm':n,'maximumParkNs':p.PARK_ORDER[n-1],
            'frozenReleaseSha256':'8'*64,'controllerSha256':'f'*64,
            'independentLocalCollectionReceiptSha256':'7'*64,
            'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allRawInputsAndFailuresRetained':True,
            'closedArchiveSha256':'6'*64,'closedNativeInventorySha256':'5'*64,
            'rootReviewedExactOwnedNativeRemoval':False}


class IdleDelta(unittest.TestCase):
    def tearDown(self):
        p.configure_arm(1); p.FROZEN_RELEASE_SHA=None

    def test_draft_and_old_artifact_source_cannot_execute(self):
        with self.assertRaisesRegex(RuntimeError,'unfrozen draft'):
            p.validate_release(json.loads((HERE/'release.template.json').read_text()))
        x=release(); self.assertIs(p.validate_release(x),x)
        x['sourceCommit']='0f7eb2e7f6409a81b9a816fdb3142941d1850013'
        with self.assertRaisesRegex(RuntimeError,'Exact reviewed'):
            p.validate_release(x)

    def test_only_four_explicit_single_arms_and_canonical_order(self):
        for n, park in enumerate([1000000,100000,1000000,100000],1):
            p.configure_arm(n); self.assertEqual(p.selected_park_ns(),park)
            self.assertEqual(p.PAIR,p.PREP/('arm-'+str(n))/'idle-arm')
        for value in [0,5,True,'1']:
            with self.subTest(value=value),self.assertRaises(RuntimeError):p.configure_arm(value)

    def test_parent_node_exact_optin_and_unchanged_owner_configuration(self):
        x=release();p.configure_arm(2)
        reg={'ports':42000,'lineage':'capacity-pilot-schema'}
        for args in [p.parent_argv(x),p.node_argv(x,8,0,reg)]:
            self.assertEqual(args[1],'-Dvectormatch.retention.idleMaxParkNs=100000')
            self.assertEqual(sum('vectormatch.retention.idle' in q for q in args),1)
            self.assertIn('-Xmx256m',args)
        self.assertEqual(p.parent_argv(x)[-3:],[str(p.PAIR),'idle-window8','42000'])
        self.assertEqual(x['configuration']['ownerLoopMaximumParkNsUnchanged'],1000000)
        for field,value in [('readWindow',1),('sync',0),('ownerLoopMaximumParkNsUnchanged',100000),('maximumParkOrderNs',[100000]*4)]:
            bad=copy.deepcopy(x);bad['configuration'][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):p.validate_release(bad)

    def test_single_arm_common_plan_and_space_bound_not_four_sum(self):
        x=release();self.assertEqual(p.allocation_limit(x),589327865+16*1024**2)
        self.assertEqual(p.allocation_limit(x)+p.GIB+p.MAX_ARCHIVE,1948282361)
        for field,value in [('requestedReadWindow',1),('maximumPhysicalOffersPerRpc',5),('maximumRawTraceBytes',3*p.GIB),('largestReplyBytes',8193)]:
            bad=copy.deepcopy(x);bad['derivedPlan'][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):p.validate_release(bad)

    def test_consumed_instance_uniqueness_and_tuple_not_hard_role_object_count(self):
        x=actual();x['instances'].reverse()
        self.assertEqual(a.validate_actual(x,1000000,123,0)['actualFactoryCreations'],7)
        for change in ['reuse','tuple','missing','bound','stack','threadclaim']:
            bad=copy.deepcopy(x)
            if change=='reuse':bad['instances'][-1]['instanceOrdinal']=bad['instances'][0]['instanceOrdinal']
            if change=='tuple':bad['instances'][1]['maximumYields']=5
            if change=='missing':bad['instances']=[r for r in bad['instances'] if r['role']!='service']
            if change=='bound':bad['instances'][1]['roleConsumptionBound']=3
            if change=='stack':bad['instances'][1]['factoryCallerStack'][0]['class']='x'*257
            if change=='threadclaim':bad['runningAgentThreadCountIndependentlyObserved']=True
            with self.subTest(change=change),self.assertRaises(RuntimeError):a.validate_actual(bad,1000000,123,0)

    def test_actual_scope_pid_and_sleep_claims_are_strict(self):
        a.validate_actual(actual(node=-1),1000000,123,-1)
        for key,value in [('pid',124),('node',1),('sleepDurationMeasured',True),('hardRealtimeGuaranteed',True),('instancesDistinct',False)]:
            bad=actual();bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):a.validate_actual(bad,1000000,123,0)
        with self.assertRaises(RuntimeError):a.validate_actual(actual(),100000,123,0)

    def test_immediate_prior_arm_independent_gate_required(self):
        p.configure_arm(2);p.FROZEN_RELEASE_SHA='8'*64
        p.validate_prior_gate(gate(),release(),1)
        for key,value in [('collectionComplete',False),('arm',2),('maximumParkNs',100000),('controllerSha256','9'*64),('frozenReleaseSha256','9'*64),('allRawInputsAndFailuresRetained',False)]:
            bad=gate();bad[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prior_gate(bad,release(),1)
        with self.assertRaises(RuntimeError):p.validate_prior_gate(gate(),release(),0)

    def test_exact_four_jars_and_classpath_prevent_mixed_artifacts(self):
        x=release();x['classPath'].pop()
        with self.assertRaises(RuntimeError):p.validate_release(x)
        x=release();x['nodeClassPath']=['/tmp/other.jar']*3
        with self.assertRaises(RuntimeError):p.validate_release(x)

    def test_original_ownership_cleanup_and_egress_functions_exactly_reused(self):
        def functions(path):
            return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}
        old=functions(HERE/'frozen/window_cloud_abab.py');new=functions(HERE/'cpu_idle_abab.py')
        for name in ['clean_all','strict_idle','owned_metrics','global_metrics','allocated_scan','validate_egress','validate_egress_progress','protected_state']:
            self.assertEqual(old[name],new[name],name)
        self.assertEqual(p.digest(HERE/'owned_linux_base_8eeb.py'),p.BASE_SHA)

    def test_closed_controller_gate_never_confuses_exit_with_owned_stop(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td).resolve()/'closed.json';c={'arm':1,'maximumParkNs':1000000,'releaseSha256':'8'*64,'remotePrep':str(p.PREP)}
            x={'schemaVersion':2,'scope':'ROOT_VERIFIED_CLOSED_CPU_IDLE_CONTROLLER','rootVerified':True,'arm':1,
               'maximumParkNs':1000000,'frozenReleaseSha256':'8'*64,'controllerSha256':'f'*64,
               'job':str(p.PREP/'arm-1'),'controllerIdentityGone':True,'allOwnedStopped':True,
               'inspectionSha256':'4'*64,'inspectionSourceSha256':'3'*64}
            file.write_text(json.dumps(x));collector.closed_proof(file,builder.sha(file),c,release())
            for key,value in [('allOwnedStopped',False),('controllerIdentityGone',False),('arm',2),('inspectionSha256',None)]:
                bad=copy.deepcopy(x);bad[key]=value;file.write_text(json.dumps(bad))
                with self.subTest(key=key),self.assertRaises(AssertionError):collector.closed_proof(file,builder.sha(file),c,release())

    def test_config_prefix_and_stage_sha_binding(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();r=root/'release.json';r.write_text(json.dumps(release()));prot=root/'protected.json';prot.write_text('{}')
            data=json.loads(r.read_text());data['protectedOriginalState']['manifestSha256']=builder.sha(prot);r.write_text(json.dumps(data))
            rows={'release/release.json':{'bytes':r.stat().st_size,'sha256':builder.sha(r)}}
            rows['cpu_idle_abab.py']={'bytes':1,'sha256':'f'*64}
            rows['owned_linux_base_8eeb.py']={'bytes':(HERE/'owned_linux_base_8eeb.py').stat().st_size,'sha256':p.BASE_SHA}
            for name in ['idle_attestation.py','common.py','read_phase_audit.py','shutdown_warning.py']:
                rows[name]={'bytes':(HERE/name).stat().st_size,'sha256':builder.sha(HERE/name)}
            for n in range(2):rows['source-%d.py'%n]={'bytes':1,'sha256':'1'*64}
            stage=root/'stage.json';stage.write_text(json.dumps({'passed':True,'applicationStarted':False,'resourceCreated':False,
                'stagedFiles':rows,'releaseSha256':builder.sha(r),'controllerSha256':'f'*64}))
            metadata=['arm-1-execution-register.json','arm-1-execution.stdout','arm-1-execution.stderr']
            config=builder.build(1,r,builder.sha(r),stage,builder.sha(stage),prot,builder.sha(prot),{},metadata,root/'out')
            c,_,_,allow=common.load_config(config);self.assertEqual(c['arm'],1);self.assertEqual(len(allow),12)
            bad=json.loads(config.read_text());bad['arm']=2;bad['maximumParkNs']=100000;config.write_text(json.dumps(bad))
            with self.assertRaisesRegex(AssertionError,'prefix'):common.load_config(config)
            with self.assertRaises(AssertionError):builder.reference(stage,'0'*64)

    def test_neither_controller_nor_collector_can_delete_or_start_automatically(self):
        tree=ast.parse((HERE/'cpu_idle_abab.py').read_text())
        called={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
        self.assertFalse(called & {'rmtree','unlink','killpg'})
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        self.assertTrue(any(isinstance(n,ast.Attribute) and n.attr=='start_new' for n in ast.walk(main)))

    def test_single_flat_arm_registry_observes_three_exact_node_identities(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();proc=root/'proc';proc.mkdir();job=root/'arm-1';job.mkdir();native=job/'idle-arm';native.mkdir()
            x=release();reg={'arrivals':6400,'rate':500,'batchCap':4,'archiveChunkBytes':6144,'readWindow':8,
                'eventFetchCount':16,'commonChunkEnvelope':False,'commonReadWindowEnvelope':True,
                'appointedLeader':0,'sync':2,'profileSha256':'c'*64,'codeSha256':'b'*64,
                'ports':42000,'lineage':'capacity-pilot-schema','retentionIdleSelection':p.selection()}
            (native/'registration.json').write_text(json.dumps(reg));identities={}
            base=p.load_base()
            for n in range(3):
                pid=200+n;(proc/str(pid)).mkdir()
                with mock.patch.object(p,'PAIR',native):args=p.node_argv(x,8,n,reg)
                rec={'pid':pid,'startTicks':100+n,'arguments':args,'commandSha256':base.argv_digest(args)};identities[pid]=rec
                row={'pid':pid,'linuxStartTicks':rec['startTicks'],'linuxCommandSha256':rec['commandSha256'],'command':args[0],'arguments':args[1:]}
                (native/('node-%d-identity.json'%n)).write_text(json.dumps(row))
            observed=types.SimpleNamespace(PROC=proc,no_links=base.no_links,save=base.save,
                process_identity=lambda pid:identities.get(pid),argv_digest=base.argv_digest,now=base.now)
            with mock.patch.object(p,'PAIR',native):
                registry=p.Registry(observed,x,job);rows=registry.discover()
            self.assertEqual(len(rows),3)
            self.assertEqual({row['role'] for row in rows},{'window-8-node-'+str(n) for n in range(3)})
            self.assertTrue(all(row['identity']['arguments'][1]=='-Dvectormatch.retention.idleMaxParkNs=1000000' for row in rows))


if __name__=='__main__':unittest.main()
