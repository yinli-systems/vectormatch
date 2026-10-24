#!/usr/bin/env python3
"""LOCAL ONLY exact closed proof copy; no SSH, execution, sparse extraction or source mutation."""
import datetime,hashlib,io,json,os
from pathlib import Path,PurePosixPath
import re,shutil,stat,tarfile,zipfile

WORKSPACE=Path('/Users/kevin/Documents/ChatGPT/App 2')
BASE=WORKSPACE/'runtime/cloud/cpu-20261024'
TARGET=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-1-r1'
HERE=Path(__file__).resolve().parent
TREES={
 'collector-preparation-r1':BASE/'cpu-owner-poll-collection-preparation-r1',
 'collector-preparation-r2':BASE/'cpu-owner-poll-collection-preparation-r2',
 'cloud-controller-preparation':BASE/'cpu-owner-poll-cloud-preparation-r1',
 'collector-peer-review':BASE/'cpu-owner-poll-collector-peer-review-r1',
 'stage-preparation-r1':BASE/'cpu-owner-poll-stage-preparation-r1',
 'stage-preparation-r2':BASE/'cpu-owner-poll-stage-preparation-r2',
 'close-preparation':BASE/'cpu-owner-poll-close-preparation-r1',
 'actual-collection':BASE/'cpu-owner-poll-arm-1-collection-r1',
 'collection-execution':BASE/'owner-cloud-arm-1-collection-execution-r1',
 'actual-config':BASE/'owner-cloud-arm-1-config-r1',
 'config-execution':BASE/'owner-cloud-arm-1-config-execution-r1',
 'root-review':BASE/'owner-cloud-root-review-arm-1-r1',
 'root-review-preparation':BASE/'owner-cloud-root-review-preparation-r1',
 'actual-root-release-freeze':BASE/'owner-cloud-root-release-freeze-r1',
 'root-release-preparation':BASE/'owner-cloud-root-release-preparation-r1',
 'actual-staging':BASE/'cpu-owner-poll-cloud-staging-r1',
 'stage-execution':BASE/'owner-cloud-stage-execution-r1',
 'close-inspection-r1':BASE/'owner-cloud-arm-1-close-inspection-r1',
 'close-inspection-r2':BASE/'owner-cloud-arm-1-close-inspection-r2',
 'close-execution-preparation':BASE/'owner-cloud-close-execution-preparation-r1',
 'actual-launch':BASE/'owner-cloud-arm-1-launch-r1',
 'launch-execution':BASE/'owner-cloud-arm-1-launch-execution-r1',
 'comparison-preparation':BASE/'owner-poll-comparison-preparation-r1',
 'comparison-a1':BASE/'owner-poll-comparison-a1-r1',
 'next-arm-execution-preparation':BASE/'owner-cloud-next-arm-execution-preparation-r1',
 'collection-root-execution-preparation':BASE/'owner-cloud-collection-root-execution-preparation-r1',
 'repository-visibility':BASE/'owner-cloud-repository-visibility-r1',
}
SINGLE={}
EXCLUDED_PARTS={'__pycache__','.pytest_cache'}

def require(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def save(p,value):
 with p.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode)and s.st_nlink==1,'Only independent regular files: '+str(p))
 return {'bytes':s.st_size,'sha256':sha(p),'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
def snapshot(root):
 require(root.is_dir()and not root.is_symlink(),'Source root is not regular directory')
 files={};dirs={};excluded=[]
 for p in [root]+sorted(root.rglob('*')):
  rel='.'if p==root else str(p.relative_to(root))
  if any(part in EXCLUDED_PARTS for part in p.relative_to(root).parts):excluded.append(rel);continue
  s=p.lstat();require(not p.is_symlink(),'Source symlink refused: '+str(p))
  if stat.S_ISDIR(s.st_mode):dirs[rel]={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
  else:files[rel]=row(p)
 return {'files':files,'directories':dirs,'explicitCacheExclusions':excluded}

def copy_tree(source,target,inventory):
 require(not target.exists(),'Never overwrite archive target')
 for name,meta in sorted(inventory['directories'].items(),key=lambda x:len(Path(x[0]).parts)):
  p=target if name=='.'else target/name;p.mkdir(mode=meta['mode'],parents=False)
 for name in inventory['files']:
  p=target/name;require(not p.exists(),'No overwrite');shutil.copy2(source/name,p)
 for name,meta in inventory['directories'].items():
  p=target if name=='.'else target/name;os.chmod(p,meta['mode'])
 require(snapshot(target)==inventory,'Copied payload mode/owner/empty-directory closure differs')

# Review only concrete known credential markers; not a universal secret detector.
MARKERS={
 'private-key-PEM':rb'-----BEGIN '+rb'(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
 'github-token':rb'gh[pousr]_[A-Za-z0-9]{30,}',
 'aws-access-key-id':rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
 'slack-token':rb'xox[baprs]-[A-Za-z0-9-]{20,}',
 'google-api-key':rb'AIza[A-Za-z0-9_-]{30,}',
 'openai-style-key':rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
}
PATTERN=re.compile(b'|'.join(b'(?P<'+k.encode().replace(b'-',b'_')+b'>'+v+b')'for k,v in MARKERS.items()))
SCANNED=[];HITS=[]

def safe_member(name):
 p=PurePosixPath(name);require(name and not p.is_absolute()and'..'not in p.parts,'Unsafe archive scan member');return name

def scan_stream(stream,label):
 h=hashlib.sha256();size=0;tail=b'';hits=set()
 for block in iter(lambda:stream.read(1024**2),b''):
  h.update(block);size+=len(block)
  candidate=tail+block
  if any(prefix in candidate for prefix in (b'-----BEGIN ',b'gh',b'AKIA',b'ASIA',b'xox',b'AIza',b'sk-')):
   for m in PATTERN.finditer(candidate):hits.add(m.lastgroup)
  tail=(tail+block)[-256:]
 if hits:HITS.append({'path':label,'knownMarkerClasses':sorted(hits)})
 SCANNED.append({'path':label,'bytes':size,'sha256':h.hexdigest()})

def scan_file(path,label):
 if path.name.endswith('.tar.gz'):
  with tarfile.open(path,'r|gz')as t:
   for member in t:
    safe_member(member.name)
    if member.isdir():continue
    require(member.isfile(),'Nonregular archive scan member')
    f=t.extractfile(member);nested=label+'!'+member.name
    if member.name.endswith(('.zip','.jar')):
     data=f.read();scan_zip(io.BytesIO(data),nested)
    else:scan_stream(f,nested)
 elif path.suffix in ('.zip','.jar'):
  with path.open('rb')as f:scan_zip(f,label)
 else:
  with path.open('rb')as f:scan_stream(f,label)

def scan_zip(stream,label):
 with zipfile.ZipFile(stream)as z:
  names=set()
  for info in z.infolist():
   safe_member(info.filename);require(info.filename not in names,'Duplicate ZIP member');names.add(info.filename)
   if info.is_dir():continue
   require(info.file_size<=256*1024**2,'Bounded ZIP member review')
   with z.open(info)as f:scan_stream(f,label+'!'+info.filename)

def main():
 require(not TARGET.exists(),'Create-new archive required')
 require(shutil.disk_usage(WORKSPACE).free>=1024**3+300*1024**2,'Local free space floor')
 require(sha(BASE/'cpu-owner-poll-collection-preparation-r2/LOCAL_PREPARATION_FROZEN.json')=='28f6865201389901f26b2c6a7c698622d5d8acc635bad24d09ddadff05777b56','Exact collector freeze required')
 require(sha(BASE/'owner-cloud-root-review-preparation-r1/review_owner_collected.py')=='f59cdda64920de06f556c5108fe8a7f37945b9a84b2dabcc3efda1c3155b23a2','Exact executed root reviewer required')
 review=json.loads((BASE/'owner-cloud-root-review-arm-1-r1/ROOT_REVIEW.json').read_text());require(review['passed']and review['allFullOuterMembersVerified']and review['allRawInputsUnchanged'],'Independent root pass required')
 for original,pin in review['inputs'].items():
  p=Path(original);p=p if p.is_absolute()else WORKSPACE/p
  require(p.stat().st_size==pin['bytes']and sha(p)==pin['sha256'],'Root-reviewed original input changed')
 before={key:snapshot(source)for key,source in TREES.items()}
 require(sum(len(v['files'])for v in before.values())<=2000 and sum(r['bytes']for v in before.values()for r in v['files'].values())<=512*1024**2,'Finite2000file/512MiB copied source scope')
 require(len(before['actual-collection']['files'])==244 and sum(r['bytes']for r in before['actual-collection']['files'].values())==202839167,'Actual244file202839167B collection closure')
 singles={key:row(source)for key,source in SINGLE.items()}
 TARGET.mkdir(mode=0o755)
 save(TARGET/'REGISTRATION.json',{'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Local closed synthetic long CPU proof archive only; no new raw execution or remote actions','sourceTrees':{key:str(p)for key,p in TREES.items()},'sourceFiles':{key:str(p)for key,p in SINGLE.items()},'rootReviewSha256':sha(BASE/'owner-cloud-root-review-arm-1-r1/ROOT_REVIEW.json'),'excludedParts':sorted(EXCLUDED_PARTS),'noSparseExtraction':True,'originalsRetained':True})
 for key,source in TREES.items():copy_tree(source,TARGET/key,before[key])
 for key,source in SINGLE.items():
  p=TARGET/key;p.parent.mkdir(parents=True,exist_ok=True);require(not p.exists(),'No overwrite');shutil.copy2(source,p);require(row(p)==singles[key],'Copied singleton metadata differs')
 save(TARGET/'SOURCE_BEFORE_COPY.json',{'trees':before,'files':singles})
 after={key:snapshot(source)for key,source in TREES.items()}
 require(before==after and all(row(SINGLE[k])==v for k,v in singles.items()),'Original source changed during copy')
 save(TARGET/'SOURCE_AFTER_COPY.json',{'trees':after,'files':singles,'allOriginalBytesModesOwnersAndEmptyDirectoriesUnchanged':True})
 shutil.copy2(Path(__file__),TARGET/'archive_closed_owner_arm1.py')
 for p in sorted(TARGET.rglob('*')):
  if p.is_file():scan_file(p,str(p.relative_to(TARGET)))
 save(TARGET/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not HITS,'scope':'All copied regular bytes plus streamed TAR member bytes and all reachable JAR/ZIP entries; known marker classes only, not a universal absence-of-secret guarantee','markerClasses':sorted(MARKERS),'hitCount':len(HITS),'hits':HITS,'scannedObjects':len(SCANNED),'scannedBytes':sum(v['bytes']for v in SCANNED),'privateKeyOrEnvironmentFilesIntentionallyIncluded':False,'sshKeyPathStringsAreNotKeyContents':True,'protectedPgReferenceIsHashInventoryOnly':True,'scanned':SCANNED})
 require(not HITS,'Known credential marker found; preserve incomplete archive for review')
 (TARGET/'README.md').open('x').write("# Closed CPU owner-poll armA1 evidence\n\nOne fresh long33792@500/s lineage,67.584s planned window, source9771976/code23586ccc/profile73220177, owner requested park1ms and fixedserver/driver100us/read8/chunk6144/Fetch16/businesscap4/leader0/sync2/42000. The authoritative strict collection completed all5steps; root independently verified193outerfiles/24dirs/1,367,724,368logicalbytes and71rawinputs, all33792fresh accepted IDs, actual constructedowner/fullkernelargv/22factory objects. Scheduled-to-reply all-arrival nearest-rankp99 is527,646,352ns. This finite A1 observation alone is not an A/B speedup, sustainedcapacity, SLA or100M proof. Local SHORT native pair and old6033cohort are separate and not compared here.\n\nAll244 actualcollection files (~202.8MB) and both complete original compressedTARs are copied byte-exact, with no sparse extraction. Bothcollector source revisions/peerreview/guard attempts and historical failures; controller/actualrootreadyrelease/stage helpersR1/R2 and actualstage/launch/config/close controls; independentrootreview/source; derivedA1 comparison and unexecuted nextarm/root-execution preparations and private-repositoryvisibility receipts are retained. Later proposals are preparations, not executions or permissions. Comparison-preparation has source-only qualification until its actualA1 result; read each receipt's actualscope.\n\nCopy scope is explicit and closed. Original absolute paths in copied receipts are intentional provenance; REGISTRATION and SOURCE_BEFORE_COPY map them into named archive subtrees. Complete fileSHA/bytes/mode/uid/gid and directory/emptydir closure is verified before/after copy. Only named Python caches are excluded with explicitpaths; no source/log/failure filtering. FullTar member streams and ZIP/JAR entries undergo knowncredentialmarker review without sparse extraction. Necessaryliteral-prefix screening preserves exactly the same regular expressions and still hashes/counts every byte, including zero-filled recording segments. No localnative archive is re-scanned or duplicated here. Marker review is bounded to namedclasses, not universal secret absence.\n\nThis archive task performs no SSH/cloud/API calls, Java/JVM/business workload, rawauditor/collector rerun, signals, newresources, PGwrites, Git or deletions. The rootreview was alreadyPASS beforecopy. INVENTORY excludes only itself and CLOSED; CLOSED binds itsSHA. Independent furtherarms and ABAB analysis require separate closed raw evidence and privatepush gates.\n")
 for filename in ['COPY_PLAN.json','SOURCE_ADAPTATION.diff','REGISTRATION.json']:shutil.copy2(HERE/filename,TARGET/('archiver-'+filename))
 allrows=snapshot(TARGET)
 save(TARGET/'INVENTORY.json',{'scope':'Only this new cloud-arm-1-r1 subtree; original frozen copied bytes unchanged','excludedSelfAndClosure':['INVENTORY.json','CLOSED.json'],'files':allrows['files'],'directories':allrows['directories'],'payloadFileCount':len(allrows['files']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values())})
 inventory=json.loads((TARGET/'INVENTORY.json').read_text())
 for name,pin in inventory['files'].items():require(row(TARGET/name)==pin,'Final archive file differs')
 save(TARGET/'CLOSED.json',{'schemaVersion':1,'passed':True,'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventorySha256':sha(TARGET/'INVENTORY.json'),'files':len(allrows['files']),'directories':len(allrows['directories']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values()),'sourceBeforeAfterEqual':True,'allCopiedPayloadShaModesOwnersAndEmptyDirectoriesVerified':True,'allFullOriginalOuterAndInnerTarsRetained':True,'knownCredentialMarkerReviewPassed':True,'noSparseExtraction':True,'noRemoteActionsOrNewBenchmark':True,'originalsRetained':True,'analysisSiblingExcluded':True,'closureExcludes':['INVENTORY.json','CLOSED.json']})
 print(json.dumps({'passed':True,'target':str(TARGET),'inventorySha256':sha(TARGET/'INVENTORY.json'),'closedSha256':sha(TARGET/'CLOSED.json'),'files':len(allrows['files']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values()),'credentialScannedObjects':len(SCANNED)}))

if __name__=='__main__':main()
