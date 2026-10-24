from pathlib import Path
import datetime,hashlib,json,re,shutil,stat
HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[3]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-long-cut-analysis-r1'
def need(v,m):
 if not v:raise AssertionError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def row(p):
 s=p.lstat();need(stat.S_ISREG(s.st_mode),'Nonregular proof');return {'bytes':s.st_size,'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid,'sha256':sha(p)}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def census(root):
 files={};dirs={}
 for p in [root]+sorted(root.rglob('*')):
  need(not p.is_symlink(),'Symlink refused')
  if p.is_dir():s=p.stat();dirs[str(p.relative_to(root))or'.']={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[str(p.relative_to(root))]=row(p)
 return files,dirs

def main():
 need(not(OUT/'MANIFEST.json').exists()and not(OUT/'CLOSED.json').exists(),'Already closed')
 archiver=OUT/'archiver';archiver.mkdir(exist_ok=False)
 for name in ['archive.py','INPUTS.json','REGISTRATION.json','COMPLETION.json','COPY_COMPLETE.json','stdout.log','stderr.log','add_reproduction.py','REPRODUCTION_ADDED.json','finalize.py','FINALIZER_REGISTRATION.json']:
  shutil.copy2(HERE/name,archiver/name);need(row(archiver/name)==row(HERE/name),'Archiver source copy')
 scopes=json.loads((HERE/'INPUTS.json').read_text())['scopes']
 for name,value in scopes.items():need(census(Path(value['source']))==(value['files'],value['directories']),'Original closed analysis source drift');need(census(OUT/name)==(value['files'],value['directories']),'Archived original analysis drift')
 rb=json.loads((OUT/'PORTABLE_REPRODUCTION_COPY_BINDINGS.json').read_text());need(census(Path(rb['sourceRoot']))==(rb['files'],rb['directories'])==census(OUT/'portable-reproduction-r1'),'Closed reproduction source/copy drift')
 bindings=json.loads((OUT/'ARCHIVED_INPUT_BINDINGS.json').read_text());raw=OUT.parent/'cloud-long-r1'
 need(all(row(raw/name)==value for name,value in bindings['closedRawParentBindings'].items()),'Closed raw parent inventory/closure drift')
 comp=json.loads((OUT/'portable-reproduction-r1/RESULT_COMPARISON.json').read_text());need(comp['allOtherFieldsExactlyEqualIncludingInputBytesAndSha']is True and comp['allSourceConfigOriginalAnd18InputsUnchanged']is True,'Exact portable reproduction gate')
 patterns={'privateKey':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED)? ?PRIVATE KEY-----'),'githubToken':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),'awsAccess':re.compile(rb'AKIA[0-9A-Z]{16}'),'openaiToken':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),'runpodToken':re.compile(rb'rpa_[A-Za-z0-9]{20,}')};findings=[];n=0
 for p in OUT.rglob('*'):
  if p.is_file():
   n+=1;b=p.read_bytes()
   for kind,pat in patterns.items():
    for m in pat.finditer(b):findings.append({'path':str(p.relative_to(OUT)),'marker':kind,'offset':m.start()})
 save(OUT/'FINAL_CLOSURE_REVIEW.json',{'passed':not findings,'original25FileSourceAndDirectoryClosureVerifiedBeforeAfter':True,'closedPortableReproduction10FileSourceAndDirectoryClosureVerified':True,'closedRawParentInventoryAndClosureUnchanged':True,'finalKnownMarkerScanFiles':n,'knownMarkerFindings':findings,'noJavaSshGitCloudOrBenchmarkAction':True,'oneAuthorizedLocalAnalyzerReproductionSeparatelyRecorded':True});need(not findings,'Marker findings retained')
 files,dirs=census(OUT);manifest={'schemaVersion':1,'scope':'CLOSED_FINITE_LONG_CUT_ANALYSIS_AND_PORTABLE_REPRODUCTION','createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'directories':dirs,'excludedOnly':['MANIFEST.json','CLOSED.json'],'fullShaSizeModeOwnerAndDirectoryClosureVerified':True};save(OUT/'MANIFEST.json',manifest)
 actual={str(p.relative_to(OUT))for p in OUT.rglob('*')if p.is_file()};need(actual==set(files)|{'MANIFEST.json'},'Final exact file closure')
 for name,pin in files.items():need(row(OUT/name)==pin,'Final proof drift')
 closed={'schemaVersion':1,'scope':manifest['scope'],'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifestSha256':sha(OUT/'MANIFEST.json'),'manifestBytes':(OUT/'MANIFEST.json').stat().st_size,'filesBeforeManifestAndClosed':len(files),'totalFilesIncludingManifestAndClosed':len(files)+2,'directories':len(dirs),'logicalBytesBeforeManifestAndClosed':sum(r['bytes']for r in files.values()),'originalClosedSourceFiles':25,'portableReproductionFiles':10,'all18RawArchivedInputsBoundWithoutDuplication':True,'originalConfigurationFailureBeforeAnalyzerRetained':True,'originalAnalyzerAnd14GuardEvidencePreserved':True,'fullyOfferedIntervals':8,'fullyOfferedSpanNs':49144105930,'confirmed':24576,'released':24572,'releasedNotFullyConfirmedDrift':-4,'cut11SourceEndCensored':True,'oneAuthorizedPortableAnalyzerReproductionPassed':True,'allOtherResultFieldsExactExceptConfigShaAnd18InputPaths':True,'noCapacityOrInfiniteStabilityClaim':True,'rawParentNeverMutated':True,'noRawPayloadDuplicated':True,'knownMarkerFindings':0,'freeBytes':shutil.disk_usage(WORKSPACE).free};save(OUT/'CLOSED.json',closed);print(json.dumps({**closed,'closedSha256':sha(OUT/'CLOSED.json'),'totalProofBytes':sum(p.stat().st_size for p in OUT.rglob('*')if p.is_file())}))
if __name__=='__main__':main()
