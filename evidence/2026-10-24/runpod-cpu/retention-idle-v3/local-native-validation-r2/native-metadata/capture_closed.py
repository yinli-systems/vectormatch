from pathlib import Path
import hashlib,json,tarfile,stat,datetime,subprocess,time
out=Path(__file__).resolve().parent;v=out.parent;start=time.monotonic()
for maximum in [1000000,100000]:
 assert json.loads((out/f'arm-{maximum}-process/exit.json').read_text())['returnCode']==0
 assert json.loads((out/f'arms/park-{maximum}/owned-stop.json').read_text())['allOwnedStopped'] is True
p=subprocess.run(['/usr/bin/pgrep','-fl','io.vectormatch.cluster.Retention'],capture_output=True,text=True);assert p.returncode==1 and not p.stdout
closure=out/'closed-originals';closure.mkdir()
items=[]
for child in sorted(out.iterdir()):
 if child==closure:continue
 for src in [child,*sorted(child.rglob('*'))] if child.is_dir() else [child]:items.append((src,Path('native')/src.relative_to(out)))
for src in sorted((v/'units-r4/artifact-state/distribution/lib').glob('*.jar')):items.append((src,Path('input-distribution/lib')/src.name))
freeze=json.loads((v/'SOURCE_FROZEN_R2.json').read_text())
for row in freeze['paths']:items.append((v/'units-r4/source'/row['path'],Path('input-source')/row['path']))
for src in [v/'SOURCE_FROZEN_R2.json',v/'SOURCE_COMMIT_R2.json']:items.append((src,Path('input-proofs')/src.name))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
rows=[];total=0
for src,arc in items:
 st=src.lstat();assert stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode),src
 row={'path':arc.as_posix(),'type':'directory' if stat.S_ISDIR(st.st_mode) else 'file','mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid,'mtimeNs':st.st_mtime_ns,'bytes':st.st_size if stat.S_ISREG(st.st_mode) else 0,'allocatedBytes':st.st_blocks*512}
 if row['type']=='file':row['sha256']=sha(src);total+=st.st_size
 rows.append(row)
assert len(rows)<=4096 and total<8*1024**3
manifest=closure/'manifest.json';manifest.write_text(json.dumps({'scope':'Complete stopped native-r2 originals including failed strict post-close wrapper gate, plus exact input distribution/changed sources. No warning or failure removed.','atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'entries':rows},indent=2)+'\n')
archive=closure/'native-originals.tar.gz';print(json.dumps({'state':'ARCHIVING_STOPPED_ORIGINALS','entries':len(rows),'logicalFileBytes':total}),flush=True)
with tarfile.open(archive,'x:gz',compresslevel=1,format=tarfile.PAX_FORMAT,dereference=True) as tar:
 for src,arc in items:tar.add(src,arcname=arc.as_posix(),recursive=False)
byname={r['path']:r for r in rows};seen=set()
with tarfile.open(archive,'r:gz') as tar:
 for member in tar:
  assert member.name in byname and member.name not in seen;seen.add(member.name);r=byname[member.name]
  assert member.mode==r['mode'] and member.uid==r['uid'] and member.gid==r['gid']
  if member.isfile():
   h=hashlib.sha256();stream=tar.extractfile(member)
   for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
   assert member.size==r['bytes'] and h.hexdigest()==r['sha256']
  else:assert member.isdir() and r['type']=='directory'
assert seen==set(byname)
receipt={'allOwnedStopped':True,'parentExitCodes':[0,0],'sourceCommit':'7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23','actualCodeSha256':'f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f','archiveSha256':sha(archive),'archiveBytes':archive.stat().st_size,'manifestSha256':sha(manifest),'entries':len(rows),'logicalFileBytes':total,'fullArchiveReadbackVerified':True,'modesOwnersAndEmptyDirectoriesPreserved':True,'strictPostCloseWrapperGatePreservedAsFailed':True,'sourceMutationPerformed':False,'elapsedSeconds':time.monotonic()-start}
(closure/'completion.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2),flush=True)
