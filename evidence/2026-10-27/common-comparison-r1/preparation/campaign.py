from pathlib import Path
import sys,json,time,traceback,shutil,subprocess
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P))
import archive_closed as archive
remote=archive.remote;BASE=archive.ROOT
W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')

def checked(code,timeout=120):
 r=remote.run('python3 -',input=code,timeout=timeout)
 assert r.returncode==0,r.stdout+'\n'+r.stderr
 return json.loads(r.stdout)
def progress(value):
 value['epoch']=time.time();(P/'PROGRESS.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)
def launch(name):
 code='BASE='+repr(BASE)+'\nNAME='+repr(name)+'\n'+r'''
from pathlib import Path
import subprocess,json,os,time
b=Path(BASE);assert not(b/NAME).exists()and not(b/(NAME+'.worker.launch.json')).exists()
with(b/(NAME+'.worker.stdout')).open('xb')as out,(b/(NAME+'.worker.stderr')).open('xb')as err:
 p=subprocess.Popen(['python3',str(b/'remote_worker.py'),NAME],stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
 stat=Path('/proc/'+str(p.pid)+'/stat').read_text().split(') ',1)[1].split()
 v={'pid':p.pid,'startTicks':stat[19],'epoch':time.time()};(b/(NAME+'.worker.launch.json')).write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
'''
 who=checked(code);(P/(name+'.launch.json')).write_text(json.dumps(who,indent=2)+'\n');return who

def wait(name,who):
 deadline=time.monotonic()+900
 while True:
  code='BASE='+repr(BASE)+'\nNAME='+repr(name)+'\nWHO='+repr(who)+'\n'+r'''
from pathlib import Path
import json
b=Path(BASE);p=Path('/proc/'+str(WHO['pid'])+'/stat');live=False
try:
 fields=p.read_text().split(') ',1)[1].split();live=fields[19]==WHO['startTicks']and fields[0]!='Z'
except(FileNotFoundError,ProcessLookupError):pass
f=b/NAME/'complete.json';print(json.dumps({'live':live,'complete':json.loads(f.read_text())if f.exists()else None}))
'''
  state=checked(code)
  if not state['live']:
   (P/(name+'.worker-closed.json')).write_text(json.dumps(state,indent=2)+'\n');assert state['complete']is not None,'worker lost without completion';return state['complete']
  assert time.monotonic()<deadline,'controller bounded wait expired; check same original worker'
  time.sleep(10)

def thin(name,proof):
 code='BASE='+repr(BASE)+'\nNAME='+repr(name)+'\n'+r'''
from pathlib import Path
import json
r=Path(BASE)/NAME
names=['complete.json','environment.json','java.launch.json','java.exit.json','PYTHON_AUDIT.json','native/configuration.json','native/result.json','native/resources.json','native/backlog.json','native/origin.json','junit/RESULT.json','junit/SUMMARY.txt']
print(json.dumps({n:(r/n).read_text()for n in names if(r/n).is_file()}))
'''
 values=checked(code);d=W/'evidence/2026-10-27/common-comparison-r1'/name;d.mkdir(parents=True)
 for n,body in values.items():(d/n.replace('/','__')).write_text(body)
 for n in ['MEMBER_MANIFEST.json','PRIVATE_ASSET_VERIFIED.json','EXACT_COMPRESSED_PLAN.json']:
  shutil.copy2(P/('archive-'+name)/n,d/n)
 shutil.copy2(P/(name+'.launch.json'),d/'worker.launch.json');shutil.copy2(P/(name+'.worker-closed.json'),d/'worker.closed.json')
 return json.loads(values['native/result.json'])if'native/result.json'in values else None

def main():
 names=['qualification-r1','native-vector-q1','native-exchange-q1']+[f'{rate}-{arm}'for rate in [10000,50000,100000,250000]for arm in ['a1','b1','a2','b2']]
 for name in names:
  progress({'stage':'launch','point':name});who=launch(name);state=wait(name,who)
  proof=archive.archive(name);summary=thin(name,proof)
  assert state['passed'],'original native/qualification failed; raw archived; no automatic rerun'
  retirement=archive.retire(name);d=W/'evidence/2026-10-27/common-comparison-r1'/name
  (d/'REMOTE_DUPLICATE_RETIREMENT.json').write_text(json.dumps(retirement,indent=2)+'\n')
  record={'stage':'raw_private_verified','point':name,'assetId':proof['assetId']}
  if summary:record.update(accepted=summary['accepted'],notSent=summary['notSent'],finiteGate=summary['finiteGatePassed'],globalP99=summary['allArrivalAcceptedLatencyNs']['p99']if summary['allArrivalAcceptedLatencyNs']else None)
  progress(record)
 (P/'COMPLETE.json').write_text(json.dumps({'all19NativeGroupsClosed':True,'finiteComparativeArms':16,'sustainedCapacityProven':False,'epoch':time.time()},indent=2)+'\n')
try:main()
except BaseException as e:
 (P/'FAILURE.json').write_text(json.dumps({'error':repr(e),'traceback':traceback.format_exc(),'epoch':time.time()},indent=2)+'\n');raise
