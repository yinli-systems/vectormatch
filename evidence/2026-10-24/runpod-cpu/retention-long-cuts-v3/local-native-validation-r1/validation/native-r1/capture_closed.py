"""One read-only stopped-tree capture; streams full sparse files, never extracts them."""
from pathlib import Path
import datetime,hashlib,json,shutil,stat,subprocess,tarfile,time
OUT=Path(__file__).resolve().parent;VALIDATION=OUT.parent;WORK=OUT.parents[2]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def write(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
start=time.monotonic();reg=json.loads((OUT/'registration.json').read_text());arm=Path(reg['ownedNamespace'])
exit=json.loads((OUT/'parent-exit.json').read_text());stop=json.loads((arm/'owned-stop.json').read_text())
assert stop['allOwnedStopped'] is True and stop['forcedKill'] is False
for identity in sorted(arm.glob('node-*-identity.json')):
 row=json.loads(identity.read_text());p=subprocess.run(['/bin/ps','-p',str(row['pid']),'-o','pid='],capture_output=True,text=True)
 assert p.returncode==1 and not p.stdout.strip(),'Owned PID remains; no archive'
assert shutil.disk_usage(WORK).free>=reg['diskBefore']['freeFloor']+reg['diskBefore']['closedArchiveReserve']
for row in reg['jars']+reg['jdk']+reg['helpers']+[reg['actualPlanInput'],reg['sourceFreeze'],reg['sourceReview']]:assert sha(Path(row['path']))==row['sha256']
inputs=OUT/'input-state';inputs.mkdir(exist_ok=False)
for row in reg['jars']:
 dest=inputs/'lib'/Path(row['path']).name;dest.parent.mkdir(exist_ok=True);shutil.copy2(row['path'],dest);assert sha(dest)==row['sha256']
freeze=json.loads(Path(reg['sourceFreeze']['path']).read_text())
for row in freeze['paths']:
 src=WORK/row['path'];assert sha(src)==row['sha256'];dest=inputs/'source'/row['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
for name,row in [('SOURCE_FROZEN_R1.json',reg['sourceFreeze']),('ROOT_REVIEW.json',reg['sourceReview']),('actual-distribution-observation.json',reg['actualPlanInput'])]:shutil.copy2(row['path'],inputs/name)
closed=OUT/'closed-originals';closed.mkdir(exist_ok=False)
items=[(OUT,Path('native'))]
for src in sorted(OUT.rglob('*')):
 if closed==src or closed in src.parents:continue
 items.append((src,Path('native')/src.relative_to(OUT)))
rows=[];total=0
for src,arc in items:
 st=src.lstat();assert stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)
 row=dict(path=arc.as_posix(),type='file' if stat.S_ISREG(st.st_mode) else 'directory',mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid,mtimeNs=st.st_mtime_ns,bytes=st.st_size if stat.S_ISREG(st.st_mode) else 0,allocatedBytes=st.st_blocks*512)
 if row['type']=='file':row['sha256']=sha(src);total+=row['bytes']
 rows.append(row)
assert len(rows)<=4096 and total<8*1024**3
write(closed/'manifest.json',dict(scope='Full stopped original one-arm native namespace, all raw/failure/warning/control logs and exact input JAR/source metadata. No performance claim.',entries=rows,logicalFileBytes=total,allOwnedStopped=True))
archive=closed/'native-originals.tar.gz'
print(json.dumps(dict(state='ARCHIVING_FULL_STOPPED_ORIGINALS',entries=len(rows),logicalFileBytes=total)),flush=True)
with tarfile.open(archive,'x:gz',compresslevel=1,format=tarfile.PAX_FORMAT) as tar:
 for src,arc in items:tar.add(src,arcname=arc.as_posix(),recursive=False)
assert archive.stat().st_size<=reg['diskBefore']['closedArchiveReserve']
expected={r['path']:r for r in rows};seen=set()
with tarfile.open(archive,'r|gz') as tar:
 for member in tar:
  assert member.name in expected and member.name not in seen;seen.add(member.name);r=expected[member.name]
  assert (member.mode,member.uid,member.gid)==(r['mode'],r['uid'],r['gid'])
  if member.isfile():
   assert r['type']=='file' and member.size==r['bytes'];h=hashlib.sha256();f=tar.extractfile(member)
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
   assert h.hexdigest()==r['sha256']
  else:assert member.isdir() and r['type']=='directory'
assert seen==set(expected)
for src,arc in items:
 row=expected[arc.as_posix()];st=src.lstat();assert (stat.S_IMODE(st.st_mode),st.st_uid,st.st_gid)==(row['mode'],row['uid'],row['gid'])
 if row['type']=='file':assert st.st_size==row['bytes'] and sha(src)==row['sha256']
write(closed/'completion.json',dict(passed=True,allOwnedStopped=True,parentReturnCode=exit['returnCode'],sourceCommit=reg['sourceCommit'],actualCodeFingerprint=reg['actualCodeFingerprint'],entries=len(rows),logicalFileBytes=total,archiveBytes=archive.stat().st_size,archiveSha256=sha(archive),manifestSha256=sha(closed/'manifest.json'),fullStreamingReadbackShaModeOwnerDirectoryClosure=True,sourceCopiesAndOriginalsUnchanged=True,noSparseExtraction=True,elapsedSeconds=time.monotonic()-start,capacityClaim=False))
print(json.dumps(dict(state='CLOSED_ARCHIVE_VERIFIED',receiptSha256=sha(closed/'completion.json'),archiveBytes=archive.stat().st_size)),flush=True)
