"""Closed round1 LOCAL archive only. No SSH/Java/Git, state extraction, deletion or launch."""
from pathlib import Path
import datetime,gzip,hashlib,io,json,os,re,shutil,stat,tarfile,zipfile
BASE=Path(__file__).resolve().parent.parent;OUT=Path(__file__).resolve().parent
DEST=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/retention-window-v3/cloud-abab-r1'
MAPPING={
 'common-collection-preparation':'window-cloud-collection-preparation-r1',
 'round-1/collection-run':'window-cloud-collection-round-1-r1',
 'round-1/closed-process-proof':'window-round-1-close-inspection-r1',
 'round-1/root-review-failed-r1':'window-root-round-1-review-r1',
 'round-1/root-review-passed-r2':'window-root-round-1-review-r2',
 'round-1/root-gate':'window-round-1-collection-root-gate-r1',
 'round-1/root-raw-comparison':'window-round1-raw-comparison-r1',
 'round-1/launch':'window-cloud-launch-round-1-r1',
 'round-1/launch-execution':'window-launch-execution-round-1-r1',
 'round-1/closed-source-review':'window-close-review-r1',
}
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
assert not DEST.exists();DEST.mkdir(parents=True,mode=0o700);(DEST/'round-1').mkdir(mode=0o700)
collection=BASE/'window-cloud-collection-round-1-r1';assert json.loads((collection/'SUCCESS.json').read_text())['passed'] is True
assert sha(collection/'finalized/LOCAL_COLLECTION_COMPLETE.json')=='30f5e1d726681722b959219cfb40de9c62c119c16b9783d7bf205c9b5bf9314f'
review=BASE/'window-root-round-1-review-r2/ROOT_REVIEW.json';assert sha(review)=='233189a682e3da0fa2d5df0c282900b2d5c4ab47385ca04a7d75c36ec3b8db2d';assert json.loads(review.read_text())['passed'] is True
assert sha(BASE/'window-round-1-collection-root-gate-r1/round-1-collection-gate.json')=='8315396ce0386e624933bc4e359e8a80813e0e5420c2afe12bb1a31ce4d328d4'
assert (BASE/'window-round-1-collection-root-gate-r1/upload').is_dir()
release=json.loads((collection/'collection/raw-files/job/release.json').read_text());outer=json.loads((collection/'collection/remote-inventory.stdout.json').read_text());omit={};omitted={}
for remote,row in release['artifacts'].items():
 name=Path(remote).name;rel='strict-native-audit/actual-runtime-artifacts/'+name;p=collection/rel
 assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];member='source/release/lib/'+name;assert all(outer['files'][member][k]==row[k] for k in ['bytes','sha256'])
 omit[rel]=row;omitted[rel]={'bytes':row['bytes'],'sha256':row['sha256'],'retainedIn':'round-1/collection-run/collection/full-closed-round.tar.gz!'+member,'omissionOnlyRemovesRedundantStandaloneCopy':True}
closure={}
for rel,source in MAPPING.items():closure[rel]=checked_copy(BASE/source,DEST/rel,set(omit) if rel=='round-1/collection-run' else ())
# Preserve the actual SSH helper source, never its key contents or process environment.
remote=BASE/'remote.py';assert sha(remote)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73';shutil.copy2(remote,DEST/'common-collection-preparation/remote-readonly-helper-source.py')
shutil.copy2(Path(__file__),DEST/'round-1/archive.py')
failed=json.loads((DEST/'round-1/root-review-failed-r1/FAILURE.json').read_text());assert failed['passed'] is False and failed['error']=='classification';assert sha(DEST/'round-1/root-review-failed-r1/executed-source.py')==failed['sourceSha256']
passed=json.loads((DEST/'round-1/root-review-passed-r2/ROOT_REVIEW.json').read_text());assert sha(DEST/'round-1/root-review-passed-r2/executed-source.py')==passed['scriptSha256']
save(DEST/'round-1/source-copy-closure.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'copiedRoots':closure,'omittedExactlyFourRedundantJarCopies':omitted,'standaloneSparseNativeTreesCopied':False,'rootReviewerFailedR1Retained':True,'rootReviewerPassedR2Retained':True,'reviewFailureWasToolCsvFieldMismatchNotBusinessFailure':True,'failedReviewStdoutStderrNotInvented':True,'noSourceRootChangedDuringCopy':True,'sourceOriginalsRetained':True,'noSshJavaGitPruneOrLaunch':True})
# Scan high-confidence known markers in copied text/binary source, logs, raw data and every loaded JAR class entry.
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
# All regular copied bytes; source ZIPs are additionally scanned uncompressed.
for p in sorted(DEST.rglob('*')):
 if not p.is_file():continue
 name=p.relative_to(DEST).as_posix()
 with p.open('rb') as f:scan_stream(name,f)
 if p.suffix=='.zip':
  with zipfile.ZipFile(p) as z:
   for m in z.infolist():
    if not m.is_dir():scan_stream(name+'!'+m.filename,z.open(m),expected_bytes=m.file_size)
 elif p.suffix=='.jar':scan_jar(name,p.read_bytes())
# Scan the full outer native/file payloads exactly once, including .rec/.dat and all JAR contents.
# The separately retained inner TAR's every native member is SHA/mode/owner bound to these same outer members by completed audits.
outer_path=DEST/'round-1/collection-run/collection/full-closed-round.tar.gz'
with tarfile.open(outer_path,'r|gz') as tar:
 for m in tar:
  if not m.isfile():continue
  row=outer['files'][m.name];payload=tar.extractfile(m);tar_members+=1
  if m.name.endswith('.jar'):
   data=payload.read();scan_stream('full-closed-round.tar.gz!'+m.name,io.BytesIO(data),row['sha256'],row['bytes']);scan_jar('full-closed-round.tar.gz!'+m.name,data)
  else:scan_stream('full-closed-round.tar.gz!'+m.name,payload,row['sha256'],row['bytes'])
# The config stage source TAR has its own explicit copied 23-source closure; inspect its members as well.
source_tar=DEST/'common-collection-preparation/round-1-config/inputs/stage-bundle.tar.gz'
with tarfile.open(source_tar,'r:gz') as tar:
 for m in tar:
  assert m.isfile();data=tar.extractfile(m).read();scan_stream('stage-bundle.tar.gz!'+m.name,io.BytesIO(data),expected_bytes=m.size)
  if m.name.endswith('.jar'):scan_jar('stage-bundle.tar.gz!'+m.name,data)
marker={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'patterns':sorted(PATTERNS),'scannedPayloadOccurrences':len(scanned),'totalBytesScanned':sum(x['bytes'] for x in scanned),'fullOuterRegularMembersScanned':tar_members,'allJarClassEntryOccurrencesScanned':jar_entries,'uniqueJarsScanned':len(jar_cache),'findings':hits,'unresolvedFindings':len(hits),'innerNativeMarkerCoverageViaExactOuterFileShaBindings':True,'scope':'Every copied regular file plus full outer uncompressed native payloads (including sparse .rec/.dat), source ZIP contents and complete unique JAR class contents. Inner native payloads are exactly SHA/mode/owner bound to scanned outer members. No private-key files, process environment or original PG payload collected; configured SSH key filepath strings are not key contents. Protected manifest contains hashes/metadata only. Known-marker review is finite, not a general secret-detection guarantee.'}
save(DEST/'round-1/known-credential-marker-review.json',marker);assert not hits,'Known markers require review; all output retained'
# Receipt links immutable source and raw proof without pretending one short pair is stable capacity.
raw=json.loads((DEST/'round-1/collection-run/strict-raw-audit/result.json').read_text());summary=[]
for a in raw['arms']:summary.append({'readWindow':a['readWindow'],'metrics':a['rawMetrics'],'classification':a['classification'],'actualOfferedHighWater':a['readPhaseBindings']['actualOfferedHighWater'],'maintenanceCycleWallNs':a['totalMaintenanceCycleNs']})
save(DEST/'round-1/ARCHIVE_SCOPE.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'round':1,'sourceCommit':release['sourceCommit'],'codeFingerprint':release['codeFingerprint'],'frozenReleaseSha256':'2a31b6f0d6b08c6863aef422a2bafa12d67a6ad11b651cbd2377b7b863943bed','collectionPreparationSha256':'b76477284d353fbec16b86003cea45f79355f1dea271174ad58439a0e8fbdf17','rootIndependentReviewSha256':sha(DEST/'round-1/root-review-passed-r2/ROOT_REVIEW.json'),'round1RootGateSha256':'8315396ce0386e624933bc4e359e8a80813e0e5420c2afe12bb1a31ce4d328d4','rootGateUploadClosed':True,'commonPreparationCopiedOnce':True,'round2EvidenceExcludedAndWillBeSeparateDirectory':True,'bothReviewAttemptsPreserved':True,'fullOuterAndInnerCompressedArtifactsRetained':True,'noStandaloneSparseNativeExtraction':True,'summary':summary,'scope':'One ordered finite same-host pair. Both finite windows end with outstanding replies; no sustained/stable capacity, 100M, exactnetwork latency or independenthost durability promotion.'})
final=census(DEST);save(DEST/'round-1/proof-inventory.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),**final,'copiedFileCountBeforeInventoryAndClosed':len(final['files']),'logicalCopiedBytesBeforeInventoryAndClosed':sum(v['bytes'] for v in final['files'].values()),'scope':'Only round-1 and once-copied common collection preparation; future round-2 is a separate append-only subtree.'})
closed={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'round':1,'proofInventorySha256':sha(DEST/'round-1/proof-inventory.json'),'sourceCopyClosureSha256':sha(DEST/'round-1/source-copy-closure.json'),'markerReviewSha256':sha(DEST/'round-1/known-credential-marker-review.json'),'scopeReceiptSha256':sha(DEST/'round-1/ARCHIVE_SCOPE.json'),'rootReviewR2Sha256':sha(DEST/'round-1/root-review-passed-r2/ROOT_REVIEW.json'),'rootReviewR1FailureRetained':True,'fullOuterArchiveSha256':sha(outer_path),'fullInnerArchiveSha256':sha(DEST/'round-1/collection-run/collection/pilot-after-clean-stop.tar.gz'),'fileCountBeforeInventoryAndClosed':len(final['files']),'logicalCopiedBytesBeforeInventoryAndClosed':sum(v['bytes'] for v in final['files'].values()),'redundantStandaloneJarCopiesOmitted':4,'fullBytePayloadRetained':True,'noOriginalsDeleted':True,'noSshJavaGitOrLaunchExecuted':True,'sustainedCapacityClaimed':False,'scope':'Local closed archival only; root owns independent review/commit/push. Existing round-1 files are frozen; later round2/gate updates must use new directories.'}
save(DEST/'round-1/CLOSED.json',closed);save(OUT/'SUCCESS.json',closed);print(json.dumps(closed))
