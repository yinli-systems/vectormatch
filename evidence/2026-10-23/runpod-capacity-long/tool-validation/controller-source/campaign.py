import sys,pathlib,json,subprocess,concurrent.futures,datetime,time,shlex,hashlib,io,tarfile,re
BASE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent/'runpod-20261023'));import remote
ROOT='/opt/vectormatch'; RELEASE=json.loads((remote.ROOT/'current-release.json').read_text())['root']
ORIGINAL=ROOT+'/releases/e1db2e755a834234efb60b7a1ed291b31ce33c16'
OUT=pathlib.Path.cwd()/'evidence/2026-10-23/runpod-capacity';OUT.mkdir(exist_ok=True)
PROFILE='baseline-30k'
LOAD_RELEASE=RELEASE
LOAD_IDENTITY={}
JAVA=ROOT+'/tools/jdk/bin/java'; OPENS=['--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED']
COMMON={'JAVA_HOME':ROOT+'/tools/jdk','VECTOR_CLUSTER_HOSTS':','.join(n['private_ipv4'] for n in remote.NODES),'VECTOR_CLIENT_EGRESS_HOST':remote.NODES[2]['private_ipv4'],'VECTOR_AERON_MTU_LENGTH':'1248','VECTOR_SYNC_LEVEL':'2','VECTOR_PORT_BASE':'23000','VECTOR_DIST_ROOT':RELEASE+'/dist','VECTOR_APPOINTED_LEADER_ID':'0','VECTOR_MAX_CLUSTER_SESSIONS':'128','VECTOR_MAX_HEAP':'1g'}
ORIG={**COMMON,'VECTOR_DIST_ROOT':ORIGINAL+'/dist','VECTOR_PORT_BASE':'19000','VECTOR_STATE_DIR':ROOT+'/runtime/cloud-20261023-01','VECTOR_APPOINTED_LEADER_ID':'','VECTOR_MAX_CLUSTER_SESSIONS':'','VM_PG_URL':'jdbc:postgresql://127.0.0.1:55432/postgres','VM_PG_USER':'vectormatch','VM_CLUSTER_ID':'runpod-cloud-20261023-01','VM_HTTP_PORT':'8000','VECTOR_WEB_DIR':ROOT+'/web/dist'}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2)+'\n')
def record(action,**kw):
 row={'timestamp':now(),'action':action,**kw};print(json.dumps(row),flush=True)
 with (OUT/'timeline.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
def budget(seconds=600):
 dt=datetime.datetime.now(datetime.timezone.utc);cost=sum((dt-datetime.datetime.fromisoformat(n['created_utc_estimate'].replace('Z','+00:00'))).total_seconds()/3600*(n['hourly_compute_usd']+n['hourly_disk_usd_estimate']) for n in remote.NODES)
 d={'asOfUtc':now(),'estimatedAccruedUsd':cost,'nextTrialReserveSeconds':seconds,'projectedIncludingRecoveryReserveUsd':cost+1.56*seconds/3600+2,'budgetUsd':20,'scope':'Project three Pods only, launch-time/rate estimate, not reconciled bill'}
 assert d['projectedIncludingRecoveryReserveUsd']<20,d
 return d

def py(i,code,timeout=90):
 p=remote.run(i,'python3 -B -',input=code,timeout=timeout)
 if p.returncode:raise RuntimeError(f'node{i} rc{p.returncode}: {p.stdout} {p.stderr}')
 return p.stdout

def service(i,role,action,env):
 supervisor=ROOT+'/deploy/remote_service.py' if env.get('VECTOR_STATE_DIR')==ORIG['VECTOR_STATE_DIR'] else RELEASE+'/deploy/remote_service.py'
 args=['python3','-B',supervisor,role,action]+([str(i)] if role=='node' else [])
 code='CONFIG='+repr({**env,'VECTOR_MAX_HEAP':env.get('VECTOR_MAX_HEAP','1g') if role=='node' else '512m'})+'\nARGS='+repr(args)+'\n'+'''import os,subprocess
e=os.environ.copy();e.update(CONFIG);p=subprocess.run(ARGS,cwd='/opt/vectormatch',env=e,capture_output=True,text=True,timeout=45);print(p.stdout+p.stderr);raise SystemExit(p.returncode)
'''
 return py(i,code,60)

def parallel(fn):
 with concurrent.futures.ThreadPoolExecutor() as pool:return list(pool.map(fn,range(3)))

def members(state):
 args=[JAVA,*OPENS,'-Xmx128m','-cp',RELEASE+'/dist/cluster/lib/*','io.aeron.cluster.ClusterTool',state+'/node-0/cluster','list-members']
 p=remote.run(0,' '.join(map(shlex.quote,args)),timeout=25)
 return {'timestamp':now(),'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}

def prepare():
 record('prepare-budget',**budget(3600))
 for i in range(3):
  q=remote.run(i,'mkdir -p '+shlex.quote(RELEASE+'/scripts/tests'));assert q.returncode==0
  for f,target in [('scripts/capacity-telemetry.py','scripts/capacity-telemetry.py'),('scripts/tests/test_capacity_telemetry.py','scripts/tests/test_capacity_telemetry.py')]:
   p=remote.upload(i,f,RELEASE+'/'+target);assert p.returncode==0,p.stderr
  code='RELEASE='+repr(RELEASE)+'\n'+'''import subprocess,sys,json
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',RELEASE+'/scripts/tests','-p','test_capacity_telemetry.py'],capture_output=True,text=True);print(json.dumps({'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}));raise SystemExit(p.returncode)
'''
  save(OUT/'tool-validation'/f'linux-telemetry-node{i}.json',json.loads(py(i,code)))
  p=remote.run(i,'cd '+shlex.quote(RELEASE+'/deploy')+' && python3 -B -m unittest test_remote_service.py',timeout=40)
  save(OUT/'tool-validation'/f'linux-launcher-node{i}.json',{'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert p.returncode==0
 for role in ('gateway','projector'):record('pause-original',role=role,stdout=service(2,role,'stop',ORIG))
 record('stop-original-nodes',stdout=parallel(lambda i:service(i,'node','stop',ORIG)))
 p=remote.run(2,"runuser -u vectormatch-pg -- /opt/vectormatch/.tools/postgres/bin/pg_ctl -D /opt/vectormatch/runtime/postgres18 -m fast -w stop",timeout=40)
 record('stop-original-postgres',exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr);assert p.returncode==0
 save(OUT/'deployment.json',json.loads((remote.ROOT/'current-release.json').read_text()))

SPAWN='''import os,pathlib,subprocess,json,hashlib,time,importlib.util
spec=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base=pathlib.Path(WATCH);base.mkdir(parents=True,exist_ok=True)
e=os.environ.copy();e.update(ENV)
records={}
for name,args in JOBS.items():
 record=base/(name+'-process.json')
 if record.exists():raise RuntimeError('Refusing duplicate job '+name)
 with (base/(name+'.log')).open('ab') as log:
  child=subprocess.Popen(args,cwd='/opt/vectormatch',env=e,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  expected=hashlib.sha256(b''.join(os.fsencode(a)+b'\\0' for a in args)).hexdigest()
  identity=m.await_process_identity(child,expected,base/(name+'.log'))
  records[name]={'version':1,'pid':child.pid,**identity};m.write_json(record,records[name])
print(json.dumps(records))
'''
CONTROLLER='''import pathlib,json,subprocess,os,hashlib,importlib.util,datetime
cfg=json.loads(pathlib.Path(__file__).with_suffix('.json').read_text());base=pathlib.Path(cfg['watch'])
spec=importlib.util.spec_from_file_location('svc',cfg['release']+'/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
e=os.environ.copy();e.update(cfg['env'])
p=None
try:
 with (base/'load.log').open('ab') as log:
  p=subprocess.Popen(cfg['args'],cwd='/opt/vectormatch',env=e,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
  identity=m.await_process_identity(p,hashlib.sha256(b''.join(os.fsencode(a)+b'\\0' for a in cfg['args'])).hexdigest(),base/'load.log')
  m.write_json(base/'load-process.json',{'version':1,'pid':p.pid,**identity})
  rc=p.wait(timeout=600)
 m.write_json(base/'receipt.json',{'exitCode':rc,'completedAt':datetime.datetime.now(datetime.timezone.utc).isoformat()})
except BaseException as exc:
 if p is not None and p.poll() is None:
  p.terminate()
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
 m.write_json(base/'receipt.json',{'exitCode':-1,'errorType':type(exc).__name__,'error':str(exc),'loadConfirmedStopped':p is None or p.poll() is not None})
 raise
'''
def trial(ident,rate,arrivals,workers,phase='screen',rep=1):
 assert ident.replace('-','').isalnum(); local=OUT/'runs'/ident
 assert not local.exists(),ident
 local.mkdir(parents=True)
 state=ROOT+'/runtime/capacity-20261023/'+ident; evidence=ROOT+'/evidence/capacity-'+ident; watch=state+'/watch'
 env={**COMMON,'VECTOR_STATE_DIR':state}
 manifest={'id':ident,'rate':rate,'arrivals':arrivals,'workers':workers,'queuePerWorker':64,'windowSeconds':arrivals/rate,'phase':phase,'repetition':rep,'state':state,'release':RELEASE,'profile':PROFILE,**LOAD_IDENTITY,'budgetBefore':budget(),'startedAt':now()};save(local/'trial.json',manifest)
 record('trial-start',id=ident,rate=rate,workers=workers,budget=manifest['budgetBefore'])
 record('nodes-start',id=ident,stdout=parallel(lambda i:service(i,'node','start',env)))
 deadline=time.monotonic()+60
 while True:
  pre=members(state)
  terms=re.findall(r'leadershipTermId=(-?\d+), logPosition=(-?\d+)',pre['stdout'])
  if pre['exitCode']==0 and 'leaderMemberId=0' in pre['stdout'] and len(terms)==3 and len({t for t,p in terms})==1 and int(terms[0][0])>=0 and min(int(p) for t,p in terms)>=0:break
  if time.monotonic()>deadline:save(local/'pre-members.json',pre);raise RuntimeError('cluster not ready '+str(pre))
  time.sleep(1)
 save(local/'pre-members.json',pre)
 def watchstart(i):
  jobs={'telemetry':['python3','-B',RELEASE+'/scripts/capacity-telemetry.py','--state-dir',state,'--output',watch+f'/node{i}-telemetry.jsonl','--interval','1','--duration','600']+(['--load-pid-file',watch+'/load-process.json'] if i==2 else []),
        'counters':[JAVA,*OPENS,'-Xmx128m','-cp',RELEASE+'/dist/cluster/lib/*','io.vectormatch.cluster.CapacityCounters',state+f'/node-{i}/driver',watch+f'/node{i}-counters.jsonl','600','1000']}
  return json.loads(py(i,'RELEASE='+repr(RELEASE)+'\nWATCH='+repr(watch)+'\nENV='+repr(env)+'\nJOBS='+repr(jobs)+'\n'+SPAWN))
 save(local/'observer-processes.json',parallel(watchstart))
 args=[JAVA,*OPENS,'-Xmx2g','-cp',LOAD_RELEASE+'/dist/cluster/lib/*','io.vectormatch.cluster.RemoteCapacityExperiment',evidence,'23000',str(rate),str(arrivals),str(workers),'64','2000','30000','0','20']+([PROFILE] if PROFILE.startswith('extended-') else [])
 cfg={'release':RELEASE,'watch':watch,'env':env,'args':args}
 code='WATCH='+repr(watch)+'\nCONFIG='+repr(cfg)+'\nCODE='+repr(CONTROLLER)+'\n'+'''import pathlib,subprocess,json
base=pathlib.Path(WATCH);p=base/'load-controller.py';assert not p.exists();p.write_text(CODE);p.with_suffix('.json').write_text(json.dumps(CONFIG))
with (base/'controller.log').open('ab') as log:q=subprocess.Popen(['python3','-B',str(p)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'controllerPid':q.pid}))
'''
 record('load-start',id=ident,**json.loads(py(2,code)))
 deadline=time.monotonic()+610
 while True:
  receipt=json.loads(py(2,'import pathlib,json\np=pathlib.Path('+repr(watch+'/receipt.json')+');print(p.read_text() if p.exists() else "null")'))
  if receipt is not None:break
  if time.monotonic()>deadline:raise RuntimeError('job pending; query same trial, do not resubmit')
  time.sleep(4)
 save(local/'receipt.json',receipt)
 save(local/'post-members.json',members(state))
 def stopwatch(i):
  code='RELEASE='+repr(RELEASE)+'\nWATCH='+repr(watch)+'\n'+'''import pathlib,importlib.util
spec=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base=pathlib.Path(WATCH)
for name in ('telemetry','counters'):m.stop(base,base/(name+'-process.json'))
'''
  return py(i,code)
 record('observer-stop',id=ident,stdout=parallel(stopwatch))
 return finish(ident)

def finish(ident):
 local=OUT/'runs'/ident;manifest=json.loads((local/'trial.json').read_text());state=manifest['state'];watch=state+'/watch';evidence=ROOT+'/evidence/capacity-'+ident;env={**COMMON,'VECTOR_STATE_DIR':state};receipt=json.loads((local/'receipt.json').read_text())
 def export(i):
  code='WATCH='+repr(watch)+'\nEVIDENCE='+repr(evidence)+'\nNODE='+repr(i)+'\nSTATE='+repr(state)+'\n'+'''import pathlib,tarfile,sys
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 base=pathlib.Path(WATCH)
 for name in [f'node{NODE}-telemetry.jsonl',f'node{NODE}-counters.jsonl','telemetry.log','counters.log']:
  p=base/name
  if p.is_file():tar.add(p,arcname=f'node{NODE}/'+name,recursive=False)
 for name in ('process.json','process.log'):
  p=pathlib.Path(STATE)/f'node-{NODE}'/name
  if p.is_file():tar.add(p,arcname=f'node{NODE}/'+name,recursive=False)
 if NODE==2:
  for name in ['load.log','load-process.json','receipt.json','controller.log']:
   p=base/name
   if p.is_file():tar.add(p,arcname=name,recursive=False)
  base=pathlib.Path(EVIDENCE)
  if base.is_dir():
   for p in sorted(base.iterdir()):
    if p.is_file() and not p.is_symlink() and p.suffix in ('.json','.csv','.bin','.log'):tar.add(p,arcname=p.name,recursive=False)
'''
  p=subprocess.run(remote.sshargs(i)+['python3 -B -'],input=code.encode(),capture_output=True,timeout=60);assert p.returncode==0,p.stderr.decode()
  with tarfile.open(fileobj=io.BytesIO(p.stdout),mode='r:gz') as a:
   for member in a.getmembers():
    name=pathlib.PurePosixPath(member.name);assert not name.is_absolute() and '..' not in name.parts and member.isfile()
    target=local.joinpath(*name.parts);target.parent.mkdir(parents=True,exist_ok=True);data=a.extractfile(member).read()
    if target.exists():
     assert target.read_bytes()==data or target.suffix=='.json' and json.loads(target.read_bytes())==json.loads(data),target
    else:target.write_bytes(data)
  for kind in ('counters','telemetry'):
   p=local/f'node{i}'/f'node{i}-{kind}.jsonl'
   if p.exists():p.replace(local/f'node{i}-{kind}.jsonl')
 parallel(export)
 record('nodes-stop',id=ident,stdout=parallel(lambda i:service(i,'node','stop',env)))
 manifest['completedAt']=now();manifest['budgetAfter']=budget(0);save(local/'trial.json',manifest)
 if pathlib.Path('scripts/check-capacity-leader.py').exists():subprocess.run([sys.executable,'-B','scripts/check-capacity-leader.py',str(local)],check=False)
 data=json.loads((local/'result.json').read_text()) if (local/'result.json').exists() else None
 record('trial-complete',id=ident,receipt=receipt,summary=None if data is None else {k:data.get(k) for k in ['targetArrivalRatePerSecond','workers','confirmedWithinArrivalWindowPerSecond','confirmedIncludingDrainPerSecond','acceptedScheduledToConfirmedMicroseconds','clientNotSentCommands','unknownAtInitialDeadline','generatorTimingInvalid','passed']})
 return data

def restore():
 p=remote.run(2,"runuser -u vectormatch-pg -- /opt/vectormatch/.tools/postgres/bin/pg_ctl -D /opt/vectormatch/runtime/postgres18 -l /opt/vectormatch/runtime/postgres18/server.log -o '-h 127.0.0.1 -p 55432 -k /opt/vectormatch/runtime/pg-socket -c fsync=on -c synchronous_commit=on -c max_connections=30' -w start",timeout=45)
 record('restore-postgres',exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr);assert p.returncode==0
 record('restore-original-nodes',stdout=parallel(lambda i:service(i,'node','start',ORIG)))
 for role in ('projector','gateway'):record('restore-original-role',role=role,stdout=service(2,role,'start',ORIG))
 record('restore-budget',**budget(0))

if __name__=='__main__':
 action=sys.argv[1]
 if action=='prepare':prepare()
 elif action=='restore':restore()
 elif action=='finish':finish(sys.argv[2])
 elif action=='trial':trial(sys.argv[2],int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]),sys.argv[6] if len(sys.argv)>6 else 'screen',int(sys.argv[7]) if len(sys.argv)>7 else 1)
 else:raise ValueError(action)
