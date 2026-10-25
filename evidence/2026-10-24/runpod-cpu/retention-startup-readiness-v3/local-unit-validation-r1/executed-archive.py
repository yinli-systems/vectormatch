from pathlib import Path
import json,hashlib,stat,tarfile,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/local-unit-validation-r1';assert not O.exists()
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
names=['startup-readiness-unit-r1','startup-readiness-unit-r2','startup-readiness-unit-preparation-r1','startup-readiness-unit-closure-preparation-r1','startup-readiness-unit-closure-preparation-r2','startup-readiness-unit-closure-preparation-r3'];valid=json.loads((B/names[1]/'VALIDATION.json').read_text());assert valid['passed']and valid['distinctTests']==72;before={n:tree(B/n)for n in names};O.mkdir(parents=True)
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
(O/'ORIGINAL_INVENTORIES.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');shutil.copy2(B/'startup-readiness-unit-r2/VALIDATION.json',O/'VALIDATION.json');(O/'README.md').write_text('# All-member startup-readiness qualification\n\n72 distinct tests across15 suites passed:64 existing maintenance/capacity regression tests plus8 readiness tests. All registered21 classpath entries,source-before-build bytes,actual test JVM options,installed JARs,XML/HTML and39 actual temporary fixture roots are retained. All224 installed application class bodies match actual compiled main classes used by tests.\n\nInitial8-test attempt had7 fixture alignment failures, corrected only by using aligned direct counter buffers. The complete failed attempt is retained. Earlier collection attempts stopped on var/private-var aliases and a deliberately cyclic POSIX fixture symlink; failed sources and full partial copies remain in the original archive. The final bounded no-follow fixture inventory records every link lexically and copies every regular fixture body once. No link is followed by the final collector.\n\nA complete compressed TAR retains all original local scopes,including earlier failed collection partials. Every original file/empty directory SHA/size/mode/owner was streamed and verified. This is a local correctness/build result, not Linux native performance proof or proof that the underlying Aeron startup race is fixed.\n');payload=tree(O);(O/'INVENTORY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),payloadFiles=len(payload['files']),inventorySha256=sha(O/'INVENTORY.json'),archiveSha256=sha(archive),archiveBytes=archive.stat().st_size,allOriginalMembersStreamVerified=True,sourceScopeInventoriesUnchanged=True),indent=2)+'\n');print(json.dumps(dict(passed=True,compressedBytes=archive.stat().st_size,originalFiles=sum(len(t['files'])for t in before.values()),inventorySha256=sha(O/'INVENTORY.json'))))
