#!/usr/bin/env python3
"""Read-only SSH collection of exact closed R3 job + explicit frozen source allowlist. Never launches/mutates remote workload."""
from pathlib import Path,PurePosixPath
import hashlib,importlib.util,json,shlex,stat,subprocess,tarfile,shutil,time
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2');BASE=ROOT/'runtime/cloud/cpu-20261024';DEST=ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-current-checkpoint-r3/collection-r1'
JOB='/opt/vectormatch-cpu/preparation/original-current-checkpoint-r3/lifecycle-attempt-r1';SOURCE='/opt/vectormatch-cpu/preparation/original-current-checkpoint-r3'
spec=importlib.util.spec_from_file_location('readonly_cpu_remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)

def hash_file(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def main():
 DEST.mkdir(parents=True,exist_ok=False)
 program='JOB='+repr(JOB)+'\nSOURCE='+repr(SOURCE)+'\n'+r'''
import hashlib,json,pathlib,stat,socket
assert socket.gethostname()=='ed6c0673f5cb'
job=pathlib.Path(JOB);source=pathlib.Path(SOURCE)
completion=json.loads((job/'completion.json').read_text());stops=json.loads((job/'owned-stop.json').read_text());reader_stops=json.loads((job/'offline-readers-stop.json').read_text())
assert completion['passed'] and completion['allOwnedStopped'] and stops['allOwnedStopped'] and reader_stops['allOwnedStopped'] and not (job/'BENCHMARK_BLOCKED.json').exists()
frozen=source/'FROZEN_PREPARATION.json';assert hashlib.sha256(frozen.read_bytes()).hexdigest()=='02aa8cab2f1c8ea921ba84e2fe0b5b8325e6e9d0fe147131720805c6e61eaee0'
manifest=json.loads(frozen.read_text());allow=set(manifest['frozenFiles'])|{'FROZEN_PREPARATION.json','execution-register.json','execution.stdout','execution.stderr'}
rows={};dirs={}
def add(p,name):
 assert not p.is_symlink();st=p.stat()
 if p.is_dir():dirs[name]={'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
 else:
  assert p.is_file() and st.st_nlink==1 and st.st_size<=70*1024**2
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024**2),b''):h.update(b)
  rows[name]={'bytes':st.st_size,'sha256':h.hexdigest(),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
for p in [job]+sorted(job.rglob('*')):add(p,'job' if p==job else 'job/'+str(p.relative_to(job)))
source_dirs={'.'}
for rel in allow:
 path=pathlib.PurePosixPath(rel);assert not path.is_absolute() and '..' not in path.parts
 source_dirs.update(str(x) for x in path.parents)
for rel in sorted(source_dirs):add(source if rel=='.' else source/rel,'source' if rel=='.' else 'source/'+rel)
for rel in sorted(allow):add(source/rel,'source/'+rel)
for rel,expected in manifest['frozenFiles'].items():assert all(rows['source/'+rel][k]==expected[k] for k in ['bytes','sha256'])
assert len(rows)<1024 and len(dirs)<256
print(json.dumps({'files':rows,'directories':dirs,'sourceAllowlist':sorted(allow),'sourceRecursiveTarAllowed':False,'completion':completion,'ownedStop':stops,'offlineReadersStop':reader_stops},sort_keys=True))
'''
 result=remote.run('python3 -B -c '+shlex.quote(program),timeout=120);(DEST/'remote-inventory.stderr').write_text(result.stderr);(DEST/'remote-inventory.json').write_text(result.stdout)
 assert result.returncode==0,result.stderr
 inventory=json.loads(result.stdout);(DEST/'after-native-baseline.json').write_text('')
 # Explicit source members only. job itself may be recursively archived because it is separately registered and fully closed.
 program='JOB='+repr(JOB)+'\nSOURCE='+repr(SOURCE)+'\nALLOW='+repr(inventory['sourceAllowlist'])+'\n'+r'''
import sys,pathlib,tarfile,gzip
source=pathlib.Path(SOURCE);parents={'.'}
for rel in ALLOW:parents.update(str(p) for p in pathlib.PurePosixPath(rel).parents)
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1) as g:
 with tarfile.open(fileobj=g,mode='w|') as t:
  t.add(JOB,arcname='job',recursive=True)
  for rel in sorted(parents):t.add(source if rel=='.' else source/rel,arcname='source' if rel=='.' else 'source/'+rel,recursive=False)
  for rel in ALLOW:t.add(source/rel,arcname='source/'+rel,recursive=False)
'''
 packed=DEST/'raw-closed-current-checkpoint.tar.gz'
 with packed.open('xb') as out,(DEST/'transfer.stderr').open('xb') as err:
  result=subprocess.run(remote.sshargs()+['python3 -B -c '+shlex.quote(program)],stdout=out,stderr=err,timeout=240)
 assert result.returncode==0,'Readonly transfer failed; retain partial archive and stderr'
 seen=set();dirs=set();small=[]
 with tarfile.open(packed,'r|gz') as t:
  for a in t:
   name=a.name.rstrip('/');q=PurePosixPath(name);assert name and not q.is_absolute() and '..' not in q.parts and name not in seen|dirs
   if a.isdir():
    row=inventory['directories'][name];assert a.mode==row['mode'] and a.uid==row['uid'] and a.gid==row['gid'];dirs.add(name);continue
   assert a.isfile();row=inventory['files'][name];assert a.size==row['bytes'] and a.mode==row['mode'] and a.uid==row['uid'] and a.gid==row['gid'];h=hashlib.sha256();f=t.extractfile(a)
   target=None
   if name=='job/native-after-clean-stop.tar.gz':target=DEST/'native-after-clean-stop.tar.gz'
   elif a.size<=2*1024**2 and not name.endswith(('.jar','.class','.gz','.bin')):target=DEST/'small-files'/name
   elif name=='source/FROZEN_PREPARATION.json':target=DEST/'small-files'/name
   dest=None
   if target:target.parent.mkdir(parents=True,exist_ok=True);dest=target.open('xb')
   try:
    for b in iter(lambda:f.read(1024**2),b''):
     h.update(b)
     if dest:dest.write(b)
   finally:
    if dest:dest.close()
   assert h.hexdigest()==row['sha256'],name;seen.add(name)
 assert seen==set(inventory['files']) and dirs==set(inventory['directories'])
 after=DEST/'small-files/job/after-native.json';shutil.copy2(after,DEST/'after-native-baseline.json')
 for name in ['original-current-checkpoint-r3-staging','original-current-checkpoint-r3-staging-r2']:
  shutil.copytree(BASE/name,DEST/'local-staging'/name,symlinks=True)
 for name in ['stage-original-checkpoint-r3.py','check-and-start-original-checkpoint-r3.py','collect-original-current-checkpoint-r3.py']:
  shutil.copy2(BASE/name,DEST/name)
 receipt={'passed':True,'scope':'Readonly SSH collection only, no remote resource/state/process mutations or workload launches','outerFiles':len(seen),'outerDirectories':len(dirs),'sourceFiles':len(inventory['sourceAllowlist']),'sourceWhitelistOnly':True,'sourceRecursiveTar':False,'allOuterFileSizesFullShaModesOwnersAndExactDirectoryClosureVerified':True,'rawArchive':{'bytes':packed.stat().st_size,'sha256':hash_file(packed)},'nativeArchiveSeparatelyPreserved':{'bytes':(DEST/'native-after-clean-stop.tar.gz').stat().st_size,'sha256':hash_file(DEST/'native-after-clean-stop.tar.gz')},'afterNativeBaselineSha256':hash_file(after),'nestedNativeVerificationPending':True,'originalsDeleted':False}
 (DEST/'collection-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
