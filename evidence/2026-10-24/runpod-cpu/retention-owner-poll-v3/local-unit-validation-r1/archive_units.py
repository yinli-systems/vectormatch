"""Local exact375-file unit proof +2 peer files; metadata is separate and untouched."""
from pathlib import Path
import datetime,hashlib,importlib.util,io,json,shutil,zipfile
HERE=Path(__file__).resolve().parent
HELPERS=HERE/'archive_helpers.py'
assert hashlib.sha256(HELPERS.read_bytes()).hexdigest()=='fc3798e12d9e9e37581902b56fc7a4f437e0d76252ee1498ef589b5bd24358a6'
spec=importlib.util.spec_from_file_location('unit_archive_closed_utilities',HELPERS);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
# Include nested source-ZIP JAR entries as well as direct distribution JAR/class bytes.
def scan_nested_zip(stream,label,depth=0):
 h.require(depth<=8,'Bounded nested ZIP depth')
 with zipfile.ZipFile(stream)as archive:
  names=set()
  for info in archive.infolist():
   h.safe_member(info.filename);h.require(info.filename not in names,'Duplicate nested ZIP member');names.add(info.filename)
   if info.is_dir():continue
   h.require(info.file_size<=64*1024**2,'Bounded nested ZIP member')
   with archive.open(info)as f:
    if info.filename.endswith(('.jar','.zip')):scan_nested_zip(io.BytesIO(f.read()),label+'!'+info.filename,depth+1)
    else:h.scan_stream(f,label+'!'+info.filename)
h.scan_zip=scan_nested_zip
plan=json.loads((HERE/'COPY_PLAN.json').read_text());target=Path(plan['target'])
h.require(not target.exists(),'Never overwrite closed or partial archive')
h.require(shutil.disk_usage(target.parent.parent).free>=1024**3+32*1024**2,'Local1GiB floor')
source=Path(plan['inventorySource']);h.require(h.sha(source)==plan['inventorySourceSha256'],'Exact375-file input inventory changed')
expected=plan['known375FileInventory'];before={};roots={}
for key,row in expected['roots'].items():
 root=Path(row['originalRoot']);actual=h.snapshot(root)
 h.require(actual['files']==row['files']and actual['directories']==row['directories'],'Closed proof original metadata changed: '+key)
 roots[key]=root;before[key]=actual
peer=Path(plan['additionalPeerRoot']);before['peer-source-review']=h.snapshot(peer);roots['peer-source-review']=peer
h.require(before['peer-source-review']['files']==plan['additionalPeerFiles'],'Exact peer proof changed')
singles=expected['singleFiles']
for name,row in singles.items():h.require(h.row(Path(row['originalPath']))=={k:row[k]for k in ('bytes','sha256','mode','uid','gid')},'Closed singleton changed')
target.mkdir(parents=True,mode=0o755)
h.save(target/'REGISTRATION.json',{'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceCommit':plan['sourceFeatureCommit'],'copyPlanSha256':h.sha(HERE/'COPY_PLAN.json'),'sourceRoots':{key:str(value)for key,value in roots.items()},'metadataObservationIncluded':False,'noRemoteTestJavaGitActions':True,'originalsRetained':True})
for key,root in roots.items():h.copy_tree(root,target/key,before[key])
runner=target/'unit-runner';runner.mkdir()
for name,row in singles.items():
 p=runner/name;shutil.copy2(row['originalPath'],p);h.require(h.row(p)=={k:row[k]for k in ('bytes','sha256','mode','uid','gid')},'Copied singleton differs')
for original,name in [(source,'UNIT_PROOF_ARCHIVE_INPUTS.json'),(HERE/'COPY_PLAN.json','COPY_PLAN.json'),(Path(__file__),'archive_units.py'),(HELPERS,'archive_helpers.py')]:shutil.copy2(original,target/name)
after={key:h.snapshot(root)for key,root in roots.items()};h.require(before==after,'Original closed proof changed during copy')
for name,row in singles.items():h.require(h.row(Path(row['originalPath']))=={k:row[k]for k in ('bytes','sha256','mode','uid','gid')},'Original singleton changed during copy')
h.save(target/'COPY_VERIFICATION.json',{'passed':True,'sourceTreesBefore':before,'sourceTreesAfter':after,'allOriginalShaModeOwnerAndEmptyDirectoryClosureUnchanged':True,'allCopiedOriginalRowsMatched':True,'knownInventoryFiles':375,'additionalPeerFiles':2,'noSparseNativeTreeIncluded':True})
for p in sorted(target.rglob('*')):
 if p.is_file():h.scan_file(p,str(p.relative_to(target)))
h.save(target/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not h.HITS,'scope':'Known marker classes only across all copied regular bytes/source ZIP contents and all compiled JAR/class entries; not a universal secret absence guarantee','markerClasses':sorted(h.MARKERS),'hits':h.HITS,'scannedObjects':len(h.SCANNED),'scannedBytes':sum(r['bytes']for r in h.SCANNED),'privateKeysEnvironmentOrOriginalPgPayloadIntentionallyIncluded':False,'objects':h.SCANNED})
h.require(not h.HITS,'Known credential marker found; preserve archive for review')
(target/'README.md').open('x').write('''# Owner-poll candidate local unit validation\n\nCandidate977197616ade0283174f2ea6ddfaa700547f6d15 has one actual forced scoped run, units-r2:78tests,0failures/errors/skips,11selected classes,11actionable Gradle tasks executed. Includes new8owner-poll tests and legacyV2 compatibility as one JUnit method. Source159inputs and registered JDK remained unchanged. No native pilot class, cloud or performance workload was selected.\n\nAll375files from the closed unit-proof input inventory plus2peer review files are copied with original SHA/bytes/mode/UID/GID and complete directory/empty-directory closure. Full source ZIP159inputs, initial8source review snapshot, R2fence-only fix, XML, actual classpaths,334compiled/XML/distribution artifacts and4JARs are retained. units-r1 was prepared only; it was not a failed or executed test run. The R1peer finding was static source review and was fixed before the only actual unit execution.\n\nInstalled-JAR fingerprint23586ccc…724b884 in units/DISTRIBUTION_MATERIALS is explicitly source-derived; actual metadata JVM attestation and native owner-runtime evidence are separate. They are not included in this unit archive.\n\nOriginal absolute paths in copied receipts remain unchanged. REGISTRATION/COPY_PLAN map those roots to named archive subtrees. Inventory excludes only itself and CLOSED.json; closure binds its exact SHA. Known credential marker review covers copied source/ZIP/JAR/class bytes with explicit bounded marker classes, not a universal no-secrets claim. No original source, runtime proof, PG or sparse native tree was modified, deleted or extracted.\n''')
rows=h.snapshot(target)
h.save(target/'INVENTORY.json',{'scope':'Only this local-unit-validation-r1 subtree','files':rows['files'],'directories':rows['directories'],'excludedSelfAndClosure':['INVENTORY.json','CLOSED.json'],'filesCount':len(rows['files']),'bytes':sum(r['bytes']for r in rows['files'].values())})
for name,pin in rows['files'].items():h.require(h.row(target/name)==pin,'Final payload changed')
h.save(target/'CLOSED.json',{'passed':True,'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventorySha256':h.sha(target/'INVENTORY.json'),'files':len(rows['files']),'directories':len(rows['directories']),'bytes':sum(r['bytes']for r in rows['files'].values()),'allOriginalAndCopiedShaModeOwnerDirectoryClosureVerified':True,'knownCredentialMarkerReviewPassed':True,'actualTests':78,'failures':0,'skipped':0,'metadataObservationIncluded':False,'noRepeatedTestJavaCloudGitOrSparseExtraction':True,'originalsRetained':True,'closureExcludes':['INVENTORY.json','CLOSED.json']})
print(json.dumps({'passed':True,'target':str(target),'closedSha256':h.sha(target/'CLOSED.json'),'inventorySha256':h.sha(target/'INVENTORY.json'),'files':len(rows['files']),'bytes':sum(r['bytes']for r in rows['files'].values()),'knownMarkerObjects':len(h.SCANNED)}))
