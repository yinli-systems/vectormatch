"""Register/submit the isolated kernel ABAB only after all six CPU capacity points close."""
import argparse,pathlib,json,hashlib,datetime,sys,importlib.util
BASE=pathlib.Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
ART=REPO/'evidence/2026-10-24/runpod-cpu/jmh-core-level-iterator';OUT=ART/'attempts/r2';OUT.mkdir(parents=True,exist_ok=True);JOB='cpu-jmh-level-iterator-abab-r2';WORKER=BASE/'jmh-abab-worker-v2.py';REG=OUT/'registration.json'
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def prior():
 m=REPO/'evidence/2026-10-24/runpod-cpu/matrices/cpu-capacity-staircase-433-r1/matrix-summary.json'
 assert m.exists(),'Six-point capacity matrix has not completed; no JMH registration or launch'
 r=json.loads(m.read_text());stop=m.parent/'capacity-stopped-before-jmh.json'
 assert stop.is_file(),'Capacity must complete or have an explicit verified protocol-stop closure'
 closed=json.loads(stop.read_text());assert closed['allAttemptedCapacityProcessesStopped'] and closed['unlaunchedLastPointVerified']
 assert closed['matrixSummarySha256']==sha(m) and closed['matrixPlanSha256']==r['matrixPlanSha256']
 assert len(r['points'])==5 and r['unlaunchedIds']==['cpu-capacity-26000-w128-r2']
 inputs={str(m.relative_to(REPO)):sha(m),str(stop.relative_to(REPO)):sha(stop)}
 for p in r['points']:
  assert p['analysisTrial']['derived']['unknownAtInitialDeadline']==p['analysisTrial']['derived']['unknownUnresolved']==0
  assert p['completion']['allOwnedProcessesStopped'] and p['completion']['archiveComplete']
  for n in ('unknownAtInitialDeadline','unknownUnresolved'):assert p['analysisTrial']['derived'][n]==0
  a=pathlib.Path(p['analysisDirectory'])/'analysis/summary.json';assert sha(a)==p['analysisSummarySha256'];inputs[str(a.relative_to(REPO))]=sha(a)
 return {'matrixPlanSha256':r['matrixPlanSha256'],'inputs':inputs,'matrixCompleted':False,'allAttemptedPointsClosed':True,'mode':closed['mode'],'noActiveCapacityWorkload':True}
def draft():
 smoke=ART/'observer-smoke-v2/verification.json'
 r=json.loads(smoke.read_text());assert r['passed'] and r['observedForks']==3 and r['workerSha256']==sha(WORKER)
 a=json.loads((ART.parent/'jmh-deployment/manifest.json').read_text());b=json.loads((ART/'artifact-deployment/manifest.json').read_text())
 assert a['revision']=='987f6526b8a0b3c3516ee668a239990cc79fbd8f' and b['revision']=='7a4cf09be5055fa48c4246b21679d9038bbbfd5f'
 return {'jobId':JOB,'hostname':'ed6c0673f5cb','registeredAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'workerSha256':sha(WORKER),'actualObserverSmokeSha256':sha(smoke),'priorObserverFailureSha256':sha(ART/'attempts/r1/collection-verification.json'),'capacityPrerequisite':prior(),'distributions':{g:{'revision':d['revision'],'root':'/opt/vectormatch-cpu/jmh-releases/'+d['revision'],'files':d['files']} for g,d in (('A',a),('B',b))},'artifactAuditSha256':sha(ART/'artifact-deployment/manifest.json'),'stages':[{'id':n,'group':g,'expectedCases':15,'forks':3,'warmup':500,'measurement':10} for n,g in (('A1','A'),('B1','B'),('A2','A'),('B2','B'))],'observerScope':'All compared stages use the same10ms owned-process observer, recording its CPU. Earlier observer-off warmup jobs are not A controls. PIDfd cleanup validates exact runner/ForkedMain descendants; no whole-host enumeration/group kill.','statisticsScope':'Report each fork mean, each repetition and all15cases including negative controls. No outlier removal. Fresh score is64-command batch mean, not individual-order p99 or system capacity. Predeclared target levels1/100 with10/100trades; remaining11cases all disclosed.','protocolSha256':sha(ART/'PROTOCOL.md')}
p=argparse.ArgumentParser(description=__doc__);m=p.add_mutually_exclusive_group();m.add_argument('--register',action='store_true');m.add_argument('--execute',action='store_true');args=p.parse_args()
if not args.execute:
 plan=draft()
 if args.register:
  with REG.open('x') as f:json.dump(plan,f,indent=2);f.write('\n')
  (OUT/'jmh-abab-worker-v2.py').write_bytes(WORKER.read_bytes())
 print(json.dumps({'registered':args.register,'jobId':JOB,'workerSha256':plan['workerSha256'],'capacityClosed':True}));sys.exit(0)
plan=json.loads(REG.read_text());assert plan['workerSha256']==sha(WORKER) and plan['capacityPrerequisite']==prior()
assert plan['actualObserverSmokeSha256']==sha(ART/'observer-smoke-v2/verification.json')
assert plan['protocolSha256']==sha(ART/'PROTOCOL.md') and plan['artifactAuditSha256']==sha(ART/'artifact-deployment/manifest.json')
control='/workspace/vectormatch-cpu/bootstrap/'+JOB
r=remote.run('python3 -B -',input='from pathlib import Path\nPath('+repr(control)+').mkdir(exist_ok=False)\n',timeout=30);assert r.returncode==0,'Control exists/ambiguous; query same job, never reissue: '+r.stderr
for a,b in ((WORKER,control+'/jmh-abab-worker-v2.py'),(REG,control+'/plan.json')):
 r=remote.upload(a,b);assert r.returncode==0,r.stderr
code='''import pathlib,subprocess,json,hashlib,os,time,platform
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path(CONTROL);plan=json.loads((root/'plan.json').read_text());assert hashlib.sha256((root/'jmh-abab-worker-v2.py').read_bytes()).hexdigest()==plan['workerSha256']
with (root/'launch-attempt.json').open('x') as f:json.dump({'jobId':plan['jobId']},f)
a=['python3','-B',str(root/'jmh-abab-worker-v2.py')];expected=hashlib.sha256(b''.join(os.fsencode(v)+bytes([0]) for v in a)).hexdigest()
with (root/'controller.log').open('x') as f:c=subprocess.Popen(a,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
s=pathlib.Path('/proc')/str(c.pid);deadline=time.monotonic()+2
while hashlib.sha256((s/'cmdline').read_bytes()).hexdigest()!=expected:
 assert c.poll() is None and time.monotonic()<deadline
 time.sleep(.01)
r={'jobId':plan['jobId'],'pid':c.pid,'startTicks':int((s/'stat').read_text().rsplit(')',1)[1].split()[19]),'arguments':a,'actualCommandSha256':expected}
with (root/'launch.json').open('x') as f:json.dump(r,f,indent=2)
print(json.dumps(r))
'''
r=remote.run('python3 -B -',input='CONTROL='+repr(control)+'\n'+code,timeout=30)
with (OUT/'launch-transport.json').open('x') as f:json.dump({'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},f,indent=2)
assert r.returncode==0,'Ambiguous launch; query same ID: '+r.stderr
print(r.stdout)
