"""Pure synthetic control-plane ownership guards; no process/remote actions."""
import ast,copy,hashlib,json,pathlib,tempfile,unittest
from unittest import mock
import inspect_closed_long_arm as p

BASE=pathlib.Path(__file__).resolve().parent.parent
CONTROLLER=b'# SYNTHETIC CONTROL-PLANE FIXTURE ONLY\n'
CONTROLLER_SHA=hashlib.sha256(CONTROLLER).hexdigest()

class CloseGuards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.prep=pathlib.Path(self.tmp.name).resolve()/'prep';self.prep.mkdir();self.job=self.prep/'arm-1';self.job.mkdir();self.native=self.job/'idle-arm';self.archive=self.job/'pilot-after-clean-stop.tar.gz';self.archive.write_bytes(b'x')
  self.release=json.loads((BASE/'cpu-long-cuts-cloud-preparation-r1/release.template.json').read_text());self.release.update(releaseReady=True,controllerSha256=CONTROLLER_SHA);self.release_bytes=json.dumps(self.release).encode();self.release_sha=hashlib.sha256(self.release_bytes).hexdigest()
  self.reg={'ports':42000,'readWindow':8,'appointedLeader':0,'sync':2,'profileSha256':p.PROFILE_SHA,'codeSha256':p.CODE_SHA,'retentionIdleSelection':{'maximumParkNs':100000},'lineage':'capacity-pilot-fixture','arrivals':33792,'rate':500,'batchCap':4,'archiveChunkBytes':6144,'eventFetchCount':16,'commonReadWindowEnvelope':True,'commonChunkEnvelope':False,'workloadPreset':'long-cuts-33792-v1','expectedFullCommandCuts':11,'expectedTrailingCommands':3,'equivalentFullLoadCutNumbers':list(range(2,12))}
  args=['/usr/bin/python3','-B',str(self.prep/'cpu_long_cuts.py'),'--arm','1','--release-sha256',self.release_sha,'--start-new']
  self.entries=[{'state':'INTENT_NO_PID_YET','expectedArguments':args,'arm':1,'frozenReleaseSha256':self.release_sha},{'state':'SPAWNED_IDENTITY_PENDING','pid':100,'arm':1},{'pid':100,'startTicks':1000,'expectedArguments':args,'arm':1,'frozenReleaseSha256':self.release_sha,'observedCommandSha256':p.argv_sha(args),'observedExecArgvMatches':True,'stableStartTicks':True}]
  self.parent=self.identity(101,p.expected_parent(self.release,self.native,100000));self.nodes=[self.identity(102+n,p.expected_node(self.release,self.native,self.reg,n,100000)) for n in range(3)]
  self.summary={'confirmedAcceptedUniqueOrders':33792,'notSent':0,'unknownObserved':0,'unknownFinal':0,'scheduledArrivals':33792,'releasedArrivals':33792,'completedLogicalReplies':33792,'ratePerSecond':500,'batchCap':4,'archiveChunkBytes':6144,'readWindow':8,'serverRejected':0,'duplicateOrOutOfRangeAcceptedOrderIds':0,'maintenanceCycles':12,'schedulerTimingValid':True,'schedulerLatenessOver20ms':0,'arrivalClockPausedForMaintenance':False}
  logs=[{'node':n,'warningPairCount':0,'afterSigtermWallTimeProven':False,'allLogLinesClassifiedAndRetained':True} for n in range(3)]
  self.completion={'arm':1,'maximumParkNs':100000,'frozenReleaseSha256':self.release_sha,'allOwnedStopped':True,'passed':True,'errors':[],'result':{'passed':True,'arms':[{'maximumParkNs':100000,'readWindow':8,'functional':{'passed':True,'actualSourceSummary':self.summary},'nodeLogClassifications':logs,'retainedPostCheckpointEosWarningPairs':0}]}}
  self.stop={'allOwnedStopped':True,'errors':[],'forcedKill':False,'numericPidSignalFallback':False,'reports':[{'role':'window-8-node-%d'%n,'record':v,'stopped':True} for n,v in enumerate(self.nodes)]}
  self.protected={'passed':True,'manifestSha256':p.PROTECTED_SHA,'nativeTrees':[{'files':18},{'files':19},{'files':20}],'postgres':{'files':989}}
  self.before={'controllerSha256':CONTROLLER_SHA,'baseSha256':'8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87','protectedOriginal':self.protected,'arm':1,'singleManualArmOnly':True,'noJavaStarted':True}
  self.after={'protectedOriginal':copy.deepcopy(self.protected),'archive':{'sameHostReadback':{'passed':True},'requiresIndependentCollectorStreamReadback':True,'archive':{'path':str(self.archive),'bytes':1,'sha256':'f'*64}}};self.reads=[]
 def identity(self,pid,args):return {'pid':pid,'startTicks':pid*10,'arguments':args,'commandSha256':p.argv_sha(args)}
 def bounded(self,path,*unused,**kw):
  self.reads.append(path.name)
  if path.name=='arm-1-execution-register.json':return b'\n'.join(json.dumps(v).encode() for v in self.entries)+b'\n'
  if path.name=='release.json':return self.release_bytes
  if path.name=='cpu_long_cuts.py':return CONTROLLER
  raise AssertionError('Unexpected bounded read '+str(path))
 def js(self,path,*unused,**kw):
  self.reads.append(path.name);name=path.name
  values={'BENCHMARK_BLOCKED.json':None,'completion.json':self.completion,'python-owned-stop.json':self.stop,'identity-observation-000.json':{'role':'pilot-parent','origin':'independent-direct-child-proc','kernelIdentity':self.parent},'parent-launch-handle.json':{'pid':self.parent['pid'],'expectedArguments':self.parent['arguments'],'expectedCommandSha256':self.parent['commandSha256']},'registration.json':self.reg,'before.json':self.before,'after-clean-stop.json':self.after}
  if name in values:return values[name]
  if name.startswith('node-'):
   v=self.nodes[int(name.split('-')[1])];return {'pid':v['pid'],'linuxStartTicks':v['startTicks'],'linuxCommandSha256':v['commandSha256'],'command':v['arguments'][0],'arguments':v['arguments'][1:]}
  raise AssertionError('Unexpected JSON read '+str(path))
 def call(self,states=None,foreign=None,identity=None,arm=1,controller_sha=CONTROLLER_SHA,release_sha=None):
  states=states or {}
  def status(v):
   state=states.get(v['pid'],'PID_ABSENT');return {'pid':v['pid'],'originalIdentityRunning':state=='REGISTERED_IDENTITY_RUNNING','observation':state}
  with mock.patch.object(p,'PREP',self.prep),mock.patch.object(p,'bounded',side_effect=self.bounded),mock.patch.object(p,'js',side_effect=self.js),mock.patch.object(p,'identity_state',side_effect=status),mock.patch.object(p,'live_jvm_pg',return_value=(foreign or [],5)),mock.patch.object(p.platform,'system',return_value='Linux'),mock.patch.object(p.platform,'machine',return_value='x86_64'),mock.patch.object(p.platform,'node',return_value='ed6c0673f5cb'),mock.patch.object(p.os,'geteuid',return_value=0):
   return p.inspect(arm,self.release_sha if release_sha is None else release_sha,controller_sha,identity or {'pid':100,'startTicks':1000,'commandSha256':p.argv_sha(self.entries[0]['expectedArguments'])})
 def test_closed_pass_binds_four_owned_and_controller_strict_absence(self):
  v=self.call();self.assertTrue(v['closedGate']);self.assertTrue(v['allFourOwnedJvmsStrictlyPidAbsent']);self.assertFalse(v['archiveFullHashReadHere']);self.assertEqual(4,len(v['ownership']));self.assertEqual(self.protected,v['protectedFinalValues']);self.assertFalse(v['nextArmExists'])
 def test_active_controller_reads_only_launch_register(self):
  v=self.call({100:'REGISTERED_IDENTITY_RUNNING'});self.assertFalse(v['closedGate']);self.assertEqual(['arm-1-execution-register.json'],self.reads)
 def test_zombie_reused_and_live_owned_identity_do_not_authorize_collection(self):
  for pid in (100,103):
   for state in ('PID_REUSED_DIFFERENT_START_TICKS','REGISTERED_IDENTITY_ZOMBIE_NOT_RUNNING','REGISTERED_IDENTITY_RUNNING'):
    with self.subTest(pid=pid,state=state):self.assertFalse(self.call({pid:state})['closedGate'])
 def test_foreign_java_or_pg_blocks_closed_gate(self):self.assertFalse(self.call(foreign=[{'pid':999}])['closedGate'])
 def test_failed_outcome_preserved_for_failure_collection(self):
  self.completion['passed']=False;self.completion['errors']=[{'phase':'fixture-failure'}];v=self.call();self.assertFalse(v['closedGate']);self.assertTrue(v['safeForReadOnlyFailureCollection']);self.assertEqual('CLOSED_FAILED_OUTCOME',v['state'])
 def test_pending_or_forged_launch_register_rejected(self):
  old=self.entries;self.entries=self.entries[:2];self.assertFalse(self.call()['closedGate']);self.entries=old;self.entries[-1]['observedCommandSha256']='0'*64;self.assertRaises(ValueError,self.call)
 def test_exact_external_pid_ticks_and_argv_are_mandatory(self):
  expected={'pid':100,'startTicks':1000,'commandSha256':p.argv_sha(self.entries[0]['expectedArguments'])}
  for change in ({'pid':999},{'startTicks':999},{'startTicks':True},{'commandSha256':'f'*64}):
   with self.subTest(change=change):self.assertRaises(ValueError,self.call,identity=dict(expected,**change))
 def test_root_frozen_sha_and_single_arm_are_mandatory(self):
  for key,value in [('arm',2),('controller_sha',''),('controller_sha','f'*64),('release_sha','F'*64),('release_sha','f'*64)]:
   with self.subTest(key=key):self.assertRaises(ValueError,self.call,**{key:value})
 def test_fixed_registration_and_workload_cannot_drift(self):
  for key,value in [('expectedTrailingCommands',0),('arrivals',6400),('rate',501),('workloadPreset','short'),('readWindow',1)]:
   old=self.reg[key];self.reg[key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,self.call)
   self.reg[key]=old
 def test_strict_cpu_scheduler_and_all_terminal_counters_required(self):
  for key,value in [('schedulerTimingValid',False),('schedulerLatenessOver20ms',1),('unknownObserved',1),('unknownFinal',1),('notSent',1),('maintenanceCycles',3),('completedLogicalReplies',33791),('duplicateOrOutOfRangeAcceptedOrderIds',1)]:
   old=self.summary[key];self.summary[key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,self.call)
   self.summary[key]=old
 def test_protected_receipt_and_actual_node_full_argv_cannot_drift(self):
  self.after['protectedOriginal']['postgres']['files']=988;self.assertRaises(ValueError,self.call);self.after['protectedOriginal']=copy.deepcopy(self.protected);self.nodes[1]['arguments'][1]='-Dvectormatch.retention.idleMaxParkNs=999999';self.assertRaises(ValueError,self.call)
 def test_force_or_numeric_pid_fallback_cannot_be_relabelled_closed(self):
  for key in ('forcedKill','numericPidSignalFallback'):
   self.stop[key]=True;self.assertFalse(self.call()['closedGate']);self.stop[key]=False
 def test_no_next_gate_and_no_mutation_network_signal_or_launch_api(self):
  tree=ast.parse(pathlib.Path(p.__file__).read_text());imports={n.names[0].name for n in tree.body if isinstance(n,ast.Import)};self.assertFalse(imports&{'subprocess','signal','socket','shutil'})
  attrs={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)};self.assertFalse(attrs&{'kill','killpg','unlink','rmtree','write_text','write_bytes','mkdir','Popen','run'})
  self.assertNotIn('prior-collection',pathlib.Path(p.__file__).read_text())

if __name__=='__main__':unittest.main(verbosity=2)
