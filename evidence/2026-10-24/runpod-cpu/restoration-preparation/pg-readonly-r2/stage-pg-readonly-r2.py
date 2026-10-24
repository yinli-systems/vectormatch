#!/usr/bin/env python3
"""Freeze/stage one derived-baseline r2 probe and run guards; no server starts here."""
from pathlib import Path
import base64,hashlib,io,json,shutil,sys,tarfile
H=Path(__file__).resolve().parent
sys.path.insert(0,str(H));import remote
ROOT=H.parents[2];I=H/'pg-recovery-preparation/r2';L=H/'pg-recovery-preparation/lifecycle-r2'
P=ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-readonly-r2'
D='/opt/vectormatch-cpu/preparation/pg-readonly-source-r2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert (I/'manifest.json').exists(),'Wait for agent freeze'
assert sha(L/'pg_recovery.py')=='e8223d9bdd5a33319002d4567856c072e7f68801b554089bad2e4a6be7d59315'
assert sha(L/'expected-baseline.json')=='060ae81fe941b41204ea89070aa0896a7f88ece9a22915cd77c7c1e6048f5fcd'
P.mkdir(exist_ok=False)
shutil.copytree(I,P/'inspector-preparation');shutil.copytree(L,P/'lifecycle-preparation');shutil.copy2(__file__,P/Path(__file__).name)
items={n:L/n for n in ['pg_recovery.py','expected-baseline.json','test_pg_recovery.py']}
for p in I.rglob('*'):
    assert not p.is_symlink()
    if p.is_file():items['inspector-preparation/'+str(p.relative_to(I))]=p
for p in (I/'classes').glob('*.class'):items['classes/'+p.name]=p
items['PgReadonlyInspect.java']=I/'PgReadonlyInspect.java'
items['r1-settings.json']=I/'r1-settings.json'
v=json.loads((I/'validation.json').read_text())
layout={'classpath':{n:e['sha256'] for n,e in v['classpath'].items()},'binaryInventory':v['compiledClasses']}
(P/'root-java-layout.json').write_text(json.dumps(layout,indent=2)+'\n');items['root-java-layout.json']=P/'root-java-layout.json'
inventory={n:{'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in items.items()}
(P/'stage-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz',compresslevel=3,dereference=True) as tf:
    for n,p in items.items():tf.add(p,arcname=n,recursive=False)
b=data.getvalue();assert len(b)<2*1024*1024
(P/'stage-bundle.tar.gz').write_bytes(b)
code="""from pathlib import Path
import base64,hashlib,io,tarfile,os,platform,json,shutil,subprocess,importlib.util,stat,sys
p=Path(%r);expected=%r;blob=base64.b64decode(%r)
assert platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert not p.exists() and all(not x.is_symlink() for x in [p]+list(p.parents))
assert hashlib.sha256(blob).hexdigest()==%r
p.mkdir(mode=0o700)
seen=set()
with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as tf:
 for t in tf:
  n=t.name;assert n in expected and n not in seen and t.isfile() and not n.startswith('/') and '..' not in Path(n).parts
  seen.add(n);e=expected[n];assert t.size==e['bytes'];b=tf.extractfile(t).read();assert hashlib.sha256(b).hexdigest()==e['sha256']
  f=p/n;f.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  with f.open('xb') as out:out.write(b)
  f.chmod(0o600)
assert seen==set(expected)
layout=json.loads((p/'root-java-layout.json').read_text());(p/'lib').mkdir(mode=0o700)
for n,h in layout['classpath'].items():
 src=Path('/opt/vectormatch-cpu/preparation/pg-readonly-source-r1/lib')/n
 assert src.is_file() and not src.is_symlink() and hashlib.sha256(src.read_bytes()).hexdigest()==h
 shutil.copyfile(src,p/'lib'/n);(p/'lib'/n).chmod(0o600)
cp=str(p/'classes')+':'+':'.join(str(p/'lib'/n) for n in layout['classpath'])
java='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java';results=[]
for args in [['/usr/bin/python3','-B',str(p/'test_pg_recovery.py')],[java,'-Xmx128m','-cp',cp,'PgReadonlyInspect','--self-test'],[java,'-Xmx128m','-cp',cp,'PgReadonlyInspectGuards',str(p/'r1-settings.json')]]:
 r=subprocess.run(args,capture_output=True,text=True,timeout=45);results.append({'arguments':args,'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
 if r.returncode:break
assert len(results)==3 and all(x['exitCode']==0 for x in results),json.dumps(results)
spec=importlib.util.spec_from_file_location('m',p/'pg_recovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
pre=m.preflight(require_access=True,expected_owner=(963,963));assert pre['account']['exists']
job=m.JOB;assert not job.exists();job.mkdir(mode=0o700)
def acl():
 r=subprocess.run(['/usr/bin/getfacl','-c','-p','-n',str(job)],capture_output=True,text=True,timeout=5)
 assert r.returncode==0 and not r.stderr
 return sorted(x.strip() for x in r.stdout.splitlines() if x.strip())
assert m.sha('/usr/bin/setfacl')=='a58683007857270335b5ed78a969e16524b715dfab5ed2fe8b4be8a86e46af60'
assert m.sha('/usr/bin/getfacl')=='416b8d800dd0ee9498c46c0446a97bacfa57459e233267d02ba2b357a90c0570'
b=job.stat();before=acl();assert b.st_uid==0 and b.st_gid==0 and stat.S_IMODE(b.st_mode)==0o700 and set(before)=={'user::rwx','group::---','other::---'}
m.save_new(p/'job-acl-intent.json',{'beforeAcl':before,'beforeMtimeNs':b.st_mtime_ns,'noRetry':True,'target':str(job),'grant':'uid963executeonly'})
r=subprocess.run(['/usr/bin/setfacl','--no-mask','-m','u:963:--x,m::--x',str(job)],capture_output=True,text=True,timeout=5)
a=job.stat();after=acl();assert r.returncode==0 and not r.stderr and a.st_uid==0 and a.st_gid==0 and stat.S_IMODE(a.st_mode)==0o710 and a.st_mtime_ns==b.st_mtime_ns
assert set(after)=={'user::rwx','user:963:--x','group::---','mask::--x','other::---'};m.job_privacy()
result={'passed':True,'guardResults':results,'preflight':pre,'jobAcl':{'before':before,'after':after,'uid':0,'gid':0,'mtimeUnchanged':True},'serverStarted':False}
m.save_new(p/'stage-result.json',result);print(json.dumps(result))
"""%(D,inventory,base64.b64encode(b).decode(),hashlib.sha256(b).hexdigest())
# Keep the exact transfer wrapper locally; its base64 contains only the frozen public source/test inputs and synthetic baseline.
(P/'actual-stage-wrapper.py').write_text(code)
r=remote.run('python3 -B -',input=code,timeout=180)
(P/'stage.stdout.json').write_text(r.stdout);(P/'stage.stderr.log').write_text(r.stderr)
assert r.returncode==0,'Stage failed; preservepartialstate,noautomaticretry'
d=json.loads(r.stdout)
summary={'passed':d['passed'],'files':len(inventory),'bundleSha256':hashlib.sha256(b).hexdigest(),'lifecycleSha256':sha(L/'pg_recovery.py'),'inspectorManifestSha256':sha(I/'manifest.json'),
         'actualLinuxGuards':33,'actualJavaProxyGuards':23,'payloadValid':2,'payloadReject':6,'newJobExecuteAcl':True,'serverStarted':False}
(P/'stage-completion.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
