from pathlib import Path
import os,stat,hashlib,json,datetime,re,zipfile,io
S=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
patterns=[re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),re.compile(rb'github_pat_[A-Za-z0-9_]{50,}'),re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),re.compile(rb'rpa_[A-Za-z0-9]{30,}')]
scanned=0;hits=[]
def scan(data,name,depth=0):
 global scanned
 scanned+=1
 for i,pattern in enumerate(patterns):
  if pattern.search(data):hits.append({'path':name,'patternIndex':i})
 if depth<3 and (name.endswith('.zip')or name.endswith('.jar')):
  with zipfile.ZipFile(io.BytesIO(data))as z:
   for item in z.infolist():
    if item.is_dir():continue
    assert item.file_size<=64*1024*1024
    scan(z.read(item),name+'!/'+item.filename,depth+1)
for p in sorted(S.rglob('*')):
 assert not p.is_symlink()
 if p.is_file():scan(p.read_bytes(),str(p.relative_to(S)))
assert not hits,hits
save(S/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'scanObjectsIncludingNestedZipJarMembers':scanned,'hits':hits,'noCredentialBodiesReadFromExternalLocations':True,'scope':'format-marker check of this local synthetic candidate scope; not general secret discovery or cryptographic proof of absence'})
rows={};dirs=[]
for p in sorted(S.rglob('*')):
 st=p.lstat();r=str(p.relative_to(S));meta={'mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid}
 if stat.S_ISDIR(st.st_mode):dirs.append({'path':r,**meta,'empty':not any(p.iterdir())})
 elif stat.S_ISREG(st.st_mode):rows[r]={'bytes':st.st_size,'sha256':sha(p),**meta}
 else:raise RuntimeError('special member refused: '+r)
save(S/'INVENTORY.json',{'schemaVersion':1,'files':rows,'directories':dirs,'fileCount':len(rows),'directoryCount':len(dirs),'bytes':sum(r['bytes']for r in rows.values())})
save(S/'CLOSED.json',{'schemaVersion':1,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'LOCAL_READ_WINDOW32_CANDIDATE_PREPARATION','sourceCommit':'605eb43fcafd8fa0a6287304387c93c4d1bbddf6','inventorySha256':sha(S/'INVENTORY.json'),'localArtifactClosureSha256':sha(S/'LOCAL_ARTIFACT_CLOSURE.json'),'metadataObservationSha256':sha(S/'metadata-r1/observation.json'),'allActualAttemptsAndKnownFailuresRetained':True,'localLinuxExecuted':False,'cloudExecuted':False,'featurePushAttempted':False,'independentRootReviewRequired':True})
print(json.dumps({'files':len(rows),'directories':len(dirs),'bytes':sum(r['bytes']for r in rows.values()),'inventorySha256':sha(S/'INVENTORY.json'),'closedSha256':sha(S/'CLOSED.json'),'markerObjects':scanned}))
