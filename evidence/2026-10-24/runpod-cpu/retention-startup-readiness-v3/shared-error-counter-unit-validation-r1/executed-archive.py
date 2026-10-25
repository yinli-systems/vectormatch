from pathlib import Path
import json,hashlib,stat,tarfile,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/shared-error-counter-unit-validation-r1';assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
def tree(p):
 files={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();row=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid);n=q.relative_to(p).as_posix()
  if q.is_dir():dirs[n]=row
  else:files[n]=dict(row,bytes=s.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
names=['startup-readiness-unit-r3','startup-readiness-unit-preparation-r1','startup-readiness-unit-closure-preparation-r4'];valid=json.loads((B/names[0]/'VALIDATION.json').read_text());assert valid['passed']and valid['distinctTests']==73;before={n:tree(B/n)for n in names};O.mkdir(parents=True)
archive=O/'all-original-local-unit-scopes.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1)as t:
 for n in names:t.add(B/n,arcname='original/'+n,recursive=True)
assert archive.stat().st_size<256*1024**2
seen={n:dict(files=set(),directories=set())for n in names}
with tarfile.open(archive,'r|gz')as t:
 for member in t:
  head,name=member.name[len('original/'):].split('/',1)if'/'in member.name[len('original/'):]else(member.name[len('original/'):],'.');assert head in before;kind='files'if member.isfile()else'directories';assert member.isfile()or member.isdir();row=before[head][kind][name];assert member.mode==row['mode']and member.uid==row['uid']and member.gid==row['gid'];assert name not in seen[head][kind];seen[head][kind].add(name)
  if member.isfile():
   assert member.size==row['bytes'];h=hashlib.sha256();count=0;f=t.extractfile(member)
   for block in iter(lambda:f.read(1024**2),b''):h.update(block);count+=len(block)
   assert count==row['bytes']and h.hexdigest()==row['sha256']
for n in names:
 assert tree(B/n)==before[n]
 for kind in ['files','directories']:assert seen[n][kind]==set(before[n][kind])
(O/'ORIGINAL_INVENTORIES.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');shutil.copy2(B/'startup-readiness-unit-r3/VALIDATION.json',O/'VALIDATION.json');(O/'README.md').write_text('# Shared Archive/driver error counter regression\n\n73 distinct tests across15 suites passed:64 prior maintenance/capacity regressions plus9 readiness tests. The new regression retains the exact eight-counter shape observed in the failed Linux startup: no dedicated Archive101 counter, with driver0,consensus212 and service215 present and zero. Missing driver errors still fail; any separately present Archive counter must also be zero.\n\nAll actual source-before-build bytes,21 registered classpath entries,installed JARs,224 matching compiled main class bodies,JUnit XML/HTML,JDK executable/release and bounded no-follow temporary fixture inventories are retained. Lexical fixture symlinks are metadata; no link is followed by this collector. Full original TAR members were streamed and checked for bytes/SHA/mode/owner/empty directories. The earlier72-test artifact and failed447-sample Linux attempt remain separately retained,not overwritten.\n\nThis is a local build/correctness regression. Real Linux startup/load qualification remains required; no throughput or100M claim.\n');payload=tree(O);(O/'INVENTORY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),payloadFiles=len(payload['files']),inventorySha256=sha(O/'INVENTORY.json'),archiveSha256=sha(archive),archiveBytes=archive.stat().st_size,allOriginalMembersStreamVerified=True,sourceScopeInventoriesUnchanged=True),indent=2)+'\n');print(json.dumps(dict(passed=True,compressedBytes=archive.stat().st_size,originalFiles=sum(len(t['files'])for t in before.values()),inventorySha256=sha(O/'INVENTORY.json'))))
