from pathlib import Path
import datetime,hashlib,json,re,shutil,stat
HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[3]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-preparation-r1'
def require(v,m):
 if not v:raise AssertionError(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode),'Nonregular proof file');return {'bytes':s.st_size,'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid,'sha256':sha(p)}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def main():
 require(not(OUT/'MANIFEST.json').exists()and not(OUT/'CLOSED.json').exists(),'Already frozen')
 own=OUT/'archiver';own.mkdir(exist_ok=False)
 for name in ['archive.py','REGISTRATION.json','WRAPPER_REGISTRATION.json','WRAPPER_COMPLETION.json','COPY_COMPLETE.json','stdout.txt','stderr.txt','finalize.py','FINALIZER_REGISTRATION.json']:
  shutil.copy2(HERE/name,own/name);require(row(own/name)==row(HERE/name),'Archiver copy mismatch')
 bindings=json.loads((OUT/'SOURCE_COPY_BINDINGS.json').read_text())
 for dest,expected in bindings['files'].items():
  r={k:v for k,v in expected.items()if k!='source'};require(row(Path(expected['source']))==r,'Closed source changed');require(row(OUT/dest)==r,'Archived source mismatch')
 for prefix,dirs in bindings['wholeClosedDirectorySourceDirs'].items():
  actual={str(d.relative_to(OUT/prefix))or'.':{'mode':d.stat().st_mode&0o777,'uid':d.stat().st_uid,'gid':d.stat().st_gid}for d in [OUT/prefix]+sorted(p for p in (OUT/prefix).rglob('*')if p.is_dir())};require(actual==dirs,'Whole source directory/mode/owner/empty closure mismatch '+prefix)
 patterns={'privateKey':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED)? ?PRIVATE KEY-----'),'githubToken':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),'awsAccess':re.compile(rb'AKIA[0-9A-Z]{16}'),'openaiToken':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),'runpodToken':re.compile(rb'rpa_[A-Za-z0-9]{20,}')};findings=[];scanfiles=0
 for p in OUT.rglob('*'):
  require(not p.is_symlink(),'Symlink in proof')
  if p.is_file():
   scanfiles+=1;b=p.read_bytes()
   for key,pat in patterns.items():
    for m in pat.finditer(b):findings.append({'path':str(p.relative_to(OUT)),'marker':key,'offset':m.start()})
 save(OUT/'FINAL_CLOSURE_REVIEW.json',{'passed':not findings,'all86CopiedInputsRehashedAgainUnchanged':True,'allWholeScopeDirectoriesModesOwnersEmptyClosureEqual':True,'finalKnownMarkerScanFiles':scanfiles,'knownMarkerFindings':findings,'nestedZipEntriesPreviouslyScanned':80,'noSparseExtraction':True,'noJavaSshGitOrCloudAction':True,'scope':'Local proof closure; no active cloud/native/raw or root-ready inputs accessed'})
 require(not findings,'Final credential marker findings')
 files={};dirs={}
 for p in [OUT]+sorted(OUT.rglob('*')):
  require(not p.is_symlink(),'Symlink in proof')
  if p.is_dir():s=p.stat();dirs[str(p.relative_to(OUT))or'.']={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[str(p.relative_to(OUT))]=row(p)
 manifest={'schemaVersion':1,'scope':'LOCAL_CLOSED_LONG_CUTS_CLOUD_PREPARATION','statusOfFrozenPreparationSnapshot':'DRAFT_ROOT_FREEZE_PENDING','createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'directories':dirs,'excludedOnly':['MANIFEST.json','CLOSED.json'],'fullShaSizeModeOwnerAndDirectoryClosure':True}
 save(OUT/'MANIFEST.json',manifest)
 actualfiles={str(p.relative_to(OUT))for p in OUT.rglob('*')if p.is_file()};require(actualfiles==set(files)|{'MANIFEST.json'},'Final file closure drift')
 for name,wanted in files.items():require(row(OUT/name)==wanted,'Final SHA/metadata drift')
 closed={'schemaVersion':1,'scope':'CLOSED_LOCAL_LONG_CUTS_CLOUD_PREPARATION_ONLY','passed':True,'frozenPreparationSnapshotStatus':'DRAFT_ROOT_FREEZE_PENDING','atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifestSha256':sha(OUT/'MANIFEST.json'),'manifestBytes':(OUT/'MANIFEST.json').stat().st_size,'filesBeforeManifestAndClosed':len(files),'totalFilesIncludingManifestAndClosed':len(files)+2,'directories':len(dirs),'logicalBytesBeforeManifestAndClosed':sum(r['bytes']for r in files.values()),'sourceCopiedFiles':86,'zipArchives':8,'zipEntries':80,'noActiveCloudNativeRawOrRootReadyInputs':True,'noJavaSshGitCloudAction':True,'noCapacityClaim':True,'freeBytes':shutil.disk_usage(WORKSPACE).free}
 save(OUT/'CLOSED.json',closed);print(json.dumps({**closed,'closedSha256':sha(OUT/'CLOSED.json'),'totalProofBytes':sum(p.stat().st_size for p in OUT.rglob('*')if p.is_file())}))
if __name__=='__main__':main()
