"""One preregistered finite V4 capacity point. No SLA/endurance/physical-host claim or resource creation."""
from pathlib import Path
import os,sys,json,hashlib,subprocess,time,shutil,socket,importlib.util,traceback
HERE=Path(__file__).resolve().parent;C=json.loads((HERE/'config.json').read_text());ROOT=Path(C['root'])
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def save(p,value):
 with p.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def require(value,reason):
 if not value:raise RuntimeError(reason)
require(HERE==ROOT and ROOT==Path('/opt/vectormatch-cpu/experiments/v4-counter-diagnostic-4000-x1-r1') and C['rate']==4000 and C['arm']=='x1'and C['policy']=='CONTINUE'and C['agentIdleMaxParkNs']==100000 and C['readBankDispatch']=='CLOSED','wrong fixed diagnostic namespace/configuration')
require(sha(HERE/'owned_linux_base_8eeb.py')==C['qualifiedBaseSha256']and sha(HERE/'owned_process_identity.py')=='51ad33fc51a92cdb9041e78093d39e38a42191a9ec50ad9635fd7cc314ba7a1a','qualified identity/signal bodies differ')
spec=importlib.util.spec_from_file_location('qualified_base',HERE/'owned_linux_base_8eeb.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
require(sha(HERE/'node_contract.py')==C['nodeContractSha256'],'node contract source differs')
require(sha(HERE/'idle_proof.py')==C['idleProofSha256']and sha(HERE/'idle_attestation.py')==C['idleAttestationSha256'],'frozen actual idle proof sources differ')
contract_spec=importlib.util.spec_from_file_location('node_contract',HERE/'node_contract.py');contract=importlib.util.module_from_spec(contract_spec);contract_spec.loader.exec_module(contract)
base.enable_pidfd();require(socket.gethostname()=='33ace3d92505','CPU host changed')
require(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==C['baseline']['bootId'],'boot changed')
require(sorted(os.sched_getaffinity(0))==C['baseline']['affinity'],'CPU affinity changed')
require(Path('/sys/fs/cgroup/cpu.max').read_text()==C['baseline']['cpuMax']and Path('/sys/fs/cgroup/memory.max').read_text()==C['baseline']['memoryMax'],'cgroups changed')
for parent in ROOT.parents:require(parent.is_dir()and not parent.is_symlink(),'unsafe namespace ancestor')
require(not(ROOT/'state').exists()and not(ROOT/'STARTED.json').exists(),'no automatic retry or reuse')
for p in [Path('/opt/vectormatch-cpu/restorations/original-native-r1'),Path('/opt/vectormatch-cpu/preparation')]:require(not p.exists(),'protected original application path changed')
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 row=base.process_identity(int(p.name))
 if row is not None:require(Path(row['arguments'][0]).name not in('java','javaw','postgres','postmaster'),'foreign Java/SQL workload active before functional run')
require(shutil.disk_usage(ROOT).free>=max(3*1024**3,C['plan']['initialFreeBytes']+96*1024**2),'fresh native/plan free-space floor')
ephemeral=[int(x)for x in Path('/proc/sys/net/ipv4/ip_local_port_range').read_text().split()]
server_ports=[22000+member*100+offset for member in range(3)for offset in range(1,6)]
require(len(ephemeral)==2 and all(not ephemeral[0]<=port<=ephemeral[1]for port in server_ports),'fixed server endpoint overlaps actual ephemeral range')
probes=[]
try:
 for port in server_ports:
  probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);probes.append(probe);probe.bind(('127.0.0.1',port))
finally:
 for probe in probes:probe.close()
save(ROOT/'UDP_PORT_PREFLIGHT.json',dict(ephemeralRange=ephemeral,serverPorts=server_ports,allFifteenBindingsProbed=True,probeSocketsClosedBeforeJava=True,kernelSettingsChanged=False))
java=Path(C['java']);require(sha(java)==C['javaSha256']and sha(java.parent.parent/'release')==C['releaseSha256'],'actual JDK differs')
lib=Path(C['lib']);require(lib==Path('/opt/vectormatch-cpu/tools/cpu-v4-agent-metadata-r1/lib'),'wrong qualified runtime')
for name,pin in C['jars'].items():require(sha(lib/name)==pin['sha256']and(lib/name).stat().st_size==pin['bytes'],'runtime JAR body differs')
command=[str(java),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xmx768m','-Dvectormatch.retention.idleMaxParkNs='+str(C['agentIdleMaxParkNs']),'-Dvectormatch.retention.readBankDispatch='+C['readBankDispatch'],'-Dvectormatch.retention.ownerPollMaxParkNs=1000000','-cp',':'.join(str(lib/name)for name in C['jarOrder']),'io.vectormatch.cluster.RetentionCapacityAeronV4',str(ROOT/'state'),str(C['rate']),C['policy']]
env=os.environ.copy()
for name in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:env.pop(name,None)
child=None;parent=None;owned={};failure=None;observer=None;observer_record=None;started=time.monotonic();native_started=False;observed=0;maximum_live=0
try:
 with(ROOT/'java.stdout').open('xb')as out,(ROOT/'java.stderr').open('xb')as err:
  child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env);native_started=True
  parent=None
  for unused in range(100):
   row=base.process_identity(child.pid)
   if row is not None and row['arguments']==command:parent=row;break
   if child.poll()is not None:break
   time.sleep(.005)
  require(parent is not None,'parent process identity not proven');owned[(parent['pid'],parent['startTicks'])]=dict(parent,role='parent')
  save(ROOT/'STARTED.json',dict(command=command,parent=parent,controller=base.process_identity(os.getpid()),sourceCommit=C['sourceCommit'],artifactFingerprint=C['artifactFingerprint'],finiteCapacityPointOnly=True))
  with(ROOT/'observations.jsonl').open('x')as observations:
   while child.poll()is None:
    now=time.monotonic();require(now-started<=180,'finite functional deadline180s exceeded')
    require(shutil.disk_usage(ROOT).free>=1024**3,'runtime free floor1GiB reached;do not lower')
    registration_path=ROOT/'state/registration.json';registration=None
    if registration_path.exists():
     try:registration=json.loads(registration_path.read_text())
     except json.JSONDecodeError:pass
    live=[]
    for proc in Path('/proc').iterdir():
     if not proc.name.isdigit():continue
     row=base.process_identity(int(proc.name))
     if row is None:continue
     args=row['arguments'];name=Path(args[0]).name
     if name not in ('java','javaw','postgres','postmaster'):continue
     if row['pid']==child.pid:require(all(row[k]==parent[k]for k in ('pid','startTicks','commandSha256','arguments')),'parent identity changed')
     elif observer_record is not None and row['pid']==observer_record['pid']:
      require(all(row[k]==observer_record[k]for k in ('pid','startTicks','commandSha256','arguments')),'observer identity changed')
     else:
      require(registration is not None,'node appeared before its registration')
      expected=[contract.expected_node_arguments(str(java),C['nodeClassPath'],member,str(ROOT/'state'),registration,C['profileFingerprint'],C['artifactFingerprint'],C['agentIdleMaxParkNs'])for member in range(3)]
      require(args in expected,'foreign or changed JVM/SQL process;no signal to unregistered identity')
      try:fields=(proc/'stat').read_text()
      except (FileNotFoundError,ProcessLookupError):continue
      sampled=base.process_identity(row['pid'])
      if sampled is None:continue
      require(all(sampled[k]==row[k]for k in ('pid','startTicks','commandSha256','arguments')),'node identity changed before registration')
      stat_fields=fields[fields.rfind(')')+2:].split();require(int(stat_fields[19])==row['startTicks'],'node birth changed during parent check');ppid=int(stat_fields[1]);require(ppid==child.pid,'node is not the owned parent direct child')
      key=(row['pid'],row['startTicks'])
      if key not in owned:owned[key]=dict(row,role='node',member=str(expected.index(args)));save(ROOT/('owned-observed-'+str(row['pid'])+'-'+str(row['startTicks'])+'.json'),owned[key])
     metric={k:row[k]for k in ('pid','startTicks','commandSha256')}
     try:
      rawstat=(proc/'stat').read_text();statparts=rawstat[rawstat.rfind(')')+2:].split()
      if int(statparts[19])==row['startTicks']:metric.update(userTicks=int(statparts[11]),kernelTicks=int(statparts[12]),minorFaults=int(statparts[7]),majorFaults=int(statparts[9]),virtualBytes=int(statparts[20]),residentBytes=int(statparts[21])*os.sysconf('SC_PAGE_SIZE'))
     except(FileNotFoundError,ProcessLookupError):pass
     live.append(metric)
    require(len(live)<=5,'registered diagnostic permits parent,three nodes and one observer only')
    if observer is None:
     ready_path=ROOT/'state/startup-readiness'
     ready=None
     if ready_path.is_file():
      try:ready=json.loads(ready_path.read_text())
      except json.JSONDecodeError:pass
     nodes=[r for r in owned.values()if r['role']=='node']
     if ready is not None and ready.get('passed')and len(nodes)==3:
      nodes=sorted(nodes,key=lambda r:int(r['member']));require([r['member']for r in nodes]==['0','1','2'],'three original diagnostic members required')
      for name,pin in C['observerInputs'].items():require(sha(ROOT/name)==pin['sha256'],'observer class/source changed')
      watch_command=[str(java),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-Xmx128m','-cp',str(ROOT/'counter-classes')+':'+':'.join(str(lib/name)for name in C['jarOrder']),'io.vectormatch.cluster.AeronCounterWatch','--watch',str(ROOT/'counter-watch.jsonl'),'600','100']
      for record in nodes:watch_command.extend([str(ROOT/('state/node-'+record['member']+'/driver')),str(record['pid'])])
      with(ROOT/'counter-watch.stdout').open('xb')as watch_out,(ROOT/'counter-watch.stderr').open('xb')as watch_err:observer=subprocess.Popen(watch_command,stdin=subprocess.DEVNULL,stdout=watch_out,stderr=watch_err,env=env)
      for unused in range(100):
       actual_observer=base.process_identity(observer.pid)
       if actual_observer is not None and actual_observer['arguments']==watch_command:observer_record=dict(actual_observer,role='observer');break
       if observer.poll()is not None:break
       time.sleep(.005)
      require(observer_record is not None,'owned observer birth not proven');owned[(observer_record['pid'],observer_record['startTicks'])]=observer_record;save(ROOT/('owned-observed-'+str(observer_record['pid'])+'-'+str(observer_record['startTicks'])+'.json'),observer_record)
      save(ROOT/'OBSERVER_STARTED.json',dict(passed=True,observer=observer_record,nodeOriginals=nodes,maximumSamples=600,periodMillis=100,maximumRawBytes=32*1024*1024,noBusinessCommandsOrSignals=True))
    maximum_live=max(maximum_live,len(live));observations.write(json.dumps(dict(monotonicSeconds=now,monotonicNs=time.monotonic_ns(),clockTicksPerSecond=os.sysconf('SC_CLK_TCK'),freeBytes=shutil.disk_usage(ROOT).free,cgroupCpuStat=Path('/sys/fs/cgroup/cpu.stat').read_text(),cgroupMemoryCurrent=Path('/sys/fs/cgroup/memory.current').read_text(),live=live))+'\n');observations.flush();observed+=1;time.sleep(.05)
  status=child.wait(timeout=5)
 require(status==0,'functional Java returned nonzero;preserve native failure')
 require(observer is not None and observer_record is not None,'observer did not start before native completion');require(observer.wait(timeout=65)==0,'observer failed;preserve raw diagnostic')
 observer_completion=json.loads((ROOT/'counter-watch.jsonl.completion.json').read_text());require(observer_completion['passed']and observer_completion['samples']>=3 and observer_completion['drivers']==3,'bounded three-driver observation did not close')
 for record in owned.values():require(base.process_identity(record['pid'])is None and not Path('/proc',str(record['pid'])).exists(),'owned Java not strictly absent after completion')
 require(len([r for r in owned.values()if r['role']=='node'])==6,'all six actual node process lifetimes must be observed')
 completion=json.loads((ROOT/'state/completion.json').read_text());require(completion['passed']and completion['allOwnedStopped'],'native completion not proven')
 actual=json.loads((ROOT/'state/registration.json').read_text());require(actual['code']==C['artifactFingerprint'] and actual['ports']==22000 and actual['ratePerSecond']==C['rate'] and actual['fileWorkDispatchPolicy']==C['policy'] and actual['activeLoadWorkers']==127,'actual fixed registration differs')
 summary=json.loads((ROOT/'state/load/load-result.json').read_text());require(summary['ownerPollActual']['available']and summary['ownerPollActual']['ownerPollMaxParkNs']==1000000,'actual constructed owner polling cap differs')
 require(summary['readBankDispatchSelection']==actual['readBankDispatchSelection']and summary['readBankDispatchSelection']['policy']==C['readBankDispatch'],'actual read-bank selection differs')
 idle_spec=importlib.util.spec_from_file_location('idle_proof',HERE/'idle_proof.py');idle=importlib.util.module_from_spec(idle_spec);idle_spec.loader.exec_module(idle)
 idle_result=idle.validate(ROOT/'state',list(owned.values()),C['agentIdleMaxParkNs']);save(ROOT/'ACTUAL_IDLE_PROOF.json',idle_result)
 result=json.loads((ROOT/'state/capacity-correctness-result.json').read_text());require(result['passed'] and result['allThreeSnapshotHashesMatched']and result['allThreeColdRestoreHashesMatched'],'native correctness/cold restore did not pass')
 for name,pin in C['jars'].items():require(sha(lib/name)==pin['sha256'],'runtime JAR changed during execution')
 save(ROOT/'SUCCESS.json',dict(passed=True,sourceCommit=C['sourceCommit'],artifactFingerprint=C['artifactFingerprint'],exitCode=status,elapsedSeconds=time.monotonic()-started,observations=observed,observedNodeLifetimes=6,maximumSimultaneousJavaProcesses=maximum_live,allOwnedJavaStrictlyAbsent=True,freeBytesAfter=shutil.disk_usage(ROOT).free,noEnduranceSlaOrPhysicalHostIsolationClaim=True,ratePerSecond=C['rate'],policy=C['policy'],arm=C['arm']))
except BaseException as error:
 failure=error;cleanup=[]
 # Discover only exact direct children while the original parent birth is still proven alive.
 # Stop registered children first,and give the finite Java program a chance to run its own finally.
 if child is not None and child.poll()is None and parent is not None and base.matching_identity(parent)is not None:
  try:
   registration=json.loads((ROOT/'state/registration.json').read_text())
   expected=[contract.expected_node_arguments(str(java),C['nodeClassPath'],member,str(ROOT/'state'),registration,C['profileFingerprint'],C['artifactFingerprint'],C['agentIdleMaxParkNs'])for member in range(3)]
   for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    row=base.process_identity(int(proc.name))
    if row is None or row['arguments']not in expected:continue
    try:fields=(proc/'stat').read_text()
    except(FileNotFoundError,ProcessLookupError):continue
    stat_fields=fields[fields.rfind(')')+2:].split()
    if int(stat_fields[1])!=child.pid or int(stat_fields[19])!=row['startTicks']:continue
    base.matching_identity(row);owned.setdefault((row['pid'],row['startTicks']),dict(row,role='node',member=str(expected.index(row['arguments']))))
  except BaseException as discovery_error:cleanup.append(dict(discoveryError=repr(discovery_error),noUnregisteredSignals=True))
 for record in [row for row in owned.values()if row['role']=='observer']:
  try:cleanup.append(base.stop_owned(record,5))
  except BaseException as cleanup_error:cleanup.append(dict(observerCleanupError=repr(cleanup_error),noNumericPidFallback=True))
 for record in [row for row in owned.values()if row['role']=='node']:
  try:cleanup.append(base.stop_owned(record,10))
  except BaseException as cleanup_error:cleanup.append(dict(pid=record['pid'],error=repr(cleanup_error),noNumericPidFallback=True))
 if child is not None:
  try:child.wait(timeout=30)
  except subprocess.TimeoutExpired:
   unknown_children=[]
   for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:fields=(proc/'stat').read_text();parts=fields[fields.rfind(')')+2:].split()
    except(FileNotFoundError,ProcessLookupError):continue
    if int(parts[1])!=child.pid:continue
    row=base.process_identity(int(proc.name))
    if row is not None:unknown_children.append({k:row[k]for k in ('pid','startTicks','commandSha256')})
   if unknown_children:cleanup.append(dict(parentNotSignalledBecauseLiveUnregisteredChildren=unknown_children))
   elif parent is not None:
    try:cleanup.append(base.stop_owned(parent,10));child.wait(timeout=5)
    except BaseException as cleanup_error:cleanup.append(dict(parentCleanupError=repr(cleanup_error),noNumericPidFallback=True))
 save(ROOT/'FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),originalFilesRetained=True,noAutomaticRetry=True,cleanup=cleanup,nativeStarted=native_started))
 raise
