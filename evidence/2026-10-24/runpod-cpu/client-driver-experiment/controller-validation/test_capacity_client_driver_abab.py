"""Bounded mixed-source controller registration/continuation guards; no live actions."""
import ast
import copy
import csv
import subprocess
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('client_driver_abab_controller_tests',BASE/'capacity_client_driver_abab.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)

class ClientDriverControlGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior=C.read(C.REPO/'evidence/2026-10-24/runpod-cpu/registrations'/(C.BASE_IDLE_MATRIX_ID+'.json'))['pilotPrerequisite']
        with patch.object(C,'remote_module',side_effect=AssertionError('network forbidden')):
            cls.plan=C.draft_matrix(prerequisite=prior,idle_prior={'ready':False})

    def test_exact_ABAB_same_candidate_only_client_driver_maximum_changes(self):
        self.assertEqual([p['stage'] for p in C.matrix_tasks()],['A1','B1','A2','B2'])
        self.assertEqual([p['clientDriverMaxParkNs'] for p in C.matrix_tasks()],[1000000,100000]*2)
        self.assertEqual(len({p['paths']['state'] for p in self.plan['trialPlans']}),4)
        a,b=self.plan['trialPlans'][:2]
        self.assertEqual({k for k in a['fixed'] if a['fixed'][k]!=b['fixed'][k]},{'clientDriverMaxParkNs'})
        for p in self.plan['trialPlans']:
            self.assertEqual(p['task']['rate'],22000);self.assertEqual(p['task']['arrivals'],350000)
            self.assertEqual(p['fixed']['nodeDataPathMaxParkNs'],100000);self.assertEqual(p['fixed']['queuePerWorker'],64)
            self.assertEqual(p['task']['workers'],128);self.assertGreaterEqual(350000/22000,10)
            self.assertEqual(p['loadArtifactManifest'],a['loadArtifactManifest'])

    def test_actual_node_and_load_sources_are_explicitly_different_and_flag_is_load_only(self):
        for p in self.plan['trialPlans']:
            C.validate_plan(p);args=C.load_arguments(p)
            self.assertEqual(p['sourceSchemaVersion'],2);self.assertEqual(p['sourceRevision'],C.REVISION)
            self.assertEqual(p['loadSourceRevision'],C.LOAD_REVISION)
            self.assertIn(str(C.LOAD_RELEASE)+'/dist/cluster/lib/*',args)
            self.assertNotIn(str(C.RELEASE)+'/dist/cluster/lib/*',args)
            self.assertFalse(any('vectormatch.node.dataPath' in a for a in args))
            self.assertFalse(any('owner' in a for a in args))
            with patch.dict(C.os.environ,{},clear=True):
                env=C.clean_environment(p);self.assertEqual(env['VECTOR_DATA_PATH_MAX_PARK_NS'],'100000')
                self.assertEqual(C.client_environment(p,env)['VECTOR_DATA_PATH_MAX_PARK_NS'],'1000000')

    def test_unmodified_original_sources_and_historical1ms_baseline_policy(self):
        self.assertEqual(C.sha(BASE/'capacity_park100_curve.py'),C.BASE_CURVE_SHA256)
        self.assertEqual(C.sha(BASE/'capacity_idle.py'),C.BASE_IDLE_SHA256)
        original=C.read(C.REPO/'evidence/2026-10-24/runpod-cpu/matrices/cpu-capacity-staircase-433-r1/trial-plans'/(C.BASELINE_IDS[0]+'.json'))
        self.assertEqual(C.historical_baseline_fixed(),original['fixed'])
        self.assertNotIn('clientDriverMaxParkNs',C.historical_baseline_fixed())

    def test_wrong_order_rate_workers_node_park_or_client_factor_is_rejected(self):
        p=copy.deepcopy(self.plan);p['order'].reverse();p['matrixPlanSha256']=C.matrix_identity(p)
        with self.assertRaises(ValueError):C.validate_matrix(p)
        for section,key,value in [('task','rate',26000),('task','workers',256),('fixed','nodeDataPathMaxParkNs',1000000),
                                  ('fixed','clientOwnerMaxParkNsPinnedSource',100000),('fixed','clientDriverMaxParkNs',100000)]:
            p=copy.deepcopy(self.plan['trialPlans'][0]);p[section][key]=value;p['planSha256']=C.plan_identity(p)
            with self.subTest(key=key),self.assertRaises(ValueError):C.validate_plan(p)

    def test_mixed_manifest_or_new_verifier_tamper_rejected_even_with_new_plan_digest(self):
        for kind in ('source','manifest','verifier'):
            p=copy.deepcopy(self.plan['trialPlans'][0])
            if kind=='source':p['loadSourceRevision']=C.REVISION
            elif kind=='manifest':p['loadArtifactManifest']['files'][0]['sha256']='f'*64
            else:p['mixedVerifier']['source']+='\n# tamper\n'
            p['planSha256']=C.plan_identity(p)
            with self.subTest(kind=kind),self.assertRaises(ValueError):C.validate_plan(p)

    def prepare(self,root):
        plan=copy.deepcopy(self.plan);path=root/'registered.json';C.save_new(path,plan)
        d=root/'evidence/2026-10-24/runpod-cpu/matrices'/C.MATRIX_ID
        d.mkdir(parents=True);C.save_new(d/'plan.json',plan)
        for p in plan['trialPlans']:C.save_new(d/'trial-plans'/(p['jobId']+'.json'),p)
        return plan,path,d

    def test_skip_first_or_previously_attempted_identity_is_blocked_before_launch(self):
        for mode in ('skip','attempted'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);p,path,d=self.prepare(root);index=1 if mode=='skip' else 0
                child=p['trialPlans'][index]
                if mode=='attempted':(d/'point-executions'/child['jobId']).mkdir(parents=True)
                with patch.object(C,'REPO',root),patch.object(C,'pilot_prerequisite',return_value=p['pilotPrerequisite']), \
                     patch.object(C,'idle_prerequisite',return_value=p['nodeIdlePrerequisite']), \
                     patch.object(C,'execute',side_effect=AssertionError('must not launch')),self.assertRaises((ValueError,FileNotFoundError)):
                    C.execute_registered_point(path,child['jobId'])

    def test_ambiguous_launch_is_one_attempt_and_never_automatically_pruned_or_reissued(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p,path,d=self.prepare(root);ident=p['trialPlans'][0]['jobId']
            with patch.object(C,'REPO',root),patch.object(C,'pilot_prerequisite',return_value=p['pilotPrerequisite']), \
                 patch.object(C,'idle_prerequisite',return_value=p['nodeIdlePrerequisite']), \
                 patch.object(C,'overlay_space',return_value={'nextPointEligible':True}), \
                 patch.object(C,'execute',side_effect=TimeoutError('query SAME identity')) as launch,patch('builtins.print'):
                self.assertEqual(C.execute_registered_point(path,ident),1)
            self.assertEqual(launch.call_count,1)
            receipt=C.read(d/'point-executions'/ident/'receipt.json')
            self.assertFalse(receipt['passed']);self.assertFalse(receipt['automaticPrunePerformed'])
            self.assertEqual(receipt['errorType'],'TimeoutError')

    def test_UNKNOWN_invalid_or_failed_cleanup_blocks_next_point_but_valid_overload_is_retained(self):
        completion={'matrixTrialPassed':True,'allOwnedProcessesStopped':True,'archiveComplete':True,'loadExitCode':0}
        summary={'trials':[{'measurementValid':True,'observedStableWindow':False,
                           'derived':{'unknownAtInitialDeadline':0,'unknownUnresolved':0}}]}
        self.assertTrue(C.continuation_check(completion,summary)['passed'])
        for key in ('unknownAtInitialDeadline','unknownUnresolved'):
            s=copy.deepcopy(summary);s['trials'][0]['derived'][key]=1
            self.assertFalse(C.continuation_check(completion,s)['passed'])
        s=copy.deepcopy(summary);s['trials'][0]['measurementValid']=False
        self.assertFalse(C.continuation_check(completion,s)['passed'])
        completion['allOwnedProcessesStopped']=False
        self.assertFalse(C.continuation_check(completion,summary)['passed'])

    def test_actual_pinned31e4_CLI_accepts_mixed_identity_and_separates_AB_fingerprints(self):
        # Tiny SYNTHETIC20-arrival inputs check schema/group compatibility only, not22k performance.
        identity=self.plan['trialPlans'][0]['analysisIdentity']
        self.assertEqual(identity['analysisIdentitySha256'],C.ANALYSIS_ID)
        self.assertEqual(C.sha(identity['python']['resolvedExecutable']),identity['python']['binarySha256'])
        for name,digest in identity['files'].items():self.assertEqual(C.sha(Path(identity['root'])/name),digest)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);runs=root/'runs';runs.mkdir()
            for child in self.plan['trialPlans']:
                d=runs/child['jobId'];d.mkdir()
                trial={**child['task'],'release':str(C.RELEASE),'sourceRevision':C.REVISION,
                    'deploymentRevision':C.REVISION,'deploymentBundleSha256':child['deployment']['bundleSha256'],
                    'fixedNodeConfiguration':child['fixed'],'loadGeneratorRevision':C.LOAD_REVISION,
                    'loadGeneratorBundleSha256':child['loadArtifactManifest']['bundleSha256'],
                    'loadGeneratorRelease':str(C.LOAD_RELEASE)}
                config={'preparedSnapshotSha256':C.PREPARED_SHA,'clientDriverMode':'shared','clientDriverCount':1,
                        'clientAeronMode':'one-session-one-network-owner'}
                result={'scheduledArrivals':20,'targetArrivalRatePerSecond':2,'arrivalWindowSeconds':10,
                        'workers':128,'queueCapacityPerWorker':64,'passed':True,'measurementValid':True,
                        'canonicalSnapshotBytesVerified':True,'fixedLeaderVerified':True,'leaderChanged':False,
                        'generatorTimingInvalid':False,'schedulerLatenessAboveLimitCount':0}
                for name,value in [('trial.json',trial),('configuration.json',config),('result.json',result),
                    ('fixed-leader-check.json',{'passed':True,'preTerm':0,'postTerm':0,'observedTerms':[0,0]})]:
                    C.save_new(d/name,value)
                with (d/'arrivals.csv').open('w',newline='') as out:
                    columns=['index','outcome','confirmed_offset_ns','scheduled_to_confirmed_ns','initial_execute_rtt_ns',
                             'queue_delay_ns','scheduler_lateness_ns','unknown_at_initial_deadline']
                    w=csv.DictWriter(out,columns);w.writeheader()
                    for index in range(20):w.writerow({'index':index,'outcome':'CONFIRMED_ACCEPTED',
                        'confirmed_offset_ns':index*500000000+1000000,'scheduled_to_confirmed_ns':1000000,
                        'initial_execute_rtt_ns':1000000,'queue_delay_ns':0,'scheduler_lateness_ns':0,
                        'unknown_at_initial_deadline':'false'})
                with (d/'backlog.csv').open('w',newline='') as out:
                    w=csv.DictWriter(out,['offset_ns','queue_depth','in_flight']);w.writeheader()
                    for second in range(11):w.writerow({'offset_ns':second*1000000000,'queue_depth':0,'in_flight':1})
            args=[identity['python']['executable'],'-I','-B',str(Path(identity['root'])/identity['entryPoint']),
                  '--runs-dir',str(runs),'--output-dir',str(root/'analysis')]
            done=subprocess.run(args,capture_output=True,text=True,timeout=15)
            self.assertEqual(done.returncode,0,done.stdout+done.stderr)
            summary=C.read(root/'analysis/summary.json')
            self.assertEqual(summary['counts']['trials'],4);self.assertEqual(summary['counts']['valid'],4)
            self.assertEqual(len(summary['groups']),2)
            by_id={p['id']:p for p in summary['trials']}
            a1,b1,a2,b2=[by_id[p['jobId']] for p in self.plan['trialPlans']]
            self.assertEqual(a1['comparisonFingerprintSha256'],a2['comparisonFingerprintSha256'])
            self.assertEqual(b1['comparisonFingerprintSha256'],b2['comparisonFingerprintSha256'])
            self.assertNotEqual(a1['comparisonFingerprintSha256'],b1['comparisonFingerprintSha256'])
            for point in summary['trials']:
                self.assertEqual(point['configurationIdentityIssues'],[])
                self.assertEqual(point['comparisonConfiguration']['sourceRevision'],C.REVISION)
                self.assertEqual(point['comparisonConfiguration']['loadGeneratorRevision'],C.LOAD_REVISION)
            print('PINNED31e4_SYNTHETIC_SCHEMA_ONLY exit=0 trials=4 valid=4 groups=2 repeatedPairsPreserved=true')

    def test_exact_point_only_no_batch_and_python38(self):
        with self.assertRaises(ValueError):C.execute_matrix(Path('not-read'))
        with patch.object(C,'execute_registered_point',return_value=0) as execute:
            ident=C.matrix_tasks()[0]['id'];self.assertEqual(C.main(['--plan','p.json','--execute-point',ident]),0)
            execute.assert_called_once_with(Path('p.json'),ident)
        for file in ('capacity_client_driver_abab.py','verify_client_driver_config.py'):
            ast.parse((BASE/file).read_text(),feature_version=(3,8))

if __name__=='__main__':unittest.main()
