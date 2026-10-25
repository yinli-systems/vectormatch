from pathlib import Path
import json,hashlib,stat,tarfile,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/local-unit-validation-r1';assert not O.exists()
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
names=['dispatch-capacity-unit-r1','dispatch-capacity-unit-r2','dispatch-capacity-unit-preparation-r1','dispatch-capacity-unit-closure-preparation-r1','dispatch-capacity-unit-failure-closure-preparation-r1','dispatch-capacity-unit-closure-preparation-r2'];valid=json.loads((B/'dispatch-capacity-unit-r2/VALIDATION.json').read_text());assert valid['passed']and valid['distinctTests']==79;before={n:tree(B/n)for n in names};O.mkdir(parents=True)
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
(O/'ORIGINAL_INVENTORIES.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');shutil.copy2(B/'dispatch-capacity-unit-r2/VALIDATION.json',O/'VALIDATION.json');(O/'README.md').write_text('# Fine dispatch-capacity local qualification\n\nThe first79-test attempt retains its failed6000/s planner qualification and all original source/class/JUnit/fixture bytes. After an explicit separate fine-plan entry was added,79 distinct tests across17 suites passed:76 prior readiness/maintenance/capacity/fairness regressions plus3 fine-preset/admission/CLI guards. Both policies at each explicit4000/6000/7000/7500/8000 rate share an identical admitted codec/resource plan and20s scheduled arrivals. Legacy factories and accepted rates retain their original restrictions;rotation remains opt-in.\n\nRead128/page32/batch4/chunk6144,W128/Q64,one pending logical order per worker,original deadlines,maintenance fencing,force/readback before ACK,raw/disk caps and all service/wire formats remain unchanged. Arbitrary/malformed selections fail before creating a native experiment root. No throughput or sustained-capacity result follows from these local tests.\n\nComplete actual source-before-build,registered test runtime classpath,installed JARs and actual compiled class bodies,JUnit XML/HTML,JDK executable/release and bounded no-follow fixture trees are retained. Every TAR member SHA/size/mode/owner and directory is verified;fixture links are lexical metadata and never followed. New homogeneous Linux class origins and original native/raw/readiness/private closure are required before any rate progression.\n');payload=tree(O);(O/'INVENTORY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),payloadFiles=len(payload['files']),inventorySha256=sha(O/'INVENTORY.json'),archiveSha256=sha(archive),archiveBytes=archive.stat().st_size,allOriginalMembersStreamVerified=True,sourceScopeInventoriesUnchanged=True),indent=2)+'\n');print(json.dumps(dict(passed=True,compressedBytes=archive.stat().st_size,originalFiles=sum(len(t['files'])for t in before.values()),inventorySha256=sha(O/'INVENTORY.json'))))
