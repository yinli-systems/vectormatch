#!/usr/bin/env python3
"""LOCAL ONLY exact closed proof copy; no SSH, execution, sparse extraction or source mutation."""
import datetime,hashlib,io,json,os
from pathlib import Path,PurePosixPath
import re,shutil,stat,tarfile,zipfile

WORKSPACE=Path('/Users/kevin/Documents/ChatGPT/App 2')
BASE=WORKSPACE/'runtime/cloud/cpu-20261024'
TARGET=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-long-r1'
HERE=Path(__file__).resolve().parent
TREES={
 'collector-preparation':BASE/'cpu-long-cuts-collection-preparation-r1',
 'actual-collection':BASE/'cpu-long-cuts-arm-1-collection-r1',
 'collection-execution':BASE/'long-cloud-collection-execution-r1',
 'actual-config':BASE/'long-cloud-arm-1-config-r1',
 'config-execution':BASE/'long-cloud-config-execution-r1',
 'root-review':BASE/'long-cloud-root-collection-review-r1',
 'root-review-preparation':BASE/'long-cloud-root-review-preparation-r1',
 'root-controller-closed':BASE/'long-cloud-root-controller-closed-r1',
 'close-inspection-r1':BASE/'long-cloud-close-inspection-r1',
 'close-inspection-r2':BASE/'long-cloud-close-inspection-r2',
 'close-inspection-preparation':BASE/'cpu-long-cuts-close-preparation-r1',
 'close-execution-preparation':BASE/'long-cloud-close-execution-preparation-r1',
 'actual-launch':BASE/'long-cloud-arm-1-launch-r1',
 'launch-execution':BASE/'long-cloud-arm-1-launch-execution-r1',
}
SINGLE={'stage-success/STAGE_SUCCESS.json':BASE/'cpu-long-cuts-cloud-staging-r1/STAGE_SUCCESS.json',
        'reviewed-remote-helper/remote.py':BASE/'remote.py'}
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
  for m in PATTERN.finditer(tail+block):hits.add(m.lastgroup)
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
 require(sha(BASE/'cpu-long-cuts-collection-preparation-r1/LOCAL_PREPARATION_FROZEN.json')=='0302832728740f4960d143575d9aac67bc9362c78c3c7d7dbf6d7ea520bbeb29','Exact collector freeze required')
 require(sha(BASE/'long-cloud-root-review-preparation-r1/review_long_collected.py')=='73307e4cd030b7346fef64d0f84e947e700aae0f07fadb43f16eadc44e59267d','Exact executed root reviewer required')
 review=json.loads((BASE/'long-cloud-root-collection-review-r1/ROOT_REVIEW.json').read_text());require(review['passed']and review['allFullOuterMembersVerified']and review['allRawInputsUnchanged'],'Independent root pass required')
 for original,pin in review['inputs'].items():
  p=Path(original);p=p if p.is_absolute()else WORKSPACE/p
  require(p.stat().st_size==pin['bytes']and sha(p)==pin['sha256'],'Root-reviewed original input changed')
 before={key:snapshot(source)for key,source in TREES.items()}
 singles={key:row(source)for key,source in SINGLE.items()}
 TARGET.mkdir(mode=0o755)
 save(TARGET/'REGISTRATION.json',{'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Local closed synthetic long CPU proof archive only; no new raw execution or remote actions','sourceTrees':{key:str(p)for key,p in TREES.items()},'sourceFiles':{key:str(p)for key,p in SINGLE.items()},'rootReviewSha256':sha(BASE/'long-cloud-root-collection-review-r1/ROOT_REVIEW.json'),'excludedParts':sorted(EXCLUDED_PARTS),'noSparseExtraction':True,'originalsRetained':True})
 for key,source in TREES.items():copy_tree(source,TARGET/key,before[key])
 for key,source in SINGLE.items():
  p=TARGET/key;p.parent.mkdir(parents=True,exist_ok=True);require(not p.exists(),'No overwrite');shutil.copy2(source,p);require(row(p)==singles[key],'Copied singleton metadata differs')
 save(TARGET/'SOURCE_BEFORE_COPY.json',{'trees':before,'files':singles})
 after={key:snapshot(source)for key,source in TREES.items()}
 require(before==after and all(row(SINGLE[k])==v for k,v in singles.items()),'Original source changed during copy')
 save(TARGET/'SOURCE_AFTER_COPY.json',{'trees':after,'files':singles,'allOriginalBytesModesOwnersAndEmptyDirectoriesUnchanged':True})
 shutil.copy2(Path(__file__),TARGET/'archive_closed_long.py')
 for p in sorted(TARGET.rglob('*')):
  if p.is_file():scan_file(p,str(p.relative_to(TARGET)))
 save(TARGET/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not HITS,'scope':'All copied regular bytes plus streamed TAR member bytes and all reachable JAR/ZIP entries; known marker classes only, not a universal absence-of-secret guarantee','markerClasses':sorted(MARKERS),'hitCount':len(HITS),'hits':HITS,'scannedObjects':len(SCANNED),'scannedBytes':sum(v['bytes']for v in SCANNED),'privateKeyOrEnvironmentFilesIntentionallyIncluded':False,'sshKeyPathStringsAreNotKeyContents':True,'protectedPgReferenceIsHashInventoryOnly':True,'scanned':SCANNED})
 require(not HITS,'Known credential marker found; preserve incomplete archive for review')
 (TARGET/'README.md').open('x').write('''# Closed CPU long-cut evidence\n\nOne fresh33792@500/s CPU observation, long-cuts-33792-v1,12maintenance cycles/24read phases, window8/chunk6144/businesscap4/100us. Root independently verified193outer files25directories,71raw inputs and all33792unique accepted arrivals. UNKNOWN, rejection, not-sent, scheduler late count and qualified warnings are0. All-arrival scheduled-to-reply p99 is554.293743ms; arrival-window goodput499.9556107954545/s. This finite observation alone does not prove sustained capacity, a production SLA or100M durability.\n\nAll actual collection bytes, both full compressed TARs, four exact runtime JARs, current source/guard attempts (including first failed temporary-path fixtures), launch/strict owned-stop/source/config/collection/root-review receipts are preserved. No sparse state extraction or original deletion. The earlier LOCAL native scheduler-invalid proof is separate and is not relabeled by this successful CPU observation.\n\nOriginal source/config receipts intentionally retain their original absolute runtime paths and SHAs. REGISTRATION/SOURCE_BEFORE_COPY map those roots to this archive's named subtrees; copied originals are not edited for relocation. Stage success is copied exactly; full staged39-source closure also resides in actual-collection/full outer TAR and its materialized source subset. Analysis from sibling active folders is outside this archive.\n\nINVENTORY.json hashes every file except itself and CLOSED.json and records full directory modes/owners (including empty directories). CLOSED.json binds that inventory and notes exclusions. Known-credential-marker review is bounded to named marker classes and includes compiled JAR/class content; no private key or environment files were requested or copied. Protected PG989 is a hash manifest only.\n''')
 allrows=snapshot(TARGET)
 save(TARGET/'INVENTORY.json',{'scope':'Only this new cloud-long-r1 subtree; original frozen copied bytes unchanged','excludedSelfAndClosure':['INVENTORY.json','CLOSED.json'],'files':allrows['files'],'directories':allrows['directories'],'payloadFileCount':len(allrows['files']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values())})
 inventory=json.loads((TARGET/'INVENTORY.json').read_text())
 for name,pin in inventory['files'].items():require(row(TARGET/name)==pin,'Final archive file differs')
 save(TARGET/'CLOSED.json',{'schemaVersion':1,'passed':True,'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventorySha256':sha(TARGET/'INVENTORY.json'),'files':len(allrows['files']),'directories':len(allrows['directories']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values()),'sourceBeforeAfterEqual':True,'allCopiedPayloadShaModesOwnersAndEmptyDirectoriesVerified':True,'allFullOriginalOuterAndInnerTarsRetained':True,'knownCredentialMarkerReviewPassed':True,'noSparseExtraction':True,'noRemoteActionsOrNewBenchmark':True,'originalsRetained':True,'analysisSiblingExcluded':True,'closureExcludes':['INVENTORY.json','CLOSED.json']})
 print(json.dumps({'passed':True,'target':str(TARGET),'inventorySha256':sha(TARGET/'INVENTORY.json'),'closedSha256':sha(TARGET/'CLOSED.json'),'files':len(allrows['files']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values()),'credentialScannedObjects':len(SCANNED)}))

if __name__=='__main__':main()
