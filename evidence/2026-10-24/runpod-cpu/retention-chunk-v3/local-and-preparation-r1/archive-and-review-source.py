#!/usr/bin/env python3
"""Local evidence snapshot and bounded SHA/mode/archive review. No SSH, cloud action or Git mutation."""
import datetime,hashlib,json,os,re,shutil,stat,tarfile,zipfile
from pathlib import Path

REPO=Path(__file__).resolve().parents[3]
BASE=Path(__file__).resolve().parent
DEST=REPO/'evidence/2026-10-24/runpod-cpu/retention-chunk-v3/local-and-preparation-r1'
SOURCES={
 'validation':BASE/'retention-chunk-v3-worktree/build/chunk-validation',
 'preparation-r1':BASE/'chunk-cloud-abab-preparation',
 'preparation-r2':BASE/'chunk-cloud-abab-preparation-r2',
 'preparation-r3':BASE/'chunk-cloud-abab-preparation-r3',
 'candidate-builder':BASE/'chunk-cloud-abab-candidate-builder',
 'candidate-r2-failed':BASE/'chunk-cloud-abab-candidate-r2',
 'candidate-r3':BASE/'chunk-cloud-abab-candidate-r3',
 'cpu-stage-r3':BASE/'chunk-cloud-abab-staging-r3',
 'cpu-round1-launch':BASE/'chunk-cloud-abab-round1-launch-r1',
}
CONTROL={'stage-r2.py':BASE/'stage-chunk-cloud-abab-r2.py','stage-r3.py':BASE/'stage-chunk-cloud-abab-r3.py','launch-r3.py':BASE/'launch-chunk-cloud-abab-r3.py'}
PATTERNS={
 'private_key_header':re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'),
 'github_pat':re.compile(rb'github_pat_[A-Za-z0-9_]{20,}'),
 'github_classic':re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'),
 'aws_access_key':re.compile(rb'(?:AKIA|ASIA)[0-9A-Z]{16}'),
 'runpod_api_key':re.compile(rb'rpa_[A-Za-z0-9]{20,}'),
}
review={'scope':'Known credential-marker review of explicitly scoped synthetic code/evidence. Not a universal secret-detection guarantee.','patterns':list(PATTERNS),'scannedMembers':0,'scannedBytes':0,'findings':[],'excludedLargeNativeMembers':[],'containerInventories':[]}
cache={}

def need(ok,message):
 if not ok:raise RuntimeError(message)

def digest(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def save(p,obj):
 with Path(p).open('x') as f:json.dump(obj,f,indent=2,sort_keys=True);f.write('\n')

def scan(root):
 need(root.is_dir() and not root.is_symlink(),'Source/evidence root must be ordinary directory')
 files,dirs={},{}
 for p in [root]+sorted(root.rglob('*')):
  if '__pycache__' in p.relative_to(root).parts:continue
  need(not p.is_symlink(),'Symlink evidence refused')
  s=p.lstat();name=str(p.relative_to(root));row={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
  if p.is_dir():dirs[name]=row
  else:
   need(p.is_file() and s.st_nlink==1 and s.st_size<=32*1024**2,'Unexpected/unbounded source file')
   files[name]=dict(row,bytes=s.st_size,sha256=digest(p))
 need(len(files)+len(dirs)<=8192,'Evidence path cap')
 return {'files':files,'directories':dirs,'bytes':sum(r['bytes'] for r in files.values())}

def markers(data,label):
 review['scannedMembers']+=1;review['scannedBytes']+=len(data)
 for kind,pattern in PATTERNS.items():
  if pattern.search(data):review['findings'].append({'path':label,'pattern':kind})

def zip_review(p,label):
 key=digest(p)
 if key in cache:
  review['containerInventories'].append({'path':label,'sha256':key,'sameBytesAsReviewed':cache[key]});return
 cache[key]=label;rows={}
 with zipfile.ZipFile(p) as z:
  for info in z.infolist():
   need(info.filename not in rows and not info.filename.startswith('/') and '..' not in Path(info.filename).parts,'Unsafe duplicate ZIP entry')
   if info.is_dir():rows[info.filename]={'directory':True};continue
   need(info.file_size<=32*1024**2,'ZIP entry cap');b=z.read(info.filename);markers(b,label+'!'+info.filename)
   rows[info.filename]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'externalMode':info.external_attr>>16}
 review['containerInventories'].append({'path':label,'sha256':key,'members':rows})

def source_tar_review(p,label):
 key=digest(p)
 if key in cache:
  review['containerInventories'].append({'path':label,'sha256':key,'sameBytesAsReviewed':cache[key]});return
 cache[key]=label;rows={}
 with tarfile.open(p,'r|gz') as archive:
  for member in archive:
   need(member.name not in rows and not member.name.startswith('/') and '..' not in Path(member.name).parts,'Unsafe source tar name')
   need(member.isdir() or member.isfile(),'Source tar special/link refused')
   row={'mode':member.mode,'uid':member.uid,'gid':member.gid,'directory':member.isdir()}
   if member.isfile():
    need(member.size<=32*1024**2,'Source tar member cap');b=archive.extractfile(member).read();markers(b,label+'!'+member.name)
    row.update(bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
   rows[member.name]=row
 review['containerInventories'].append({'path':label,'sha256':key,'members':rows})

def native_readback(manifest_path):
 m=json.loads(manifest_path.read_text());p=manifest_path.parent/'native-state.tar.gz'
 need(p.stat().st_size==m['archiveBytes'] and digest(p)==m['archiveSha256'],'Native compressed artifact SHA/size differs')
 files,dirs={},{};fingerprints=set()
 with tarfile.open(p,'r|gz') as archive:
  for member in archive:
   need(not member.name.startswith('/') and '..' not in Path(member.name).parts and (member.isdir() or member.isfile()),'Native unsafe member')
   expected=(m['directories'] if member.isdir() else m['files']).get(member.name)
   need(expected is not None and member.mode==expected['mode'],'Unexpected native member/mode')
   row={'mode':member.mode,'uid':member.uid,'gid':member.gid}
   if member.isdir():need(member.name not in dirs,'Duplicate native directory');dirs[member.name]=row;continue
   need(member.name not in files and member.size==expected['bytes'],'Native duplicate/size differs')
   h=hashlib.sha256();size=0;small=bytearray() if member.size<=8*1024**2 else None
   payload=archive.extractfile(member)
   for b in iter(lambda:payload.read(1024**2),b''):
    h.update(b);size+=len(b)
    if small is not None:small.extend(b)
   need(size==expected['bytes'] and h.hexdigest()==expected['sha256'],'Native full logical SHA/size differs')
   row.update(bytes=size,sha256=h.hexdigest());files[member.name]=row
   label=str(p.relative_to(DEST))+'!'+member.name
   if small is not None:
    markers(small,label)
    if member.name.endswith('/artifact-inventory.json'):fingerprints.add(json.loads(small)['codeFingerprint'])
   else:review['excludedLargeNativeMembers'].append({'path':label,'bytes':size,'sha256':h.hexdigest(),'reason':'Large generated sparse native binary; full logical SHA/mode/closure verified, not credential marker scanned'})
 need(set(files)==set(m['files']) and set(dirs)==set(m['directories']),'Native full file/directory/empty-dir closure differs')
 need(sum(r['bytes'] for r in files.values())==m['logicalBytes'],'Native total logical size differs')
 return {'passed':True,'manifest':str(manifest_path.relative_to(DEST)),'manifestSha256':digest(manifest_path),'archiveSha256':digest(p),'fileCount':len(files),'directoryCount':len(dirs),'logicalBytes':m['logicalBytes'],'actualNativeCodeFingerprints':sorted(fingerprints),'files':files,'directories':dirs,'fullLogicalReadback':True,'extracted':False}

def main():
 need(not DEST.exists(),'Fresh scoped proof destination required');DEST.mkdir(parents=True,mode=0o700)
 copied={}
 for label,source in SOURCES.items():
  before=scan(source);shutil.copytree(source,DEST/label,ignore=shutil.ignore_patterns('__pycache__'))
  after=scan(source);actual=scan(DEST/label)
  need(before==after==actual,'Source changed or destination closure/owner/mode/SHA differs: '+label)
  copied[label]={'source':str(source),'snapshot':before,'sourceUnchangedDuringCopy':True}
 control=DEST/'root-control';control.mkdir(mode=0o700)
 for name,source in CONTROL.items():shutil.copy2(source,control/name);need(digest(source)==digest(control/name),'Control source copy differs')
 copied['root-control']={'sourceFiles':{n:str(p) for n,p in CONTROL.items()},'snapshot':scan(control)}
 shutil.copy2(Path(__file__),DEST/'archive-and-review-source.py')
 launch=json.loads((DEST/'cpu-round1-launch/launch.stdout.json').read_text())
 stage=json.loads((DEST/'cpu-stage-r3/SUCCESS.json').read_text())
 need(stage['passed'] is True and stage['linuxPureGuards']==69 and stage['releaseSha256']=='5d8bd210f5f7e78cb421a1dc80f3367ecee07e90bcba9a54c6c0a88db05a92c7','Actual stage receipt differs')
 need(launch['round']==1 and launch['frozenReleaseSha256']==stage['releaseSha256'] and launch['noResubmission'] is True,'Actual immutable launch receipt differs')
 save(DEST/'SOURCE_COPY_MANIFEST.json',{'schemaVersion':1,'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Explicit local-only snapshots; current cloud runtime/results not collected or inspected by this author','copied':copied,'excludedDirectoryName':'__pycache__','noRemoteAction':True,'noGitMutation':True})
 native=[native_readback(p) for p in sorted((DEST/'validation').glob('native-*-archives/*/manifest.json'))]
 save(DEST/'NATIVE_FULL_READBACK.json',{'passed':True,'archives':native,'noExtraction':True})
 for p in sorted(DEST.rglob('*')):
  if not p.is_file() or p.name in ['NATIVE_FULL_READBACK.json']:continue
  label=str(p.relative_to(DEST))
  if p.name=='native-state.tar.gz':continue
  if p.suffix in ['.jar','.zip']:zip_review(p,label)
  elif p.name.endswith('.tar.gz'):source_tar_review(p,label)
  else:markers(p.read_bytes(),label)
 review['passed']=not review['findings'];save(DEST/'CREDENTIAL_MARKER_REVIEW.json',review)
 need(not review['findings'],'Known credential marker findings; root review required before Git')
 print(json.dumps({'passed':True,'destination':str(DEST),'copiedRoots':len(copied),'nativeArchives':len(native),'nativeLogicalBytes':sum(r['logicalBytes'] for r in native),'fileBytes':sum(r['snapshot']['bytes'] for r in copied.values()),'credentialMarkerFindings':len(review['findings'])}),flush=True)

if __name__=='__main__':main()
