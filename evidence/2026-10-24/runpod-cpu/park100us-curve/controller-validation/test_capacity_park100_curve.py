"""Bounded local-only curve guards. No SSH, registration, JVM, workload, or raw copies."""
import ast
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('park100_curve_guard', BASE / 'capacity_park100_curve.py')
C = importlib.util.module_from_spec(spec);sys.modules[spec.name] = C;spec.loader.exec_module(C)

def idle_ready():
    return {'ready': True, 'matrixId': C.BASE_IDLE_MATRIX_ID, 'controllerSha256': C.BASE_IDLE_SHA256,
            **{key: 'a'*64 for key in ('comparisonSha256','matrixPlanFileSha256','matrixPlanSha256','summarizerSha256')},
            'points': [{'stage': stage, 'jobId': 'cpu-capacity-idle-'+stage.lower()+'-18000-w128-r1',
                        'valid': True, 'finiteStable': stage.startswith('B'), 'actualInstanceCountPerNode': [11,11,11],
                        **{key: 'b'*64 for key in ('completionContentSha256','archiveSha256','analysisSha256','pointSha256','receiptSha256','idleProofSha256')}}
                       for stage in ('A1','B1','A2','B2')]}

class Guards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original = C.read(C.REPO / 'evidence/2026-10-24/runpod-cpu/registrations' / (C.BASE_IDLE_MATRIX_ID+'.json'))
        with patch.object(C,'remote_module',side_effect=AssertionError('network forbidden')):
            cls.plan=C.draft_matrix(prerequisite=original['pilotPrerequisite'],idle_prior=idle_ready())

    def test_exact_two_ascending_repetitions_and_minimum_window(self):
        tasks=C.matrix_tasks()
        self.assertEqual([t['rate'] for t in tasks],[22000,26000,30000,34000]*2)
        self.assertEqual([t['repetition'] for t in tasks],[1]*4+[2]*4)
        self.assertEqual(len({t['id'] for t in tasks}),8)
        self.assertTrue(all(t['arrivals']==350000 and t['workers']==128 and t['nodeMaxParkNs']==100000 for t in tasks))
        self.assertGreaterEqual(min(t['arrivals']/t['rate'] for t in tasks),10)
        self.assertEqual(len({p['paths']['state'] for p in self.plan['trialPlans']}),8)

    def test_fixed_config_all_points_and_pinned_source(self):
        self.assertEqual(C.sha(BASE/'capacity_idle.py'),C.BASE_IDLE_SHA256)
        for p in self.plan['trialPlans']:
            C.validate_plan(p)
            self.assertEqual(p['controllerVersion'],5)
            self.assertEqual(p['fixed'],C.FIXED)
            self.assertEqual(p['sourceRevision'],C.REVISION)
        self.assertEqual(self.plan['variableFixedFields'],[])

    def test_reorder_or_missing_point_rejected_even_rehashed(self):
        for mutation in ('reverse','pop'):
            p=copy.deepcopy(self.plan)
            getattr(p['order'],mutation)()
            p['matrixPlanSha256']=C.matrix_identity(p)
            with self.assertRaises(ValueError):C.validate_matrix(p)

    def test_task_or_fixed_mutation_rejected(self):
        for section,key,value in [('task','rate',18000),('task','workers',256),('task','arrivals',349999),
                                  ('fixed','nodeDataPathMaxParkNs',1000000),('fixed','clientNakUnicastDelayNs',100000),
                                  ('fixed','queuePerWorker',32),('fixed','nodeHeap','4g')]:
            p=copy.deepcopy(self.plan['trialPlans'][0]);p[section][key]=value;p['planSha256']=C.plan_identity(p)
            with self.subTest(key=key),self.assertRaises(ValueError):C.validate_plan(p)

    def test_historical13k_gate_preserves1ms_and_rejects_current100us(self):
        p=C.REPO/'evidence/2026-10-24/runpod-cpu/matrices/cpu-capacity-staircase-433-r1/trial-plans'/(C.BASELINE_IDS[0]+'.json')
        legacy=C.read(p)
        self.assertEqual(legacy['fixed'],C.historical_baseline_fixed())
        self.assertNotEqual(C.FIXED,C.historical_baseline_fixed())
        changed=copy.deepcopy(legacy);changed['fixed']=C.FIXED
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);prefix=root/'evidence/2026-10-24/runpod-cpu'
            ident=C.BASELINE_IDS[0];local=prefix/'capacity'/ident;trial=local/'raw/evidence/runs'/ident
            names=[prefix/'matrices/cpu-capacity-staircase-433-r1/trial-plans'/(ident+'.json'),
                   local/'raw/plan.json',local/'completion.json',local/'postprocess.json',local/'analysis/summary.json',
                   local/(ident+'.tar.gz'),local/'raw/full-state-manifest.json']
            names += [trial/name for name in ('result.json','load-result.json','matrix-trial-check.json',
                                              'configuration-verification.json','fixed-leader-check.json','configuration.json')]
            for name in names:C.save_new(name,changed if name.name in ('plan.json',ident+'.json') else {})
            with self.assertRaisesRegex(ValueError,'13k baseline source/controller/fixed policy differs'):
                C.baseline_13000_prerequisite(ident,root,required=True)

    def test_all_four_idle_attempts_required(self):
        for n in (0,1,2,3):
            prior=idle_ready();prior['points']=prior['points'][:n]
            with self.assertRaises(ValueError):C.validate_idle_prerequisite_declaration(prior)

    def test_both_B_must_be_stable_A_overload_allowed(self):
        C.validate_idle_prerequisite_declaration(idle_ready())
        for i in (1,3):
            prior=idle_ready();prior['points'][i]['finiteStable']=False
            with self.assertRaises(ValueError):C.validate_idle_prerequisite_declaration(prior)

    def test_invalid_or_missing_instance_or_sha_blocks_prerequisite(self):
        for key,value in [('valid',False),('actualInstanceCountPerNode',[8,8,8]),('archiveSha256','bad')]:
            prior=idle_ready();prior['points'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):C.validate_idle_prerequisite_declaration(prior)

    def test_missing_prerequisite_fails_without_network(self):
        with tempfile.TemporaryDirectory() as root,patch.object(C,'remote_module',side_effect=AssertionError('network forbidden')):
            self.assertFalse(C.idle_prerequisite(Path(root))['ready'])
            with self.assertRaises(ValueError):C.idle_prerequisite(Path(root),required=True)

    def test_load_and_environment_leave_client_unchanged(self):
        with patch.dict(C.os.environ,{},clear=True):
            for p in self.plan['trialPlans']:
                args=C.load_arguments(p);env=C.clean_environment(p);client=C.client_environment(p,env)
                self.assertEqual(env['VECTOR_DATA_PATH_MAX_PARK_NS'],'100000')
                self.assertEqual(client['VECTOR_DATA_PATH_MAX_PARK_NS'],'1000000')
                self.assertFalse(any('vectormatch.node.dataPath' in a for a in args))
                self.assertEqual(args[args.index('io.vectormatch.cluster.RemoteCapacityExperiment')+3],str(p['task']['rate']))
                self.assertIn('-Dvectormatch.capacity.client.transport=multiplexed',args)
                self.assertIn('-Daeron.nak.unicast.delay=1000',args)

    def test_unknown_invalid_and_incomplete_cleanup_stop_continuation(self):
        completion={'matrixTrialPassed':True,'allOwnedProcessesStopped':True,'archiveComplete':True,'loadExitCode':0}
        summary={'trials':[{'measurementValid':True,'observedStableWindow':False,
                           'derived':{'unknownAtInitialDeadline':0,'unknownUnresolved':0}}]}
        self.assertTrue(C.continuation_check(completion,summary)['passed'])
        for key in ('matrixTrialPassed','allOwnedProcessesStopped','archiveComplete'):
            p=dict(completion);p[key]=False;self.assertFalse(C.continuation_check(p,summary)['passed'])
        for key in ('unknownAtInitialDeadline','unknownUnresolved'):
            s=copy.deepcopy(summary);s['trials'][0]['derived'][key]=1
            self.assertFalse(C.continuation_check(completion,s)['passed'])
        s=copy.deepcopy(summary);s['trials'][0]['measurementValid']=False
        self.assertFalse(C.continuation_check(completion,s)['passed'])

    def test_batch_execution_disabled(self):
        with patch.object(C,'remote_module',side_effect=AssertionError('network forbidden')),self.assertRaises(ValueError):
            C.execute_matrix(Path('never-read'))

    def prepare_attempt(self,root):
        plan=copy.deepcopy(self.plan);path=root/'registered.json';C.save_new(path,plan)
        destination=root/'evidence/2026-10-24/runpod-cpu/matrices'/C.MATRIX_ID
        destination.mkdir(parents=True);C.save_new(destination/'plan.json',plan)
        for child in plan['trialPlans']:C.save_new(destination/'trial-plans'/(child['jobId']+'.json'),child)
        return plan,path,destination

    def test_cannot_skip_first_point(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p,path,d=self.prepare_attempt(root)
            with patch.object(C,'REPO',root),patch.object(C,'pilot_prerequisite',return_value=p['pilotPrerequisite']), \
                 patch.object(C,'idle_prerequisite',return_value=p['nodeIdlePrerequisite']), \
                 patch.object(C,'execute',side_effect=AssertionError('must not launch')),self.assertRaises(FileNotFoundError):
                C.execute_registered_point(path,p['trialPlans'][1]['jobId'])

    def test_attempted_identity_never_reissued(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p,path,d=self.prepare_attempt(root);ident=p['trialPlans'][0]['jobId']
            (d/'point-executions'/ident).mkdir(parents=True)
            with patch.object(C,'REPO',root),patch.object(C,'pilot_prerequisite',return_value=p['pilotPrerequisite']), \
                 patch.object(C,'idle_prerequisite',return_value=p['nodeIdlePrerequisite']), \
                 patch.object(C,'execute',side_effect=AssertionError('must not launch')),self.assertRaises(ValueError):
                C.execute_registered_point(path,ident)

    def test_ambiguous_launch_retained_no_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p,path,d=self.prepare_attempt(root);ident=p['trialPlans'][0]['jobId']
            with patch.object(C,'REPO',root),patch.object(C,'pilot_prerequisite',return_value=p['pilotPrerequisite']), \
                 patch.object(C,'idle_prerequisite',return_value=p['nodeIdlePrerequisite']), \
                 patch.object(C,'overlay_space',return_value={'nextPointEligible':True}), \
                 patch.object(C,'execute',side_effect=TimeoutError('query SAME identity')) as launch,patch('builtins.print'):
                self.assertEqual(C.execute_registered_point(path,ident),1)
            self.assertEqual(launch.call_count,1)
            receipt=C.read(d/'point-executions'/ident/'receipt.json')
            self.assertFalse(receipt['passed']);self.assertFalse(receipt['automaticPrunePerformed'])
            self.assertEqual(receipt['errorType'],'TimeoutError')
            self.assertEqual(len(list((d/'point-executions').iterdir())),1)

    def test_cli_exact_id_and_no_implicit_batch(self):
        with patch.object(C,'execute_registered_point',return_value=0) as run:
            ident=C.matrix_tasks()[0]['id'];self.assertEqual(C.main(['--plan','p.json','--execute-point',ident]),0)
            run.assert_called_once_with(Path('p.json'),ident)
        with self.assertRaises(SystemExit):C.main(['--execute'])

    def test_create_new_output_and_python38(self):
        ast.parse((BASE/'capacity_park100_curve.py').read_text(),feature_version=(3,8))
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'x.json';C.save_new(p,{'x':1})
            with self.assertRaises(FileExistsError):C.save_new(p,{'x':2})

if __name__=='__main__':unittest.main()
