"""Closed round2 LOCAL archival only; scoped to a new round2 subtree."""
from pathlib import Path
import datetime,hashlib,io,json,re,shutil,stat,tarfile,zipfile
BASE=Path(__file__).resolve().parent.parent;OUT=Path(__file__).resolve().parent
DEST=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/retention-window-v3/cloud-abab-r1/round-2'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def attrs(p):
 s=p.lstat();return {'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}

def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

def census(root,omit=()):
 files={};dirs={'.':attrs(root)};excluded=[]
 for p in sorted(root.rglob('*')):
  rel=p.relative_to(root).as_posix();s=p.lstat()
  if '__pycache__' in p.parts:excluded.append({'path':rel,'reason':'Python derived cache, not an executed source/input'});continue
  assert not stat.S_ISLNK(s.st_mode),('Link refused',str(p))
  if rel in omit:excluded.append({'path':rel,'reason':'Exact standalone audit JAR duplicate retained in full outer source/release/lib member'});continue
  if stat.S_ISDIR(s.st_mode):dirs[rel]=attrs(p)
  else:
   assert stat.S_ISREG(s.st_mode) and s.st_size<512*1024**2
   assert p.name not in ['.env','id_rsa','id_ed25519'] and '.ssh' not in p.parts,('Key/env file refused',str(p))
   files[rel]={**attrs(p),'bytes':s.st_size,'sha256':sha(p)}
 return {'files':files,'directories':dirs,'excluded':excluded}

def checked_copy(source,target,omit=()):
 before=census(source,omit);target.mkdir(mode=before['directories']['.']['mode'])
 for rel,row in before['directories'].items():
  p=target if rel=='.' else target/rel
  if rel!='.':p.mkdir()
  p.chmod(row['mode'])
 for rel in before['files']:shutil.copy2(source/rel,target/rel)
 after=census(target);assert before['files']==after['files'] and before['directories']==after['directories'];assert census(source,omit)==before
 return {'sourceRoot':str(source),'sourceAndDestinationShaSizeModeUidGidExact':True,'allDirectoryOwnersModesAndEmptyDirectoriesExact':True,'sourceSnapshot':before}

def scan_stream(name,stream,expected_sha=None,expected_bytes=None):
 h=hashlib.sha256();count=0;tail=b''
 for chunk in iter(lambda:stream.read(1024*1024),b''):
  h.update(chunk);data=tail+chunk
  for label,pattern in PATTERNS.items():
   for match in pattern.finditer(data):
    if count and match.end()<=len(tail):continue
    hits.append({'path':name,'marker':label,'offset':count-len(tail)+match.start(),'matchSha256':hashlib.sha256(match.group()).hexdigest()})
  count+=len(chunk);tail=data[-4096:]
 digest=h.hexdigest()
 if expected_sha:assert digest==expected_sha
 if expected_bytes is not None:assert count==expected_bytes
 scanned.append({'path':name,'bytes':count,'sha256':digest});return digest

def scan_jar(name,data):
 global jar_entries
 digest=hashlib.sha256(data).hexdigest()
 if digest in jar_cache:return
 jar_cache.add(digest)
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  assert len(z.namelist())==len(set(z.namelist()))
  for m in z.infolist():
   if not m.is_dir():scan_stream(name+'!'+m.filename,z.open(m),expected_bytes=m.file_size);jar_entries+=1
MAPPING={'collection-run':'window-cloud-collection-round-2-r1','round-2-config':'window-cloud-collection-round-2-config-r1','closed-process-proof':'window-round-2-close-inspection-r1','root-review-passed-r1':'window-root-round-2-review-r1','launch':'window-cloud-launch-round-2-r1','launch-execution':'window-launch-execution-round-2-r1'}
assert not DEST.exists();DEST.mkdir(parents=True,mode=0o700)
collection=BASE/'window-cloud-collection-round-2-r1';assert json.loads((collection/'SUCCESS.json').read_text())['passed'] is True
assert sha(collection/'finalized/LOCAL_COLLECTION_COMPLETE.json')=='4245ce244bc517336f9111dfd80b2816fa7eda020b9fff02add8ca377b7d582b'
assert sha(BASE/'window-root-round-2-review-r1/ROOT_REVIEW.json')=='cf4d769164b94d25d214ab1e3ba4b73880a43b9c731976f12362c7381b071112'
assert sha(BASE/'window-round-2-close-inspection-r1/ROOT_CONTROLLER_CLOSED.json')=='a41ca48e9edc738695389f7412dc5905c67a1d80689fcc268a5f7030e76fc6e9'
release=json.loads((collection/'collection/raw-files/job/release.json').read_text());outer=json.loads((collection/'collection/remote-inventory.stdout.json').read_text());omitted={}
for remote,row in release['artifacts'].items():
 name=Path(remote).name;rel='strict-native-audit/actual-runtime-artifacts/'+name;p=collection/rel;member='source/release/lib/'+name
 assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'] and all(outer['files'][member][k]==row[k] for k in ['bytes','sha256'])
 omitted[rel]={'bytes':row['bytes'],'sha256':row['sha256'],'retainedIn':'collection-run/collection/full-closed-round.tar.gz!'+member,'reason':'Only redundant standalone audit extraction omitted; complete payload is retained in full outer archive'}
closure={}
for rel,src in MAPPING.items():closure[rel]=checked_copy(BASE/src,DEST/rel,set(omitted) if rel=='collection-run' else ())
(DEST/'collection-tool-execution').mkdir(mode=0o700)
for name in ['actual-round-2-collection.stdout','actual-round-2-collection.stderr','build-round-2.stdout','build-round-2.stderr']:
 p=BASE/'window-cloud-collection-preparation-r1'/name;shutil.copy2(p,DEST/'collection-tool-execution'/name);assert sha(p)==sha(DEST/'collection-tool-execution'/name)
shutil.copy2(Path(__file__),DEST/'archive.py')
save(DEST/'excluded-source-files.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'omittedExactlyFourRedundantStandaloneJars':omitted,'derivedCacheExclusions':{key:row['sourceSnapshot']['excluded'] for key,row in closure.items()},'commonPreparationCopiedAgain':False,'commonPreparationReference':'../common-collection-preparation','fullOuterAndInnerNativeArchivesRetained':True,'rootReadmeAndComparisonSiblingsNotReadOrInventoried':True})
save(DEST/'source-copy-closure.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'copiedRoots':closure,'allOriginalSourceInputsUnchangedDuringCopy':True,'allCopyFileShaSizeModeUidGidExact':True,'allDirectoryModesOwnersAndEmptyDirectoriesExact':True,'sparseNativePayloadsExtracted':False,'sourceOriginalsRetained':True,'noSshJavaGitPruneOrLaunch':True})
PATTERNS={
 'private-key-header':re.compile(b'-----BEGIN '+b'(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
 'github-classic-token':re.compile(b'ghp_'+b'[A-Za-z0-9]{36}'),
 'github-fine-token':re.compile(b'github_pat_'+b'[A-Za-z0-9_]{40,}'),
 'aws-access-key-id':re.compile(b'(?:AKIA|ASIA)'+b'[A-Z0-9]{16}'),
 'openai-project-token':re.compile(b'sk'+b'-proj-[A-Za-z0-9_-]{30,}'),
 'google-api-key':re.compile(b'AIza'+b'[A-Za-z0-9_-]{35}'),
 'slack-token':re.compile(b'xox[baprs]'+b'-[A-Za-z0-9-]{20,}'),
}
hits=[];scanned=[];jar_entries=0;tar_members=0;jar_cache=set()
for p in sorted(DEST.rglob('*')):
 if not p.is_file():continue
 name=p.relative_to(DEST).as_posix()
 with p.open('rb') as f:scan_stream(name,f)
 if p.suffix=='.zip':
  with zipfile.ZipFile(p) as z:
   for m in z.infolist():
    if not m.is_dir():scan_stream(name+'!'+m.filename,z.open(m),expected_bytes=m.file_size)
 elif p.suffix=='.jar':scan_jar(name,p.read_bytes())
outer_path=DEST/'collection-run/collection/full-closed-round.tar.gz'
with tarfile.open(outer_path,'r|gz') as tar:
 for m in tar:
  if not m.isfile():continue
  row=outer['files'][m.name];payload=tar.extractfile(m);tar_members+=1
  if m.name.endswith('.jar'):
   data=payload.read();scan_stream('full-closed-round.tar.gz!'+m.name,io.BytesIO(data),row['sha256'],row['bytes']);scan_jar('full-closed-round.tar.gz!'+m.name,data)
  else:scan_stream('full-closed-round.tar.gz!'+m.name,payload,row['sha256'],row['bytes'])
with tarfile.open(DEST/'round-2-config/inputs/stage-bundle.tar.gz','r:gz') as tar:
 for m in tar:
  assert m.isfile();data=tar.extractfile(m).read();scan_stream('stage-bundle.tar.gz!'+m.name,io.BytesIO(data),expected_bytes=m.size)
  if m.name.endswith('.jar'):scan_jar('stage-bundle.tar.gz!'+m.name,data)
save(DEST/'known-credential-marker-review.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'patterns':sorted(PATTERNS),'scannedPayloadOccurrences':len(scanned),'totalBytesScanned':sum(row['bytes'] for row in scanned),'fullOuterRegularMembersScanned':tar_members,'allUniqueJarClassEntriesScanned':jar_entries,'uniqueJarsScanned':len(jar_cache),'findings':hits,'unresolvedFindings':len(hits),'innerNativePayloadsCoveredByExactOuterMemberShaBindings':True,'scope':'All copied regular bytes, full outer uncompressed native payloads including sparse .rec/.dat, source ZIPs and unique JAR class contents scanned. Inner payloads exactly bind those outer files. No private-key files, process environment or original PG payloads collected; known marker review is finite, not a general secret-detection guarantee.'});assert not hits,'Known marker findings require review; all copies retained'
raw=json.loads((DEST/'collection-run/strict-raw-audit/result.json').read_text());rootreview=json.loads((DEST/'root-review-passed-r1/ROOT_REVIEW.json').read_text());assert rootreview['passed'] is True and sha(DEST/'root-review-passed-r1/executed-source.py')==rootreview['scriptSha256']
save(DEST/'ARCHIVE_SCOPE.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'round':2,'sourceCommit':release['sourceCommit'],'codeFingerprint':release['codeFingerprint'],'releaseSha256':'2a31b6f0d6b08c6863aef422a2bafa12d67a6ad11b651cbd2377b7b863943bed','collectionPreparationSha256':'b76477284d353fbec16b86003cea45f79355f1dea271174ad58439a0e8fbdf17','round2ConfigSha256':'53d8328a2d9ae975a96008168558f1bca5ad4336c538d01e309a9605a253f331','priorRound1GateSha256':'8315396ce0386e624933bc4e359e8a80813e0e5420c2afe12bb1a31ce4d328d4','rootIndependentReviewSha256':sha(DEST/'root-review-passed-r1/ROOT_REVIEW.json'),'onlyRound2SubtreeInventoried':True,'commonPreparationAndRound1Unchanged':True,'rootReadmeComparisonExcludedFromInventory':True,'summary':[{'readWindow':a['readWindow'],'metrics':a['rawMetrics'],'classification':a['classification'],'actualOfferedHighWater':a['readPhaseBindings']['actualOfferedHighWater'],'maintenanceCycleWallNs':a['totalMaintenanceCycleNs']} for a in raw['arms']],'scope':'Second ordered finite same-host pair. Both windows end with outstanding replies; no sustained/stable capacity,100M or independenthost durability promotion.'})
final=census(DEST);save(DEST/'proof-inventory.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),**final,'scope':'Only this new round-2 subtree, excluding the inventory and CLOSED receipts themselves. No parent README/comparison/common/round1 sibling inventory.','fileCountBeforeInventoryAndClosed':len(final['files']),'logicalCopiedBytesBeforeInventoryAndClosed':sum(row['bytes'] for row in final['files'].values())})
closed={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'round':2,'proofInventorySha256':sha(DEST/'proof-inventory.json'),'excludedInventorySha256':sha(DEST/'excluded-source-files.json'),'sourceCopyClosureSha256':sha(DEST/'source-copy-closure.json'),'markerReviewSha256':sha(DEST/'known-credential-marker-review.json'),'scopeReceiptSha256':sha(DEST/'ARCHIVE_SCOPE.json'),'rootIndependentReviewSha256':sha(DEST/'root-review-passed-r1/ROOT_REVIEW.json'),'fullOuterArchiveSha256':sha(outer_path),'fullInnerArchiveSha256':sha(DEST/'collection-run/collection/pilot-after-clean-stop.tar.gz'),'fileCountBeforeInventoryAndClosed':len(final['files']),'logicalCopiedBytesBeforeInventoryAndClosed':sum(row['bytes'] for row in final['files'].values()),'onlyNewRound2SubtreeArchived':True,'parentRootReadmeAndComparisonExcluded':True,'commonPreparationAndRound1NotMutated':True,'redundantStandaloneJarsOmitted':4,'allBytePayloadRetained':True,'noOriginalsDeleted':True,'noSshJavaGitOrLaunchExecuted':True,'sustainedCapacityClaimed':False}
save(DEST/'CLOSED.json',closed);save(OUT/'SUCCESS.json',closed);print(json.dumps(closed))
