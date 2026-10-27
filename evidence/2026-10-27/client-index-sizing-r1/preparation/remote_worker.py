"""One bounded CPU-only qualification or finite diagnostic. No remote resource creation."""
from pathlib import Path
import subprocess,json,os,sys,time,signal,shutil,hashlib,traceback
BASE=Path('/opt/vectormatch-cpu/experiments/client-index-sizing-20261027-r1')
JAVA=Path('/opt/vectormatch-cpu/experiments/soak-20261026-r1/tools/jdk-21.0.13+9/bin/java')
BOOT='8d765c71-dbfa-4354-8db0-6c392e701e6f'

def write(path,value):
 with path.open('x')as f:json.dump(value,f,indent=2);f.write('\n')
def identity(pid):
 try:
  p=Path('/proc')/str(pid);v=p.joinpath('stat').read_text().split(') ',1)[1].split()
  return {'pid':int(pid),'startTicks':v[19],'state':v[0],'pgrp':int(v[2]),'comm':p.joinpath('comm').read_text().strip()}
 except(FileNotFoundError,ProcessLookupError):return None
def members(group):
 out=[]
 for p in Path('/proc').glob('[0-9]*'):
  i=identity(p.name)
  if i and i['pgrp']==group and i['state']!='Z':out.append(i)
 return out
def same(i):
 cur=identity(i['pid']);return cur and cur['startTicks']==i['startTicks'] and cur['pgrp']==i['pgrp'] and cur['state']!='Z'
def quiet():
 for p in Path('/proc').glob('[0-9]*'):
  i=identity(p.name)
  assert not i or i['comm']!='java' or i['state']=='Z',('Java still active',i)
def stop(group,root):
 own=members(group);write(root/'watchdog-owned-before-stop.json',own)
 # Only identities in the private process group are signalled. Never a machine-wide kill.
 for i in own:
  if same(i):os.kill(i['pid'],signal.SIGTERM)
 until=time.monotonic()+6
 while time.monotonic()<until and any(same(i)for i in own):time.sleep(.1)
 for i in own:
  if same(i):os.kill(i['pid'],signal.SIGKILL)
 time.sleep(.2);assert not members(group),'owned group cleanup incomplete'
def sample(group):
 values=[]
 for i in members(group):
  p=Path('/proc')/str(i['pid']);row={'identity':i}
  for name in ['stat','status','io','schedstat']:
   try:row[name]=p.joinpath(name).read_text()
   except(FileNotFoundError,ProcessLookupError):pass
  values.append(row)
 return {'epoch':time.time(),'monotonicNs':time.monotonic_ns(),'processes':values,'freeBytes':shutil.disk_usage(BASE).free,'cpuStat':Path('/sys/fs/cgroup/cpu.stat').read_text(),'udp':Path('/proc/net/snmp').read_text()}
def supervise(argv,root,stem,limit):
 env=os.environ.copy()
 for n in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:env.pop(n,None)
 with(root/(stem+'.stdout')).open('xb')as out,(root/(stem+'.stderr')).open('xb')as err,(root/(stem+'.resources.jsonl')).open('x')as telemetry:
  begin=time.monotonic();p=subprocess.Popen(argv,stdout=out,stderr=err,env=env,start_new_session=True)
  who=identity(p.pid);assert who and who['pgrp']==p.pid
  write(root/(stem+'.launch.json'),{'identity':who,'bootId':BOOT,'argv':argv,'epoch':time.time(),'timeoutSeconds':limit})
  try:
   while p.poll()is None:
    telemetry.write(json.dumps(sample(p.pid))+'\n');telemetry.flush()
    if time.monotonic()-begin>limit:raise TimeoutError(stem+' exceeded its bounded lifetime')
    time.sleep(1)
   if members(p.pid):raise RuntimeError('original process exited with live descendants')
  except BaseException:
   stop(p.pid,root);p.wait(timeout=10);raise
  finally:
   write(root/(stem+'.exit.json'),{'exitCode':p.poll(),'elapsedSeconds':time.monotonic()-begin,'epoch':time.time(),'groupClosed':not members(p.pid)})
  return p.returncode


def main():
 name=sys.argv[1];plan=json.loads((BASE/'PLAN.json').read_text());assert name in plan['points'];point=plan['points'][name]
 assert Path('/etc/hostname').read_text().strip()=='33ace3d92505'and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
 quiet();root=BASE/name;root.mkdir();result={'passed':False,'rawAuditPassed':False}
 try:
  admission=json.loads((BASE/'CPU_ADMISSION.json').read_text());chosen=admission['chosen'];assert set(chosen)<=os.sched_getaffinity(0)
  candidate=json.loads((BASE/'CANDIDATE.json').read_text())
  assert hashlib.sha256(JAVA.read_bytes()).hexdigest()==candidate['javaBinarySha256']
  for n,v in candidate['files'].items():
   f=BASE/n;assert not f.is_symlink()and f.stat().st_size==v['bytes']and hashlib.sha256(f.read_bytes()).hexdigest()==v['sha256']
  sources=json.loads((BASE/'SOURCE_FILES.json').read_text());inputs=root/'inputs';inputs.mkdir()
  for n,v in sources.items():
   f=BASE/n;assert f.stat().st_size==v['bytes']and hashlib.sha256(f.read_bytes()).hexdigest()==v['sha256'];d=inputs/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,d)
  shutil.copy2(BASE/'SOURCE_FILES.json',inputs/'SOURCE_FILES.json')
  write(root/'environment.json',{'epoch':time.time(),'bootId':BOOT,'hostname':Path('/etc/hostname').read_text().strip(),'cpuMax':Path('/sys/fs/cgroup/cpu.max').read_text(),'clockTicksPerSecond':os.sysconf('SC_CLK_TCK'),'affinity':chosen,'allowed':sorted(os.sched_getaffinity(0)),'cpuInfo':Path('/proc/cpuinfo').read_text(),'freeBytes':shutil.disk_usage(BASE).free,'sourceCommit':candidate['sourceCommit'],'point':point})
  flags=['--add-opens=java.base/java.lang.reflect=ALL-UNNAMED','--add-opens=java.base/java.lang=ALL-UNNAMED','--add-opens=java.base/java.nio=ALL-UNNAMED','--add-exports=java.base/jdk.internal.ref=ALL-UNNAMED','--add-exports=java.base/sun.nio.ch=ALL-UNNAMED','--add-opens=java.base/java.io=ALL-UNNAMED','--add-opens=java.base/java.util=ALL-UNNAMED']
  argv=['taskset','-c',','.join(map(str,chosen)),str(JAVA),'-Xms1g','-Xmx1g','-XX:ActiveProcessorCount=8','-XX:+UseG1GC',*flags,'-Xlog:gc*,safepoint:file='+str(root/'controller-gc.log')+':time,uptime,level,tags']
  if point.get('qualification'):
   shutil.copytree(BASE/'dist',root/'input-artifacts/dist');shutil.copytree(BASE/'qualification',root/'input-artifacts/qualification')
   argv+=['-cp',str(BASE/'qualification/classes')+':'+str(BASE/'qualification/*')+':'+str(BASE/'dist/lib/*'),'io.vectormatch.bench.comparison.LinuxQualification',str(root/'junit')]
  else:
   assert shutil.disk_usage(BASE).free>point['rate']*point['seconds']*1024+768*1024**2
   argv+=['-Dvectormatch.comparison.presizeClientIds='+str(point.get('presize',False)).lower(),'-cp',str(BASE/'dist/lib/*'),'io.vectormatch.bench.comparison.ProcessIsolationComparison',point['placement'],point['collector'],str(point['rate']),str(point['seconds']),'73439',str(root/'native'),'3']
  assert supervise(argv,root,'java',450)==0,'native Java failed; retain original'
  quiet()
  if point.get('qualification'):
   proof=json.loads((root/'junit/RESULT.json').read_text());assert proof['found']==proof['passed']==12 and all(proof[k]==0 for k in ['failed','skipped','aborted','containerFailures'])
   assert supervise(['python3','-B','-m','unittest','discover','-s',str(BASE/'tests'),'-p','test_common_comparison.py','-v'],root,'python-tests',60)==0
   result['rawAuditPassed']=None
  else:
   assert supervise(['python3','-B',str(BASE/'audit-process-isolation.py'),str(root/'native'),'--output',str(root/'PYTHON_AUDIT.json')],root,'audit',300)==0
   assert json.loads((root/'PYTHON_AUDIT.json').read_text())['passed'];result['rawAuditPassed']=True
  result['passed']=True
 except BaseException as e:
  result['failure']=repr(e);(root/'failure.txt').write_text(traceback.format_exc());raise
 finally:write(root/'complete.json',result)
if __name__=='__main__':main()
