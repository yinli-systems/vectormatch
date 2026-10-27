"""Archive stopped experiment bytes with an exact compressed admission bound."""
from pathlib import Path
import sys,subprocess,hashlib,json,tarfile,shutil,time
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'current-read-window32-collection-preparation-r2'))
import remote_current as remote
ROOT='/opt/vectormatch-cpu/experiments/overload-20261027-r2'
GH='/Users/kevin/.local/bin/gh';REPO='yinli-systems/vectormatch';RELEASE=423510304

def checked(code,timeout=600):
 r=remote.run("python3 - <<'CLOSED_ARCHIVE'\n"+code+"\nCLOSED_ARCHIVE",timeout=timeout)
 assert r.returncode==0,r.stdout+'\n'+r.stderr
 return r.stdout

def sha(f):
 h=hashlib.sha256()
 with Path(f).open('rb')as inp:
  for b in iter(lambda:inp.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def gh(*args):return json.loads(subprocess.check_output([GH,'api',*args],text=True))

PACK_SOURCE=r'''from pathlib import Path
import hashlib,json,gzip,tarfile,sys,os
r=Path(ROOT);point=r/NAME;manifest=json.loads((r/(NAME+'.members.json')).read_text())
class Sink:
 def __init__(self):self.digest=hashlib.sha256();self.total=0
 def write(self,b):self.digest.update(b);self.total+=len(b);return len(b)
 def flush(self):pass
sink=Sink()if PREPASS else sys.stdout.buffer
with gzip.GzipFile(fileobj=sink,mode='wb',filename='',compresslevel=1,mtime=0)as gz,tarfile.open(fileobj=gz,mode='w|')as t:
 t.add(r/(NAME+'.members.json'),arcname='MEMBER_MANIFEST.json',recursive=False)
 for name,v in manifest['files'].items():
  f=point/name;s=f.stat();assert not f.is_symlink()and s.st_size==v['bytes']and s.st_mtime_ns==v['mtimeNs']and s.st_ino==v['inode']and s.st_dev==v['device']
  t.add(f,arcname=name,recursive=False)
if PREPASS:print(json.dumps({'bytes':sink.total,'sha256':sink.digest.hexdigest()}))
'''

def archive(name):
 assert name=='qualification-r1'or name in {f'{r}-{a}'for r in [7000,8000]for a in ['a1','b1','a2','b2']}
 dest=P/('archive-'+name);dest.mkdir(exist_ok=True);proofpath=dest/'PRIVATE_ASSET_VERIFIED.json'
 if proofpath.exists():return json.loads(proofpath.read_text())
 bindings='ROOT='+repr(ROOT)+'\nNAME='+repr(name)+'\n'
 source=r'''from pathlib import Path
import hashlib,json,os
r=Path(ROOT);point=r/NAME
assert Path('/etc/hostname').read_text().strip()=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
assert (point/'complete.json').is_file()
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java','Java active during closure'
 except(FileNotFoundError,ProcessLookupError):pass
launch=json.loads((r/(NAME+'.worker.launch.json')).read_text());stat=Path('/proc/'+str(launch['pid'])+'/stat')
if stat.exists():
 try:
  fields=stat.read_text().split(') ',1)[1].split();assert fields[19]!=str(launch['startTicks'])or fields[0]=='Z','worker still active'
 except(FileNotFoundError,ProcessLookupError):pass
rows={}
for f in sorted(point.rglob('*')):
 assert not f.is_symlink()
 if f.is_dir():continue
 assert f.is_file();s=f.stat();h=hashlib.sha256()
 with f.open('rb')as inp:
  for b in iter(lambda:inp.read(1024**2),b''):h.update(b)
 assert f.stat().st_mtime_ns==s.st_mtime_ns
 rows[str(f.relative_to(point))]={'bytes':s.st_size,'sha256':h.hexdigest(),'mtimeNs':s.st_mtime_ns,'inode':s.st_ino,'device':s.st_dev,'mode':s.st_mode}
manifest={'schema':'closed-overload-evidence-1','scope':NAME,'files':rows,'allJavaAndOriginalWorkerStopped':True}
f=r/(NAME+'.members.json')
if f.exists():assert json.loads(f.read_text())==manifest
else:f.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
'''
 manifest=json.loads(checked(bindings+source));(dest/'MEMBER_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
 plan=json.loads(checked(bindings+'PREPASS=True\n'+PACK_SOURCE));assert 0<plan['bytes']<1900*1024**2
 (dest/'EXACT_COMPRESSED_PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
 local=dest/('vectormatch-overload-20261027-r2-'+name+'.tar.gz')
 if not local.exists():
  assert shutil.disk_usage(P).free>plan['bytes']+300*1024**2,'local exact compressed admission refused'
  cmd="python3 - <<'BOUNDED_STREAM'\n"+bindings+'PREPASS=False\n'+PACK_SOURCE+'\nBOUNDED_STREAM'
  proc=subprocess.Popen(remote.sshargs()+[cmd],stdout=subprocess.PIPE,stderr=(dest/'stream.stderr').open('wb'))
  h=hashlib.sha256();total=0;started=time.monotonic()
  try:
   with local.open('xb')as out:
    for b in iter(lambda:proc.stdout.read(1024**2),b''):
     assert total+len(b)<=plan['bytes'],'stream exceeded frozen compressed size'
     out.write(b);h.update(b);total+=len(b)
     assert time.monotonic()-started<900,'stream deadline exceeded'
   assert proc.wait(timeout=30)==0 and total==plan['bytes']and h.hexdigest()==plan['sha256']
  except BaseException:
   proc.terminate();proc.wait(timeout=30);raise
 assert local.stat().st_size==plan['bytes']and sha(local)==plan['sha256']
 observed={};manifest_seen=False
 with tarfile.open(local,'r|gz')as t:
  for m in t:
   assert m.isfile()and not Path(m.name).is_absolute()and'..'not in Path(m.name).parts
   inp=t.extractfile(m)
   if m.name=='MEMBER_MANIFEST.json':assert not manifest_seen and json.loads(inp.read())==manifest;manifest_seen=True;continue
   assert m.name in manifest['files']and m.name not in observed
   h=hashlib.sha256()
   for b in iter(lambda:inp.read(1024**2),b''):h.update(b)
   v=manifest['files'][m.name];assert m.size==v['bytes']and h.hexdigest()==v['sha256'];observed[m.name]=True
 assert manifest_seen and set(observed)==set(manifest['files'])
 assert gh('repos/'+REPO)['private'];release=gh('repos/'+REPO+'/releases/'+str(RELEASE));assert release['draft']
 assets=[a for a in release['assets']if a['name']==local.name]
 if not assets:
  subprocess.run([GH,'release','upload',release['tag_name'],str(local),'--repo',REPO],check=True,timeout=1200)
  release=gh('repos/'+REPO+'/releases/'+str(RELEASE));assets=[a for a in release['assets']if a['name']==local.name]
 assert len(assets)==1 and assets[0]['size']==plan['bytes'];a=assets[0]
 proc=subprocess.Popen([GH,'api','-H','Accept: application/octet-stream','repos/'+REPO+'/releases/assets/'+str(a['id'])],stdout=subprocess.PIPE)
 h=hashlib.sha256();total=0
 for b in iter(lambda:proc.stdout.read(1024**2),b''):h.update(b);total+=len(b)
 assert proc.wait(timeout=60)==0 and total==plan['bytes']and h.hexdigest()==plan['sha256']
 proof={'assetId':a['id'],'name':local.name,'bytes':plan['bytes'],'sha256':plan['sha256'],'privateDraftRelease':RELEASE,'authenticatedFullDownloadVerified':True,'allOriginalMembersVerified':True,'memberCount':len(observed),'closedNativeRoot':ROOT+'/'+name,'epoch':time.time()}
 proofpath.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'archived':name,'proof':proof}),flush=True);return proof

def retire(name):
 d=P/('archive-'+name);proof=json.loads((d/'PRIVATE_ASSET_VERIFIED.json').read_text());manifest=json.loads((d/'MEMBER_MANIFEST.json').read_text())
 assert proof['privateDraftRelease']==RELEASE and proof['authenticatedFullDownloadVerified']and proof['allOriginalMembersVerified']
 # Retire large stopped duplicate files only. Preserve all metadata, snapshots and small diagnostics.
 selected={n:v for n,v in manifest['files'].items()if (v['bytes']>=1024**2 or (n.startswith('native/load/writer/') and n.endswith('.bin'))) and not n.endswith('.snapshot')and'canonical-final'not in n and not n.startswith('junit/')}
 source=r'''from pathlib import Path
import hashlib,json,shutil
r=Path(ROOT)/NAME
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java','Java active'
 except(FileNotFoundError,ProcessLookupError):pass
before=shutil.disk_usage(r).free
verified=[]
for n,v in SELECTED.items():
 f=r/n;assert not f.is_symlink()and f.is_file();s=f.stat();assert s.st_size==v['bytes']and s.st_mtime_ns==v['mtimeNs']and s.st_ino==v['inode']and s.st_dev==v['device']
 h=hashlib.sha256()
 with f.open('rb')as inp:
  for b in iter(lambda:inp.read(1024**2),b''):h.update(b)
 assert h.hexdigest()==v['sha256'];verified.append((f,s))
for f,s in verified:
 current=f.stat();assert current.st_ino==s.st_ino and current.st_mtime_ns==s.st_mtime_ns;f.unlink()
result={'assetId':PROOF['assetId'],'archiveSha256':PROOF['sha256'],'files':list(SELECTED),'freeBefore':before,'freeAfter':shutil.disk_usage(r).free,'privateFullEvidenceRetained':True}
(r.parent/(NAME+'.duplicate-retirement.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
'''
 result=json.loads(checked('ROOT='+repr(ROOT)+'\nNAME='+repr(name)+'\nPROOF='+repr(proof)+'\nSELECTED='+repr(selected)+'\n'+source))
 (d/'REMOTE_DUPLICATE_RETIREMENT.json').write_text(json.dumps(result,indent=2)+'\n')
 local=d/proof['name']
 if local.exists():assert local.stat().st_size==proof['bytes']and sha(local)==proof['sha256'];local.unlink()
 return result
if __name__=='__main__':archive(sys.argv[1])
