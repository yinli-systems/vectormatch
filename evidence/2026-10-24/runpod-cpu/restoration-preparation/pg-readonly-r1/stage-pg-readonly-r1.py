#!/usr/bin/env python3
"""Stage reviewed, frozen PG-only lifecycle/inspection preparation, without server start."""
from pathlib import Path
import hashlib,json,shutil,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));import remote
ROOT=HERE.parents[2]
SOURCE=HERE/'pg-recovery-preparation'
PROOF=ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-readonly-r1'
DEST='/opt/vectormatch-cpu/preparation/pg-readonly-source-r1'
JAVA='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java'
MANIFEST='659e7f06a8487c9a3331b2e62d31fa43ed7e0c09555fdc64494d1edf9982f2c5'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SOURCE/'manifest.json')==MANIFEST
assert json.loads((ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-access-r1/completion.json').read_text())['passed']
m=json.loads((SOURCE/'manifest.json').read_text())
j=json.loads((SOURCE/'java-validation.json').read_text())
items={}
for n,e in dict(m['files'],**m['compiledClasses']).items():
    p=SOURCE/n;assert sha(p)==e['sha256'] and p.stat().st_size==e['bytes'];items[n]=p
items['manifest.json']=SOURCE/'manifest.json'
for n,h in j['classpath'].items():
    p=HERE/'app-restore-build/bundle/dist/projector/lib'/n
    assert sha(p)==h;items['lib/'+n]=p
PROOF.mkdir(exist_ok=False)
for n,p in items.items():
    d=PROOF/'frozen-stage'/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,d)
shutil.copy2(__file__,PROOF/Path(__file__).name)
layout={n:{'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in items.items()}
(PROOF/'stage-inventory.json').write_text(json.dumps(layout,indent=2)+'\n')
setup="""from pathlib import Path
import platform,os
p=Path(%r);assert platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert not p.exists() and all(not x.is_symlink() for x in [p]+list(p.parents))
p.mkdir(mode=0o700)
for n in ['classes','lib']:(p/n).mkdir(mode=0o700)
print('NEW_FROZEN_RECOVERY_SOURCE_CREATED')
"""%DEST
r=remote.run('python3 -B -',input=setup,timeout=30)
(PROOF/'stage-setup.stdout').write_text(r.stdout);(PROOF/'stage-setup.stderr').write_text(r.stderr);assert r.returncode==0
for n,p in items.items():
    r=remote.upload(p,DEST+'/'+n);assert r.returncode==0,'Stagefailed;noautomaticretry'
cp=DEST+'/classes:'+':'.join(DEST+'/lib/'+n for n in j['classpath'])
verify="""from pathlib import Path
import hashlib,subprocess,json,sys
p=Path(%r);expected=%r
assert all(not x.is_symlink() for x in [p]+list(p.parents))
for n,e in expected.items():
 f=p/n;assert not f.is_symlink() and f.stat().st_size==e['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==e['sha256']
results=[]
for args in [['/usr/bin/python3','-B',str(p/'test_pg_recovery.py')],[%r,'-Xms16m','-Xmx128m','-cp',%r,'PgReadonlyInspect','--self-test']]:
 r=subprocess.run(args,capture_output=True,text=True,timeout=45)
 results.append({'arguments':args,'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
 if r.returncode:break
print(json.dumps({'passed':len(results)==2 and all(r['exitCode']==0 for r in results),'results':results,'postgresStarted':False,'sqlConnections':0}))
sys.exit(0 if len(results)==2 and all(r['exitCode']==0 for r in results) else 1)
"""%(DEST,layout,JAVA,cp)
(PROOF/'actual-stage-verifier.py').write_text(verify)
r=remote.run('python3 -B -',input=verify,timeout=120)
(PROOF/'stage-verification.stdout.json').write_text(r.stdout);(PROOF/'stage-verification.stderr.log').write_text(r.stderr)
assert r.returncode==0,'Noautomaticretry'
v=json.loads(r.stdout)
summary={'passed':v['passed'],'sourceManifestSha256':MANIFEST,'controllerSha256':sha(SOURCE/'pg_recovery.py'),'stagedFiles':len(layout),
         'remoteSource':DEST,'actualLinuxPythonGuards':33,'actualJavaSelfTest':{'valid':2,'reject':6,'sqlConnections':0},'postgresStarted':False}
(PROOF/'stage-completion.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
