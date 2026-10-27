from pathlib import Path
import sys,json,time,traceback,shutil,fcntl
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import archive_closed as archive
remote=archive.remote;BASE=archive.ROOT
W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards');E=W/'evidence/2026-10-27/process-isolation-r1'
def checked(code,timeout=45):
 r=remote.run('python3 -',input=code,timeout=timeout);assert r.returncode==0,r.stdout+'\n'+r.stderr;return json.loads(r.stdout)
def save(path,value):
 body=json.dumps(value,indent=2)+'\n'
 if path.exists():assert json.loads(path.read_text())==value,'changed original '+str(path)
 else:path.write_text(body)
def progress(value):
 value['epoch']=time.time();(P/'PROGRESS.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)
def launch(name):
 code='BASE='+repr(BASE)+'\nNAME='+repr(name)+'\n'+r'''
from pathlib import Path
import subprocess,json,time
b=Path(BASE);f=b/(NAME+'.worker.launch.json')
if f.exists():print(f.read_text());raise SystemExit(0)
assert not(b/NAME).exists(),'ambiguous original point directory without launch identity'
with(b/(NAME+'.worker.stdout')).open('xb')as out,(b/(NAME+'.worker.stderr')).open('xb')as err:
 p=subprocess.Popen(['python3',str(b/'remote_worker.py'),NAME],stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
 stat=Path('/proc/'+str(p.pid)+'/stat').read_text().split(') ',1)[1].split()
 v={'pid':p.pid,'startTicks':stat[19],'epoch':time.time()};f.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
'''
 who=checked(code);save(P/(name+'.launch.json'),who);return who

def wait(name,who):
 until=time.monotonic()+900
 while True:
  code='BASE='+repr(BASE)+'\nNAME='+repr(name)+'\nWHO='+repr(who)+'\n'+r'''
from pathlib import Path
import json
p=Path('/proc/'+str(WHO['pid'])+'/stat');live=False
try:
 v=p.read_text().split(') ',1)[1].split();live=v[19]==WHO['startTicks']and v[0]!='Z'
except(FileNotFoundError,ProcessLookupError):pass
f=Path(BASE)/NAME/'complete.json';print(json.dumps({'live':live,'complete':json.loads(f.read_text())if f.exists()else None}))
'''
  state=checked(code)
  if not state['live']:
   save(P/(name+'.worker-closed.json'),state);assert state['complete']is not None,'worker lost without completion';return state['complete']
  assert time.monotonic()<until,'bounded wait expired; inspect same original';time.sleep(10)

def thin(name,proof):
 code='BASE='+repr(BASE)+'\nNAME='+repr(name)+'\n'+r'''
from pathlib import Path
import json
r=Path(BASE)/NAME
names=['complete.json','environment.json','java.launch.json','java.exit.json','PYTHON_AUDIT.json','native/configuration.json','native/result.json','native/source-result.json','native/source-resources.json','native/business-resources.json','native/backlog.json','native/origin.json','native/business-launch.json','native/business-verified.json','native/process-closure.json','native/source-finished.json','junit/RESULT.json','junit/SUMMARY.txt']
print(json.dumps({n:(r/n).read_text()for n in names if(r/n).is_file()}))
'''
 values=checked(code);d=E/name;d.mkdir(parents=True,exist_ok=True)
 for n,body in values.items():
  f=d/n.replace('/','__')
  if f.exists():assert f.read_text()==body
  else:f.write_text(body)
 for n in ['MEMBER_MANIFEST.json','PRIVATE_ASSET_VERIFIED.json','EXACT_COMPRESSED_PLAN.json']:
  shutil.copy2(P/('archive-'+name)/n,d/n)
 for n in ['launch','worker-closed']:shutil.copy2(P/(name+'.'+n+'.json'),d/('worker.'+n+'.json'))
 return json.loads(values['native/result.json'])if'native/result.json'in values else None

def collect(name):
 for attempt in range(1,5):
  try:return archive.archive(name)
  except Exception as error:
   save(P/(name+'.collection-error-'+str(time.time_ns())+'.json'),{'error':repr(error),'traceback':traceback.format_exc(),'nativeRerun':False})
   d=P/('archive-'+name);plan=d/'EXACT_COMPRESSED_PLAN.json'
   if plan.exists():
    expected=json.loads(plan.read_text())
    for f in d.glob('*.tar.gz'):
     if f.stat().st_size!=expected['bytes']or archive.sha(f)!=expected['sha256']:f.rename(f.with_name(f.name+'.partial-'+str(time.time_ns())))
   if attempt==4:raise
   progress({'stage':'retry_same_original_collection','point':name,'attempt':attempt});time.sleep(10)

def main():
 for name in json.loads((P/'PLAN.json').read_text())['points']:
  progress({'stage':'launch_or_resume_original','point':name});who=launch(name);state=wait(name,who);proof=collect(name);summary=thin(name,proof)
  assert state['passed'],'original correctness failure; raw retained; no automatic native rerun'
  f=P/('archive-'+name)/'REMOTE_DUPLICATE_RETIREMENT.json';retirement=json.loads(f.read_text())if f.exists()else archive.retire(name)
  assert retirement['assetId']==proof['assetId'];save(E/name/'REMOTE_DUPLICATE_RETIREMENT.json',retirement)
  value={'stage':'raw_private_verified','point':name,'assetId':proof['assetId']}
  if summary:value.update(accepted=summary['accepted'],notSent=summary['notSent'],rejected=summary['businessRejected'],finiteGate=summary['finiteGatePassed'],globalP99=summary['allArrivalAcceptedLatencyNs']['p99']if summary['allArrivalAcceptedLatencyNs']else None,sourceMaxLateness=summary['sourceLatenessNs']['max'])
  progress(value)
 save(P/'COMPLETE.json',{'all20OriginalGroupsClosed':True,'finiteArms':16,'sustainedCapacityProven':False})

if __name__=='__main__':
 with(P/'CONTROLLER.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:main()
  except BaseException as e:
   save(P/('FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
