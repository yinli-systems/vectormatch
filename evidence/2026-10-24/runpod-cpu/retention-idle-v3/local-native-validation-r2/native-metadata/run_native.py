#!/usr/bin/env python3
"""LOCAL direct installed-JAR functional arms. Never signals processes or overwrites an attempt."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,socket,subprocess,sys,time,traceback
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
WORK=OUT.parents[2]
BASE=WORK.parents[3]
VALIDATION=OUT.parent
DIST=VALIDATION/'units-r4/artifact-state/distribution/lib'
JAVA=(BASE/'.tools/jdk/bin/java').resolve()
JDK=JAVA.parent.parent
SOURCE_COMMIT='7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23'
MAX_ALLOC=589327865
FREE_FLOOR=1073741824
ARCHIVE_RESERVE=2*MAX_ALLOC+128*1024*1024
TIMEOUT_SECONDS=420

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def write(path,value):
 with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def require(value,message):
 if not value:raise AssertionError(message)
def metadata(path):
 require(path.is_file() and not path.is_symlink() and path.stat().st_size<=1024*1024,'Unsafe metadata: '+str(path))
 return json.loads(path.read_text())
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def pgrep():
 p=subprocess.run(['/usr/bin/pgrep','-fl','io.vectormatch.cluster.Retention'],capture_output=True,text=True)
 require(p.returncode in (0,1),'pgrep failed')
 require(len(p.stdout.encode())<128*1024,'Process inventory bound')
 return {'returnCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def ps(pid):
 p=subprocess.run(['/bin/ps','-p',str(pid),'-ww','-o','pid=','-o','lstart=','-o','command='],capture_output=True,text=True)
 require(p.returncode in (0,1) and len(p.stdout.encode())<128*1024,'Bounded exact-PID ps failed')
 return {'pid':pid,'returnCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
def check_sources():
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORK,text=True).strip()==SOURCE_COMMIT,'Source commit changed')
 require(not subprocess.check_output(['git','status','--porcelain'],cwd=WORK,text=True),'Source worktree dirty')
 for row in FROZEN['paths']:require(sha(WORK/row['path'])==row['sha256'],'Source input changed')
 for row in JARS:require(sha(Path(row['path']))==row['sha256'],'Installed JAR changed')
def free_guard(remaining):
 free=shutil.disk_usage(WORK).free;required=FREE_FLOOR+remaining*MAX_ALLOC+ARCHIVE_RESERVE
 require(free>=required,'Native plus closed-archive reserve/floor unavailable')
 return {'freeBytes':free,'requiredBytes':required,'remainingNativeArmAllowanceBytes':remaining*MAX_ALLOC,'closedArchiveReserveBytes':ARCHIVE_RESERVE,'freeFloorBytes':FREE_FLOOR}
def port_guard():
 bound=[]
 try:
  for node in range(3):
   for offset in range(1,6):
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',42000+node*100+offset));bound.append(sock)
 finally:
  for sock in bound:sock.close()
def validate_idle(actual,maximum,node,pid):
 require(actual['schema']=='retention-idle-actual-v2' and actual['node']==node and actual['pid']==pid,'Actual idle association differs')
 require(actual['selection']['maximumParkNs']==maximum and actual['selection']['property']=='vectormatch.retention.idleMaxParkNs','Actual idle selection differs')
 require(actual['instancesDistinct'] is True and actual['sleepDurationMeasured'] is False and actual['hardRealtimeGuaranteed'] is False and actual['runningAgentThreadCountIndependentlyObserved'] is False,'Idle witness scope differs')
 expected={'owner-driver-shared':1} if node<0 else {'driver-shared':1,'archive-shared':2,'consensus':2,'service':2}
 require(actual['expectedConsumptionCounts']==actual['observedConsumptionCounts']==expected and set(actual['selectedLogicalRoles'])==set(expected),'Per-role exact factory inventory differs')
 instances=actual['instances'];total=sum(expected.values())
 require(len(instances)==total and {v['instanceOrdinal'] for v in instances}==set(range(1,total+1)),'Distinct actual creation inventory differs')
 consumers={'archive-shared':('io.aeron.archive.ArchiveConductor','io.aeron.archive.Archive'),'consensus':('io.aeron.cluster.ConsensusModuleAgent','io.aeron.cluster.ConsensusModule'),'service':('io.aeron.cluster.service.ClusteredServiceAgent','io.aeron.cluster.service.ClusteredServiceContainer')}
 contexts={'archive-shared':'io.aeron.archive.Archive$Context','consensus':'io.aeron.cluster.ConsensusModule$Context','service':'io.aeron.cluster.service.ClusteredServiceContainer$Context'}
 observed={role:set() for role in expected}
 for row in instances:
  role=row['role'];ordinal=row['roleConsumptionOrdinal'];require(role in expected and 1<=ordinal<=expected[role] and ordinal not in observed[role],'Per-role consumption ordinal differs');observed[role].add(ordinal)
  yields=5 if 'driver' in role else 20
  expected_text=f'BackoffIdleStrategy{{alias=backoff, maxSpins=10, maxYields={yields}, minParkPeriodNs=1000, maxParkPeriodNs={maximum}}}'
  require(row['strategyClass']=='org.agrona.concurrent.BackoffIdleStrategy' and row['strategyDescription']==expected_text,'Actual supplied strategy differs')
  require((row['maximumSpins'],row['maximumYields'],row['minimumParkNs'],row['maximumParkNs'],row['roleConsumptionBound'])==(10,yields,1000,maximum,expected[role]),'Actual configured tuple/bound differs')
  trace=row['factoryCallerStack'];require(1<=len(trace)<=5 and row['factoryCallerFrameLimit']==5 and row['factoryCallerTextByteLimit']==256,'Caller trace bound differs')
  for frame in trace:require(len(frame['class'].encode())<=256 and len(frame['method'].encode())<=256,'Caller strings exceed byte bound')
  require(not trace[0]['classTruncated'] and not trace[0]['methodTruncated'],'Head consumer frame truncated')
  if 'driver' in role:
   expected_class='io.vectormatch.cluster.RetentionNodeMainV3' if node>=0 else 'io.vectormatch.cluster.RetentionBatchAeronTransportV3'
   require(trace[0]['class']==expected_class,'Direct driver creator differs')
   require(row['association']=='actual installed shared-driver getter object','Direct driver association differs')
  else:
   require(len(trace)>=2 and trace[0]['class']==contexts[role] and trace[0]['method']=='idleStrategy','Observed factory context call differs')
   require(trace[1]['class']==consumers[role][ordinal-1] and trace[1]['method']=='<init>','Observed pinned constructor consumer differs')
   require('source-ordered factory consumption' in row['association'],'Factory/runner inference scope differs')
  require(row['sourceDerivedIntendedUse'],'Missing source-derived intended use')
 require(all(observed[role]==set(range(1,count+1)) for role,count in expected.items()),'Per-role creation sequence incomplete')
 return {'node':node,'pid':pid,'maximumRequestedParkNs':maximum,'selectedLogicalRoles':sorted(expected),'factoryCreations':total,'perRoleConsumptions':expected,'configuredObjectsAndCallerStacksAttested':True,'sleepDurationMeasured':False,'activeThreadCountClaimed':False}
def inspect_arm(arm,maximum,parent_pid,returncode):
 require(returncode==0,'Native parent exit must be zero')
 completion=metadata(arm/'completion.json');functional=metadata(arm/'functional-result.json');summary=metadata(arm/'load/load-result.json');cfg=metadata(arm/'load/configuration.json');reg=metadata(arm/'registration.json');stopped=metadata(arm/'owned-stop.json');reference=metadata(arm/'physical-reference-reconciliation.json');final=metadata(arm/'final-position.json')
 require(completion['passed'] is True and completion['allOwnedStopped'] is True and stopped['allOwnedStopped'] is True and stopped['forcedKill'] is False,'Owned closure failed')
 require(len(stopped['reports'])==3 and all(v.get('stopped') is True or v.get('alreadyExited') is True for v in stopped['reports']),'Three node close reports required')
 require(functional['passed'] is True and functional['allThreeSnapshotLogsMatched'] is True and functional['noCapacityPromotion'] is True and reference['passed'] is True,'Full functional/reference/snapshot proof required')
 require((cfg['arrivals'],cfg['ratePerSecond'],cfg['batchCap'],cfg['archiveChunkBytes'],cfg['eventFetchCount'],cfg['readWindow'])==(6400,500,4,6144,16,8),'Fixed workload differs')
 require(reg['appointedLeader']==0 and reg['sync']==2 and reg['ports']==42000 and reg['codeSha256']==cfg['actualCodeSha256'],'Fixed leader/sync/ports/code differs')
 require(summary['confirmedAcceptedUniqueOrders']==6400 and summary['notSent']==0 and summary['unknownFinal']==0 and summary['maintenanceCycles']==3,'Original orders/cycles not closed')
 require(cfg['retentionIdleSelection']==reg['retentionIdleSelection']==summary['retentionIdleSelection']==completion['retentionIdleSelection'],'Selection metadata closure differs')
 require(cfg['retentionIdleSelection']['maximumParkNs']==maximum,'Registered idle arm differs')
 plan=metadata(arm/'load/admission-plan.json')
 require(plan['maximumRawTraceBytes']==38033404 and plan['maximumAllocatedGrowthBytes']==MAX_ALLOC,'Unchanged admitted byte envelope differs')
 node_idle=[];node_observations=[]
 for node in range(3):
  identity=metadata(arm/f'node-{node}-identity.json');actual=metadata(arm/f'node-{node}/idle-observations/idle-000.actual.json');intent=metadata(arm/f'node-{node}/idle-observations/idle-000.intent.json')
  require(intent['pid']==identity['pid'] and intent['selection']==actual['selection'],'Reserved/actual node identity differs')
  require([v for v in identity['arguments'] if v.startswith('-Dvectormatch.retention.idleMaxParkNs=')]==[f'-Dvectormatch.retention.idleMaxParkNs={maximum}'],'Actual child argv idle selection differs')
  require('-Daeron.cluster.appointed.leader.id=0' in identity['arguments'] and Path(identity['command']).resolve()==JAVA,'Actual child executable/leader differs')
  text=(arm/f'node-{node}.log').read_text();require(len(text.encode())<=4*1024*1024,'Node log bound')
  expected=f"VECTOR_V3_NODE_READY node={node} pid={identity['pid']} profile={cfg['profileSha256']} lineage={cfg['lineage']} code={cfg['actualCodeSha256']}"
  require(text.count(expected)==1 and text.count('VECTOR_V3_IDLE_ATTESTATION ')==1 and 'sync=2 mtu=1248 preparedArchiveCacheEnabled=true' in text,'Node actual readiness differs')
  checkpoint=f"VECTOR_V3_SNAPSHOT_WRITTEN profile={cfg['profileSha256']} lineage={cfg['lineage']} hash={final['combinedSha256']}"
  require(checkpoint in text and 'Exception' not in text and 'ERROR' not in text,'Node checkpoint/error log differs')
  process=ps(identity['pid']);require(process['returnCode']==1 and not process['stdout'].strip(),'Owned node PID still present after program closure; no signal sent')
  node_observations.append({'identity':identity,'postClosePs':process,'snapshotSha256':final['combinedSha256']})
  node_idle.append(validate_idle(actual,maximum,node,identity['pid']))
 samples=metadata(arm/'load/transport-observations.json');require(samples,'Missing owner transport samples')
 for sample in samples:
  require(sample['leaderMemberId']==0 and sample['leadershipTermId']==0 and sample['newLeaderEvents']==[] and sample['mtuLength']==1248,'Load leader/term/MTU changed')
  validate_idle(sample['retentionIdlePolicy'],maximum,-1,parent_pid)
 require(reference['actualRepliesCompared']==summary['physicalOfferTape']['recordedReplies'],'Every raw callback/reference reconciliation count differs')
 return {'passed':True,'localFunctionalOnly':True,'speedupClaimed':False,'sourceScope':'Source functional reference compares physical admitted original wires to the same candidate service adapter, not an independent matching algorithm. Independent raw correlation/prefix audit follows closure.','maximumRequestedParkNs':maximum,'actualCodeSha256':cfg['actualCodeSha256'],'lineage':cfg['lineage'],'functionalResultSha256':sha(arm/'functional-result.json'),'reference':reference,'nodeIdleObjects':node_idle,'ownerIdleSamples':len(samples),'nodeStopObservations':node_observations,'schedulerTimingValidReported':summary['schedulerTimingValid'],'parentExitCode':returncode}

FROZEN=metadata(VALIDATION/'SOURCE_FROZEN_R2.json')
JARS=[]
for name in ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','agrona-2.6.1.jar']:
 p=DIST/name;st=p.stat();JARS.append({'path':str(p),'bytes':st.st_size,'sha256':sha(p),'mode':st.st_mode,'uid':st.st_uid,'gid':st.st_gid})
check_sources();port_guard();before_processes=pgrep();require(not before_processes['stdout'].strip(),'Existing local retention JVMs; do not launch')
ARMS=OUT/'arms';ARMS.mkdir()
common=[str(JAVA),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xms128m','-Xmx512m']
commands=[]
for maximum in [1000000,100000]:
 arm=ARMS/f'park-{maximum}';require(not arm.exists(),'Native arm must be fresh')
 argv=[*common,f'-Dvectormatch.retention.idleMaxParkNs={maximum}','-cp',os.pathsep.join(r['path'] for r in JARS),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',str(arm),'idle-window8','42000']
 commands.append({'maximumParkNs':maximum,'root':str(arm),'argv':argv,'argvNulSha256':hashlib.sha256(b'\0'.join(s.encode() for s in argv)+b'\0').hexdigest()})
reg={'schema':'retention-idle-local-native-registration-v1','createdAtUTC':stamp(),'sourceCommit':SOURCE_COMMIT,'sourceFreezeSha256':sha(VALIDATION/'SOURCE_FROZEN_R2.json'),'guardCompletionSha256':sha(VALIDATION/'units-r4/completion.json'),'jdkPins':[{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in [JAVA,JAVA.parent/'javac',JDK/'release']],'jarPins':JARS,'commands':commands,'diskBefore':free_guard(2),'portsPreflightBoundAndReleased':True,'processesBefore':before_processes,'timeoutSecondsPerArm':TIMEOUT_SECONDS,'timeoutPolicy':'Preserve active ownership and return failure; do not signal, escalate or launch another arm.','scope':'LOCAL direct-installed-JAR functional verification only; no capacity, realtime SLA or speedup claim.'}
write(OUT/'registration.json',reg)
print(json.dumps({'nativeRegistration':str(OUT/'registration.json'),'sha256':sha(OUT/'registration.json'),'state':'REGISTERED'}),flush=True)
env=os.environ.copy()
for name in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:env.pop(name,None)
results=[]
try:
 for index,command in enumerate(commands):
  check_sources();port_guard();require(not pgrep()['stdout'].strip(),'Prior retention process still present; no new arm')
  maximum=command['maximumParkNs'];arm=Path(command['root']);control=OUT/f'arm-{maximum}-process';control.mkdir()
  write(control/'before.json',{'atUTC':stamp(),'disk':free_guard(2-index),'fresh':not arm.exists(),'argvNulSha256':command['argvNulSha256']})
  start=time.monotonic()
  with (control/'stdout.txt').open('x') as stdout,(control/'stderr.txt').open('x') as stderr:
   child=subprocess.Popen(command['argv'],cwd=WORK,env=env,stdout=stdout,stderr=stderr)
   write(control/'parent-identity.json',{'pid':child.pid,'startedAtUTC':stamp(),'launchArgv':command['argv'],'launchArgvNulSha256':command['argvNulSha256'],'ownership':'direct unreaped subprocess.Popen child handle; ps is supplementary','psAfterLaunch':ps(child.pid)})
   print(json.dumps({'maximumParkNs':maximum,'parentPid':child.pid,'state':'STARTED'}),flush=True)
   while True:
    try:rc=child.wait(timeout=10);break
    except subprocess.TimeoutExpired:
     elapsed=time.monotonic()-start
     print(json.dumps({'maximumParkNs':maximum,'parentPid':child.pid,'state':'ACTIVE','elapsedSeconds':round(elapsed,1)}),flush=True)
     if elapsed>TIMEOUT_SECONDS:
      write(control/'DEADLINE_ACTIVE.json',{'atUTC':stamp(),'elapsedSeconds':elapsed,'parentPid':child.pid,'ps':ps(child.pid),'noSignalSent':True,'nextArmForbidden':True})
      raise RuntimeError('Local native deadline; active evidence preserved, no signal or next arm')
  write(control/'exit.json',{'atUTC':stamp(),'returnCode':rc,'elapsedSeconds':time.monotonic()-start,'noSignalSent':True,'parentExitIndependentlyObserved':True})
  result=inspect_arm(arm,maximum,child.pid,rc);write(control/'functional-inspection.json',result);results.append(result)
  print(json.dumps({'maximumParkNs':maximum,'state':'CLOSED_FUNCTIONAL_PASS','actualCodeSha256':result['actualCodeSha256']}),flush=True)
 check_sources();require(len({r['actualCodeSha256'] for r in results})==1,'Same installed distribution fingerprint differs between arms')
 after_processes=pgrep();require(not after_processes['stdout'].strip(),'Retention JVM remains after pair; preserve evidence')
 result={'passed':True,'allOwnedStopped':True,'atUTC':stamp(),'localFunctionalOnly':True,'speedupClaimed':False,'hardRealtimeGuaranteed':False,'arms':results,'afterProcesses':after_processes,'sourceAndJarsUnchanged':True,'fullClosedArchiveAndRawAuditPending':True}
 write(OUT/'native-pair-completion.json',result);print(json.dumps({'state':'PAIR_CLOSED','passed':True,'completionSha256':sha(OUT/'native-pair-completion.json')}),flush=True)
except BaseException as failure:
 write(OUT/'native-failure.json',{'atUTC':stamp(),'type':type(failure).__name__,'traceback':traceback.format_exc(),'completedArms':results,'noSignalSent':True,'noRetryOrOverwrite':True})
 print(json.dumps({'state':'FAILED_PRESERVED','type':type(failure).__name__,'message':str(failure)}),flush=True)
 raise
