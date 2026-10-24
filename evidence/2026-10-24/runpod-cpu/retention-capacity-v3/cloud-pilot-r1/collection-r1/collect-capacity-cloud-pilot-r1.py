#!/usr/bin/env python3
"""Readonly SSH complete closed capacity pilot collection; explicit source allowlist, no recursive SOURCE tar."""
from pathlib import Path,PurePosixPath
import hashlib,importlib.util,json,shlex,subprocess,tarfile,shutil
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2');BASE=ROOT/'runtime/cloud/cpu-20261024';DEST=ROOT/'evidence/2026-10-24/runpod-cpu/retention-capacity-v3/cloud-pilot-r1/collection-r1'
SOURCE='/opt/vectormatch-cpu/preparation/capacity-cloud-pilot-r1';JOB=SOURCE+'/attempt-r1'
spec=importlib.util.spec_from_file_location('readonly_capacity_remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 DEST.mkdir(parents=True,exist_ok=False);staged=json.loads((BASE/'capacity-cloud-pilot-staging-r2/receipt.json').read_text());assert staged['passed']
 expected=staged['stagedFiles'];allow=sorted(set(expected)|{'execution-register.json','execution.stdout','execution.stderr'})
 program='JOB='+repr(JOB)+'\nSOURCE='+repr(SOURCE)+'\nALLOW='+repr(allow)+'\nEXPECTED='+repr(expected)+'\n'+r'''
import hashlib,json,pathlib,stat,socket
assert socket.gethostname()=='ed6c0673f5cb';job=pathlib.Path(JOB);source=pathlib.Path(SOURCE)
completion=json.loads((job/'completion.json').read_text());closed=json.loads((job/'python-owned-stop.json').read_text());assert completion['passed'] and completion['allOwnedStopped'] and not completion['errors'] and closed['allOwnedStopped'] and not closed['forcedKill'] and not (job/'BENCHMARK_BLOCKED.json').exists()
rows={};dirs={}
def add(p,name):
 assert not p.is_symlink();st=p.stat()
 if p.is_dir():dirs[name]={'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
 else:
  assert p.is_file() and st.st_nlink==1 and st.st_size<=512*1024**2
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024**2),b''):h.update(b)
  rows[name]={'bytes':st.st_size,'sha256':h.hexdigest(),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
for p in [job]+sorted(job.rglob('*')):add(p,'job' if p==job else 'job/'+str(p.relative_to(job)))
parents={'.'}
for rel in ALLOW:
 p=pathlib.PurePosixPath(rel);assert not p.is_absolute() and '..' not in p.parts;parents.update(str(x) for x in p.parents)
for rel in sorted(parents):add(source if rel=='.' else source/rel,'source' if rel=='.' else 'source/'+rel)
for rel in ALLOW:add(source/rel,'source/'+rel)
for rel,expected in EXPECTED.items():assert all(rows['source/'+rel][k]==expected[k] for k in ['bytes','sha256'])
assert len(rows)<2048 and sum(r['bytes'] for r in rows.values())<14*1024**3
print(json.dumps({'files':rows,'directories':dirs,'sourceAllowlist':ALLOW,'sourceRecursiveTarAllowed':False,'completion':completion,'pythonOwnedStop':closed},sort_keys=True))
'''
 r=remote.run('python3 -B -c '+shlex.quote(program),timeout=240);(DEST/'remote-inventory.stdout.json').write_text(r.stdout);(DEST/'remote-inventory.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr;inv=json.loads(r.stdout)
 program='JOB='+repr(JOB)+'\nSOURCE='+repr(SOURCE)+'\nALLOW='+repr(allow)+'\n'+r'''
import sys,pathlib,tarfile,gzip
source=pathlib.Path(SOURCE);parents={'.'}
for rel in ALLOW:parents.update(str(x) for x in pathlib.PurePosixPath(rel).parents)
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1) as g:
 with tarfile.open(fileobj=g,mode='w|') as t:
  t.add(JOB,arcname='job',recursive=True)
  for rel in sorted(parents):t.add(source if rel=='.' else source/rel,arcname='source' if rel=='.' else 'source/'+rel,recursive=False)
  for rel in ALLOW:t.add(source/rel,arcname='source/'+rel,recursive=False)
'''
 packed=DEST/'full-closed-pilot.tar.gz'
 with packed.open('xb') as out,(DEST/'transfer.stderr').open('xb') as err:r=subprocess.run(remote.sshargs()+['python3 -B -c '+shlex.quote(program)],stdout=out,stderr=err,timeout=300)
 assert r.returncode==0,'Keep failed partial transfer; no retry identity automatically changed'
 seen=set();dirs=set()
 with tarfile.open(packed,'r|gz') as t:
  for a in t:
   name=a.name.rstrip('/');q=PurePosixPath(name);assert name and not q.is_absolute() and '..' not in q.parts and name not in seen|dirs
   if a.isdir():
    row=inv['directories'][name];assert (a.mode,a.uid,a.gid)==(row['mode'],row['uid'],row['gid']);dirs.add(name);continue
   assert a.isfile();row=inv['files'][name];assert (a.size,a.mode,a.uid,a.gid)==(row['bytes'],row['mode'],row['uid'],row['gid']);h=hashlib.sha256();f=t.extractfile(a);target=None
   if name=='job/pilot-after-clean-stop.tar.gz':target=DEST/'pilot-after-clean-stop.tar.gz'
   elif a.size<=32*1024**2 and not name.endswith(('.rec','.dat','.catalog','.jar','.class','.gz','.zip')):target=DEST/'raw-files'/name
   stream=None
   if target:target.parent.mkdir(parents=True,exist_ok=True);stream=target.open('xb')
   try:
    for b in iter(lambda:f.read(1024**2),b''):
     h.update(b)
     if stream:stream.write(b)
   finally:
    if stream:stream.close()
   assert h.hexdigest()==row['sha256'],name;seen.add(name)
 assert seen==set(inv['files']) and dirs==set(inv['directories'])
 for name in ['capacity-cloud-pilot-staging-r1','capacity-cloud-pilot-staging-r2']:shutil.copytree(BASE/name,DEST/'local-staging'/name,symlinks=True)
 for name in ['stage-capacity-cloud-pilot-r1.py','resume-and-start-capacity-cloud-pilot-r1.py','collect-capacity-cloud-pilot-r1.py']:shutil.copy2(BASE/name,DEST/name)
 receipt={'passed':True,'scope':'Readonly SSH file queries/transfers only; no app launch, PG, signal, resource purchase or remote state mutation','outerFiles':len(seen),'outerDirectories':len(dirs),'outerLogicalBytes':sum(v['bytes'] for v in inv['files'].values()),'sourceWhitelistFiles':len(allow),'sourceRecursiveTar':False,'allOuterFileFullShaSizeModeOwnerAndEmptyDirClosureVerified':True,'fullOuterArchive':{'bytes':packed.stat().st_size,'sha256':sha(packed)},'nestedNativeArchive':{'bytes':(DEST/'pilot-after-clean-stop.tar.gz').stat().st_size,'sha256':sha(DEST/'pilot-after-clean-stop.tar.gz')},'nestedFullVerificationPending':True,'originalsDeleted':False}
 (DEST/'collection-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
