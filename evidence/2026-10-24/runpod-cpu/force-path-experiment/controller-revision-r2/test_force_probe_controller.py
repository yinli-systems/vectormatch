#!/usr/bin/env python3
"""Offline guards only: no SSH, JVM, workload or actual process signaling."""
from pathlib import Path
from unittest import mock
import ast
import copy
import csv
import hashlib
import importlib.util
import json
import signal
import tempfile
import types
import unittest

SOURCE=Path(__file__).with_name('force_probe_controller.py')
spec=importlib.util.spec_from_file_location('force_probe_controller_guard',SOURCE)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class ControllerGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=c.draft(prior={'ready':False,'missing':['offline fixture']})
    def test_exact_matrix_and_byte_force_caps(self):
        p=self.plan
        self.assertEqual([t['writers'] for t in p['order']],[1]*4+[3]*4)
        self.assertEqual([t['blockBytes'] for t in p['order']],list(c.BLOCKS)*2)
        self.assertEqual(p['globalPlannedDataWriteBytes'],85164032)
        self.assertEqual(p['globalPlannedForceCalls'],3376)
        self.assertLess(p['globalPlannedDataWriteBytes'],256*1024**2)
        self.assertTrue(all(t['measurements']==200 and t['warmup']==10 for t in p['order']))
    def test_recomputed_plan_hash_cannot_weaken_bounds_or_paths(self):
        for key,value in [('globalSeconds',999),('minimumFreeBytes',0),('control','/tmp/arbitrary'),('globalPlannedForceCalls',1)]:
            p=copy.deepcopy(self.plan);p[key]=value;p['planSha256']=c.plan_identity(p)
            with self.assertRaises(ValueError):c.validate_plan(p)
    def test_unique_canonical_namespace(self):
        for value in ('other','force-probe-../x','force-probe-a/extra','force-probe-A','force-probe-'+'a'*50):
            with self.assertRaises(ValueError):c.identifier(value)
    def test_exact_artifact_source_classes_and_python38_remote_import(self):
        meta,data=c.artifact();self.assertEqual(hashlib.sha256(data).hexdigest(),meta['sha256'])
        self.assertNotIn('classes/ForcePathProbeClockGuard.class',meta['files'])
        ast.parse(SOURCE.read_text(),feature_version=(3,8))
        # The real remote parent is shallower than the repository tree: imports must remain safe.
        namespace={'__file__':'/workspace/vectormatch-cpu-control/force-probe-test/controller.py','__name__':'offline_remote_import'}
        exec(compile(SOURCE.read_text(),str(SOURCE),'exec'),namespace)
        self.assertIsNone(namespace['REPO'])
    def test_artifact_create_new_and_hash_bound(self):
        meta,data=c.artifact()
        with tempfile.TemporaryDirectory() as d:
            d=Path(d).resolve();archive=d/'artifact.tar';archive.write_bytes(data)
            p=copy.deepcopy(self.plan);p['artifactRoot']=str(d/'new-artifact')
            self.assertTrue(c.stage_artifact(p,archive)['passed'])
            with self.assertRaises(ValueError):c.stage_artifact(p,archive)
            target=Path(p['artifactRoot'])/'classes/ForcePathProbe.class';target.chmod(0o644);target.write_bytes(b'changed')
            with self.assertRaises(ValueError):c.check_artifact(p,Path(p['artifactRoot']))
    def test_save_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d).resolve()/'receipt.json';c.save(p,{'one':1})
            with self.assertRaises(FileExistsError):c.save(p,{'two':2})
            self.assertEqual(c.read(p),{'one':1})
    def test_proc_parser_handles_parentheses_and_start_ticks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p=root/'123';p.mkdir();fields=['S']+['0']*18+['987']+['0']*30
            (p/'stat').write_text('123 (java ) name) '+' '.join(fields))
            (p/'cmdline').write_bytes(b'java\0-cp\0owned\0')
            with mock.patch.object(c,'PROC',root):record=c.identity(123)
            self.assertEqual(record['startTicks'],987);self.assertEqual(record['arguments'],['java','-cp','owned'])
    def test_double_observation_ignores_transient_run_state_only(self):
        args=['java','owned'];record={'pid':123,'startTicks':456,'state':'R','arguments':args,'commandSha256':c.command_sha(args)}
        second={**record,'state':'S'};child=types.SimpleNamespace(pid=123,poll=lambda:None)
        with mock.patch.object(c,'identity',side_effect=[record,second]):self.assertTrue(c.await_identity(child,args)['twoMatchingObservations'])
        with mock.patch.object(c,'identity',side_effect=[record,{**second,'startTicks':789}]):
            with self.assertRaises(ValueError):c.await_identity(child,args)
    def test_pid_reuse_is_stopped_not_signaled_and_argv_change_rejected(self):
        record={'pid':123,'startTicks':5,'arguments':['java'],'commandSha256':c.command_sha(['java'])}
        with mock.patch.object(c,'identity',return_value={**record,'startTicks':6,'state':'R'}),mock.patch.object(c.os,'pidfd_open',create=True) as opened:
            self.assertTrue(c.stop_owned(record)['stopped']);opened.assert_not_called()
        with mock.patch.object(c,'identity',return_value={**record,'state':'R','arguments':['other']}):
            with self.assertRaises(ValueError):c.state(record)
    def test_pidfd_signal_requires_recheck_and_closes_fd(self):
        record={'pid':123,'startTicks':5}
        with mock.patch.object(c,'state',side_effect=['running','running','running','stopped','stopped','stopped']),mock.patch.object(c.os,'pidfd_open',return_value=91,create=True),mock.patch.object(c.signal,'pidfd_send_signal',create=True) as sent,mock.patch.object(c.os,'close') as closed:
            result=c.stop_owned(record)
        self.assertTrue(result['stopped']);sent.assert_called_once_with(91,signal.SIGTERM);closed.assert_called_once_with(91)
    def test_sigterm_raises_once_for_owned_cleanup(self):
        handlers={}
        def install(sig,fn):old=handlers.get(sig,'old');handlers[sig]=fn;return old
        with mock.patch.object(c.signal,'signal',side_effect=install):previous=c.install_cancellation_handlers()
        self.assertEqual(len(previous),2)
        with self.assertRaises(InterruptedError):handlers[signal.SIGTERM](signal.SIGTERM,None)
        handlers[signal.SIGTERM](signal.SIGTERM,None) # repeated cancellation must not interrupt cleanup
    def test_unreceipted_attempt_is_not_stopped_proof(self):
        with tempfile.TemporaryDirectory() as d:
            p={'control':str(Path(d).resolve()),'order':[{'id':'force-probe-x'}]};attempt=Path(d).resolve()/'points/force-probe-x';attempt.mkdir(parents=True)
            closed,attempted,unproven=c.closed_attempts(p)
            self.assertEqual(closed,[]);self.assertEqual(attempted,['force-probe-x']);self.assertEqual(len(unproven),1)
    def test_worker_stops_sequence_after_failed_partial(self):
        with tempfile.TemporaryDirectory() as d:
            control=Path(d).resolve();p={'id':'force-probe-x','control':str(Path(d).resolve()),'dataParent':str(control/'data'),'artifactRoot':str(control/'artifact'),'planSha256':'x','order':[{'id':'force-probe-x-a'},{'id':'force-probe-x-b'}]};c.save(control/'plan.json',p)
            def point(plan,t,deadline):
                path=control/'points'/t['id'];path.mkdir(parents=True);r={'passed':False,'point':t,'cleanup':{'stopped':True}};c.save(path/'receipt.json',r);return r
            with mock.patch.object(c,'validate_plan',side_effect=lambda value:value),mock.patch.object(c,'identity',return_value={}),mock.patch.object(c,'enable_pidfd',return_value={}),mock.patch.object(c,'idle_check',return_value={}),mock.patch.object(c,'remote_predecessors'),mock.patch.object(c,'stage_artifact',return_value={}),mock.patch.object(c,'point_run',side_effect=point) as launch,mock.patch.object(c,'archive_results',return_value={'sha256':'test'}):
                self.assertEqual(c.worker(control/'plan.json'),1)
            launch.assert_called_once();result=c.read(control/'completion.json')
            self.assertTrue(result['allMeasuredJvmsStopped']);self.assertEqual(result['unlaunchedIds'],['force-probe-x-b']);self.assertFalse(result['passed'])
    def test_exited_jvm_cannot_bypass_final_log_cap(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p={'control':str(root/'control'),'dataParent':str(root/'data'),'artifactRoot':str(root/'artifact'),'planSha256':'x'}
            t={'id':'force-probe-logcap','maximumOutputBytes':1000,'fileBytesPerWriter':10}
            child=types.SimpleNamespace(pid=123,returncode=0,poll=lambda:0,wait=lambda timeout:0)
            def spawn(*args,**kwargs):kwargs['stdout'].write(b'x'*(c.MAX_LOG+1));kwargs['stdout'].flush();return child
            with mock.patch.object(c,'idle_check',return_value={}),mock.patch.object(c,'check_artifact',return_value={}),mock.patch.object(c,'java_arguments',return_value=['java','owned']),mock.patch.object(c.subprocess,'Popen',side_effect=spawn),mock.patch.object(c,'await_identity',return_value={'pid':123}),mock.patch.object(c,'stop_owned',return_value={'stopped':True}),mock.patch.object(c,'validate_output') as validate,mock.patch.dict(c.os.environ,{},clear=True):
                result=c.point_run(p,t,c.time.monotonic()+100)
            self.assertFalse(result['passed']);self.assertIn('Final JVM log cap',result['error']);validate.assert_not_called()
    def test_predecessor_same_count_duplicate_ids_is_rejected(self):
        p=copy.deepcopy(self.plan);rows=[]
        for ident in c.PREDECESSOR_POINTS:
            row={'jobId':ident,'archivePath':'/workspace/vectormatch-cpu-archives/'+ident+'.tar.gz'}
            row.update({key:'a'*64 for key in ('completionSha256','archiveSha256','analysisSha256','pointSha256','receiptSha256','configurationSha256','ownedStopSha256')});rows.append(row)
        p['prerequisite']={'ready':True,'controllerSha256':c.CLIENT_CONTROLLER_SHA,'matrixId':c.PREDECESSOR_ID,'points':rows};p['planSha256']=c.plan_identity(p);c.validate_plan(p)
        p['prerequisite']['points'][3]=copy.deepcopy(rows[0]);p['planSha256']=c.plan_identity(p)
        with self.assertRaises(ValueError):c.validate_plan(p)
    def test_explicit_idle_confirmation_required_before_remote(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d).resolve()/'plan.json';c.save(path,self.plan)
            with mock.patch.object(c,'remote_module') as network:
                with self.assertRaisesRegex(ValueError,'idle window'):c.execute(path,False)
                network.assert_not_called()

class OutputGuards(unittest.TestCase):
    def fixture(self,d):
        t=c.tasks('force-probe-fixture')[0];path=Path(d).resolve()/t['id'];path.mkdir()
        config={'schemaVersion':1,'label':'diagnostic','writers':1,'blockBytes':4096,'fileBytesPerWriter':65536,'warmupIterationsPerWriter':10,'measurementIterationsPerWriter':200,'maxTotalWriteBytes':t['plannedDataWriteBytes'],'plannedTotalWriteBytes':t['plannedDataWriteBytes'],'plannedForceCalls':t['plannedForceCalls'],'maxDurationMs':30000,'minFreeBytes':c.MIN_FREE,'forceMetadata':True,'os':{'name':'Linux'},'filesystem':{'type':'overlay'},'writerModel':'one JVM, threads'}
        c.save(path/'configuration.json',config);data=path/'synthetic-force-writer-0.data';data.write_bytes(bytes(65536))
        rows=[];phases=[('preallocation',-1,0,65536)]+[('warmup',i,i%16*4096,4096) for i in range(10)]+[('measurement',i,i%16*4096,4096) for i in range(200)]
        for i,(phase,index,offset,size) in enumerate(phases):
            rows.append(dict(zip(c.HEADER,[1,phase,0,index,'2026-10-24T01:00:00Z',i*100,offset,size,size,1,1,10,20,30,'','false','complete',''])))
        with (path/'writer-0.csv').open('w',newline='') as stream:
            out=csv.DictWriter(stream,fieldnames=c.HEADER);out.writeheader();out.writerows(rows)
        c.save(path/'success.json',{'passed':True,'allWorkerThreadsTerminated':True,'totalWrittenBytes':t['plannedDataWriteBytes'],'forceTrueCalls':211,'writers':[{'writerId':0,'writtenBytes':t['plannedDataWriteBytes'],'forceCalls':211,'preallocationRows':1,'warmupRows':10,'measurementRows':200}],'dataFiles':[{'name':data.name,'bytes':65536,'sha256':c.sha(data)}]})
        return t,path,rows
    def test_complete_phases_and_missing_cpu_is_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            t,path,_=self.fixture(d);result=c.validate_output({},t,path)
            self.assertEqual(result['writers'][0]['rows'],211);self.assertEqual(result['writers'][0]['measurementRows'],200)
    def test_reordered_phase_wrong_force_and_timing_rejected(self):
        for key,value in [('phase','warmup'),('force_calls','0'),('total_elapsed_ns','31'),('written_bytes','0')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                t,path,rows=self.fixture(d);rows[0][key]=value
                with (path/'writer-0.csv').open('w',newline='') as stream:
                    out=csv.DictWriter(stream,fieldnames=c.HEADER);out.writeheader();out.writerows(rows)
                with self.assertRaises(ValueError):c.validate_output({},t,path)
    def test_post_readback_corruption_or_extra_failure_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            t,path,_=self.fixture(d);(path/'synthetic-force-writer-0.data').write_bytes(b'x'*65536)
            with self.assertRaises(ValueError):c.validate_output({},t,path)
        with tempfile.TemporaryDirectory() as d:
            t,path,_=self.fixture(d);c.save(path/'failure.json',{'expected':True})
            with self.assertRaises(ValueError):c.validate_output({},t,path)

if __name__=='__main__':unittest.main(verbosity=2)
