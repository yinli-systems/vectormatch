#!/usr/bin/env python3
"""Copy closed local integration proofs only; inspect known markers without extraction."""
from pathlib import Path, PurePosixPath
import datetime, hashlib, io, json, os, re, shutil, subprocess, tarfile, zipfile

ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2')
WORK=ROOT/'runtime/cloud/cpu-20261024/retention-integration-worktree'
SOURCE=WORK/'build/integration-validation'
DEST=ROOT/'evidence/2026-10-24/runpod-cpu/retention-integration-v3/validation-r1'
GIB=1024**3
SELECTED=('r1','r2','test-db-r1')
PATTERNS={
 'complete-private-key-pem':re.compile(rb'-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----[\r\n]+[A-Za-z0-9+/=\r\n]{64,}-----END (?:[A-Z0-9]+ )?PRIVATE KEY-----'),
 'github-classic-token':re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
 'github-fine-grained-token':re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
 'aws-access-key-id':re.compile(rb'AKIA[0-9A-Z]{16}'),
 'openai-style-secret-token':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{32,}'),
 'runpod-style-token':re.compile(rb'rpa_[A-Za-z0-9_-]{25,}'),
 'literal-secret-environment-assignment':re.compile(rb'(?:RUNPOD_API_KEY|GH_TOKEN|GITHUB_TOKEN|OPENAI_API_KEY|AWS_SECRET_ACCESS_KEY)\s*[:=]\s*[\"\x27][A-Za-z0-9_./+\-=]{20,}[\"\x27]'),
}

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def guard():
 free=shutil.disk_usage(ROOT).free
 if free<GIB:raise RuntimeError('1GiB local free-space floor')
 return free

def checked(p):
 p=Path(p)
 if any(q.is_symlink() for q in [p,*p.parents]):raise ValueError('Symlink proof source refused: '+str(p))
 return p

def safe_member(name):
 p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe archive member')
 return p

assert not DEST.exists(),'CREATE_NEW evidence target required'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORK,text=True).strip()=='2bda894886937c589d9f1b28e2a23132bca3188b'
assert not subprocess.check_output(['git','status','--porcelain=v1'],cwd=WORK,text=True).strip()
assert json.loads((SOURCE/'r2/execution.json').read_text())['exitCode']==0
for rel in ['r1/archives/capture-complete.json','r2/archives/capture-complete.json']:
 assert (SOURCE/rel).is_file()

guard();DEST.mkdir(parents=True,exist_ok=False)
copy_manifest={};directories={};copied=0
for selection in SELECTED:
 root=checked(SOURCE/selection)
 for p in [root,*sorted(root.rglob('*'))]:
  checked(p);rel=str(p.relative_to(SOURCE));target=DEST/rel;st=p.stat()
  if p.is_dir():
   target.mkdir(parents=True,exist_ok=False);shutil.copystat(p,target,follow_symlinks=False);directories[rel]={'mode':st.st_mode&0o777};continue
  assert p.is_file();copied+=st.st_size
  if copied>512*1024**2:raise RuntimeError('Copy exceeds512MiB bounded compressed proof envelope')
  if guard()-st.st_size<GIB:raise RuntimeError('Copy would cross free-space floor')
  before={'bytes':st.st_size,'sha256':sha(p),'mode':st.st_mode&0o777}
  with p.open('rb') as src,target.open('xb') as out:shutil.copyfileobj(src,out,1024**2)
  shutil.copystat(p,target,follow_symlinks=False)
  assert target.stat().st_size==before['bytes'] and sha(target)==before['sha256'] and target.stat().st_mode&0o777==before['mode']
  assert p.stat().st_size==before['bytes'] and sha(p)==before['sha256'],'Frozen proof changed during copy'
  copy_manifest[rel]=before

tool=DEST/'tool-validation';tool.mkdir();shutil.copy2(Path(__file__),tool/'archive-retention-integration-validation-r1.py')
hits=[];scanned=[];jar_unique={};jar_occurrences=[];excluded=[];scanned_bytes=0

def inspect(data,label):
 global scanned_bytes
 scanned_bytes+=len(data)
 if scanned_bytes>1024**3:raise RuntimeError('Marker inspection exceeds1GiB selected uncompressed bytes')
 for key,pattern in PATTERNS.items():
  for match in pattern.finditer(data):hits.append({'path':label,'pattern':key,'offset':match.start(),'secretValueRecorded':False})
 scanned.append({'path':label,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})

def inspect_zip(data,label,jar=False,depth=0):
 if depth>4:raise RuntimeError('Nested ZIP depth bound')
 digest=hashlib.sha256(data).hexdigest()
 if jar:
  jar_occurrences.append({'path':label,'sha256':digest})
  if digest in jar_unique:return
  jar_unique[digest]={'firstPath':label,'entries':0,'uncompressedBytes':0}
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  infos=z.infolist()
  if len(infos)>20000 or sum(i.file_size for i in infos)>256*1024**2:raise RuntimeError('ZIP inventory bound')
  for i in infos:
   safe_member(i.filename)
   if i.is_dir():continue
   if i.file_size>64*1024**2:raise RuntimeError('ZIP member bound')
   body=z.read(i);item=label+'!'+i.filename
   if jar:jar_unique[digest]['entries']+=1;jar_unique[digest]['uncompressedBytes']+=len(body)
   if i.filename.endswith('.jar'):inspect_zip(body,item,True,depth+1)
   elif i.filename.endswith('.zip'):inspect_zip(body,item,False,depth+1)
   else:inspect(body,item)

# Top-level files, source ZIPs and the actual four-JAR distribution.
for rel in sorted(copy_manifest):
 p=DEST/rel
 if rel.endswith('.tar.gz'):continue
 if p.stat().st_size>64*1024**2:raise RuntimeError('Direct proof file bound')
 data=p.read_bytes()
 if rel.endswith('.zip'):inspect_zip(data,rel)
 elif rel.endswith('.jar'):inspect_zip(data,rel,True)
 else:inspect(data,rel)

# Full artifact tars are small and contain all exact classpaths, including every JAR member.
for manifest_path in sorted(DEST.glob('r*/archives/artifacts*/manifest.json')):
 manifest=json.loads(manifest_path.read_text());packed=manifest_path.parent/manifest['archive']['path']
 assert sha(packed)==manifest['archive']['sha256']
 with tarfile.open(packed,'r|gz') as archive:
  for member in archive:
   safe_member(member.name)
   if member.isdir():continue
   if not member.isreg() or member.size>64*1024**2:raise RuntimeError('Artifact tar member bound')
   data=archive.extractfile(member).read();assert len(data)==member.size
   item=str(packed.relative_to(DEST))+'!'+member.name
   if member.name.endswith('.jar'):inspect_zip(data,item,True)
   elif member.name.endswith('.zip'):inspect_zip(data,item)
   else:inspect(data,item)

# Native text and small binary proofs are inspected at their retained, hash-bound original
# paths. Prior full-tar readback proves those exact bytes are present in the copied archives.
# This avoids decompressing25GB of mostlyzero Aeron allocations a second time.
for manifest_path in sorted(DEST.glob('r*/archives/retention-*/manifest.json')):
 manifest=json.loads(manifest_path.read_text());assert manifest['everyLogicalFileByteSha256ReadBack'] is True
 packed=manifest_path.parent/manifest['archive']['path'];assert sha(packed)==manifest['archive']['sha256']
 assert manifest['allCompletionAllOwnedStopped'] is True
 for name,spec in manifest['files'].items():
  candidates=[]
  for root in manifest['roots']:
   if name==root['archiveRoot']:candidates.append(Path(root['source']))
   elif name.startswith(root['archiveRoot']+'/'):candidates.append(Path(root['source'])/name[len(root['archiveRoot'])+1:])
  assert len(candidates)==1
  p=checked(candidates[0]);item=str(manifest_path.relative_to(DEST))+'!'+name
  if p.suffix in {'.rec','.dat'} or spec['bytes']>32*1024**2:
   excluded.append({'path':item,'bytes':spec['bytes'],'sha256':spec['sha256'],'reason':'Large Aeron recording/mapped state: prior every-byte archive readback and synthetic fixture provenance; not content-marker inspected'})
   continue
  assert p.stat().st_size==spec['bytes'] and sha(p)==spec['sha256']
  data=p.read_bytes()
  if name.endswith('.jar'):inspect_zip(data,item,True)
  elif name.endswith('.zip'):inspect_zip(data,item)
  else:inspect(data,item)

review={'reviewedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'method':'Bounded known-pattern inspection, not a general secret scanner or proof of absence','patterns':{k:v.pattern.decode('ascii') for k,v in PATTERNS.items()},'hitCount':len(hits),'hits':hits,'selectedBytesInspected':scanned_bytes,'inspectedEntries':scanned,'allJarOccurrencesCoveredByExactContentSha256':True,'jarOccurrences':jar_occurrences,'uniqueJarSha256Inventories':jar_unique,'largeNativeBinaryContentMarkerExclusions':excluded,'syntheticProvenance':'Native states produced by six local functional fixtures with fresh lineages and source-bound synthetic commands, matched against canonical/reference state. No original PGDATA/application files, SSH credentials, /proc/environ, API keys or host filesystem snapshots were selected. Test DB receipt covers one fresh local database, not its physical PGDATA.','rawSecretsPrinted':False}
with (DEST/'credential-marker-review.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
if hits:raise RuntimeError('Known credential-marker hits require review; no successful completion receipt')

scope={'sourceWorktree':str(WORK),'sourceDirectories':list(SELECTED),'sourceBranch':'codex/retention-integration','sourceCommit':'2bda894886937c589d9f1b28e2a23132bca3188b','sourceCopyFileCount':len(copy_manifest),'copiedRegularBytes':copied,'sourceCopyFiles':copy_manifest,'sourceCopyDirectories':directories,'originalSparseNativeTreesCopied':False,'originalSparseNativeTreesDeleted':False,'nativeArchives':'Closed gzip/tar only; prior source manifests bind every logical file byte, mode and empty directory','noSshOrCloudOperations':True,'noTestsRerunForCopy':True,'localFreeBytesAfter':guard(),'copiedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (DEST/'source-scope.json').open('x') as f:json.dump(scope,f,indent=2);f.write('\n')
readme='''# Isolated V3 integration validation

Source branch `codex/retention-integration`, commit `2bda894886937c589d9f1b28e2a23132bca3188b`, was privately pushed. Main was not merged by this operation.

`r1` preserves the complete failed forced run: two functional observation recorders attempted CREATE_NEW twice on the same open path. Both failures, original source, exact class/JAR inputs, XML/logs and all six native trees remain archived. `r2` preserves the bounded recorder fix and successful forced run: 291/291 tests, zero failures/errors/skips;23/23 actionable tasks executed. All nine native completion receipts passed and stopped. Tests used a new dedicated local PostgreSQL database, not the existing application schema.

Only already-closed compressed native archives were copied here, never25GB of original sparse native trees. Every copied file SHA256, size and mode was checked against its frozen source. Existing archive manifests additionally attest full logical-byte readback, modes and empty directories. `r2/tested-source-commit-comparison.json` verifies all239 tested materialized files against the pushed commit; only the integration validation document was added after testing.

The known-marker review scans all exact JAR entries (duplicate JARs are bound by SHA256), source ZIPs, text/receipts/logs, classes and small native binary proofs. Native text/small proofs were scanned through their preserved original paths only after matching archived file hashes. Large Aeron recordings/mapped files were excluded from content-marker inspection, with exact paths/hashes/reasons recorded; their complete archive readback and synthetic source/reference provenance remain preserved. This bounded review is not a general proof that arbitrary secrets cannot exist. No SSH/private-key/API-secret files or original PGDATA were selected.

This is local functional integration evidence, not an independent-host throughput, durability or100M result. The integrated artifact is different from frozen e3 used by the CPU chunk ABAB experiment. No deployment or default promotion occurred here.
'''
with (DEST/'README.md').open('x') as f:f.write(readme)

all_files={};all_dirs={}
for p in sorted(DEST.rglob('*')):
 checked(p);rel=str(p.relative_to(DEST))
 if p.is_dir():all_dirs[rel]={'mode':p.stat().st_mode&0o777}
 elif p.is_file():all_files[rel]={'bytes':p.stat().st_size,'sha256':sha(p),'mode':p.stat().st_mode&0o777}
 else:raise RuntimeError('Nonregular destination')
for rel,spec in copy_manifest.items():assert all_files[rel]==spec
inventory={'schemaVersion':1,'files':all_files,'directoriesIncludingEmpty':all_dirs,'totalRegularBytes':sum(x['bytes'] for x in all_files.values()),'inventorySelfAndCompletionExcluded':['proof-inventory.json','completion.json'],'allCopiedFileBytesAndModesMatchFrozenSources':True}
with (DEST/'proof-inventory.json').open('x') as f:json.dump(inventory,f,indent=2);f.write('\n')
completion={'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'proofInventorySha256':sha(DEST/'proof-inventory.json'),'credentialReviewSha256':sha(DEST/'credential-marker-review.json'),'sourceScopeSha256':sha(DEST/'source-scope.json'),'fileCountBeforeClosureMetadata':len(all_files),'regularBytesBeforeClosureMetadata':inventory['totalRegularBytes'],'knownMarkerHitCount':0,'uniqueJarsInspected':len(jar_unique),'jarOccurrencesCovered':len(jar_occurrences),'allCopiedFileBytesAndModesMatchFrozenSources':True,'originalSparseNativeTreesCopied':False,'noTestsOrCloudOperations':True,'freeBytesAfter':guard()}
with (DEST/'completion.json').open('x') as f:json.dump(completion,f,indent=2);f.write('\n')
print(json.dumps(completion,indent=2))
