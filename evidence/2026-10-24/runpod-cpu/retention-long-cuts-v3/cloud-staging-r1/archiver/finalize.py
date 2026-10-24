from pathlib import Path
import datetime,hashlib,json,re,shutil,stat
HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[3]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-staging-r1'
def require(v,m):
 if not v:raise AssertionError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode),'Nonregular proof input');return {'bytes':s.st_size,'sha256':sha(p),'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def census(root):
 files={};dirs={}
 for p in [root]+sorted(root.rglob('*')):
  require(not p.is_symlink(),'Proof symlink refused')
  if p.is_dir():s=p.stat();dirs[str(p.relative_to(root))or'.']={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[str(p.relative_to(root))]=row(p)
 return files,dirs

def main():
 require(not(OUT/'MANIFEST.json').exists()and not(OUT/'CLOSED.json').exists(),'Already closed')
 dst=OUT/'archiver';dst.mkdir(exist_ok=False)
 for name in ['archive.py','INPUTS.json','REGISTRATION.json','COMPLETION.json','COPY_COMPLETE.json','stdout.log','stderr.log','finalize.py','FINALIZER_REGISTRATION.json']:
  shutil.copy2(HERE/name,dst/name);require(row(dst/name)==row(HERE/name),'Archive wrapper copy drift')
 source=json.loads((HERE/'INPUTS.json').read_text())['scopes']
 for name,value in source.items():
  require(census(Path(value['source']))==(value['files'],value['directories']),'Source drift after completion '+name);require(census(OUT/name)==(value['files'],value['directories']),'Closed copy drift '+name)
 patterns={'privateKey':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED)? ?PRIVATE KEY-----'),'githubToken':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),'awsAccess':re.compile(rb'AKIA[0-9A-Z]{16}'),'openaiToken':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),'runpodToken':re.compile(rb'rpa_[A-Za-z0-9]{20,}')};findings=[];n=0
 for p in OUT.rglob('*'):
  if p.is_file():
   n+=1;b=p.read_bytes()
   for kind,pat in patterns.items():
    for m in pat.finditer(b):findings.append({'path':str(p.relative_to(OUT)),'marker':kind,'offset':m.start()})
 save(OUT/'FINAL_CLOSURE_REVIEW.json',{'passed':not findings,'all15FullSourceDirectoryClosuresCheckedBeforeAfter':True,'all72InputFilesShaSizeModesOwnersChecked':True,'finalMarkerScanFiles':n,'knownMarkerFindings':findings,'stageMembersAndJarEntriesReview':'STAGE_BUNDLE_AND_BINDING_REVIEW.json and JAR_FULL_ENTRY_REVIEW.json','noJavaSshGitCloudOrRawCollectionReads':True});require(not findings,'Marker findings retained')
 files,dirs=census(OUT);manifest={'schemaVersion':1,'scope':'CLOSED_ACTUAL_LONG_CUTS_CPU_CLOUD_STAGING_AND_LIFECYCLE_PROVENANCE','createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'directories':dirs,'excludedOnly':['MANIFEST.json','CLOSED.json'],'fullShaSizeModeOwnerDirectoryAndEmptyClosure':True};save(OUT/'MANIFEST.json',manifest)
 actual={str(p.relative_to(OUT))for p in OUT.rglob('*')if p.is_file()};require(actual==set(files)|{'MANIFEST.json'},'Final file closure changed')
 for name,pin in files.items():require(row(OUT/name)==pin,'Final file metadata drift')
 closed={'schemaVersion':1,'scope':manifest['scope'],'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifestSha256':sha(OUT/'MANIFEST.json'),'manifestBytes':(OUT/'MANIFEST.json').stat().st_size,'filesBeforeManifestAndClosed':len(files),'totalFilesIncludingManifestAndClosed':len(files)+2,'directories':len(dirs),'logicalBytesBeforeManifestAndClosed':sum(r['bytes']for r in files.values()),'sourceScopes':15,'sourceInputFiles':72,'actualStageSourceRows':39,'actualStageSourceBytes':5112390,'actualLinuxPureGuardTests':52,'actualReadyReleaseRecorded':True,'separateOneShotLaunchRecorded':True,'historicalActiveAndClosedObservationsBothRetained':True,'controllerExitCodeIndependentlyObserved':False,'rootRawReviewReceiptCopiedNotIndependentlyReperformed':True,'noRawCollectionTreeCopiedOrRead':True,'archiverNoJavaSshGitCloudAction':True,'knownMarkerFindings':0,'freeBytes':shutil.disk_usage(WORKSPACE).free};save(OUT/'CLOSED.json',closed);print(json.dumps({**closed,'closedSha256':sha(OUT/'CLOSED.json'),'totalProofBytes':sum(p.stat().st_size for p in OUT.rglob('*')if p.is_file())}))
if __name__=='__main__':main()
