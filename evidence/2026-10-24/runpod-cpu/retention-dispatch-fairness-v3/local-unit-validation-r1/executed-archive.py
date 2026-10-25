from pathlib import Path
import json,hashlib,stat,tarfile,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/local-unit-validation-r1';assert not O.exists()
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
names=['dispatch-fairness-unit-r1','dispatch-fairness-unit-preparation-r1','dispatch-fairness-unit-closure-preparation-r1'];valid=json.loads((B/names[0]/'VALIDATION.json').read_text());assert valid['passed']and valid['distinctTests']==76;before={n:tree(B/n)for n in names};O.mkdir(parents=True)
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
(O/'ORIGINAL_INVENTORIES.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');shutil.copy2(B/'dispatch-fairness-unit-r1/VALIDATION.json',O/'VALIDATION.json');(O/'README.md').write_text('# Opt-in rotating-dispatch local qualification\n\n76 distinct tests across16 suites passed:73 previous readiness/maintenance/capacity regressions plus3 dispatch-policy tests. Both policies have exactly the same admitted codec/resource plan. Legacy configurations retain FIXED_ZERO_START; ROTATING_CONTINUE is allowed only by explicit160000@8000 read128 selection. All producer FIFO identities,per-worker Q64,one pending request per worker,original deadlines,maintenance fencing and force/readback before ACK remain unchanged.\n\nThe fairness model uses the real128 Q64 ledger queues and repeatedly interrupts scans after120 placements. Fixed scans starve the last8 workers; rotating scans serve every worker45 times over48 cuts while preserving each original producer sequence. This is a deterministic scheduling regression,not a native throughput result or a model of actual3072-command maintenance timing.\n\nActual source-before-build bytes,21 registered runtime classpath entries,installed JARs,225 matching compiled main class bodies,JUnit XML/HTML,JDK executable/release and41 no-follow fixture roots are retained. The complete TAR was streamed and every member SHA/size/mode/owner/empty directory checked. Lexical fixture links are metadata;none are followed.\n\nNew homogeneous Linux origins and a fixed/rotating/fixed/rotating same-artifact native comparison remain required. No performance gain,hard realtime or100M result is established.\n');payload=tree(O);(O/'INVENTORY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),payloadFiles=len(payload['files']),inventorySha256=sha(O/'INVENTORY.json'),archiveSha256=sha(archive),archiveBytes=archive.stat().st_size,allOriginalMembersStreamVerified=True,sourceScopeInventoriesUnchanged=True),indent=2)+'\n');print(json.dumps(dict(passed=True,compressedBytes=archive.stat().st_size,originalFiles=sum(len(t['files'])for t in before.values()),inventorySha256=sha(O/'INVENTORY.json'))))
