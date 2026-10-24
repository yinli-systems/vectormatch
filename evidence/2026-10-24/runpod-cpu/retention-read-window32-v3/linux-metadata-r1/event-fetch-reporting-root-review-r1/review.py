from pathlib import Path
import json,hashlib,stat,datetime
ROOT=Path.cwd(); BASE=ROOT/'runtime/cloud/cpu-20261024'; OUT=Path(__file__).resolve().parent

def load(p): return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
def tree(p):
 files={}; dirs={}
 for q in [p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink(),str(q)
  s=q.stat(); r=q.relative_to(p).as_posix(); m=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():dirs[r]=m
  else: files[r]=dict(m,bytes=s.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
def closure(p):
 inv=load(p/'INVENTORY.json');closed=load(p/'CLOSED.json');assert closed['passed']
 assert sha(p/'INVENTORY.json')==closed['inventorySha256']
 t=tree(p)
 for n in ['INVENTORY.json','CLOSED.json']: t['files'].pop(n)
 assert t['files']==inv['files'] and t['directories']==inv['directories'],str(p)
 return dict(path=str(p),payloadFiles=len(t['files']),directories=len(t['directories']),inventorySha256=sha(p/'INVENTORY.json'),closedSha256=sha(p/'CLOSED.json'))
p=ROOT/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/comparison-and-ui-r1'
u=ROOT/'evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/local-unit-validation-r1'
results=[closure(p),closure(u)]
before=load(p/'SOURCE_BEFORE_COPY.json');after=load(p/'SOURCE_AFTER_COPY.json')
assert after['passed'] and after['allOriginalsUnchanged'] and len(before)==26
for n,row in before.items():
 for location in [Path(row['source']),p/n]:
  t=tree(location)
  assert t['files']==row['inventory']['files'] and t['directories']==row['inventory']['directories'],str(location)
 assert after['sourceTrees'][n]==row['inventory']
bindings=load(p/'ROOT_COMPARISON_AND_UI_INPUT_PORTABLE_BINDINGS.json');count=0;differences=[]
for group,rows in bindings['inputs'].items():
 for original,row in rows.items():
  q=(p/row['archivedAt']).resolve(); pin=row['pin'];assert q.stat().st_size==pin['bytes'] and sha(q)==pin['sha256']
  origin=Path(original);matches=origin.exists() and origin.stat().st_size==pin['bytes'] and sha(origin)==pin['sha256']
  assert matches==row['originalPathCurrentlyMatchesRecordedPin']
  if not matches: differences.append(original);assert row['historicalUiBaselineMappedWithoutRewritingOriginalPath']
  count+=1
assert count==56 and differences==[str(ROOT/'evidence/index.json')]
refs=load(p/'IMMUTABLE_SHARED_ARCHIVE_REFERENCES.json')['sharedArchives'];assert len(refs)==5
for row in refs:
 for name,pin in row['receipts'].items():
  q=Path(row['path'])/name;assert q.stat().st_size==pin['bytes'] and sha(q)==pin['sha256']
assert (ROOT/'evidence/index.json').read_bytes()==(p/'event-fetch-ui-live-application-r1/index-after.json').read_bytes()
assert (ROOT/'scripts/export-event-fetch-ui.py').read_bytes()==(p/'event-fetch-ui-preparation-r1/export-event-fetch-ui.py').read_bytes()
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),reviewer='root; independent of archive authors',archives=results,full26OriginalAndCopiedScopeMirrorsVerified=True,all56PortableInputBodiesVerified=True,onlyChangedHistoricalInput=differences,allFiveSharedArchiveClosuresPinned=True,liveIndexAndShippedExporterMatchArchivedBodies=True,noJvmTestsSshOrBenchmarkExecuted=True)
with (OUT/'ROOT_REVIEW.json').open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(r))
