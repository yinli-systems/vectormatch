"""One-shot pinned Linux loader probe on the existing CPU; never starts a database."""
from pathlib import Path
import sys,json,hashlib,datetime
BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
source=BASE/'app-restore-build/linux-postgres';out=REPO/'evidence/2026-10-24/runpod-cpu/restoration-preparation/loader-probe-r1';out.mkdir(exist_ok=False)
root='/opt/vectormatch-cpu/preparation/pg18-loader-probe-r1';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
jar=source/'embedded-postgres-binaries-linux-amd64-18.6.0.jar';extractor=source/'extract-pinned-linux.py'
assert sha(jar)=='008ee189eaa7ca2b58bd01dd950291e638b998392cf982297acd4779ec898ac1'
closed=REPO/'evidence/2026-10-24/runpod-cpu/node-idle-abab/comparison/stopped-before-next-work.json';assert json.loads(closed.read_text())['allOwnedIdentitiesStoppedNow']
plan={'jobId':'cpu-app-pg18-loader-probe-r1','root':root,'jarSha256':sha(jar),'extractorSha256':sha(extractor),'sourceSha256':sha(__file__),'idleStopProofSha256':sha(closed),'registeredAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'ExistingCPU only; prepare immutable binaries and execute file/readelf/ldd/postgres --version. No initdb,PGDATA,server,start,ports or database mutation.'}
(out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');(out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
p=remote.run('python3 -B -',input='from pathlib import Path\nimport platform,shutil\nassert platform.node()=="ed6c0673f5cb"\nassert shutil.disk_usage("/opt").free>3*1024**3\nPath('+repr(root)+').mkdir(parents=True,exist_ok=False)\n',timeout=30);assert p.returncode==0,p.stderr
for local,name in [(jar,'postgres.jar'),(extractor,'extract.py')]:
 p=remote.upload(local,root+'/'+name);assert p.returncode==0,p.stderr
code='''from pathlib import Path
import json,hashlib,platform,subprocess,sys,datetime,shutil,os
assert platform.node()=='ed6c0673f5cb'
r=Path(PLAN['root']);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(r/'postgres.jar')==PLAN['jarSha256'] and sha(r/'extract.py')==PLAN['extractorSha256']
steps=[]
args=[sys.executable,'-B',str(r/'extract.py'),'--jar',str(r/'postgres.jar'),'--target',str(r/'binaries'),'--artifact-os','linux','--artifact-arch','amd64','--purpose','restore-binaries','--receipt',str(r/'extraction.json')]
p=subprocess.run(args,capture_output=True,text=True,timeout=30);steps.append({'arguments':args,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr});assert p.returncode==0,steps
binary=r/'binaries/bin/postgres'
for command in [['file',str(binary)],['readelf','-h',str(binary)],['ldd',str(binary)],[str(binary),'--version']]:
 if shutil.which(command[0]) is None:steps.append({'arguments':command,'unavailable':True});continue
 p=subprocess.run(command,capture_output=True,text=True,timeout=10,env={'PATH':os.environ['PATH'],'LANG':'C'});steps.append({'arguments':command,'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
last=steps[-1];passed=last.get('exitCode')==0 and last.get('stdout','').strip()=='postgres (PostgreSQL) 18.6'
receipt={'passed':passed,'completedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'steps':steps,'scope':'Linux loader and version only. PGDATA was never read; no server was started. Major/control-data/locale/lineage/application recovery remain unverified.'}
with (r/'receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
print(json.dumps({'receipt':receipt,'extraction':json.loads((r/'extraction.json').read_text())}))
'''
p=remote.run('python3 -B -',input='PLAN='+repr(plan)+'\n'+code,timeout=90)
(out/'transport.json').write_text(json.dumps({'exitCode':p.returncode,'stderr':p.stderr},indent=2)+'\n');assert p.returncode==0,p.stderr
r=json.loads(p.stdout)
for name in ('receipt','extraction'):(out/(name+'.json')).write_text(json.dumps(r[name],indent=2)+'\n')
assert r['receipt']['passed'],r['receipt'];print(json.dumps({'passed':True,'postgresVersion':'18.6','databaseStarted':False}))
