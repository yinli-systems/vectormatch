import hashlib, importlib.util, json, pathlib, shlex, subprocess, tarfile

BASE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('remote',BASE/'remote.py')
remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
DEST=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-cluster-recovery-r1/collection-r2'
DEST.mkdir(parents=True,exist_ok=False)
JOB='/opt/vectormatch-cpu/preparation/original-cluster-probe-r2/lifecycle-attempt-r1'
SOURCE='/opt/vectormatch-cpu/preparation/original-cluster-lifecycle-r1-source'
program=r'''
import hashlib,json,pathlib,stat
job=pathlib.Path(JOB);source=pathlib.Path(SOURCE)
completion=json.loads((job/'completion.json').read_text());stops=json.loads((job/'owned-stop.json').read_text())
assert completion['allOwnedStopped'] and stops['allOwnedStopped'] and not (job/'BENCHMARK_BLOCKED.json').exists()
rows={};dirs={}
for label,root in [('job',job),('source',source)]:
 for p in [root]+sorted(root.rglob('*')):
  assert not p.is_symlink();st=p.stat();name=label+'/'+str(p.relative_to(root));name=name.rstrip('/.') if p==root else name
  if p.is_dir():dirs[name]={'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
  else:
   assert p.is_file() and st.st_nlink==1 and st.st_size<=70*1024**2
   h=hashlib.sha256()
   with p.open('rb') as f:
    for b in iter(lambda:f.read(1024**2),b''):h.update(b)
   rows[name]={'bytes':st.st_size,'sha256':h.hexdigest(),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
print(json.dumps({'files':rows,'directories':dirs,'completion':completion,'ownedStop':stops},sort_keys=True))
'''.replace('JOB',repr(JOB)).replace('SOURCE',repr(SOURCE))
r=remote.run('python3 -c '+shlex.quote(program),timeout=90)
(DEST/'remote-inventory.stderr').write_text(r.stderr)
assert r.returncode==0,r.stderr
(DEST/'remote-inventory.json').write_text(r.stdout)
inventory=json.loads(r.stdout)
program="import sys,tarfile,gzip;\nwith gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1) as g:\n with tarfile.open(fileobj=g,mode='w|') as t:\n  t.add(%r,arcname='job');t.add(%r,arcname='source')"%(JOB,SOURCE)
bundle=DEST/'raw-closed-recovery.tar.gz'
with bundle.open('xb') as out,(DEST/'transfer.stderr').open('xb') as err:
 p=subprocess.run(remote.sshargs()+['python3 -c '+shlex.quote(program)],stdout=out,stderr=err,timeout=180)
assert p.returncode==0
seen=set();dirs=set()
with tarfile.open(bundle,mode='r|gz') as stream:
 for member in stream:
  name=member.name.rstrip('/')
  assert name not in seen|dirs and not name.startswith('/') and '..' not in pathlib.PurePosixPath(name).parts
  if member.isdir():
   row=inventory['directories'][name];assert member.mode==row['mode'] and member.uid==row['uid'] and member.gid==row['gid'];dirs.add(name)
  else:
   assert member.isfile();row=inventory['files'][name];assert member.size==row['bytes'] and member.mode==row['mode'] and member.uid==row['uid'] and member.gid==row['gid']
   h=hashlib.sha256();f=stream.extractfile(member)
   for b in iter(lambda:f.read(1024**2),b''):h.update(b)
   assert h.hexdigest()==row['sha256'];seen.add(name)
assert seen==set(inventory['files']) and dirs==set(inventory['directories'])
# Extract only bounded convenient metadata/source; full native tree stays compressed.
with tarfile.open(bundle,'r:gz') as stream:
 for member in stream:
  if member.isfile() and member.size<=2*1024**2 and not any(member.name.endswith(ext) for ext in ('.jar','.gz','.bin')):
   target=DEST/'small-files'/member.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(stream.extractfile(member).read())
for p in (BASE/'original-cluster-lifecycle-r1-staging').iterdir():
 if p.is_file():
  target=DEST/'staging'/p.name;target.parent.mkdir(exist_ok=True);target.write_bytes(p.read_bytes())
for name in ('stage-original-lifecycle-r1.py','start-original-lifecycle-r1.py','collect-original-lifecycle-r1.py'):
 (DEST/name).write_bytes((BASE/name).read_bytes())
(DEST/'collection-receipt.json').write_text(json.dumps({'passed':True,'files':len(seen),'directories':len(dirs),'allFileSizesHashesModesOwnersVerified':True,'exactClosureVerified':True,'bundleBytes':bundle.stat().st_size,'bundleSha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'nativeAfterArchiveRequiresIndependentStreamReadback':True,'originalsDeleted':False},indent=2)+'\n')
print(json.dumps({'collected':True,'files':len(seen),'completion':inventory['completion'],'bundleBytes':bundle.stat().st_size}))
