"""Preserve and independently verify the stopped first idle-startup failure. Local only."""
import pathlib,json,hashlib,tarfile,zipfile,io,shutil,stat
out=pathlib.Path(__file__).resolve().parent
src=pathlib.Path('runtime/cloud/cpu-20261024/latency-idle-v3-worktree/runtime/latency-idle-local-validation/native-r1')
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pins={}
for rel in ['registration.json','native-failure.json','run_native.py','closed-failure-originals/completion.json','closed-failure-originals/manifest.json','closed-failure-originals/failed-native-originals.tar.gz']:
 p=src/rel;target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists();shutil.copy2(p,target);assert h(target)==h(p);pins[rel]={'bytes':p.stat().st_size,'sha256':h(p)}
manifest=json.loads((out/'closed-failure-originals/manifest.json').read_text());expected={r['path']:r for r in manifest['entries']};assert len(expected)==58
archive=out/'closed-failure-originals/failed-native-originals.tar.gz';assert h(archive)=='c89f808630724f429f97b4f70a65127f8b3c5d4ecbc730bc75afc515931247db'
seen=set();scanned=0;jarEntries=0;hits=[];markers=[b'-----BEGIN PRIVATE KEY-----',b'-----BEGIN OPENSSH PRIVATE KEY-----',b'-----BEGIN RSA PRIVATE KEY-----',b'-----BEGIN EC PRIVATE KEY-----']
def scan(name,data):
 global scanned
 scanned+=len(data)
 for m in markers:
  if m in data:hits.append({'path':name,'marker':m.decode()})
with tarfile.open(archive,'r|gz') as stream:
 for m in stream:
  name=m.name.rstrip('/');r=expected[name];assert name not in seen;seen.add(name);assert (m.mode,m.uid,m.gid)==(r['mode'],r['uid'],r['gid'])
  if r['type']=='directory':assert m.isdir();continue
  assert m.isfile() and m.size==r['bytes'] and m.size<=32*1024**2;raw=stream.extractfile(m).read();assert hashlib.sha256(raw).hexdigest()==r['sha256'];scan(name,raw)
  if name.endswith('.jar'):
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for entry in z.infolist():
     if entry.is_dir():continue
     assert entry.file_size<=32*1024**2;scan(name+'!'+entry.filename,z.read(entry));jarEntries+=1
assert seen==set(expected) and not hits
completion=json.loads((out/'closed-failure-originals/completion.json').read_text());assert completion['allOwnedStopped'] and completion['parentExitCode']==1 and completion['nextArmNotLaunched']
report={'passed':True,'scope':'Complete byte/owner/mode/empty-dir archival of a FUNCTIONALLY FAILED local startup attempt, not a performance result. No SSH/Java/new workload or signal executed by this archive helper.','sourceCommit':completion['sourceCommit'],'nativePassed':False,'controlParentExitCode':1,'allOwnedStopped':True,'treatmentNotLaunched':True,'fullTarEntriesVerified':len(seen),'archiveSha256':h(archive),'sourceCopies':pins,'knownCredentialMarkerFindings':hits,'markerScanBytes':scanned,'jarEntriesScanned':jarEntries,'scriptSha256':h(pathlib.Path(__file__))}
(out/'ARCHIVE_REVIEW.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='sourceCopies'},indent=2))
