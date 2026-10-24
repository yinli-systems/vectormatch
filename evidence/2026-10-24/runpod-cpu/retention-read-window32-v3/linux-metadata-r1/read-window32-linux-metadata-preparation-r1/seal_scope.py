from pathlib import Path
import json,hashlib,stat,re,zipfile,tarfile,io,datetime
P=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,v):
 with(P/name).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
# Faithful tool-output observation recorded after the prepare-only call; not a preregistered execution log.
save('PREPARATION_TOOL_OBSERVATION.json',{'recordedAfterInvocation':True,'argv':['python3','-B',str(P/'stage_metadata.py'),'--prepare-only','--local-observation-directory',str(P.parent/'read-window32-local-preparation-r1'),'--local-observation-sha256','212a58a80575f82cb165e09c87040709d8c471d86ca8a0fa30e80f5ac351fa7c'],'observedExitCode':0,'observedStdoutJson':{'prepared':True,'configSha256':'1dae0b808015de83f65d3b046940f41c9fa3f6ee17e5f749f952ae65b3f0369b'},'sshOrMetadataMainExecutedByThisCall':False})
patterns=[re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),re.compile(rb'github_pat_[A-Za-z0-9_]{50,}'),re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'rpa_[A-Za-z0-9]{30,}')]
scanned=0;hits=[]
def scan(data,name,depth=0):
 global scanned
 scanned+=1
 for i,pattern in enumerate(patterns):
  if pattern.search(data):hits.append({'path':name,'patternIndex':i})
 if depth<3 and (name.endswith('.zip')or name.endswith('.jar')):
  with zipfile.ZipFile(io.BytesIO(data))as z:
   for row in z.infolist():
    if row.is_dir():continue
    assert row.file_size<=64*1024*1024;scan(z.read(row),name+'!/'+row.filename,depth+1)
 elif depth<3 and name.endswith('.tar.gz'):
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz')as t:
   for row in t:
    assert row.isfile()and row.size<=64*1024*1024;scan(t.extractfile(row).read(),name+'!/'+row.name,depth+1)
for p in sorted(P.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():scan(p.read_bytes(),str(p.relative_to(P)))
assert not hits,hits
save('KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'scanObjectsIncludingNestedZipJarTarMembers':scanned,'hits':hits,'scope':'known format marker check of this synthetic local preparation and copied provenance only; no external credentials accessed'})
files={};dirs=[]
for p in sorted(P.rglob('*')):
 st=p.lstat();r=str(p.relative_to(P));meta={'mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid}
 if stat.S_ISDIR(st.st_mode):dirs.append({'path':r,'empty':not any(p.iterdir()),**meta})
 elif stat.S_ISREG(st.st_mode):files[r]={'bytes':st.st_size,'sha256':sha(p),**meta}
 else:raise RuntimeError('special object refused')
save('INVENTORY.json',{'schemaVersion':1,'files':files,'directories':dirs,'fileCount':len(files),'directoryCount':len(dirs),'bytes':sum(row['bytes']for row in files.values())})
save('CLOSED.json',{'schemaVersion':1,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'SOURCE_ONLY_READ_WINDOW32_LINUX_METADATA_PREPARATION','sourceCommit':'605eb43fcafd8fa0a6287304387c93c4d1bbddf6','inventorySha256':sha(P/'INVENTORY.json'),'sourceFrozenSha256':sha(P/'SOURCE_FROZEN.json'),'metadataConfigSha256':sha(P/'metadata-config.json'),'purePythonGuardsPassed':17,'compilerJvmExecuted':True,'metadataJvmExecuted':False,'sshExecuted':False,'linuxExecuted':False,'cloudExecuted':False,'actualLinuxMetadataPending':True,'actualLinuxObservationGenerated':False,'benchmarkReleaseReady':False,'newResourcesCreated':False,'independentRootPreexecutionReviewRequired':True})
print(json.dumps({'files':len(files),'dirs':len(dirs),'bytes':sum(row['bytes']for row in files.values()),'inventorySha256':sha(P/'INVENTORY.json'),'closedSha256':sha(P/'CLOSED.json'),'sourceFrozenSha256':sha(P/'SOURCE_FROZEN.json'),'scanObjects':scanned}))
