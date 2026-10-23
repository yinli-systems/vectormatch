import sys,pathlib,json,subprocess,concurrent.futures,datetime,time,shlex,hashlib,io,tarfile,re,shutil
BASE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(BASE.parent.parent/'runpod-20261023'));import remote
WORKSPACE=BASE.parents[3]
ROOT='/opt/vectormatch'; RELEASE=None
BUILD_TOOLS=None
OUT=WORKSPACE/'evidence/2026-10-23/runpod-optimization/threading'
PROFILE='baseline-30k'
LOAD_RELEASE=RELEASE
LOAD_IDENTITY={}
LOAD_JVM_ARGUMENTS=[]
ATTRIBUTION_ROOT=None
SOCKET_PROBE=None
JAVA=ROOT+'/tools/jdk/bin/java'; OPENS=['--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED']
COMMON={'JAVA_HOME':ROOT+'/tools/jdk','VECTOR_CLUSTER_HOSTS':','.join(n['private_ipv4'] for n in remote.NODES),'VECTOR_CLIENT_EGRESS_HOST':remote.NODES[2]['private_ipv4'],'VECTOR_AERON_MTU_LENGTH':'1248','VECTOR_SYNC_LEVEL':'2','VECTOR_PORT_BASE':'23000','VECTOR_DIST_ROOT':'','VECTOR_APPOINTED_LEADER_ID':'0','VECTOR_MAX_CLUSTER_SESSIONS':'128','VECTOR_MAX_HEAP':'1g'}
EVIDENCE=WORKSPACE/'evidence/2026-10-23/runpod-optimization'
PINNED_LOAD_REVISION='bdfe09a2907d9b953309e9e870d6f61f28c5e054'
PINNED_LOAD_BUNDLE='0afb2570dbfdfe6c11b43a68f18135b9e21e4c0efd79a66a8e5996f0f6f4f6c4'
PINNED_OBSERVER='b51226cc3902e77e457836e2ea2545b71fe7b1722caa7da9ee0630f118aa5dee'
PINNED_PROBE='29eaef020c644e9f64384c0b1773a5b4ede25326552b2cf6c68bf61799ebaf50'
PREPARED_SHA='2247db9c15b0043a0b28172c5bfa2d9e4f20b5748f6a16424d881e296102655f'


def digest(path):
 h=hashlib.sha256()
 with pathlib.Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()


def read_json(path):return json.loads(pathlib.Path(path).read_text())


def exclusive_save(path,value):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def archive_manifest(release):
 assert re.fullmatch('[a-f0-9]{40}',release['revision'])
 assert pathlib.PurePosixPath(release['root']).name==release['revision']
 archive=pathlib.Path(release['archive']);assert archive.is_file() and not archive.is_symlink()
 assert archive.stat().st_size==release['archiveBytes'] and digest(archive)==release['bundleSha256']
 with tarfile.open(archive) as tar:
  members=tar.getmembers();assert len(members)<=128
  assert len({m.name for m in members})==len(members)
  for item in members:
   q=pathlib.PurePosixPath(item.name)
   assert not q.is_absolute() and '..' not in q.parts and (item.isfile() or item.isdir())
  manifest=json.load(tar.extractfile('DEPLOYMENT.json'));assert manifest['revision']==release['revision']
  for name,expected in manifest['files'].items():
   assert hashlib.sha256(tar.extractfile(name).read()).hexdigest()==expected,name
  assert {m.name for m in members if m.isfile()}==set(manifest['files'])|{'DEPLOYMENT.json'}
 return manifest


def artifact_inputs(require_upload=False):
 """Local validation only; no remote action happens while loading a controller."""
 node=read_json(BASE/'node-release.json');build=read_json(BASE/'build.json')
 assert build['revision']==node['revision'] and build['source']=='git archive of committed source/build/tool files only'
 build_root=pathlib.Path(build['root']).resolve()
 assert build_root.parent==BASE and build_root.name=='build-'+node['revision']
 node_manifest=archive_manifest(node)
 assert read_json(EVIDENCE/'threading/node-deployment-manifest.json')==node_manifest
 java=read_json(EVIDENCE/'threading/tool-validation/java-tests.json')
 assert java['revision']==node['revision'] and java['exitCode']==0 and java['failures']==0 and java['skipped']==0
 tools={}
 for name in ('scripts/check-capacity-leader.py','scripts/verify-capacity-config.py','scripts/analyze-capacity.py'):
  path=build_root/name;assert path.is_file() and not path.is_symlink()
  tools[name]={'path':str(path),'sha256':digest(path)}
 load=read_json(BASE.parent/'loadgen-release.json')
 assert load['revision']==PINNED_LOAD_REVISION and load['bundleSha256']==PINNED_LOAD_BUNDLE
 load_manifest=archive_manifest(load);receipt=read_json(EVIDENCE/'loadgen-upload-receipt.json')
 assert receipt['verified'] and receipt['loadGeneratorRevision']==load['revision'] and receipt['files']==load_manifest['files']
 observer=read_json(BASE.parent/'attribution-release.json')
 assert observer['identity']==PINNED_OBSERVER
 deployed_observer=read_json(EVIDENCE/'attribution-deployment.json')
 assert deployed_observer['identity']==observer['identity'] and deployed_observer['sha256']==observer['sha256']
 assert {n['node'] for n in deployed_observer['nodes'] if n['passed']}=={0,1,2}
 probe=read_json(BASE.parent/'network/socket-probe.json')
 assert probe['sha256']==PINNED_PROBE and pathlib.PurePosixPath(probe['remotePath']).name=='owned-socket-buffer-29eaef020c644e9f.py'
 source=pathlib.Path(probe['source']);source=source if source.is_absolute() else WORKSPACE/source
 assert digest(source)==PINNED_PROBE
 uploaded_probe=read_json(EVIDENCE/'network/socket-probe-upload-receipt.json')
 assert {n['node'] for n in uploaded_probe['nodes'] if n['verified'] and n['sha256']==PINNED_PROBE}=={0,1,2}
 if require_upload:
  upload=read_json(EVIDENCE/'threading/node-upload-receipt.json')
  assert upload['bundleSha256']==node['bundleSha256'] and len(upload['nodes'])==3
  assert {n['node'] for n in upload['nodes']}=={0,1,2}
  for n in upload['nodes']:
   assert n['verified'] and n['nodeRevision']==node['revision'] and n['files']==node_manifest['files']
   assert n['launcherTest']['exitCode']==0
 return {'node':node,'load':load,'observer':observer,'probe':probe,'build':build,'buildTools':tools}


def checked_trial(root,task,expected_node=None):
 """Preserve overloaded points; require validity and correctness, not stability."""
 directory=root/task['cohort']/'runs'/task['id']
 trial=read_json(directory/'trial.json');result=read_json(directory/'result.json')
 assert trial.get('completedAt') and read_json(directory/'receipt.json')['exitCode']==0
 assert result['passed'] and read_json(directory/'fixed-leader-check.json')['passed']
 assert read_json(directory/'configuration-verification.json')['passed']
 if expected_node is not None:
  assert trial['release']==expected_node['root'] and trial['deploymentBundleSha256']==expected_node['bundleSha256']
 for key in ('rate','arrivals','workers','phase','repetition'):assert trial[key]==task[key],key
 summary=read_json(root/task['cohort']/'analysis/summary.json')
 rows=[r for r in summary['trials'] if r['id']==task['id']];assert len(rows)==1
 row=rows[0];assert row['measurementValid']
 configuration=read_json(directory/'configuration.json')
 assert configuration['preparedSnapshotSha256']==PREPARED_SHA
 assert configuration['clientDriverMode']=='shared' and configuration['clientDriverCount']==1
 assert configuration['clientAeronMode']=='one-independent-Aeron-per-client'
 fixed=trial['fixedNodeConfiguration']
 assert fixed['socketReceiveBufferArgumentBytes']==task['receiveBytes']
 if 'driverThreading' in task:assert fixed['driverThreadingArgument']==task['driverThreading']
 socket_states={}
 for stage in ('before','after'):
  observation=read_json(directory/f'socket-buffer-{stage}.json')
  assert observation['probeSourceSha256']==PINNED_PROBE and len(observation['nodes'])==3
  stage_state={}
  for observation_node in observation['nodes']:
   assert observation_node['exitCode']==0 and observation_node['result']['passed']
   result=observation_node['result'];member=result['node']
   assert member in (0,1,2) and member not in stage_state
   process=read_json(directory/f'node{member}'/'process.json')
   assert all(result[key]==process[key] for key in ('pid','startTicks','commandSha256'))
   roles={}
   for socket in result['sockets']:
    assert socket['receiveBufferKernelBytes']==2*task['receiveBytes'] and socket['sendBufferKernelBytes']==262144
    assert socket['role'] not in roles
    roles[socket['role']]=(socket['inode'],tuple(socket['fdNumbers']))
   required_roles={'ingress'} if member==0 else {'ingress','log'}
   assert required_roles <= set(roles)
   stage_state[member]=roles
  assert set(stage_state)=={0,1,2};socket_states[stage]=stage_state
 assert socket_states['before']==socket_states['after'],'Owned socket identities changed across the trial'
 for name,expected in row['inputSha256'].items():
  assert pathlib.PurePosixPath(name).name==name and digest(directory/name)==expected,name
 return {'id':task['id'],'classification':row['classification'],
         'resultSha256':digest(directory/'result.json'),'summarySha256':digest(root/task['cohort']/'analysis/summary.json'),
         'goodput':row['derived']['arrivalWindowGoodputPerSecond'],
         'conditionalP99Millis':row['derived']['latency']['conditionalAccepted']['p99Millis']}


def network_prerequisites():
 root=EVIDENCE/'network';plan=read_json(root/'plan.json')
 expected={f'n-r{label}-15000-w128-r{r}' for r in (1,2) for label in ('128k','1m')}
 assert len(plan['trials'])==4 and {t['id'] for t in plan['trials']}==expected
 checked=[checked_trial(root,t,plan['node']) for t in plan['trials']]
 timeline=root/'timeline.jsonl';events=[json.loads(line) for line in timeline.read_text().splitlines()]
 completed=[r for r in events if r.get('action')=='network-receive-buffer-matrix-completed']
 assert completed,'Network matrix has not completed; registration forbidden'
 latest=max(datetime.datetime.fromisoformat(read_json(root/t['cohort']/'runs'/t['id']/'trial.json')['completedAt']) for t in plan['trials'])
 assert datetime.datetime.fromisoformat(completed[-1]['timestamp'])>=latest
 return {'planSha256':digest(root/'plan.json'),'completionTimelineSha256':digest(timeline),'trials':checked}

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
 supervisor=RELEASE+'/deploy/remote_service.py'
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
def capture_socket_buffers(state, local, stage):
 if not SOCKET_PROBE:return
 def one(i):
  output=state+f'/watch/node{i}-socket-buffer-{stage}.json'
  args=['python3','-B',SOCKET_PROBE['remotePath'],'--node-record',state+f'/node-{i}/process.json','--node',str(i),'--port-base','23000','--bind-address',remote.NODES[i]['private_ipv4'],'--roles','ingress,log','--required-roles','ingress' if i==0 else 'ingress,log','--output',output]
  code='ARGS='+repr(args)+'\nSHA='+repr(SOCKET_PROBE['sha256'])+'\n'+"import subprocess,pathlib,json,hashlib\nassert hashlib.sha256(pathlib.Path(ARGS[2]).read_bytes()).hexdigest()==SHA;f=pathlib.Path(ARGS[-1]);f.parent.mkdir(parents=True,exist_ok=True);p=subprocess.run(ARGS,capture_output=True,text=True,timeout=8);print(json.dumps({'exitCode':p.returncode,'result':json.loads(f.read_text()) if f.exists() else None,'probeStderrBytes':len(p.stderr.encode())}))"
  return json.loads(py(i,code,20))
 rows=parallel(one);save(local/f'socket-buffer-{stage}.json',{'timestamp':now(),'probeSourceSha256':SOCKET_PROBE['sha256'],'nodes':rows})
 assert all(row['exitCode']==0 and row['result']['passed'] for row in rows),'Effective socket buffer evidence unavailable; do not proceed/replay'
 values=[s for row in rows for s in row['result']['sockets']]
 assert values and all(s['sendBufferKernelBytes']==262144 for s in values),'send buffer changed'
 requested=int(COMMON['VECTOR_SOCKET_RECEIVE_BUFFER_BYTES']);assert all(s['receiveBufferKernelBytes']==2*requested for s in values),'receive buffer treatment clamped/not effective'

def trial(ident,rate,arrivals,workers,phase='screen',rep=1):
 assert BUILD_TOOLS and RELEASE, 'Only the verified immutable matrix may launch trials'
 assert ident.replace('-','').isalnum(); local=OUT/'runs'/ident
 assert not local.exists(),ident
 assert shutil.disk_usage(OUT).free>350*1024*1024,'Insufficient local space to preserve full raw export'
 local.mkdir(parents=True)
 state=ROOT+'/runtime/capacity-20261023/'+ident; evidence=ROOT+'/evidence/capacity-'+ident; watch=state+'/watch'
 env={**COMMON,'VECTOR_STATE_DIR':state}
 manifest={'id':ident,'rate':rate,'arrivals':arrivals,'workers':workers,'queuePerWorker':64,'windowSeconds':arrivals/rate,'phase':phase,'repetition':rep,'state':state,'release':RELEASE,'profile':PROFILE,'loadGeneratorJvmArguments':list(LOAD_JVM_ARGUMENTS),**LOAD_IDENTITY,'budgetBefore':budget(),'startedAt':now()};save(local/'trial.json',manifest)
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
 capture_socket_buffers(state, local, 'before')
 def watchstart(i):
  jobs={'telemetry':['python3','-B',RELEASE+'/scripts/capacity-telemetry.py','--state-dir',state,'--output',watch+f'/node{i}-telemetry.jsonl','--interval','1','--duration','600']+(['--load-pid-file',watch+'/load-process.json'] if i==2 else []),
        'counters':[JAVA,*OPENS,'-Xmx128m','-cp',RELEASE+'/dist/cluster/lib/*','io.vectormatch.cluster.CapacityCounters',state+f'/node-{i}/driver',watch+f'/node{i}-counters.jsonl','600','1000']}
  if ATTRIBUTION_ROOT:
   jobs['attribution']=['python3','-B',ATTRIBUTION_ROOT+'/capacity-attribution.py','--node-record',state+f'/node-{i}/process.json','--output',watch+f'/node{i}-attribution.jsonl','--interval','1','--duration','600']+(['--load-record',watch+'/load-process.json'] if i==2 else [])
  return json.loads(py(i,'RELEASE='+repr(RELEASE)+'\nWATCH='+repr(watch)+'\nENV='+repr(env)+'\nJOBS='+repr(jobs)+'\n'+SPAWN))
 save(local/'observer-processes.json',parallel(watchstart))
 args=[JAVA,*OPENS,*LOAD_JVM_ARGUMENTS,'-Xmx2g','-cp',LOAD_RELEASE+'/dist/cluster/lib/*','io.vectormatch.cluster.RemoteCapacityExperiment',evidence,'23000',str(rate),str(arrivals),str(workers),'64','2000','30000','0','20']+([PROFILE] if PROFILE.startswith('extended-') else [])
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
 capture_socket_buffers(state, local, 'after')
 def stopwatch(i):
  code='RELEASE='+repr(RELEASE)+'\nWATCH='+repr(watch)+'\n'+'''import pathlib,importlib.util
spec=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base=pathlib.Path(WATCH)
for name in ('telemetry','counters','attribution'):m.stop(base,base/(name+'-process.json'))
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
 for name in [f'node{NODE}-telemetry.jsonl',f'node{NODE}-counters.jsonl',f'node{NODE}-attribution.jsonl','telemetry.log','counters.log','attribution.log']:
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
  for kind in ('counters','telemetry','attribution'):
   p=local/f'node{i}'/f'node{i}-{kind}.jsonl'
   if p.exists():p.replace(local/f'node{i}-{kind}.jsonl')
 parallel(export)
 record('nodes-stop',id=ident,stdout=parallel(lambda i:service(i,'node','stop',env)))
 manifest['completedAt']=now();manifest['budgetAfter']=budget(0);save(local/'trial.json',manifest)
 assert BUILD_TOOLS, 'Immutable leader checker was not configured'
 subprocess.run([sys.executable,'-B',BUILD_TOOLS['scripts/check-capacity-leader.py']['path'],str(local)],check=True)
 data=json.loads((local/'result.json').read_text()) if (local/'result.json').exists() else None
 record('trial-complete',id=ident,receipt=receipt,summary=None if data is None else {k:data.get(k) for k in ['targetArrivalRatePerSecond','workers','confirmedWithinArrivalWindowPerSecond','confirmedIncludingDrainPerSecond','acceptedScheduledToConfirmedMicroseconds','clientNotSentCommands','unknownAtInitialDeadline','generatorTimingInvalid','passed']})
 return data


if __name__=='__main__':
 raise SystemExit('Helper only: review register.py / matrix.py; never submit an existing trial ID again')
