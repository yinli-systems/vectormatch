from pathlib import Path
import sys,time,json,shutil
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from evidence_archive import archive,retire,checked,ROOT
W=P.parent.parent.parent/'worktrees/production-soak-shards'
E=W/'evidence/2026-10-27/anchored-continuity-r1';E.mkdir(parents=True,exist_ok=True)
started=time.time()
def stage(value):
    value['epoch']=time.time();(P/'campaign.progress.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value),flush=True)
def wait(name):
    start=time.time()
    while True:
        code="""import pathlib,json
r=pathlib.Path(ROOT);name=NAME
result={}
for suffix in [name+'.exit.json','audit-'+name+'.exit.json']:
 p=r/suffix
 if p.exists():result[suffix]=json.loads(p.read_text())
w=r/(name+'.worker.launch.json')
result['workerAlive']=False
if w.exists():
 x=json.loads(w.read_text());p=pathlib.Path('/proc/'+str(x['pid'])+'/stat')
 if p.exists():
  try:
   f=p.read_text().split(') ',1)[1].split();result['workerAlive']=f[19]==str(x['startTicks']) and f[0]!='Z'
  except (FileNotFoundError,ProcessLookupError):pass
print(json.dumps(result))
"""
        result=json.loads(checked('ROOT='+repr(ROOT)+'\nNAME='+repr(name)+'\n'+code,timeout=60))
        for key,value in result.items():
            if key.endswith('.json') and value['exitCode']!=0:raise RuntimeError(name+' failed '+json.dumps(result))
        if 'audit-'+name+'.exit.json' in result and not result['workerAlive']:return
        if not result['workerAlive']:raise RuntimeError(name+' worker exited before audit closure '+json.dumps(result))
        if time.time()-start>2200:raise RuntimeError(name+' watchdog exceeded; no additional work launched')
        time.sleep(15)
def copy_receipt(name):
    src=P/('archive-'+name);out=E/name;out.mkdir(exist_ok=True)
    for n in ['MEMBER_MANIFEST.json','PRIVATE_ASSET_VERIFIED.json','EXACT_SERVICE_SAMPLES.json','exact-service-frequency.csv.gz','REMOTE_RAW_RETIREMENT.json']:
        f=src/n
        if f.exists():shutil.copy2(f,out/n)
def launch(name,previous,target):
    code=r"""import pathlib,subprocess,json,shutil
r=pathlib.Path(ROOT);name=NAME
assert pathlib.Path('/etc/hostname').read_text().strip()=='33ace3d92505'
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
assert shutil.disk_usage(r).free>2*1024**3
for f in pathlib.Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java',str(f)
 except (FileNotFoundError,ProcessLookupError):pass
assert not (r/name).exists() and not (r/(name+'.worker.launch.json')).exists()
with (r/(name+'.worker.stdout')).open('xb') as out,(r/(name+'.worker.stderr')).open('xb') as err:
 p=subprocess.Popen(['python3',str(r/'worker.py'),name,'continue',PREVIOUS,str(TARGET)],stdout=out,stderr=err,start_new_session=True)
 birth=pathlib.Path('/proc/'+str(p.pid)+'/stat').read_text().split(') ',1)[1].split()[19]
 (r/(name+'.worker.launch.json')).write_text(json.dumps({'pid':p.pid,'startTicks':birth})+'\n')
 print(json.dumps({'pid':p.pid,'startTicks':birth}))
"""
    return json.loads(checked('ROOT='+repr(ROOT)+'\nNAME='+repr(name)+'\nPREVIOUS='+repr(previous)+'\nTARGET='+str(target)+'\n'+code,timeout=60))
try:
    # 1M and the 1M->5M native continuation were started interactively with the same JAR.
    wait('segment-0004');archive('segment-0004');copy_receipt('segment-0004')
    retire('through-1m','segment-0004',True);copy_receipt('through-1m')
    previous='segment-0004'
    for index,target in enumerate(range(10000000,100000001,5000000),start=5):
        assert time.time()-started<4*3600,'campaign time bound'
        name='segment-'+str(index).zfill(4);stage({'stage':'launch','segment':name,'cumulativeTarget':target})
        launch(name,previous,target);wait(name)
        stage({'stage':'full_native_audit_passed','segment':name,'cumulativeTarget':target})
        archive(name);copy_receipt(name);retire(previous,name);copy_receipt(previous)
        stage({'stage':'private_raw_verified','segment':name,'acceptedTotal':target})
        previous=name
    (P/'campaign.complete.json').write_text(json.dumps({'acceptedTotal':100000000,'lastSegment':previous,'sameLineage':True,'replicated':False,'elapsedSeconds':time.time()-started},indent=2)+'\n')
except BaseException as error:
    (P/'campaign.failure.json').write_text(json.dumps({'failure':repr(error),'elapsedSeconds':time.time()-started},indent=2)+'\n');raise
