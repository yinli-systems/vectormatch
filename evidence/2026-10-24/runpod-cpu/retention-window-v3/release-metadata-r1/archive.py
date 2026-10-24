from pathlib import Path
import datetime,hashlib,io,json,os,re,shutil,stat,tarfile,zipfile
BASE=Path(__file__).resolve().parent.parent
OUT=Path(__file__).resolve().parent
DEST=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/retention-window-v3/release-metadata-r1'
EXPECTED={'candidate':('window-cloud-abab-candidate-r1','candidate-inventory.json','0685e812d6469429c6350cc7cb0e36da2451212a37ec78afe41a7a29b8112acb'),
          'linux-metadata':('window-linux-metadata-r1','FINAL-INVENTORY.json','98874c0b3af8f6ecbcd283b2698b9bb7495e9a820e5590467b40d9f189e98b73')}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return h.hexdigest()
def save(p,value):
 with p.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def census(root):
 files={};dirs={'.':attrs(root)};excluded=[]
 for p in sorted(root.rglob('*')):
  rel=p.relative_to(root).as_posix();s=p.lstat()
  if '__pycache__' in p.parts:
   excluded.append(rel);continue
  assert not stat.S_ISLNK(s.st_mode),('Symlink refused',rel)
  if stat.S_ISDIR(s.st_mode):dirs[rel]=attrs(p)
  else:
   assert stat.S_ISREG(s.st_mode),('Non-regular refused',rel)
   files[rel]={**attrs(p),'bytes':s.st_size,'sha256':sha(p)}
 return {'files':files,'directories':dirs,'excludedCachePaths':excluded}
def attrs(p):
 s=p.lstat();return {'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
assert not DEST.exists();DEST.mkdir(parents=True,mode=0o700)
source_census={};binding={}
for label,(name,manifest,h) in EXPECTED.items():
 source=BASE/name;assert sha(source/manifest)==h;expected=json.loads((source/manifest).read_text());allowed=set(expected['files'])|{manifest}
 if label=='candidate':allowed.add('SUCCESS.json')
 before=census(source);assert set(before['files'])==allowed,('Explicit input allowlist mismatch',label)
 for rel,row in expected['files'].items():
  assert all(before['files'][rel][k]==row[k] for k in ('bytes','mode','sha256'))
 dest=DEST/label;dest.mkdir(mode=before['directories']['.']['mode'])
 for rel,row in before['directories'].items():
  target=dest if rel=='.' else dest/rel
  if rel!='.':target.mkdir(exist_ok=False)
  target.chmod(row['mode'])
 for rel in sorted(allowed):shutil.copy2(source/rel,dest/rel)
 after=census(dest);assert after['files']==before['files'] and after['directories']==before['directories']
 assert census(source)==before,'Frozen source changed while copying'
 source_census[label]=before;binding[label]={'source':str(source),'sourceManifest':manifest,'sourceManifestSha256':h,'sourceAndCopyFileShaSizeModeUidGidExact':True,'allDirectoryModesOwnersAndEmptyDirectoriesExact':True}
# Read nested metadata input TAR without extracting anything.
meta=DEST/'linux-metadata';config=json.loads((meta/'REGISTRATION.json').read_text())['inputConfig'];tarpath=meta/'metadata-inputs.tar.gz';assert sha(tarpath)==config['bundleSha256'];expected=config['rows'];nested={}
with tarfile.open(tarpath,'r:gz') as tar:
 for member in tar:
  assert member.isfile() and member.name in expected and member.name not in nested and '..' not in Path(member.name).parts and not member.name.startswith('/')
  row=expected[member.name];assert member.size==row['bytes'] and member.mode==row['mode'];raw=tar.extractfile(member).read();assert hashlib.sha256(raw).hexdigest()==row['sha256']
  input_row=source_census['linux-metadata']['files']['inputs/'+member.name];assert row['sha256']==input_row['sha256'] and member.uid==input_row['uid'] and member.gid==input_row['gid']
  nested[member.name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mode':member.mode,'uid':member.uid,'gid':member.gid}
assert set(nested)==set(expected) and len(nested)==6
# Verify all four full JARs, actual anchor-derived fingerprint and metadata parity, no Java execution.
candidate=DEST/'candidate';release=json.loads((candidate/'release/release.candidate.json').read_text());assert release['releaseReady'] is False
linux_raw=meta/'actual-linux-distribution-observation.json';linux=json.loads(linux_raw.read_text());local=json.loads((candidate/'actual-distribution-observation.json').read_text());fingerprint=hashlib.sha256()
assert linux['noDriverOrClusterStarted'] is True
for a,b in zip(local['actualSources'],linux['actualSources']):
 assert {k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'}
 p=candidate/'release/lib'/Path(a['path']).name;assert sha(p)==a['sha256'];fingerprint.update(a['type'].encode());fingerprint.update(p.read_bytes())
for k in local:
 if k!='actualSources':assert local[k]==linux[k]
assert fingerprint.hexdigest()==release['codeFingerprint']==linux['codeFingerprint']=='b148bbd416beca0c63ec10a2921a7709f1e82e8f3263604c930d5d901367117b'
assert release['derivedPlans']==linux['plans'];x=dict(linux['plans']['1']);y=dict(linux['plans']['8']);x.pop('requestedReadWindow');y.pop('requestedReadWindow');assert x==y
receipt=json.loads((meta/'remote-receipt.json').read_text());assert receipt['execution']['exitCode']==0 and receipt['execution']['metadataJvmExited'] is True and receipt['execution']['allInputsUnchanged'] is True
assert receipt['registration']['javaExecutableSha256']==receipt['execution']['javaExecutableSha256After']=='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155'
assert receipt['registration']['jdkReleaseSha256']==receipt['execution']['jdkReleaseSha256After']=='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898'
assert sha(candidate/'release/current-stopped-original-state.json')=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
assert sha(linux_raw)=='9836554b70e1aed2a70d8e09e70596ab73ebe558d3ae9bede9061235ce4e6057'
review={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'nestedInputTarSha256':sha(tarpath),'exactSixRegularMembersVerified':nested,'compiledHelperClassSha256':nested['classes/io/vectormatch/cluster/WindowReleaseObservationV3.class']['sha256'],'helperJavaSourceSha256':nested['WindowReleaseObservationV3.java']['sha256'],'codeFingerprintReconstructedFromActualFourAnchorJarBytes':fingerprint.hexdigest(),'allLinuxMetadataFieldsEqualLocalExceptJarPaths':True,'bothPlanOperationalEnvelopesExactExceptRequestedWindow':True,'linuxActualJdkExecutableBeforeAfterVerified':True,'linuxActualJdkReleaseBeforeAfterVerified':True,'sourceCommit':release['sourceCommit'],'proofTip':release['rootReview']['candidateProvenance']['proofTip'],'candidateSha256':sha(candidate/'release/release.candidate.json'),'releaseReady':False,'protectedManifestOnlyCopiedUnchanged':True,'firstAndOnlyActualSshMetadataSucceeded':True,'noFailedSshAttemptInvented':True,'pureGuardLogsPreserved':['guards.stdout','guards.stderr','guards-final.stdout','guards-final.stderr','guards-final-receipt.json'],'priorPreparationGuardAttemptsAlreadyArchivedAt':'evidence/2026-10-24/runpod-cpu/retention-window-v3/local-preparation-r1','scope':'Archive verification only: no SSH/Java/SQL/controller/driver/business workload executed. CPU functionality/performance unproved.'};save(DEST/'nested-input-and-metadata-review.json',review)
# High-confidence known credential marker scan of every copied file and every JAR entry (including class bytes).
patterns={
 'private-key-header':re.compile(b'-----BEGIN '+b'(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
 'github-classic-token':re.compile(b'ghp_'+b'[A-Za-z0-9]{36}'),
 'github-fine-token':re.compile(b'github_pat_'+b'[A-Za-z0-9_]{40,}'),
 'aws-access-key-id':re.compile(b'(?:AKIA|ASIA)'+b'[A-Z0-9]{16}'),
 'openai-project-token':re.compile(b'sk'+b'-proj-[A-Za-z0-9_-]{30,}'),
 'google-api-key':re.compile(b'AIza'+b'[A-Za-z0-9_-]{35}'),
 'slack-token':re.compile(b'xox[baprs]'+b'-[A-Za-z0-9-]{20,}'),
}
hits=[];scanned=[];jar_entries=0;unique_payloads=set()
def scan(name,raw):
 global jar_entries
 digest=hashlib.sha256(raw).hexdigest();scanned.append({'path':name,'bytes':len(raw),'sha256':digest});unique_payloads.add(digest)
 for label,pattern in patterns.items():
  for match in pattern.finditer(raw):hits.append({'path':name,'marker':label,'offset':match.start(),'matchSha256':hashlib.sha256(match.group()).hexdigest()})
for label in EXPECTED:
 for p in sorted((DEST/label).rglob('*')):
  if not p.is_file():continue
  raw=p.read_bytes();name=p.relative_to(DEST).as_posix();scan(name,raw)
  if p.suffix=='.jar':
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    assert len(z.namelist())==len(set(z.namelist()))
    for entry in z.infolist():
     if not entry.is_dir():scan(name+'!'+entry.filename,z.read(entry));jar_entries+=1
# TAR inputs duplicate the six individually scanned input bytes; verify and scan their contents explicitly.
with tarfile.open(tarpath,'r:gz') as tar:
 for member in tar:
  raw=tar.extractfile(member).read();scan('linux-metadata/metadata-inputs.tar.gz!'+member.name,raw)
  if member.name.endswith('.jar'):
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for entry in z.infolist():
     if not entry.is_dir():scan('linux-metadata/metadata-inputs.tar.gz!'+member.name+'!'+entry.filename,z.read(entry));jar_entries+=1
marker={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'patterns':sorted(patterns),'copiedFileCount':sum(len(v['files']) for v in source_census.values()),'jarEntryOccurrencesScanned':jar_entries,'uniqueScannedPayloads':len(unique_payloads),'scannedPayloads':len(scanned),'hits':hits,'unresolvedMarkerFindings':len(hits),'scope':'Known high-confidence private-key/API-token marker review of every copied file plus all JAR entry/class contents, helper source/class, stdout/stderr, inline staging source, nested six-member input TAR. No process environments, private-key files or PG payloads were collected; SSH key filepath references are not private-key contents. Protected original-state manifest contains names/hashes/metadata only. This finite marker review is not a general secret-detection guarantee.'};save(DEST/'known-credential-marker-review.json',marker);assert not hits,'Known marker findings require review; copies retained'
# Preserve the actual archiver source and full source/copy owner/mode/empty-dir census.
shutil.copy2(Path(__file__),DEST/'archive.py');save(DEST/'source-copy-closure.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceBindings':binding,'sourceAndCopyInventories':source_census,'sourceInputsUnchangedAfterVerification':all(census(BASE/EXPECTED[label][0])==before for label,before in source_census.items()),'originalsRetained':True,'noGitJavaSshOrSourceMutation':True})
final=census(DEST);save(DEST/'proof-inventory.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),**final,'fileCount':len(final['files']),'logicalBytes':sum(row['bytes'] for row in final['files'].values()),'allCopiedInputsVerified':True,'nestedTarSixExactMembers':True,'knownCredentialMarkerReviewNoUnresolvedFindings':True,'releaseReady':False})
closed={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'destination':str(DEST),'proofInventorySha256':sha(DEST/'proof-inventory.json'),'sourceCopyClosureSha256':sha(DEST/'source-copy-closure.json'),'markerReviewSha256':sha(DEST/'known-credential-marker-review.json'),'nestedReviewSha256':sha(DEST/'nested-input-and-metadata-review.json'),'candidateSha256':sha(DEST/'candidate/release/release.candidate.json'),'actualLinuxObservationSha256':sha(linux_raw),'fileCountBeforeInventoryAndClosure':len(final['files']),'logicalBytesBeforeInventoryAndClosure':sum(row['bytes'] for row in final['files'].values()),'originalsRetained':True,'releaseReady':False,'cpuFunctionalOrPerformanceProven':False,'scope':'Closed local archival task only; no additional SSH/Java/Git or source mutation. Root owns review/commit/push.'};save(DEST/'CLOSED.json',closed);save(OUT/'SUCCESS.json',closed);print(json.dumps(closed))
