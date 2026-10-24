import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('current_checkpoint',HERE/'original_current_checkpoint_lifecycle.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Guards(unittest.TestCase):
 def setUp(self):self.plan=m.load_plan()
 def test_frozen_actual_post_r1_plan(self):
  self.assertEqual(hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest(),m.PLAN_SHA)
  self.assertEqual(self.plan['expectedState']['commandSeq'],4609)
  self.assertEqual([len(x['files']) for x in self.plan['nodes']],[16,17,18])
  self.assertEqual([x['files']['cluster/recording.log']['bytes'] for x in self.plan['nodes']],[1280]*3)
  old=json.loads((HERE/'parent-r1-after-native.json').read_text())
  self.assertEqual([x['files'] for x in self.plan['nodes']],[x['files'] for x in old['inventories']])
 def test_exact_root_executed_ownership_library(self):self.assertEqual(m.file_sha(HERE/'original_cluster_lifecycle_base.py'),m.BASE_SHA)
 def test_default_preflight_never_starts(self):
  with patch.object(m,'preflight',return_value={}) as read,patch.object(m,'execute') as start,patch('builtins.print'):m.main([])
  read.assert_called_once();start.assert_not_called()
 def test_only_explicit_start_new(self):
  with patch.object(m,'preflight') as read,patch.object(m,'execute',return_value={}) as start,patch('builtins.print'):m.main(['--start-new'])
  start.assert_called_once();read.assert_not_called()
 def test_old_or_abbreviated_execute_flags_refused(self):
  for flag in ['--start','--execute','--yes']:
   with patch.object(m,'execute') as start,patch('sys.stderr'),self.assertRaises(SystemExit):m.main([flag])
   start.assert_not_called()
 def test_node_arguments_preserve_original_profile(self):
  for n in range(3):
   a=m.base.node_argv(self.plan,n,Path('/owned/lib'));i=a.index('io.vectormatch.cluster.ClusterNodeMain');self.assertEqual(a[i+1:],[str(n),str(Path(self.plan['nodes'][n]['base']).parent),'19000','2','65536','127.0.0.1,127.0.0.1,127.0.0.1']);self.assertIn('-Xmx1g',a)
 def test_new_helper_only_and_no_wildcard(self):
  a=m.helper_argv(self.plan,Path('/owned/artifacts'));self.assertIn('io.vectormatch.cluster.CheckpointOriginalRestorationR3',a);self.assertNotIn('ProbeOriginalRestorationR2',str(a));self.assertEqual(a[-1],self.plan['probeOutput']);self.assertNotIn('*',a[a.index('-cp')+1]);self.assertIn('-Xmx128m',a)
 def test_wrong_host_fails_before_process_launch(self):
  with patch.object(m.platform,'system',return_value='OtherOS'),patch.object(m.base.subprocess,'Popen') as launch,self.assertRaises(RuntimeError):m.preflight(self.plan)
  launch.assert_not_called()
 def test_exact_native_tree_and_same_size_byte_drift(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();(d/'empty').mkdir();(d/'x').write_bytes(b'abc');v=m.base.scan(d,True);m.verify_tree(v,v);(d/'x').write_bytes(b'abd')
   with self.assertRaises(RuntimeError):m.verify_tree(m.base.scan(d,True),v)
 def test_native_mode_and_owner_drift(self):
  x={'files':{'x':{'bytes':3,'sha256':'0'*64,'mode':384,'uid':0,'gid':0}},'directories':{'.':{'mode':448,'uid':0,'gid':0}}}
  for key in ['mode','uid','gid']:
   v=copy.deepcopy(x);v['files']['x'][key]+=1
   with self.assertRaises(RuntimeError):m.verify_tree(v,x)
 def test_native_extra_empty_directory_refused(self):
  x={'files':{},'directories':{'.':{'mode':448,'uid':0,'gid':0}}};v=copy.deepcopy(x);v['directories']['extra']=dict(x['directories']['.'])
  with self.assertRaises(RuntimeError):m.verify_tree(v,x)
 def test_real_reader_frozen_package_closure(self):m.verify_reader(HERE/'offline-reader',self.plan)
 def test_reader_extra_empty_directory_refused(self):
  with tempfile.TemporaryDirectory() as td:
   dest=Path(td).resolve()/'reader';m.shutil.copytree(HERE/'offline-reader',dest);(dest/'extra').mkdir()
   with self.assertRaises(RuntimeError):m.verify_reader(dest,self.plan)
 def test_reader_same_size_source_corruption_refused(self):
  with tempfile.TemporaryDirectory() as td:
   dest=Path(td).resolve()/'reader';m.shutil.copytree(HERE/'offline-reader',dest);f=dest/'read-current-checkpoints.py';b=f.read_bytes();f.write_bytes(b'X'+b[1:])
   with self.assertRaises(RuntimeError):m.verify_reader(dest,self.plan)
 def test_reader_symlink_refused(self):
  with tempfile.TemporaryDirectory() as td:
   dest=Path(td).resolve()/'reader';m.shutil.copytree(HERE/'offline-reader',dest);(dest/'unexpected-link').symlink_to(dest/'PREPARATION.json')
   with self.assertRaises(RuntimeError):m.verify_reader(dest,self.plan)
 def test_prefix_fullsha_and_zero_tail(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();f=d/'9-0.rec'
   with f.open('wb') as o:o.write(b'a'*64);o.seek(17*1024**2-1);o.write(b'\0')
   original=m.file_sha(f);row=m.prefix_copy(f,d/'prefix.bin',{'bytes':f.stat().st_size,'sha256':original});self.assertEqual(row['bytes'],16*1024**2);self.assertEqual(row['sha256'],m.file_sha(d/'prefix.bin'));self.assertEqual(original,m.file_sha(f))
 def test_prefix_nonzero_tail_refused(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();f=d/'9-0.rec'
   with f.open('wb') as o:o.seek(16*1024**2);o.write(b'X')
   with self.assertRaises(RuntimeError):m.prefix_copy(f,d/'prefix.bin',{'bytes':f.stat().st_size,'sha256':m.file_sha(f)})
 def test_prefix_wrong_fullsha_refused(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();f=d/'9-0.rec';f.write_bytes(b'\0'*64)
   with self.assertRaises(RuntimeError):m.prefix_copy(f,d/'prefix.bin',{'bytes':64,'sha256':'0'*64})
 def test_prefix_symlink_refused(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();f=d/'real';f.write_bytes(b'\0'*64);(d/'9-0.rec').symlink_to(f)
   with self.assertRaises(RuntimeError):m.prefix_copy(d/'9-0.rec',d/'prefix.bin',{'bytes':64,'sha256':m.file_sha(f)})
 def test_no_prefix_scan_before_owned_clean_stop(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();out=d/'result';out.mkdir();job=d/'job';job.mkdir();(job/'owned-stop.json').write_text(json.dumps({'allOwnedStopped':False}));plan=copy.deepcopy(self.plan);plan['probeOutput']=str(out)
   with patch.object(m.base,'idle_check'),patch.object(m.base,'scan') as scan,self.assertRaises(RuntimeError):m.prepare_offline(plan,job)
   scan.assert_not_called()
 def test_stopped_prefix_producer_schema_integrates_reader_without_any_child(self):
  with tempfile.TemporaryDirectory() as td:
   d=Path(td).resolve();out=d/'result';out.mkdir();job=d/'job';job.mkdir();plan=copy.deepcopy(self.plan);plan['probeOutput']=str(out);plan['nodes']=[];meta=[]
   stop={'allOwnedStopped':True,'errors':[],'forcedKill':False,'stops':[{'role':'node-'+str(n),'stopped':True} for n in range(3)]};(job/'owned-stop.json').write_text(json.dumps(stop))
   for n in range(3):
    b=d/('native'+str(n));(b/'cluster').mkdir(parents=True);(b/'archive').mkdir();(b/'cluster/recording.log').write_bytes(b'\0'*64);(b/'archive/9-0.rec').write_bytes(b'\0'*64);plan['nodes'].append({'node':n,'base':str(b)})
    meta.append({'node':n,'preflightMaxSnapshotEntryIndex':17,'selected':{'recordingId':9,'leadershipTermId':11,'termBaseLogPosition':5000,'logPosition':6016,'timestamp':7000,'serviceEntryIndex':20,'consensusRecordingId':10,'consensusEntryIndex':21}})
   (out/'snapshot-metadata.json').write_text(json.dumps(meta))
   with patch.object(m.base,'idle_check'),patch.object(m.base.subprocess,'Popen') as launch:manifest=m.prepare_offline(plan,job)
   launch.assert_not_called();content=json.loads(manifest.read_text());self.assertEqual(len(content['nodes']),3);self.assertTrue(all(x['recording']['zeroTailBeyondPrefixVerified'] for x in content['nodes']))
   rs=importlib.util.spec_from_file_location('reader_integration_guard',HERE/'offline-reader/read-current-checkpoints.py');reader=importlib.util.module_from_spec(rs);rs.loader.exec_module(reader)
   java_fixture=d/'java';java_fixture.write_bytes(b'PURE_API_GUARD_NEVER_EXECUTED');java_fixture.chmod(0o700)
   with patch.object(reader.subprocess,'run') as hidden:prepared=reader.prepare_inputs(manifest,out/'not-decoded',str(java_fixture))
   hidden.assert_not_called();self.assertEqual([n['node'] for n in prepared['nodes']],[0,1,2])
   for row in prepared['nodes']:self.assertIn('io.vectormatch.cluster.ReadCurrentOriginalCheckpointsR3',row['argv'])
 def test_source_preparation_and_import_have_no_real_child_launch(self):
  source=(HERE/'original_current_checkpoint_lifecycle.py').read_text();ast.parse(source,feature_version=(3,8));self.assertNotIn('subprocess.run(',source);self.assertNotIn('subprocess.Popen(',source);self.assertIn('base.launch(plan,\'offline-reader-',source)
 def test_no_numeric_signal_forced_kill_or_delete(self):
  allsource=(HERE/'original_current_checkpoint_lifecycle.py').read_text()+(HERE/'original_cluster_lifecycle_base.py').read_text()
  for token in ['os.kill(', 'os.killpg(', 'SIGKILL','rmtree(','.unlink(']:self.assertNotIn(token,allsource)
 def test_cleanup_pid_reuse_is_blocked_without_signal(self):
  fake=MagicMock();fake.poll.return_value=None;slot={'role':'node-0','child':fake,'args':['java'],'record':{'pid':12345}};
  with patch.object(m.base,'stop_owned',side_effect=RuntimeError('identity mismatch')),patch.object(m.base.signal,'pidfd_send_signal',create=True) as signal:closed=m.clean_owned(self.plan,[slot])
  self.assertFalse(closed['allOwnedStopped']);signal.assert_not_called()
 def test_already_exited_direct_child_never_signals(self):
  fake=MagicMock();fake.poll.return_value=0;fake.returncode=0;slot={'role':'reader','child':fake,'args':['java'],'record':None}
  with patch.object(m.base,'stop_owned') as stop:closed=m.clean_owned(self.plan,[slot])
  self.assertTrue(closed['allOwnedStopped']);stop.assert_not_called()
if __name__=='__main__':unittest.main()
