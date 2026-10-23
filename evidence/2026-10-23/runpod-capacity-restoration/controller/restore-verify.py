import campaign as c,pathlib,json,time,urllib.request,subprocess,sys,shlex
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-capacity-restoration').resolve();c.OUT.mkdir(parents=True,exist_ok=True)
c.restore()
import socket,os,hashlib
probe=socket.socket();probe.settimeout(1);connected=probe.connect_ex(('127.0.0.1',8011))==0;probe.close()
if not connected:
 ssh=c.remote.sshargs(2);args=ssh[:-1]+['-N','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-L','127.0.0.1:8011:127.0.0.1:8000',ssh[-1]]
 with pathlib.Path('runtime/cloud/capacity-20261023/restored-tunnel.log').open('ab') as log:
  tunnel=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 c.save(pathlib.Path('runtime/cloud/capacity-20261023/restored-tunnel.json'),{'pid':tunnel.pid,'commandSha256':hashlib.sha256(b''.join(os.fsencode(x)+b'\0' for x in args)).hexdigest(),'purpose':'owned loopback-only forward for original platform after capacity tests'})
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
