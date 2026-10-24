"""One fixed LOCAL functional arm. --prepare never launches; --start-new is exclusive and never retried."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,socket,stat,subprocess,sys,time,traceback
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;VALIDATION=OUT.parent;WORK=OUT.parents[2];BASE=WORK.parents[3]
JAVA=(BASE/'.tools/jdk/bin/java').resolve();JDK=JAVA.parent.parent
SOURCE_COMMIT='bcf49c10b77a14708b53d3fc6c115a6a3b834408'
CODE='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
MAX_ALLOC=757122377;FREE_FLOOR=1024**3;ARCHIVE_RESERVE=MAX_ALLOC+128*1024**2
ARM=OUT/'arm-100000-long-cuts';DIST=WORK/'cluster/build/install/cluster/lib';MAX_SECONDS=420

def require(v,m):
 if not v:raise AssertionError(m)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def pin(p):
 s=p.stat();return dict(path=str(p),bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
def write(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def metadata(p):
 require(p.is_file() and not p.is_symlink() and p.stat().st_size<=1024**2,'Bounded regular metadata required: '+str(p))
 return json.loads(p.read_text())
def ps(pid):
 p=subprocess.run(['/bin/ps','-p',str(pid),'-ww','-o','pid=','-o','lstart=','-o','command='],capture_output=True,text=True)
 require(p.returncode in (0,1) and len(p.stdout.encode())<128*1024,'Exact PID ps failed/bound')
 return dict(pid=pid,returnCode=p.returncode,stdout=p.stdout,stderr=p.stderr)
def processes():
 p=subprocess.run(['/usr/bin/pgrep','-fl','io.vectormatch.cluster.Retention'],capture_output=True,text=True)
 require(p.returncode in (0,1) and len(p.stdout.encode())<128*1024,'Process inventory failed/bound')
 return dict(returnCode=p.returncode,stdout=p.stdout,stderr=p.stderr)
def ports():
 sockets=[]
 try:
  for node in range(3):
   for offset in range(1,6):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',42000+node*100+offset));sockets.append(s)
 finally:
  for s in sockets:s.close()
def sources():
 require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORK,text=True).strip()==SOURCE_COMMIT,'Source commit changed')
 require(not subprocess.check_output(['git','status','--porcelain'],cwd=WORK,text=True),'Source worktree dirty')
 final=metadata(VALIDATION/'SOURCE_FROZEN_R1.json')
 for row in final['paths']:require(sha(WORK/row['path'])==row['sha256'],'Final source changed')
 original=metadata(VALIDATION/'units-r1/source-freeze.json')
 for path,row in original.items():
  if path!='cluster/RETENTION_LONG_CUTS_V3.md':require(sha(WORK/path)==row['sha256'],'Registered test/build/source changed')
def disk():
 free=shutil.disk_usage(WORK).free;minimum=FREE_FLOOR+MAX_ALLOC+ARCHIVE_RESERVE
 require(free>=minimum,'Free floor + prospective growth + closed archive reserve unavailable')
 return dict(freeBytes=free,requiredBytes=minimum,sourceAllocatedGrowthBound=MAX_ALLOC,freeFloor=FREE_FLOOR,closedArchiveReserve=ARCHIVE_RESERVE)
def sample():
 files=dirs=allocated=logical=0
 if ARM.exists():
  for p in [ARM,*ARM.rglob('*')]:
   st=p.lstat();require(stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode),'Unsafe owned type')
   allocated+=st.st_blocks*512;files+=int(stat.S_ISREG(st.st_mode));dirs+=int(stat.S_ISDIR(st.st_mode));logical+=st.st_size if stat.S_ISREG(st.st_mode) else 0
   require(files+dirs<=2048,'Existing Java owned path bound exceeded')
 return dict(atUTC=stamp(),observedMonotonicNs=time.monotonic_ns(),files=files,directories=dirs,allocatedBytes=allocated,logicalBytes=logical,usableBytes=shutil.disk_usage(WORK).free,scope='Supporting sampled wrapper accounting; actual Java source enforces its own unchanged disk stop bounds')

from idle_inventory import validate_idle
validate_idle.__globals__.update(require=require)
from shutdown_warning import classify

def prepare():
 sources();ports();before=processes();require(not before['stdout'].strip(),'Existing retention JVM; no launch')
 observation=VALIDATION/'distribution-observation-r1/actual-distribution-observation.json'
 require(sha(observation)=='185b06b904f0d498f88371b621f4f443b99e03b87790b9c61811f724fb412ec4','Actual-JAR plan observation changed')
 observed=metadata(observation);plan=observed['workloads']['LONG_CUTS']['plan']
 require(observed['actualCodeFingerprint']==CODE and plan['admitted'] is True and plan['maximumRawTraceBytes']==185514924 and plan['maximumAllocatedGrowthBytes']==MAX_ALLOC,'Actual long plan differs')
 expected=metadata(VALIDATION/'distribution-observation-r1/registration.json')['jars']
 jars=[pin(DIST/name) for name in ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','agrona-2.6.1.jar']]
 require([(r['bytes'],r['sha256']) for r in jars]==[(r['bytes'],r['sha256']) for r in expected],'Actual installed JARs differ')
 argv=[str(JAVA),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xms128m','-Xmx512m','-Dvectormatch.retention.idleMaxParkNs=100000','-cp',os.pathsep.join(r['path'] for r in jars),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',str(ARM),'idle-window8-long-cuts','42000']
 require(not ARM.exists(),'New native arm must be fresh')
 helpers=[pin(OUT/n) for n in ['run_native.py','idle_inventory.py','shutdown_warning.py','capture_closed.py','COPIED_HELPER_PROVENANCE.json','PLAN.md']]
 write(OUT/'registration.json',dict(schema='retention-long-cuts-local-native-v1',atUTC=stamp(),sourceCommit=SOURCE_COMMIT,actualCodeFingerprint=CODE,sourceFreeze=pin(VALIDATION/'SOURCE_FROZEN_R1.json'),sourceReview=pin(BASE/'runtime/cloud/cpu-20261024/long-cuts-root-source-review-r1/ROOT_REVIEW.json'),jdk=[pin(p) for p in [JAVA,JAVA.parent/'javac',JDK/'release']],jars=jars,helpers=helpers,actualPlanInput=pin(observation),actualPlan=plan,argv=argv,argvNulSha256=hashlib.sha256(b'\0'.join(s.encode() for s in argv)+b'\0').hexdigest(),diskBefore=disk(),processesBefore=before,portsBoundAndReleased=True,ownedNamespace=str(ARM),maximumSeconds=MAX_SECONDS,cleanupPolicy='Java exact-owned Process handles check startInstant/command/argv then TERM only. Wrapper sends no signals or escalation; deadline preserves active evidence and forbids rerun.',startupBoundSeconds=30,scheduledExposureNs=67584000000,drainBoundSeconds=90,capacityClaim=False))
 print(json.dumps(dict(state='REGISTERED_NOT_LAUNCHED',registrationSha256=sha(OUT/'registration.json'))),flush=True)

def inspect(pid,rc):
 require(rc==0,'Native parent exit nonzero; preserve raw failure')
 completion=metadata(ARM/'completion.json');functional=metadata(ARM/'functional-result.json');summary=metadata(ARM/'load/load-result.json');cfg=metadata(ARM/'load/configuration.json');reg=metadata(ARM/'registration.json');stopped=metadata(ARM/'owned-stop.json');reference=metadata(ARM/'physical-reference-reconciliation.json');final=metadata(ARM/'final-position.json')
 require(completion['passed'] and completion['allOwnedStopped'] and stopped['allOwnedStopped'] and not stopped['forcedKill'],'Owned closure failed')
 require(len(stopped['reports'])==3 and all(r.get('stopped') or r.get('alreadyExited') for r in stopped['reports']),'Three exact owned stop reports required')
 require(functional['passed'] and functional['allThreeSnapshotLogsMatched'] and reference['passed'],'Functional/reference/three snapshot proof failed')
 require((cfg['arrivals'],cfg['ratePerSecond'],cfg['batchCap'],cfg['archiveChunkBytes'],cfg['eventFetchCount'],cfg['readWindow'])==(33792,500,4,6144,16,8),'Fixed workload changed')
 require(reg['workloadPreset']=='long-cuts-33792-v1' and reg['expectedFullCommandCuts']==11 and reg['expectedTrailingCommands']==3 and reg['equivalentFullLoadCutNumbers']==list(range(2,12)),'Declared exact cut workload differs')
 require(reg['appointedLeader']==0 and reg['sync']==2 and reg['ports']==42000 and reg['codeSha256']==cfg['actualCodeSha256']==CODE,'Fixed code/leader/sync/ports differs')
 require(summary['scheduledArrivals']==summary['releasedArrivals']==summary['confirmedAcceptedUniqueOrders']==33792 and summary['notSent']==summary['unknownFinal']==0 and summary['maintenanceCycles']==12,'Original full planned arrival/cycle closure failed')
 require((final['businessSeq'],final['eventSeq'],final['marketSeq'],functional['acceptedPlaceCount'])==(33795,67587,67585,33793),'Final exact counters differ')
 require(cfg['retentionIdleSelection']==reg['retentionIdleSelection']==summary['retentionIdleSelection']==completion['retentionIdleSelection'] and cfg['retentionIdleSelection']['maximumParkNs']==100000,'Idle selection closure differs')
 require(metadata(ARM/'load/admission-plan.json')==metadata(OUT/'registration.json')['actualPlan'],'Runtime plan differs from preregistered actual-JAR plan')
 logs=[];idle=[];strict=[]
 for node in range(3):
  identity=metadata(ARM/f'node-{node}-identity.json');actual=metadata(ARM/f'node-{node}/idle-observations/idle-000.actual.json');intent=metadata(ARM/f'node-{node}/idle-observations/idle-000.intent.json')
  require(intent['pid']==identity['pid'] and intent['selection']==actual['selection'],'Node intent/actual PID differs')
  require([v for v in identity['arguments'] if v.startswith('-Dvectormatch.retention.idleMaxParkNs=')]==['-Dvectormatch.retention.idleMaxParkNs=100000'],'Actual child idle argv differs')
  require('-Daeron.cluster.appointed.leader.id=0' in identity['arguments'] and Path(identity['command']).resolve()==JAVA,'Actual child Java/leader differs')
  require(ps(identity['pid'])['returnCode']==1,'Owned node PID remains after Java-owned stop')
  raw=(ARM/f'node-{node}.log').read_bytes();strict.append(dict(node=node,passed=b'Exception' not in raw and b'ERROR' not in raw and b'WARN' not in raw,logSha256=sha(ARM/f'node-{node}.log')))
  logs.append((raw,node,identity['pid'],actual))
  idle.append(validate_idle(actual,100000,node,identity['pid']))
 write(OUT/'strict-node-log-review.json',dict(passed=all(r['passed'] for r in strict),originalStrictOutcomePreserved=True,nodes=strict))
 logs=[classify(raw,node=node,pid=node_pid,profile=cfg['profileSha256'],lineage=cfg['lineage'],code=CODE,final_hash=final['combinedSha256'],idle_actual=actual) for raw,node,node_pid,actual in logs]
 samples=metadata(ARM/'load/transport-observations.json')
 require(samples,'Owner transport samples absent')
 for v in samples:
  require(v['leaderMemberId']==0 and v['leadershipTermId']==0 and v['newLeaderEvents']==[] and v['mtuLength']==1248,'Leader/term/MTU changed')
  validate_idle(v['retentionIdlePolicy'],100000,-1,pid)
 require(reference['actualRepliesCompared']==summary['physicalOfferTape']['recordedReplies'],'Raw callback/reference count differs')
 return dict(passed=True,functionalCanonicalOnly=True,cpuPerformanceClaim=False,schedulerTimingValidReported=summary['schedulerTimingValid'],schedulerLateOver20ms=summary['schedulerLatenessOver20ms'],allPlannedOrders=33792,cycles=12,fullCommandCuts=11,equivalentFullLoadCuts=10,trailingCommands=3,actualCodeFingerprint=CODE,allOwnedStopped=True,nodeIdleInventories=idle,ownerFactoryCreations=1,expectedTotalFactoryCreations=22,measuredSleepOrThreadCounts=False,nodeLogClassifications=logs,strictLogPassed=all(r['passed'] for r in strict),rawLongPhaseAuditPending=True)

def start():
 reg=metadata(OUT/'registration.json');sources();ports();require(not processes()['stdout'].strip(),'Prior retention process present')
 for row in reg['jars']+reg['jdk']+reg['helpers']+[reg['actualPlanInput'],reg['sourceFreeze'],reg['sourceReview']]:require(pin(Path(row['path']))==row,'Registered input changed')
 require(not ARM.exists(),'Arm already exists; no rerun');disk()
 write(OUT/'START_INTENT.json',dict(atUTC=stamp(),registrationSha256=sha(OUT/'registration.json'),argv=reg['argv'],noResubmit=True))
 env=os.environ.copy()
 for name in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:env.pop(name,None)
 start=time.monotonic();child=None;rc=None
 try:
  with (OUT/'parent.stdout').open('x') as stdout,(OUT/'parent.stderr').open('x') as stderr,(OUT/'monitor.jsonl').open('x') as monitor:
   child=subprocess.Popen(reg['argv'],cwd=WORK,env=env,stdout=stdout,stderr=stderr)
   write(OUT/'parent-identity.json',dict(pid=child.pid,atUTC=stamp(),launchArgv=reg['argv'],argvNulSha256=reg['argvNulSha256'],ownership='Direct unreaped subprocess.Popen child handle; ps supplementary',psAfterLaunch=ps(child.pid)))
   print(json.dumps(dict(state='STARTED',pid=child.pid)),flush=True)
   count=0
   while True:
    try:rc=child.wait(timeout=5);break
    except subprocess.TimeoutExpired:
     count+=1;require(count<=96,'Bounded monitor inventory exhausted')
     row=sample();row['elapsedSeconds']=time.monotonic()-start;row['parent']=ps(child.pid);monitor.write(json.dumps(row)+'\n');monitor.flush()
     print(json.dumps(dict(state='ACTIVE',pid=child.pid,elapsedSeconds=round(row['elapsedSeconds'],1),allocatedBytes=row['allocatedBytes'])),flush=True)
     if row['elapsedSeconds']>MAX_SECONDS:
      write(OUT/'DEADLINE_ACTIVE.json',dict(atUTC=stamp(),pid=child.pid,observation=row,noSignalSent=True,noRerun=True))
      raise RuntimeError('Deadline reached; active evidence preserved, no signals/rerun')
  write(OUT/'parent-exit.json',dict(atUTC=stamp(),returnCode=rc,elapsedSeconds=time.monotonic()-start,noWrapperSignalSent=True))
  result=inspect(child.pid,rc);sources()
  for row in reg['jars']+reg['jdk']:require(pin(Path(row['path']))==row,'Runtime input changed')
  write(OUT/'functional-inspection.json',result);print(json.dumps(dict(state='CLOSED_FUNCTIONAL_PASS',result=result)),flush=True)
 except BaseException as e:
  write(OUT/'native-failure.json',dict(atUTC=stamp(),type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),parentPid=None if child is None else child.pid,parentReturnCode=rc,noWrapperSignalSent=True,noRetry=True))
  raise

if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--start-new',action='store_true');a=p.parse_args()
 if a.prepare:prepare()
 else:start()
