"""Pure synthetic control-plane ownership guards; no process/remote actions."""
import ast,copy,hashlib,json,pathlib,tempfile,unittest
from unittest import mock
import inspect_closed_read_window32_arm as p

BASE=pathlib.Path(__file__).resolve().parent.parent
CONTROLLER=(pathlib.Path(__file__).resolve().parent/'fixtures/cpu_read_window32_abab.py').read_bytes()
CONTROLLER_SHA=hashlib.sha256(CONTROLLER).hexdigest()

class CloseGuards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.prep=pathlib.Path(self.tmp.name).resolve()/'prep';self.prep.mkdir();self.job=self.prep/'arm-1';self.job.mkdir();self.native=self.job/'idle-arm';self.archive=self.job/'pilot-after-clean-stop.tar.gz';self.archive.write_bytes(b'x')
  self.release=json.loads((pathlib.Path(__file__).resolve().parent/'fixtures/release.template.json').read_text());self.release.update(releaseReady=True,controllerSha256=CONTROLLER_SHA);self.release_bytes=json.dumps(self.release).encode();self.release_sha=hashlib.sha256(self.release_bytes).hexdigest()
  self.reg={'ports':42000,'readWindow':8,'appointedLeader':0,'sync':2,'profileSha256':p.PROFILE_SHA,'codeSha256':p.CODE_SHA,'retentionIdleSelection':{'maximumParkNs':100000},'lineage':'capacity-pilot-fixture','arrivals':33792,'rate':500,'batchCap':4,'archiveChunkBytes':6144,'eventFetchCount':32,'commonReadWindowEnvelope':True,'commonChunkEnvelope':False,'workloadPreset':'long-cuts-33792-v1','expectedFullCommandCuts':11,'expectedTrailingCommands':3,'equivalentFullLoadCutNumbers':list(range(2,12))}
  args=['/usr/bin/python3','-B',str(self.prep/'cpu_read_window32_abab.py'),'--arm','1','--release-sha256',self.release_sha,'--start-new']
  self.arm=1;self.prior=None
  self.entries=[{'state':'INTENT_NO_PID_YET','expectedArguments':args,'arm':1,'frozenReleaseSha256':self.release_sha},{'state':'SPAWNED_IDENTITY_PENDING','pid':100,'arm':1},{'pid':100,'startTicks':1000,'expectedArguments':args,'arm':1,'frozenReleaseSha256':self.release_sha,'observedCommandSha256':p.argv_sha(args),'observedExecArgvMatches':True,'stableStartTicks':True}]
  self.parent=self.identity(101,p.expected_parent(self.release,self.native,1000000,32,8));self.nodes=[self.identity(102+n,p.expected_node(self.release,self.native,self.reg,n,100000)) for n in range(3)]
  self.summary={'confirmedAcceptedUniqueOrders':33792,'notSent':0,'unknownObserved':0,'unknownFinal':0,'scheduledArrivals':33792,'releasedArrivals':33792,'completedLogicalReplies':33792,'ratePerSecond':500,'batchCap':4,'archiveChunkBytes':6144,'readWindow':8,'serverRejected':0,'duplicateOrOutOfRangeAcceptedOrderIds':0,'maintenanceCycles':12,'schedulerTimingValid':True,'schedulerLatenessOver20ms':0,'arrivalClockPausedForMaintenance':False}
  logs=[{'node':n,'warningPairCount':0,'afterSigtermWallTimeProven':False,'allLogLinesClassifiedAndRetained':True} for n in range(3)]
  self.completion={'arm':1,'ownerPollMaximumParkNs':1000000,'serverDriverMaximumParkNs':100000,'frozenReleaseSha256':self.release_sha,'allOwnedStopped':True,'passed':True,'errors':[],'result':{'passed':True,'arms':[{'ownerPollMaximumParkNs':1000000,'serverDriverMaximumParkNs':100000,'readWindow':8,'functional':{'passed':True,'actualSourceSummary':self.summary},'nodeLogClassifications':logs,'retainedPostCheckpointEosWarningPairs':0}]}}
  self.stop={'allOwnedStopped':True,'errors':[],'forcedKill':False,'numericPidSignalFallback':False,'reports':[{'role':'window-8-node-%d'%n,'record':v,'stopped':True} for n,v in enumerate(self.nodes)]}
  self.protected={'passed':True,'manifestSha256':p.PROTECTED_SHA,'nativeTrees':[{'files':18},{'files':19},{'files':20}],'postgres':{'files':989}}
  self.before={'controllerSha256':CONTROLLER_SHA,'baseSha256':'8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87','protectedOriginal':self.protected,'arm':1,'singleManualArmOnly':True,'noJavaStarted':True}
  self.after={'protectedOriginal':copy.deepcopy(self.protected),'archive':{'sameHostReadback':{'passed':True},'requiresIndependentCollectorStreamReadback':True,'archive':{'path':str(self.archive),'bytes':1,'sha256':'f'*64}}};self.reads=[]
  self.before.update(ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000)
  self.reg['ownerPollSelection']={'schema':'retention-owner-poll-selection-v1','property':'vectormatch.retention.ownerPollMaxParkNs','maximumParkNs':1000000,'factor':'owner poll requested park cap only','hardRealtimeGuaranteed':False}
  self.summary['ownerPollSelection']=copy.deepcopy(self.reg['ownerPollSelection'])
  self.summary['ownerPollActual']={'available':True,'source':'actual-constructed-owner-snapshot','ownerPollMaxParkNs':1000000,'requestedSleepOnly':True,'osLatenessBounded':False}
  self.completion['result']['arms'][0]['ownerPollAttestation']={'passed':True,'ownerPollMaximumParkNs':1000000,'serverDriverMaximumParkNs':100000,'ownerPropertyParentOnly':True,'selectionIntentAndConstructedOwnerSnapshotReconciled':True,'actualConfiguredIdleFactoryCreations':22,'hardRealtimeOrPerformanceClaimed':False}
  self.reg.update(commonEventFetchEnvelope=False,commonReadWindow32Envelope=True)
  self.summary.update(eventFetchCount=32,commonEventFetchEnvelope=False,commonReadWindow32Envelope=True)
  self.before.update(eventFetchCount=32,readWindow=8,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False)
  self.completion.update(eventFetchCount=32,readWindow=8,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False)
  self.completion['result']['arms'][0].update(eventFetchCount=32,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,completion={'eventFetchCount':32,'commonEventFetchEnvelope':False,'commonReadWindow32Envelope':True,'readWindow':8})
  self.completion['result']['arms'][0]['functional'].update(eventFetchCount=32,commonEventFetchEnvelope=False,commonReadWindow32Envelope=True,readWindow=8)
 def set_arm(self,arm):
  self.arm=arm;self.prior=None if arm==1 else'b'*64;maximum=p.OWNER_PARK_ORDER[arm-1]
  self.job=self.prep/('arm-'+str(arm));self.job.mkdir(exist_ok=True);self.native=self.job/'idle-arm';self.archive=self.job/'pilot-after-clean-stop.tar.gz'
  if not self.archive.exists():self.archive.write_bytes(b'x')
  args=['/usr/bin/python3','-B',str(self.prep/'cpu_read_window32_abab.py'),'--arm',str(arm),'--release-sha256',self.release_sha]
  if arm>1:args+=['--prior-collection-sha256',self.prior]
  args+=['--start-new']
  for row in self.entries:
   row['arm']=arm
   if 'expectedArguments'in row:row['expectedArguments']=args
  self.entries[2]['observedCommandSha256']=p.argv_sha(args)
  self.parent=self.identity(101,p.expected_parent(self.release,self.native,maximum,p.EVENT_PAGE_ORDER[arm-1],p.READ_WINDOW_ORDER[arm-1]))
  self.nodes=[self.identity(102+n,p.expected_node(self.release,self.native,self.reg,n,maximum))for n in range(3)]
  self.stop['reports']=[{'role':'window-8-node-%d'%n,'record':v,'stopped':True}for n,v in enumerate(self.nodes)]
  self.reg['ownerPollSelection']['maximumParkNs']=maximum
  self.summary['ownerPollSelection']=copy.deepcopy(self.reg['ownerPollSelection']);self.summary['ownerPollActual']['ownerPollMaxParkNs']=maximum
  self.completion.update(arm=arm,ownerPollMaximumParkNs=maximum);self.completion['result']['arms'][0]['ownerPollMaximumParkNs']=maximum;self.completion['result']['arms'][0]['ownerPollAttestation']['ownerPollMaximumParkNs']=maximum
  self.before.update(arm=arm,ownerPollMaximumParkNs=maximum);self.after['archive']['archive']['path']=str(self.archive)
  window=p.READ_WINDOW_ORDER[arm-1]
  self.reg['readWindow']=window;self.summary['readWindow']=window;self.before['readWindow']=window;self.completion['readWindow']=window
  for container in [self.completion['result']['arms'][0],self.completion['result']['arms'][0]['completion'],self.completion['result']['arms'][0]['functional']]:container['readWindow']=window
  self.stop['reports']=[{'role':'window-%d-node-%d'%(window,n),'record':v,'stopped':True}for n,v in enumerate(self.nodes)]
  page=p.EVENT_PAGE_ORDER[arm-1];self.reg['eventFetchCount']=page;self.summary['eventFetchCount']=page;self.before['eventFetchCount']=page;self.completion['eventFetchCount']=page
  self.completion['result']['arms'][0]['eventFetchCount']=page;self.completion['result']['arms'][0]['functional']['eventFetchCount']=page;self.completion['result']['arms'][0]['completion']['eventFetchCount']=page
 def identity(self,pid,args):return {'pid':pid,'startTicks':pid*10,'arguments':args,'commandSha256':p.argv_sha(args)}
 def bounded(self,path,*unused,**kw):
  self.reads.append(path.name)
  if path.name=='arm-%d-execution-register.json'%self.arm:return b'\n'.join(json.dumps(v).encode() for v in self.entries)+b'\n'
  if path.name=='release.json':return self.release_bytes
  if path.name=='cpu_read_window32_abab.py':return CONTROLLER
  raise AssertionError('Unexpected bounded read '+str(path))
 def js(self,path,*unused,**kw):
  self.reads.append(path.name);name=path.name
  values={'BENCHMARK_BLOCKED.json':None,'completion.json':self.completion,'python-owned-stop.json':self.stop,'identity-observation-000.json':{'role':'pilot-parent','origin':'independent-direct-child-proc','kernelIdentity':self.parent},'parent-launch-handle.json':{'pid':self.parent['pid'],'expectedArguments':self.parent['arguments'],'expectedCommandSha256':self.parent['commandSha256']},'registration.json':self.reg,'before.json':self.before,'after-clean-stop.json':self.after}
  if name in values:return values[name]
  if name.startswith('node-'):
   v=self.nodes[int(name.split('-')[1])];return {'pid':v['pid'],'linuxStartTicks':v['startTicks'],'linuxCommandSha256':v['commandSha256'],'command':v['arguments'][0],'arguments':v['arguments'][1:]}
  raise AssertionError('Unexpected JSON read '+str(path))
 def call(self,states=None,foreign=None,identity=None,arm=None,controller_sha=CONTROLLER_SHA,release_sha=None,prior_gate_sha='USE_FIXTURE'):
  states=states or {}
  def status(v):
   state=states.get(v['pid'],'PID_ABSENT');return {'pid':v['pid'],'originalIdentityRunning':state=='REGISTERED_IDENTITY_RUNNING','observation':state}
  with mock.patch.object(p,'PREP',self.prep),mock.patch.object(p,'bounded',side_effect=self.bounded),mock.patch.object(p,'js',side_effect=self.js),mock.patch.object(p,'identity_state',side_effect=status),mock.patch.object(p,'live_jvm_pg',return_value=(foreign or [],5)),mock.patch.object(p.platform,'system',return_value='Linux'),mock.patch.object(p.platform,'machine',return_value='x86_64'),mock.patch.object(p.platform,'node',return_value='ed6c0673f5cb'),mock.patch.object(p.os,'geteuid',return_value=0):
   return p.inspect(self.arm if arm is None else arm,self.release_sha if release_sha is None else release_sha,controller_sha,identity or {'pid':100,'startTicks':1000,'commandSha256':p.argv_sha(self.entries[0]['expectedArguments'])},self.prior if prior_gate_sha=='USE_FIXTURE'else prior_gate_sha)
 def test_closed_pass_binds_four_owned_and_controller_strict_absence(self):
  v=self.call();self.assertTrue(v['closedGate']);self.assertTrue(v['allFourOwnedJvmsStrictlyPidAbsent']);self.assertFalse(v['archiveFullHashReadHere']);self.assertEqual(4,len(v['ownership']));self.assertEqual(self.protected,v['protectedFinalValues']);self.assertFalse(v['nextArmStartedByProbe'])
 def test_active_controller_reads_only_launch_register(self):
  v=self.call({100:'REGISTERED_IDENTITY_RUNNING'});self.assertFalse(v['closedGate']);self.assertEqual(['arm-1-execution-register.json'],self.reads)
 def test_zombie_reused_and_live_owned_identity_do_not_authorize_collection(self):
  for pid in (100,103):
   for state in ('PID_REUSED_DIFFERENT_START_TICKS','REGISTERED_IDENTITY_ZOMBIE_NOT_RUNNING','REGISTERED_IDENTITY_RUNNING'):
    with self.subTest(pid=pid,state=state):self.assertFalse(self.call({pid:state})['closedGate'])
 def test_live_owned_identity_never_reads_completion_or_summary(self):
  for pid in (101,102,103,104):
   self.reads=[];v=self.call({pid:'REGISTERED_IDENTITY_RUNNING'});self.assertFalse(v['closedGate'])
   self.assertNotIn('completion.json',self.reads);self.assertNotIn('before.json',self.reads);self.assertNotIn('after-clean-stop.json',self.reads)
 def test_all_four_manual_modes_bind_parent_only_owner_and_previous_gate(self):
  for arm in (1,2,3,4):
   self.set_arm(arm);v=self.call();self.assertTrue(v['closedGate']);self.assertEqual(p.OWNER_PARK_ORDER[arm-1],v['ownerPollMaximumParkNs']);self.assertEqual(100000,v['serverDriverMaximumParkNs']);self.assertEqual(str(self.job),v['job'])
   for node in self.nodes:self.assertFalse(any('ownerPollMaxParkNs'in value for value in node['arguments']))
   if arm>1:self.assertRaises(ValueError,self.call,prior_gate_sha=None)
 def test_constructed_owner_proof_is_required_after_pid_absence(self):
  for key,value in [('actualConfiguredIdleFactoryCreations',21),('ownerPropertyParentOnly',False),('ownerPollMaximumParkNs',100000),('hardRealtimeOrPerformanceClaimed',True)]:
   row=self.completion['result']['arms'][0]['ownerPollAttestation'];old=row[key];row[key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,self.call)
   row[key]=old
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
  for key,value in [('arm',0),('arm',5),('arm',True),('controller_sha',''),('controller_sha','f'*64),('release_sha','F'*64),('release_sha','f'*64)]:
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
  self.assertNotIn('start-new-session',pathlib.Path(p.__file__).read_text())

 def test_actual_page_wrong_in_any_control_container_rejected(self):
  self.set_arm(2)
  arm=self.completion['result']['arms'][0]
  for row in [self.reg,self.summary,self.before,self.completion,arm,arm['completion'],arm['functional']]:
   old=row['eventFetchCount'];row['eventFetchCount']=16
   with self.subTest(container=id(row)),self.assertRaises(ValueError):self.call()
   row['eventFetchCount']=old
 def test_common32_envelope_is_mandatory_and_common_event_envelope_forbidden(self):
  for row in [self.reg,self.summary,self.completion['result']['arms'][0]['functional'],self.completion['result']['arms'][0]['completion']]:
   row['commonEventFetchEnvelope']=True
   with self.assertRaises(ValueError):self.call()
   row['commonEventFetchEnvelope']=False
   row['commonReadWindow32Envelope']=False
   with self.assertRaises(ValueError):self.call()
   row['commonReadWindow32Envelope']=True
 def test_selected_window_required_in_every_closed_container(self):
  for arm in (1,2,3,4):
   self.set_arm(arm);value=self.call();window=p.READ_WINDOW_ORDER[arm-1]
   self.assertEqual(window,value['readWindow']);self.assertEqual(32,value['eventFetchCount'])
   containers=[self.reg,self.summary,self.before,self.completion,self.completion['result']['arms'][0],self.completion['result']['arms'][0]['completion'],self.completion['result']['arms'][0]['functional']]
   for row in containers:
    old=row['readWindow'];row['readWindow']=32 if window==8 else 8
    with self.subTest(arm=arm,container=id(row)),self.assertRaises(ValueError):self.call()
    row['readWindow']=old
 def test_common32_flags_and_fixed_page_cannot_drift_in_all_containers(self):
  containers=[self.reg,self.summary,self.before,self.completion,self.completion['result']['arms'][0],self.completion['result']['arms'][0]['completion'],self.completion['result']['arms'][0]['functional']]
  for row in containers:
   for key,value in [('commonReadWindow32Envelope',False),('commonEventFetchEnvelope',True),('eventFetchCount',16)]:
    old=row[key];row[key]=value
    with self.subTest(container=id(row),key=key),self.assertRaises(ValueError):self.call()
    row[key]=old
if __name__=='__main__':unittest.main(verbosity=2)

