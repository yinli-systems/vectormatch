"""One LOCAL SHORT pair; explicit root-reviewed preparation and start, never automatic retry/signals."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,socket,stat,subprocess,sys,time,traceback
from owner_poll_attestation import validate_owner_bundle
from shutdown_warning import classify
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WORKSPACE=BASE.parents[2]
NATIVE=BASE/'owner-poll-local-native-r1'
ORDER=(1000000,100000)
SOURCE_COMMIT='977197616ade0283174f2ea6ddfaa700547f6d15'
CODE='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'
PROFILE='732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68'
MAX_ALLOC=589327865
FLOOR=1024**3
ARCHIVE_RESERVE=2*MAX_ALLOC+128*1024**2
TIMEOUT_SECONDS=420

def need(value,message):
 if not value:raise AssertionError(message)
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def pin(path):
 path=Path(path);s=path.lstat();need(stat.S_ISREG(s.st_mode)and not path.is_symlink(),'Regular input required');return {'path':str(path),'bytes':s.st_size,'mode':s.st_mode&0o777,'sha256':sha(path)}
def write(path,value):
 with Path(path).open('x')as f:json.dump(value,f,indent=2);f.write('\n')
def js(path):
 path=Path(path);need(path.is_file()and not path.is_symlink()and path.stat().st_size<=1024**2,'Bounded metadata file required');return json.loads(path.read_text())
def check_pin(row):need(pin(row['path'])==row,'Pinned input changed: '+row['path'])
def inventory():
 r=subprocess.run(['/usr/bin/pgrep','-fl','io.vectormatch.cluster.Retention'],capture_output=True,text=True);need(r.returncode in (0,1)and len(r.stdout.encode())<128*1024,'Bounded process inventory');return {'returnCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
def ps(pid):
 r=subprocess.run(['/bin/ps','-p',str(pid),'-ww','-o','pid=','-o','lstart=','-o','command='],capture_output=True,text=True);need(r.returncode in (0,1)and len(r.stdout.encode())<128*1024,'Bounded exact PID observation');return {'pid':pid,'returnCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
def port_check():
 sockets=[]
 try:
  for member in range(3):
   for offset in range(1,6):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',42000+100*member+offset));sockets.append(s)
 finally:
  for s in sockets:s.close()
def disk(remaining):
 free=shutil.disk_usage(WORKSPACE).free;required=FLOOR+remaining*MAX_ALLOC+ARCHIVE_RESERVE;need(free>=required,'Free1GiB+remaining actualPlan growth+unchanged two-arm archive reserve unavailable');return {'freeBytes':free,'requiredBytes':required,'remainingArms':remaining,'perArmSourceGrowthBound':MAX_ALLOC,'archiveReserveBytes':ARCHIVE_RESERVE,'floorBytes':FLOOR}
def load_inputs(path,expected):
 need(sha(path)==expected,'Exact root-reviewed config SHA required');c=js(path)
 need(c['sourceCommit']==SOURCE_COMMIT and c['codeFingerprint']==CODE and c['profileSha256']==PROFILE,'Exact new source/artifact required')
 for row in c['pinnedInputs']:check_pin(row)
 observed=js(c['linuxObservation']['path']);receipt=js(c['linuxReceipt']['path'])
 need(observed['actualCodeFingerprint']==CODE and observed['profileSha256']==PROFILE and observed['ownerConstructed']is False and observed['ownerRuntimeObservationAvailable']is False,'Actual metadata is prospective only')
 need(receipt['passed']is True and receipt['observationSha256']==c['linuxObservation']['sha256'] and receipt['execution']['metadataJvmExited']is True and receipt['execution']['processIdentityObservationGap']is False,'Closed actual Linux metadata identity required')
 need(receipt['execution']['ownedParentPid']==receipt['execution']['actualProcessIdentity']['pid'],'Actual metadata child PID binding')
 need(observed['workloads']['SHORT']['plan']==c['shortPlan']and c['shortPlan']['maximumRawTraceBytes']==38033404 and c['shortPlan']['maximumAllocatedGrowthBytes']==MAX_ALLOC,'Actual unchanged SHORT plan required')
 need(len(c['jars'])==4 and [Path(r['path']).name for r in c['jars']]==['aeron-all-1.53.3.jar','agrona-2.6.1.jar','cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar'],'Exact4JAR order')
 for row in c['jars']+c['jdk']:check_pin(row)
 need(c['ownerCaps']==list(ORDER)and c['nodeDriverCap']==100000 and c['rootReviewRequiredBeforeStart']is True,'Fixed pair factor only')
 return c

def arguments(c,cap,arm):
 return [c['java'],'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xms128m','-Xmx512m','-Dvectormatch.retention.idleMaxParkNs=100000','-Dvectormatch.retention.ownerPollMaxParkNs='+str(cap),'-cp',os.pathsep.join(r['path']for r in c['jars']),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',str(arm),'idle-window8','42000']
def expected_node(c,root,reg,n):
 jars=[r['path']for r in c['jars']if Path(r['path']).name!='agrona-2.6.1.jar']
 # Actual class-source closure order from pilot.startNodes: cluster, core, Aeron.
 byname={Path(p).name:p for p in jars};cp=[byname[n]for n in ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar']]
 return [c['java'],'-Dvectormatch.retention.idleMaxParkNs=100000','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xmx256m','-Daeron.cluster.appointed.leader.id=0','-cp',os.pathsep.join(cp),'io.vectormatch.cluster.RetentionNodeMainV3',str(n),str(root),'42000','2','finite-batch-load-v3-v1',reg['lineage'],PROFILE,CODE,'bounded-maintenance-v1']
def inspect(c,cap,arm,parent_pid,argv,process_dir):
 completion=js(arm/'completion.json');functional=js(arm/'functional-result.json');reg=js(arm/'registration.json');cfg=js(arm/'load/configuration.json');summary=js(arm/'load/load-result.json');stopped=js(arm/'owned-stop.json');final=js(arm/'final-position.json');reference=js(arm/'physical-reference-reconciliation.json')
 need(completion['passed']is True and completion['allOwnedStopped']is True and stopped['allOwnedStopped']is True and stopped['forcedKill']is False,'Java owned clean closure required')
 need(len(stopped['reports'])==3 and all(r.get('stopped')or r.get('alreadyExited')for r in stopped['reports']),'Three exact node stop reports')
 need(functional['passed']is True and functional['allThreeSnapshotLogsMatched']is True and functional['noCapacityPromotion']is True and reference['passed']is True,'Functional all3checkpoint/reference proof')
 need((cfg['arrivals'],cfg['ratePerSecond'],cfg['batchCap'],cfg['archiveChunkBytes'],cfg['eventFetchCount'],cfg['readWindow'])==(6400,500,4,6144,16,8),'Fixed SHORT source changed')
 need(reg['appointedLeader']==0 and reg['sync']==2 and reg['ports']==42000 and reg['codeSha256']==cfg['actualCodeSha256']==CODE and cfg['profileSha256']==PROFILE,'Fixed source/leader/sync/ports/profile')
 need(summary['scheduledArrivals']==summary['releasedArrivals']==summary['confirmedAcceptedUniqueOrders']==6400 and summary['notSent']==summary['unknownObserved']==summary['unknownFinal']==summary['serverRejected']==0 and summary['maintenanceCycles']==3,'All6400originals+3cycles must close; preserve partial outcomes onfailure')
 need((final['businessSeq'],final['eventSeq'],final['marketSeq'],final['exportedEventSeq'])==(6403,12803,12801,12803),'Exact final frontiers')
 need(sha(arm/'reference-final.bin')==final['combinedSha256']and reference['actualRepliesCompared']==summary['physicalOfferTape']['recordedReplies'],'Canonical reference/raw callback closure')
 need(js(arm/'load/admission-plan.json')==c['shortPlan'],'Runtime actual plan differs')
 nodes={};actuals={};expected={};node_ps=[];logs=[]
 for n in range(3):
  identity=js(arm/('node-%d-identity.json'%n));nodes[n]={'pid':identity['pid'],'arguments':[identity['command']]+identity['arguments']};expected[n]=expected_node(c,arm,reg,n);actuals[n]=js(arm/('node-%d/idle-observations/idle-000.actual.json'%n));p=ps(identity['pid']);need(p['returnCode']==1 and not p['stdout'].strip(),'Node PID still present; no wrapper signal');node_ps.append(p)
  raw=(arm/('node-%d.log'%n)).read_bytes();need(len(raw)<=4*1024**2,'Node log cap');logs.append(classify(raw,node=n,pid=identity['pid'],profile=PROFILE,lineage=reg['lineage'],code=CODE,final_hash=final['combinedSha256'],idle_actual=actuals[n]))
 samples=js(arm/'load/transport-observations.json');need(samples,'Owner transport samples required')
 for value in samples:need(value['leaderMemberId']==0 and value['leadershipTermId']==0 and value['newLeaderEvents']==[]and value['mtuLength']==1248,'Fixed leader/term/MTU')
 actual=validate_owner_bundle(registration=reg,configuration=cfg,summary=summary,before=js(arm/'load/owner-before-close.json'),after=js(arm/'load/owner-after-close.json'),parent={'pid':parent_pid,'arguments':argv},nodes=nodes,expected_owner_cap=cap,expected_parent_arguments=arguments(c,cap,arm),expected_node_arguments=expected,node_idle_actuals=actuals,parent_idle_actuals=[v['retentionIdlePolicy']for v in samples])
 write(process_dir/'owner-actual-attestation.json',actual);write(process_dir/'post-close-node-observations.json',node_ps)
 return {'passed':True,'ownerPollMaximumParkNs':cap,'serverDriverMaximumParkNs':100000,'arrivals':6400,'accepted':6400,'functionalCanonicalPassed':True,'ownerActualAttestationPassed':actual['passed'],'schedulerTimingValid':summary['schedulerTimingValid'],'schedulerLatenessOver20ms':summary['schedulerLatenessOver20ms'],'localPerformanceClaimed':False,'newForcedUnknownScenarioExecuted':False,'originalWireUnknownCreditMeaningfulUnitCoverageSeparate':True,'nodeLogClassifications':logs,'rawFunctionalPassed':None,'rawFunctionalAuditPending':True,'scope':'Native functional/canonical+constructedowner proof only; subsequent fullwire/phase archive audit required; no performance comparison evenwhenlocal scheduler valid'}
def prepare(config,config_sha):
 c=load_inputs(config,config_sha);need(not NATIVE.exists(),'Fresh pair namespace only');need(not inventory()['stdout'].strip(),'Existing retention JVM; no launch');port_check();d=disk(2);NATIVE.mkdir(mode=0o700)
 write(NATIVE/'registration.json',{'atUTC':now(),'sourceCommit':SOURCE_COMMIT,'codeFingerprint':CODE,'profileSha256':PROFILE,'config':pin(config),'sourceHelpers':[pin(HERE/n)for n in ['run_native_pair.py','owner_poll_attestation.py','idle_attestation.py','shutdown_warning.py']],'pinnedInputs':c['pinnedInputs'],'jars':c['jars'],'jdk':c['jdk'],'actualPlan':c['shortPlan'],'ownerCaps':list(ORDER),'nodeDriverCap':100000,'diskBefore':d,'pidInventoryBefore':inventory(),'portsBoundAndReleased':True,'cleanupPolicy':'Direct unreaped Popen child; Java checks exact-owned Process handles and TERM-only nodes. Wrapper never signals/escalates or retries. Deadline retains active evidence and blockssecondarm.','maximumSecondsPerArm':TIMEOUT_SECONDS,'localPerformanceClaimed':False});print(json.dumps({'state':'REGISTERED_NOT_LAUNCHED','registrationSha256':sha(NATIVE/'registration.json')}))
def start(config,config_sha):
 c=load_inputs(config,config_sha);reg=js(NATIVE/'registration.json');need(reg['config']==pin(config),'Registered config changed')
 for p in reg['sourceHelpers']+reg['jars']+reg['jdk']+reg['pinnedInputs']:check_pin(p)
 need(not(NATIVE/'START_INTENT.json').exists(),'One exclusive pair; no resubmission');need(not inventory()['stdout'].strip(),'Prior retention JVM present');port_check();disk(2);write(NATIVE/'START_INTENT.json',{'atUTC':now(),'registrationSha256':sha(NATIVE/'registration.json'),'ownerCaps':list(ORDER),'noResubmit':True});arms=[];child=None
 try:
  for index,cap in enumerate(ORDER):
   load_inputs(config,config_sha);need(not inventory()['stdout'].strip(),'Firstarm must fullyclose before second');port_check();disk(2-index);arm=NATIVE/('owner-'+str(cap));need(not arm.exists(),'Fresh lineage directory required');process=NATIVE/('owner-'+str(cap)+'-process');process.mkdir(mode=0o700);argv=arguments(c,cap,arm);write(process/'before.json',{'atUTC':now(),'argv':argv,'argvNulSha256':hashlib.sha256(b'\0'.join(v.encode()for v in argv)+b'\0').hexdigest(),'disk':disk(2-index)})
   env=os.environ.copy()
   for name in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:env.pop(name,None)
   env['VECTOR_AERON_MTU_LENGTH']='1248';started=time.monotonic();child=None
   with(process/'stdout.log').open('x')as out,(process/'stderr.log').open('x')as err,(process/'monitor.jsonl').open('x')as monitor:
    child=subprocess.Popen(argv,cwd=WORKSPACE,env=env,stdout=out,stderr=err);write(process/'parent-identity.json',{'pid':child.pid,'atUTC':now(),'launchArguments':argv,'ownership':'Direct unreaped subprocess.Popen child handle','actualKernelArgvIndependentlyDecoded':False,'psAfterLaunch':ps(child.pid)})
    for tick in range(96):
     try:status=child.wait(timeout=5);break
     except subprocess.TimeoutExpired:
      elapsed=time.monotonic()-started;sample={'atUTC':now(),'elapsedSeconds':elapsed,'parent':ps(child.pid),'freeBytes':shutil.disk_usage(WORKSPACE).free};monitor.write(json.dumps(sample)+'\n');monitor.flush();print(json.dumps({'state':'ACTIVE','ownerCap':cap,'pid':child.pid,'elapsedSeconds':round(elapsed,1)}),flush=True)
      need(elapsed<=TIMEOUT_SECONDS,'Deadline active; wrapper sends no signal or retry');need(sample['freeBytes']>=FLOOR,'Local free floor violated; preserve active process/evidence');need((process/'stdout.log').stat().st_size<=4*1024**2 and(process/'stderr.log').stat().st_size<=4*1024**2,'Parent log bound')
    else:raise RuntimeError('Bounded96monitor slots exhausted; no signals/retry')
   write(process/'exit.json',{'returnCode':status,'elapsedSeconds':time.monotonic()-started,'noWrapperSignalSent':True});need(status==0,'Parent failed; preserve alloutcomes anddo notstartsecondarm');report=inspect(c,cap,arm,child.pid,argv,process);write(process/'functional-inspection.json',report);arms.append(report);need(not inventory()['stdout'].strip(),'Owned/global retention processes remain');load_inputs(config,config_sha)
  write(NATIVE/'PAIR_FUNCTIONAL_COMPLETE.json',{'schemaVersion':1,'scope':'OWNER_POLL_NEW_ARTIFACT_FUNCTIONAL_PAIR_PRE_RAW_AUDIT','passed':True,'sourceCommit':SOURCE_COMMIT,'codeFingerprint':CODE,'profileSha256':PROFILE,'arms':arms,'sameNewArtifact':True,'localPerformanceClaimed':False,'allInputsUnchanged':True,'allOwnedStopped':True,'fullNativeArchiveAndRawAuditPending':True});print(json.dumps({'state':'PAIR_FUNCTIONAL_CLOSED','rawAuditPending':True,'performanceClaimed':False}))
 except BaseException as e:
  write(NATIVE/'FAILED.json',{'atUTC':now(),'passed':False,'error':repr(e),'traceback':traceback.format_exc(),'completedArms':arms,'activeChildPid':None if child is None or child.poll()is not None else child.pid,'noWrapperSignalsOrEscalation':True,'noRetry':True,'originalsRetained':True});raise
if __name__=='__main__':
 p=argparse.ArgumentParser(allow_abbrev=False);g=p.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--start-new',action='store_true');p.add_argument('--config',type=Path,required=True);p.add_argument('--root-reviewed-config-sha256',required=True);a=p.parse_args();prepare(a.config.resolve(),a.root_reviewed_config_sha256)if a.prepare else start(a.config.resolve(),a.root_reviewed_config_sha256)
