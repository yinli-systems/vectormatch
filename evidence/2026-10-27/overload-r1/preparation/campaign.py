"""Sequential finite overload diagnostics; gated on completed 100M raw closure."""
from pathlib import Path
import sys,json,time,hashlib,shutil,subprocess,traceback,tarfile
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from archive_closed import checked,archive,retire,remote,ROOT
from analyse_point import analyse
W=P.parent.parent.parent/'worktrees/production-soak-shards';E=W/'evidence/2026-10-27/overload-r1'

def save(n,v):
 with (P/n).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def progress(v):
 v['epoch']=time.time();(P/'PROGRESS.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v),flush=True)
def stage():
 complete=json.loads((P.parent/'anchored-continuity-20261027-r1/campaign.complete.json').read_text());assert complete['acceptedTotal']==100000000
 assert (P/'RETIREMENT_COMPLETE.json').is_file()
 files=['remote_worker.py','CANDIDATE.json','QUALIFICATION_PACKAGE.json','LinuxQualification.java']
 for name in ['audit-async-capacity-v4.py','retention_read_yield_audit_v4.py']:
  shutil.copy2(W/'scripts'/name,P/name);files.append(name)
 sources={n:{'bytes':(P/n).stat().st_size,'sha256':hashlib.sha256((P/n).read_bytes()).hexdigest()}for n in files}
 save('SOURCE_FILES.json',sources)
 checked('from pathlib import Path\nr=Path('+repr(ROOT)+')\nassert not r.exists()\nr.mkdir()')
 for n in files+['SOURCE_FILES.json','candidate-dist.tar.gz','qualification-package.tar.gz']:
  q=remote.upload(P/n,ROOT+'/'+n);assert q.returncode==0,q.stderr.decode()
 code='ROOT='+repr(ROOT)+'\n'+r'''from pathlib import Path
import json,hashlib,tarfile,os,shutil
r=Path(ROOT)
for bundle,meta,target in [('candidate-dist.tar.gz','CANDIDATE.json','dist'),('qualification-package.tar.gz','QUALIFICATION_PACKAGE.json','qualification')]:
 m=json.loads((r/meta).read_text());f=r/bundle;k='bundleSha256'if bundle.startswith('candidate')else'sha256';assert hashlib.sha256(f.read_bytes()).hexdigest()==m[k]
 out=r/target;out.mkdir()
 with tarfile.open(f)as t:
  for member in t.getmembers():assert not Path(member.name).is_absolute()and'..'not in Path(member.name).parts and(member.isfile()or member.isdir())
  t.extractall(out,filter='data')
print(json.dumps({'sourceCommit':json.loads((r/'CANDIDATE.json').read_text())['sourceCommit'],'freeBytes':shutil.disk_usage(r).free}))
'''
 # CPU Python 3.8 does not accept tarfile extraction filters; enforce regular-only paths above.
 code=code.replace("t.extractall(out,filter='data')","t.extractall(out)")
 save('STAGED.json',json.loads(checked(code)))
def launch(name):
 code='ROOT='+repr(ROOT)+'\nNAME='+repr(name)+'\n'+r'''from pathlib import Path
import subprocess,json
r=Path(ROOT);assert not(r/NAME).exists()and not(r/(NAME+'.worker.launch.json')).exists()
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java'
 except(FileNotFoundError,ProcessLookupError):pass
with(r/(NAME+'.worker.stdout')).open('xb')as out,(r/(NAME+'.worker.stderr')).open('xb')as err:
 p=subprocess.Popen(['python3',str(r/'remote_worker.py'),NAME],stdout=out,stderr=err,start_new_session=True)
 birth=Path('/proc/'+str(p.pid)+'/stat').read_text().split(') ',1)[1].split()[19];v={'pid':p.pid,'startTicks':birth};(r/(NAME+'.worker.launch.json')).write_text(json.dumps(v)+'\n');print(json.dumps(v))
'''
 save(name+'.launch.json',json.loads(checked(code)))
def wait(name):
 started=time.monotonic()
 while True:
  code='ROOT='+repr(ROOT)+'\nNAME='+repr(name)+'\n'+r'''from pathlib import Path
import json
r=Path(ROOT);x=json.loads((r/(NAME+'.worker.launch.json')).read_text());p=Path('/proc/'+str(x['pid'])+'/stat');alive=False
if p.exists():
 try:
  f=p.read_text().split(') ',1)[1].split();alive=f[19]==str(x['startTicks'])and f[0]!='Z'
 except(FileNotFoundError,ProcessLookupError):pass
v={'workerAlive':alive};p=r/NAME/'complete.json'
if p.exists():v['complete']=json.loads(p.read_text())
if not alive:
 for n in [NAME+'.worker.stdout',NAME+'.worker.stderr']:
  p=r/n;v[n]=p.read_text()[-10000:]
print(json.dumps(v))
'''
  v=json.loads(checked(code,timeout=90))
  if not v['workerAlive']:save(name+'.worker-closed.json',v);return v.get('complete',{'passed':False,'failure':'worker exited without native completion'})
  assert time.monotonic()-started<1800,'worker exceeded outer bound; no further arm launched'
  time.sleep(10)
def copy_index(name):
 dest=E/name;dest.mkdir(parents=True,exist_ok=True);source=P/('archive-'+name)
 for n in ['MEMBER_MANIFEST.json','PRIVATE_ASSET_VERIFIED.json','EXACT_COMPRESSED_PLAN.json','REMOTE_DUPLICATE_RETIREMENT.json']:
  if(source/n).exists():shutil.copy2(source/n,dest/n)
 if(P/('analysis-'+name)).exists():shutil.copytree(P/('analysis-'+name),dest/'analysis',dirs_exist_ok=True)
 for n in [name+'.launch.json',name+'.worker-closed.json']:shutil.copy2(P/n,dest/n)
if __name__=='__main__':
 try:
  stage()
  for name in ['qualification-r1']+[f'{rate}-{arm}'for rate in [7000,8000]for arm in ['a1','b1','a2','b2']]:
   progress({'stage':'launch','point':name});launch(name);v=wait(name)
   proof=archive(name)
   if name!='qualification-r1'and v['passed']:
    result=analyse(P/('archive-'+name)/proof['name'],P/('analysis-'+name));progress({'stage':'audited','point':name,'goodput':result['inWindowGoodputPerSecond'],'notSent':result['notSent'],'globalP99Ns':result['allArrivalLatency']['p99Ns']if result['allArrivalLatency']else None})
   copy_index(name)
   assert v['passed'],'failed correctness/closure; complete original evidence retained'
   retire(name);copy_index(name)
   progress({'stage':'private_full_raw_verified','point':name})
  save('COMPLETE.json',{'allEightFiniteOverloadPointsClosed':True,'sustainedProof':False,'epoch':time.time()})
 except BaseException as e:
  save('FAILURE.json',{'failure':repr(e),'traceback':traceback.format_exc(),'epoch':time.time()});raise
