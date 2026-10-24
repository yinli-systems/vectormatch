"""Synthetic mixed-source fixtures; historical node logs only seed node-policy parser cases."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parent

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
C=module('mixed_controller_test_source',BASE/'capacity_client_driver_abab.py')
V=module('independent_mixed_verifier_test',BASE/'verify_client_driver_config.py')
L=module('unchanged433_node_parser_test',C.REPO/'scripts/verify-capacity-config.py')

class MixedSourceGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original=C.read(C.REPO/'evidence/2026-10-24/runpod-cpu/registrations'/(C.BASE_IDLE_MATRIX_ID+'.json'))
        with patch.object(C,'remote_module',side_effect=AssertionError('network forbidden')):
            cls.matrix=C.draft_matrix(prerequisite=original['pilotPrerequisite'],idle_prior={'ready':False})
        cls.baseline=C.REPO/'evidence/2026-10-24/runpod-cpu/capacity/cpu-capacity-idle-b2-18000-w128-r1/raw/evidence/runs/cpu-capacity-idle-b2-18000-w128-r1'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.plan=copy.deepcopy(self.matrix['trialPlans'][0])
        self.populate()

    def populate(self):
        trial={**self.plan['task'],'release':V.NODE_ROOT,'state':self.plan['paths']['state'],
               'sourceRevision':V.NODE_REVISION,'deploymentRevision':V.NODE_REVISION,
               'loadGeneratorRevision':V.LOAD_REVISION,'loadGeneratorRelease':V.LOAD_ROOT,
               'loadGeneratorBundleSha256':self.plan['loadArtifactManifest']['bundleSha256'],
               'fixedNodeConfiguration':self.plan['fixed'],'loadGeneratorJvmArguments':V.load_flags(self.plan),
               'sourceSchemaVersion':2,'nodeSourceRevision':V.NODE_REVISION,'loadSourceRevision':V.LOAD_REVISION}
        self.write('trial.json',trial)
        config=C.read(self.baseline/'configuration.json');config['ratePerSecond']=22000
        config['clientSharedDriverIdleObservation']=self.observation()
        self.write('configuration.json',config)
        fields=('clientDriverCount','clientSessionCount','clientDriverMode','clientTransportMode','clientAeronMode',
                'clientPendingCapacity','clientNakUnicastDelayNs','clientNakUnicastRetryDelayRatio','workers',
                'queueCapacityPerWorker','scheduledArrivals','clientSharedDriverIdleObservation')
        load={k:config[k] for k in fields};load['targetArrivalRatePerSecond']=22000
        self.write('load-result.json',load);self.write('result.json',load)
        args=V.load_arguments(self.plan);self.write('load-process.json',self.process(args,201))
        for node in range(3):
            args=V.node_arguments(self.plan,node,L);proof=self.process(args,101+node)
            self.write('node'+str(node)+'/process.json',{k:v for k,v in proof.items() if not k.startswith('actual')})
            self.write('node'+str(node)+'-actual-process.json',proof)
            p=self.directory/('node'+str(node))/'process.log';p.write_bytes((self.baseline/('node'+str(node))/'process.log').read_bytes())
        (self.directory/'prepared-snapshot.bin').write_bytes((self.baseline/'prepared-snapshot.bin').read_bytes())
        (self.directory/'load.log').write_text(self.startup())
        node={n:{'sha256':self.plan['deployment']['filesVerified'][n]} for n in V.JARS}
        load={r['path']:{'sha256':r['sha256'],'bytes':r['bytes']} for r in self.plan['loadArtifactManifest']['files']}
        self.write('mixed-source-classpath-verification.json',{'schemaVersion':1,'passed':True,
            'nodeRevision':V.NODE_REVISION,'loadRevision':V.LOAD_REVISION,'nodeRoot':V.NODE_ROOT,'loadRoot':V.LOAD_ROOT,
            'manifestSha256':V.MANIFEST_SHA256,'before':{'node':node,'load':load},'after':{'node':node,'load':load}})

    def write(self,name,value):
        path=self.directory/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def alter(self,name,key,value):
        x=C.read(self.directory/name);x[key]=value;self.write(name,x)
    def process(self,args,pid):
        return {'pid':pid,'startTicks':321,'arguments':args,'actualArguments':args,
                'commandSha256':V.command_sha(args),'actualCommandSha256':V.command_sha(args)}
    def observation(self):
        return {'available':True,'source':'measured-multiplexed-owner',
                'directory':self.plan['paths']['trial']+'/load-multiplexed-driver','threadingMode':'SHARED',
                'strategyClass':'org.agrona.concurrent.BackoffIdleStrategy',
                'strategyDescription':'BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=5, minParkPeriodNs=1000, maxParkPeriodNs='+str(self.plan['task']['clientDriverMaxParkNs'])+'}'}
    def startup(self,directory=None):
        directory=directory or self.observation()['directory']
        return ('VECTOR_CLIENT_DRIVER_IDLE policyVersion=1 maxSpins=10 maxYields=5 minParkNs=1000 maxParkNs='+str(self.plan['task']['clientDriverMaxParkNs'])+' threadingMode=SHARED driverDirectoryUri='
                +Path(directory).as_uri()+'/ actualStrategy='+self.observation()['strategyDescription']+' scope=client-driver-only\n')
    def verify(self):return V.verify(self.plan,self.directory,L)

    def test_valid_mixed_source_attestation_never_claims_business_or_legacy_source_mutation(self):
        before=(L.load_generator_arguments,L.load_generator_jvm_arguments,L.main)
        result=self.verify();self.assertTrue(result['passed']);self.assertFalse(result['businessCorrectnessVerified'])
        self.assertFalse(result['legacyMainInvoked']);self.assertFalse(result['legacyFunctionsReplaced'])
        self.assertEqual(before,(L.load_generator_arguments,L.load_generator_jvm_arguments,L.main))
        self.assertEqual(result['nodeRevision'],V.NODE_REVISION);self.assertEqual(result['loadRevision'],V.LOAD_REVISION)
        self.assertNotEqual(result['nodeRevision'],result['loadRevision'])

    def test_controller_configuration_pipeline_writes_new_receipts_without_mutating_legacy_or_trial(self):
        self.plan['paths']['trial']=str(self.directory)
        self.plan['paths']['evidence']=str(self.directory/'evidence')
        self.populate()
        receipt=C.read(self.directory/'mixed-source-classpath-verification.json')
        (self.directory/'mixed-source-classpath-verification.json').unlink()
        root=self.directory/'worker-root';root.mkdir()
        C.save_new(root/'preflight.json',{'mixedSourceClasspathBefore':receipt['before']})
        tools=self.directory/'pinned-tools';(tools/'scripts').mkdir(parents=True)
        (tools/'scripts/verify-capacity-config.py').write_bytes((C.REPO/'scripts/verify-capacity-config.py').read_bytes())
        (tools/'verify-client-driver-config.py').write_bytes((BASE/'verify_client_driver_config.py').read_bytes())
        original_trial=(self.directory/'trial.json').read_bytes()
        with patch.object(C,'paths',return_value={'root':root}),patch.object(C,'classpath_inventory',return_value=receipt['after']):
            C.cpu_configuration_check(self.plan,tools)
        self.assertEqual((self.directory/'trial.json').read_bytes(),original_trial)
        result=C.read(self.directory/'configuration-verification.json')
        self.assertTrue(result['passed']);self.assertFalse(result['legacyFunctionsReplaced'])
        self.assertEqual(result['loadRevision'],V.LOAD_REVISION)
        self.assertTrue(C.read(self.directory/'node-idle-variant-verification.json')['passed'])
        self.assertEqual(C.read(self.directory/'evidence/configuration-verification.json')['schemaVersion'],2)

    def test_b_arm_same_candidate_accepts_actual100us_with_node_still100us(self):
        self.plan=copy.deepcopy(self.matrix['trialPlans'][1]);self.populate()
        receipt=self.verify();self.assertTrue(receipt['passed'])
        self.assertIn('maxParkPeriodNs=100000}',receipt['actualMeasuredDriverObservation']['strategyDescription'])
        self.assertEqual(self.plan['fixed']['nodeDataPathMaxParkNs'],100000)
        self.assertEqual(self.plan['loadArtifactManifest'],self.matrix['trialPlans'][0]['loadArtifactManifest'])

    def test_requested_flag_cannot_substitute_unavailable_or_fake_owner_evidence(self):
        for changes in ({'available':False},{'source':'setup-control'},{'strategyDescription':self.observation()['strategyDescription'].replace('1000000}','100000}')},
                        {'directory':self.plan['paths']['trial']+'/setup-driver'},{'threadingMode':'DEDICATED'}):
            obs={**self.observation(),**changes};self.alter('configuration.json','clientSharedDriverIdleObservation',obs)
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.verify()

    def test_setup_only_or_duplicate_matching_startup_cannot_attest_measured_owner(self):
        for log in (self.startup(self.plan['paths']['trial']+'/control-driver'),self.startup()*2):
            (self.directory/'load.log').write_text(log)
            with self.assertRaises(ValueError):self.verify()

    def test_result_or_load_observation_mismatch_rejected(self):
        for name in ('load-result.json','result.json'):
            original=C.read(self.directory/name);self.alter(name,'clientSharedDriverIdleObservation',{'available':False})
            with self.assertRaises(ValueError):self.verify()
            self.write(name,original)

    def test_runtime_session_window_or_driver_count_mismatch_rejected(self):
        for name,key,value in [('load-result.json','clientPendingCapacity',256),('result.json','clientSessionCount',128),
                               ('configuration.json','clientDriverCount',128),('load-result.json','workers',True)]:
            original=C.read(self.directory/name);self.alter(name,key,value)
            with self.subTest(name=name,key=key),self.assertRaises(ValueError):self.verify()
            self.write(name,original)

    def test_relabelled_old_load_revision_or_release_rejected(self):
        for key,value in [('loadGeneratorRevision',V.NODE_REVISION),('loadGeneratorRelease',V.NODE_ROOT),('sourceRevision',V.LOAD_REVISION)]:
            original=C.read(self.directory/'trial.json');self.alter('trial.json',key,value)
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.write('trial.json',original)

    def test_exact_actual_load_argv_rejects_old_classpath_extra_ownerflag_or_conflicting_property(self):
        for args in ([a.replace(V.LOAD_ROOT,V.NODE_ROOT) for a in V.load_arguments(self.plan)],
                     [*V.load_arguments(self.plan)[:3],'-Dvectormatch.client.driverMaxParkNs=100000',*V.load_arguments(self.plan)[3:]],
                     [*V.load_arguments(self.plan)[:3],'-Dvectormatch.owner.maxParkNs=100000',*V.load_arguments(self.plan)[3:]]):
            self.write('load-process.json',self.process(args,201))
            with self.assertRaises(ValueError):self.verify()

    def test_actual_node_identity_or_policy_mismatch_rejected(self):
        for args in ([a.replace('-Dvectormatch.node.dataPathMaxParkNs=100000','-Dvectormatch.node.dataPathMaxParkNs=1000000') for a in V.node_arguments(self.plan,0,L)],
                     [a.replace(V.NODE_ROOT,V.LOAD_ROOT) for a in V.node_arguments(self.plan,0,L)]):
            self.write('node0/process.json',self.process(args,101))
            self.write('node0-actual-process.json',self.process(args,101))
            with self.assertRaises(ValueError):self.verify()

    def test_before_after_inventory_wrong_bytes_extra_jar_or_crossed_source_rejected(self):
        path='mixed-source-classpath-verification.json';original=C.read(self.directory/path)
        for phase in ('before','after'):
            for change in ('hash','extra','source'):
                x=copy.deepcopy(original)
                if change=='hash':x[phase]['load']['dist/cluster/lib/cluster-0.1.0-SNAPSHOT.jar']['sha256']='0'*64
                elif change=='extra':x[phase]['load']['dist/cluster/lib/extra.jar']={'sha256':'a'*64,'bytes':1}
                else:x['loadRevision']=V.NODE_REVISION
                self.write(path,x)
                with self.subTest(phase=phase,change=change),self.assertRaises(ValueError):self.verify()
        self.write(path,original)

    def test_manifest_payload_cannot_be_changed_under_pinned_claimed_sha(self):
        self.plan['loadArtifactManifest']['files'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):self.verify()

    def test_unknown_failure_never_creates_business_result(self):
        (self.directory/'result.json').unlink();self.alter('trial.json','completedAt','2026-10-24T00:00:00Z')
        load=C.read(self.directory/'load-result.json');load['unresolvedFinal']=2;self.write('load-result.json',load)
        self.write('receipt.json',{'exitCode':1})
        self.write('failure.json',{'passed':False,'errorType':'java.lang.IllegalStateException',
            'error':L.UNKNOWN_GUARD.format(count=2),'loadSummary':load})
        result=self.verify();self.assertTrue(result['configurationOnly']);self.assertFalse((self.directory/'result.json').exists())
        self.alter('failure.json','error','different generic exception')
        with self.assertRaises(AssertionError):self.verify()

if __name__=='__main__':unittest.main()
