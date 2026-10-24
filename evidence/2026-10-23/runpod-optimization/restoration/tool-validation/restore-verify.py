import campaign as c,pathlib,json,time,urllib.request,subprocess,sys,shlex
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-optimization/restoration').resolve();c.OUT.mkdir(parents=True,exist_ok=True)
if '--resume-checks' not in sys.argv:c.restore()
import socket,os,hashlib
probe=socket.socket();probe.settimeout(1);connected=probe.connect_ex(('127.0.0.1',8011))==0;probe.close()
if not connected:
 ssh=c.remote.sshargs(2);args=ssh[:-1]+['-N','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-L','127.0.0.1:8011:127.0.0.1:8000',ssh[-1]]
 with pathlib.Path('runtime/cloud/optimization-20261024/restored-tunnel.log').open('ab') as log:
  tunnel=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 c.save(pathlib.Path('runtime/cloud/optimization-20261024/restored-tunnel.json'),{'pid':tunnel.pid,'commandSha256':hashlib.sha256(b''.join(os.fsencode(x)+b'\0' for x in args)).hexdigest(),'purpose':'owned loopback-only forward for original platform after capacity tests'})
# Pause generated flow as soon as HTTP binds, before waiting for projection catch-up.
pause_errors=[];pause_deadline=time.monotonic()+100
while True:
 try:
  req=urllib.request.Request('http://127.0.0.1:8011/api/control/flow',data=b'{"enabled":false}',headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=8) as r:early_flow=json.load(r)
  assert early_flow['enabled'] is False
  c.save(c.OUT/'early-flow-pause.json',{'timestamp':c.now(),'response':early_flow,'retries':pause_errors});break
 except Exception as exc:
  pause_errors.append({'timestamp':c.now(),'type':type(exc).__name__})
  if time.monotonic()>pause_deadline:raise RuntimeError('Unable to pause generated flow after restoration')
  time.sleep(.5)
errors=[];deadline=time.monotonic()+100
while True:
 try:
  with urllib.request.urlopen('http://127.0.0.1:8011/api/state',timeout=20) as r:state=json.load(r)
  if state['health']['status']=='UP' and state['health']['mode']=='CLUSTER_REPLICATED' and state['health']['mirrorStatus']=='SYNCHRONIZED' and state['projection']['status']=='OBSERVED' and state['projection']['clusterId']=='runpod-cloud-20261023-01' and state['projection']['lag']==0 and state['projection']['cursor']==state['health']['mirrorEventSeq']:break
 except Exception as exc:errors.append({'timestamp':c.now(),'type':type(exc).__name__})
 if time.monotonic()>deadline:raise RuntimeError('Original application readiness failed')
 time.sleep(1)
req=urllib.request.Request('http://127.0.0.1:8011/api/control/flow',data=b'{"enabled":false}',headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=30) as r:flow=json.load(r)
with urllib.request.urlopen('http://127.0.0.1:8011/api/state',timeout=30) as r:state=json.load(r)
assert flow['enabled'] is False and state['health']['flowEnabled'] is False
assert state['projection']['cursor']==state['health']['mirrorEventSeq'] and state['projection']['lag']==0
c.save(c.OUT/'http-state.json',state)
c.save(c.OUT/'restored-readiness.json',{'passed':True,'timestamp':c.now(),'health':state['health'],'projection':state['projection'],'flowPauseResponse':flow,'readinessRetries':errors,'scope':'Resumed original e1db release and preserved original state on the same Pods; normal leader election, original port19000/outbox65536/session defaults. No Pod restart, state backup restore, or high-load measurement of gateway/PostgreSQL/WS.'})
original_manifest=json.loads(pathlib.Path('evidence/2026-10-23/runpod-egress/deployment/DEPLOYMENT.json').read_text())
assert original_manifest['revision']=='e1db2e755a834234efb60b7a1ed291b31ce33c16'
def original_identity(i):
 code='RELEASE='+repr(c.ORIGINAL)+'\nFILES='+repr(original_manifest['files'])+'\nSTATE='+repr(c.ORIG['VECTOR_STATE_DIR'])+'\nNODE='+repr(i)+'\n'+'''import pathlib,hashlib,json,importlib.util
spec=importlib.util.spec_from_file_location('original_supervisor','/opt/vectormatch/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for name,expected in FILES.items():assert hashlib.sha256((pathlib.Path(RELEASE)/name).read_bytes()).hexdigest()==expected,name
roles={'node':pathlib.Path(STATE)/('node-'+str(NODE))}
if NODE==2:roles.update(projector=pathlib.Path(STATE)/'projector',gateway=pathlib.Path(STATE)/'gateway')
records={}
for role,folder in roles.items():
 status,record=m.record_state(folder/'process.json');assert status=='running',role
 assert record['role']==role and RELEASE+'/dist/'+{'node':'cluster','gateway':'server','projector':'projector'}[role]+'/lib/*' in record['arguments']
 if role=='node':
  assert '-Xmx1g' in record['arguments'] and '19000' in record['arguments']
  assert not any(a.startswith(('-Daeron.cluster.appointed.leader.id=','-Daeron.cluster.max.sessions=')) for a in record['arguments'])
 records[role]=record
print(json.dumps({'passed':True,'node':NODE,'verifiedArtifactFiles':len(FILES),'processRecords':records}))
'''
 return json.loads(c.py(i,code,45))
c.save(c.OUT/'original-artifact-and-processes.json',{'timestamp':c.now(),'manifestRevision':original_manifest['revision'],'manifestSha256':hashlib.sha256(pathlib.Path('evidence/2026-10-23/runpod-egress/deployment/DEPLOYMENT.json').read_bytes()).hexdigest(),'nodes':c.parallel(original_identity),'scope':'Known artifact files hashed and live PID/startTicks/full-command identity verified; no process environments or database archives read.'})
cp=c.ORIGINAL+'/dist/server/lib/*'
source=pathlib.Path('runtime/cloud/runpod-20261023/PgAudit.java')
r=c.remote.run(2,'mkdir -p /opt/vectormatch/probe',timeout=20);assert r.returncode==0
r=c.remote.upload(2,source,'/opt/vectormatch/probe/PgAudit.java');assert r.returncode==0
args=[c.JAVA,'-Xmx128m','-cp',cp,'/opt/vectormatch/probe/PgAudit.java']
r=c.remote.run(2,' '.join(map(shlex.quote,args)),timeout=60)
if r.returncode:
 c.save(c.OUT/'pg-audit-failure.json',{'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr});raise RuntimeError('PG audit failed')
a=json.loads(r.stdout);assert a['passed'];assert a['cursor']['event_seq']==state['projection']['cursor'];assert a['cursor']['trades_stored']==state['projection']['tradesStored'];c.save(c.OUT/'postgres-ledger.json',a)
subprocess.run([str(pathlib.Path('.tools/node/bin/node').resolve()),'runtime/cloud/runpod-20261023/ws-check.mjs',str(c.OUT/'websocket.json')],check=True)
c.save(c.OUT/'budget.json',c.budget(0))
c.record('original-platform-restored-and-verified',health=state['health'],projection=state['projection'])
