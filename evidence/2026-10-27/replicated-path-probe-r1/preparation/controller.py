"""Existing-host replicated qualification and bounded 30-minute endurance controller."""
from pathlib import Path
import sys,json,time,shlex,subprocess,base64,concurrent.futures,hashlib
P=Path(__file__).resolve().parent
sys.path.insert(0,'/Users/kevin/Documents/ChatGPT/App 2/runtime/cloud/cpu-20261024/current-read-window32-collection-preparation-r2');import remote_current as remote
ROOT='/opt/vectormatch-cpu/experiments/replicated-path-probe-20261027-r1';PLAN=json.loads((P/'PLAN.json').read_text());JAVA=json.loads((P/'CANDIDATE.json').read_text())['javaPath']
def checked(code,timeout=60):
 r=remote.run('python3 -',input=code,timeout=timeout)
 assert r.returncode==0,r.stdout+'\n'+r.stderr
 return json.loads(r.stdout)
def save(path,value):
 body=json.dumps(value,indent=2)+'\n'
 if path.exists():assert json.loads(path.read_text())==value
 else:path.write_text(body)
def progress(value):
 value['epoch']=time.time();(P/'PROGRESS.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)
def config(role,case,collector,seconds,qualification,probe=None):
 prefix=ROOT+'/experiments/'+case;run=prefix+'/node%d-g0'%role;spec=PLAN['cases'][case]
 env=dict(VECTOR_AERON_MTU_LENGTH='1248',VECTOR_CLUSTER_HOSTS='127.0.0.1,127.0.0.1,127.0.0.1',VECTOR_CLIENT_EGRESS_HOST='127.0.0.1',VECTOR_OUTBOX_CAPACITY='524288')
 state=prefix+('/evidence'if role==3 else'/state');telemetry=prefix+'/telemetry/node%d-g0'%role
 props=['-Daeron.cluster.max.sessions=256','-Xlog:class+load=info:file='+run+'/class-origins.log','-javaagent:'+ROOT+'/soak-agent.jar='+state+','+telemetry,'-Xlog:gc*,safepoint:file='+run+'/gc.log:time,uptime,level,tags:filecount=2,filesize=10M']
 if role<3:
  props+=['-Daeron.cluster.appointed.leader.id=0','-Dvectormatch.node.dataPathMaxParkNs='+str(spec['maxParkNs'])]
  args=['io.vectormatch.cluster.ReplicatedPathProbeNode',spec['mode'],prefix+'/worker-%d.csv'%role,str(role),prefix+'/state',str(PLAN['portBase']),'2','524288',env['VECTOR_CLUSTER_HOSTS'],'capacity-190k-v1','131072','SHARED']
 else:args=['io.vectormatch.cluster.ReplicatedPathProbe',prefix+'/evidence',str(PLAN['portBase']),str(spec['rate']),str(seconds),spec['mode']]
 return dict(root=ROOT,java=JAVA,boot=PLAN['boot'],host=PLAN['host'],case=case,generation='node%d-g0'%role,deadline=time.time()+seconds+900,environment=env,properties=props,mainArgs=args,collector='G1',cpus=PLAN['cpuSets'][role])
def start(cfg):
 code='ROOT='+repr(ROOT)+'\nC='+repr(cfg)+'\n'+r'''
from pathlib import Path
import json,subprocess
r=Path(ROOT);p=r/'control';p.mkdir(exist_ok=True);name=C['case']+'-'+C['generation'];launch=p/(name+'.launch.json')
if launch.exists():print(launch.read_text());raise SystemExit(0)
cf=p/(name+'.json');cf.open('x').write(json.dumps(C));log=(p/(name+'.log')).open('xb')
with cf.open('rb')as inp:q=subprocess.Popen(['python3',str(r/'process_agent.py')],stdin=inp,stdout=log,stderr=log,start_new_session=True)
s=Path('/proc/'+str(q.pid)+'/stat').read_text().split(') ',1)[1].split();v={'pid':q.pid,'startTicks':s[19]};launch.write_text(json.dumps(v));print(json.dumps(v))
'''
 return checked(code)
def status(case):
 return checked('ROOT='+repr(ROOT)+'\nCASE='+repr(case)+'\n'+r'''
from pathlib import Path
import json,shutil
p=Path(ROOT)/'experiments'/CASE
out=[]
for i in range(4):
 d=p/('node%d-g0'%i);out.append({n:(d/n).read_text()[-6000:]if(d/n).exists()else None for n in ['LAUNCH.json','EXIT.json','stdout.log','stderr.log']})
f=p/'evidence/soak-minute-windows.csv';print(json.dumps({'roles':out,'free':shutil.disk_usage(ROOT).free,'minutes':f.read_text()[-1600:]if f.exists()else None}))
''')
def stop(role,case):
 code='ROOT='+repr(ROOT)+'\nCASE='+repr(case)+'\nROLE='+repr(role)+'\nJAVA='+repr(JAVA)+'\n'+r'''
from pathlib import Path
import json,subprocess,time
p=Path(ROOT)/'experiments'/CASE/('node%d-g0'%ROLE)
if not(p/'LAUNCH.json').exists():print(json.dumps({'notLaunched':True}));raise SystemExit(0)
r=json.loads((p/'LAUNCH.json').read_text());assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==r['boot']
if not(p/'EXIT.json').exists():
 stat=Path('/proc/%d/stat'%r['pid']);fields=stat.read_text().split(') ',1)[1].split();assert fields[19]==r['startTicks']
 option=next(x for x in r['argv']if x.startswith('-javaagent:'));dest=Path(option.split(',',1)[1])/'final-buffered-tail.jfr'
 if not dest.exists():
  q=subprocess.run([str(Path(JAVA).with_name('jcmd')),str(r['pid']),'JFR.dump','name=1','filename='+str(dest)],capture_output=True,text=True,timeout=30)
  (p/'JFR_CONTROLLED_DUMP.json').write_text(json.dumps(dict(returncode=q.returncode,stdout=q.stdout,stderr=q.stderr),indent=2))
  # Even on failed dump stop this owned test child, retaining the failed capture.
 (p/'stop.json').write_text(json.dumps({'epoch':time.time()}))
print(json.dumps({'stopRequested':True}))
'''
 return checked(code,45)
def stop_all(case):
 # Source first on abort; replica stops are concurrent and restricted to birth-checked PIDs.
 ss=status(case)['roles']
 if ss[3]['LAUNCH.json']and not ss[3]['EXIT.json']:stop(3,case)
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:list(pool.map(lambda i:stop(i,case),range(3)))
 for k in range(40):
  ss=status(case)['roles']
  if all(not s['LAUNCH.json']or s['EXIT.json']for s in ss):return
  time.sleep(1)
 raise RuntimeError('owned child closure not confirmed')
def run(case,collector,seconds,qualification,probe=None):
 progress({'stage':'native_start','case':case,'collector':collector,'seconds':seconds})
 quiet=checked('from pathlib import Path\nimport json,shutil\nrows=[]\nfor f in Path("/proc").glob("[0-9]*/comm"):\n try:\n  if f.read_text().strip()=="java":rows.append(str(f))\n except(FileNotFoundError,ProcessLookupError):pass\nprint(json.dumps({"java":rows,"free":shutil.disk_usage('+repr(ROOT)+').free}))')
 assert not quiet['java']and quiet['free']>1_800_000_000,quiet
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:list(pool.map(lambda i:start(config(i,case,collector,seconds,qualification)),range(3)))
  for k in range(100):
   ss=status(case)['roles'][:3];assert not any(s['EXIT.json']for s in ss),ss
   if all('VECTOR_CLUSTER_STARTED'in(s['stdout.log']or'')for s in ss):break
   time.sleep(.5)
  else:raise RuntimeError('cluster startup timeout')
  save(P/(case+'-nodes-ready.json'),ss);start(config(3,case,collector,seconds,qualification,probe))
  until=time.monotonic()+seconds+700;next_progress=0
  while time.monotonic()<until:
   state=status(case);s=state['roles'][3]
   if time.monotonic()>=next_progress:
    next_progress=time.monotonic()+30;progress({'stage':'native_active','case':case,'free':state['free'],'minutes':state['minutes']})
   assert state['free']>=512*1024**2,'disk floor; preserve original partial outcomes'
   assert not any(x['EXIT.json']for x in state['roles'][:3]),'replica exited'
   if s['EXIT.json']:
    save(P/(case+'-client-exit.json'),s);assert json.loads(s['EXIT.json'])['returncode']==0,s;break
   time.sleep(5)
  else:raise RuntimeError('client watchdog')
 finally:stop_all(case)
 save(P/(case+'-closed.json'),status(case));progress({'stage':'native_closed','case':case})
