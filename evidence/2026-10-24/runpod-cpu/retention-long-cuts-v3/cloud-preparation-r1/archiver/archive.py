from pathlib import Path
import datetime,hashlib,json,re,shutil,stat,zipfile
BASE=Path(__file__).resolve().parents[1]
WORKSPACE=BASE.parents[2]
HERE=Path(__file__).resolve().parent
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-preparation-r1'
PREP=BASE/'cpu-long-cuts-cloud-preparation-r1'
def require(v,m):
 if not v:raise AssertionError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode),'Not regular '+str(p));return {'bytes':s.st_size,'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid,'sha256':sha(p)}
def save(path,value):
 with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def frozen_files(root,name,expected):
 manifest=root/name;require(sha(manifest)==expected,'Frozen manifest changed');value=json.loads(manifest.read_text());files=value['files'];actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()};require(actual==set(files)|{name},'Unexpected/omitted closed files '+str(root))
 for rel,wanted in files.items():
  got=row(root/rel);require(all(got[k]==v for k,v in wanted.items()),'Source manifest mismatch '+rel)
 return sorted(actual)
def main():
 require(not OUT.exists(),'New evidence path required');require(shutil.disk_usage(WORKSPACE).free>512*1024**2,'Local free floor')
 frozen=json.loads((PREP/'LOCAL_PREPARATION_FROZEN.json').read_text());require(sha(PREP/'LOCAL_PREPARATION_FROZEN.json')=='f4025d2ce6c6ca7d94ebe612f561890192c87deb57fc91169f3ebd0f0b1c6107','Controller freeze changed')
 for rel,wanted in frozen['files'].items():
  got=row(PREP/rel);require(all(got[k]==v for k,v in wanted.items()),'Frozen controller file changed '+rel)
 selected=[]
 def add(root,relative,prefix):selected.append((root/relative,prefix+'/'+relative))
 for rel in list(frozen['files'])+['LOCAL_PREPARATION_FROZEN.json','long-parser/COPY_BINDINGS.json','test_long_metadata.py','ACTUAL_LINUX_BINDING_R1.json']:add(PREP,rel,'preparation')
 for dirname in ['guards-r1','guards-r2','guards-r3','parser-guards-r1']:
  source=PREP/dirname
  for p in sorted(source.rglob('*')):
   require(not p.is_symlink(),'Symlink refused')
   if p.is_file():add(PREP,str(p.relative_to(PREP)),'preparation')
 stage=BASE/'cpu-long-cuts-stage-preparation-r1';stage_names=frozen_files(stage,'HELPERS_FROZEN.json','d4b8a9c58c35f44b96b2f194b995a7e45b15ebc5189f8eac10863ca1faa70617')
 for rel in stage_names:add(stage,rel,'stage-launch')
 close=BASE/'cpu-long-cuts-close-preparation-r1';close_names=frozen_files(close,'PREPARATION_FROZEN.json','2ae474f46e970e23f8a63d33c0b928501cd56ab7fa6d7af99188eca88e75c798')
 for rel in close_names:add(close,rel,'close-probe')
 for dirname,expected in [('cpu-long-cuts-peer-review-r1','ad674'),('cpu-long-cuts-peer-review-r2','22f9eadaff86b1e32941808e14ff89cbe015e27587c0c2d9499e333001e548c7')]:
  source=BASE/dirname;require({p.name for p in source.iterdir()}=={'REVIEW.json'},'Unexpected peer review inputs');require(sha(source/'REVIEW.json').startswith(expected),'Peer review changed');add(source,'REVIEW.json','peer-review/'+dirname.rsplit('-',1)[1])
 require(len({dest for _,dest in selected})==len(selected),'Duplicate output')
 rows={dest:{'source':str(src),**row(src)} for src,dest in selected};require(sum(v['bytes'] for v in rows.values())<8*1024**2,'Bounded source-only proof cap')
 save(HERE/'REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Local closed source/preparation archival only; no Java/SSH/Git/native/raw','output':str(OUT),'inputFiles':rows,'sourceDirectoryClosureScopes':['stage-launch','close-probe','peer-review/r1','peer-review/r2'],'controllerSourceSelection':'Exact27frozen stageable files plus explicitly named closed guards/copy-bindings/localmetadata-test/historicalbinding; excluded six-input metadata bundle/JARs/actual root ready files and all cloud jobs'})
 OUT.mkdir(parents=True,exist_ok=False)
 for src,dest in selected:
  target=OUT/dest;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target);wanted={k:v for k,v in rows[dest].items() if k!='source'};require(row(target)==wanted,'Copy metadata drift '+dest);require(row(src)==wanted,'Source changed during copy '+dest)
 save(OUT/'SOURCE_COPY_BINDINGS.json',{'allSelectedInputsUnchangedBeforeAfter':True,'allCopiedBytesModesOwnersEqual':True,'files':rows,'selectedInputFiles':len(rows),'selectedInputBytes':sum(v['bytes'] for v in rows.values()),'wholeClosedDirectorySourceDirs':{prefix:{str(p.relative_to(root)) or '.':{'mode':p.stat().st_mode&0o777,'uid':p.stat().st_uid,'gid':p.stat().st_gid}for p in [root]+sorted(q for q in root.rglob('*') if q.is_dir())}for root,prefix in [(stage,'stage-launch'),(close,'close-probe'),(BASE/'cpu-long-cuts-peer-review-r1','peer-review/r1'),(BASE/'cpu-long-cuts-peer-review-r2','peer-review/r2')]}})
 zip_report=[]
 patterns={'privateKey':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED)? ?PRIVATE KEY-----'),'githubToken':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),'awsAccess':re.compile(rb'AKIA[0-9A-Z]{16}'),'openaiToken':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),'runpodToken':re.compile(rb'rpa_[A-Za-z0-9]{20,}')};findings=[]
 def scan(name,b):
  for key,pattern in patterns.items():
   for match in pattern.finditer(b):findings.append({'path':name,'marker':key,'offset':match.start()})
 for dest in rows:
  file=OUT/dest;scan(dest,file.read_bytes())
  if file.suffix=='.zip':
   registration=json.loads((file.parent/'registration.json').read_text());expected=registration.get('files',registration.get('sourceFiles'));require(isinstance(expected,dict),'Missing ZIP input manifest')
   with zipfile.ZipFile(file) as z:
    require(z.testzip() is None,'ZIP CRC failure');names=z.namelist();require(len(names)==len(set(names)) and set(names)==set(expected),'ZIP full name closure differs');members=[]
    for info in z.infolist():
     rel=Path(info.filename);require(not rel.is_absolute() and '..'not in rel.parts and not info.is_dir(),'Unsafe ZIP member');b=z.read(info);wanted=expected[info.filename];require(len(b)==wanted['bytes'] and hashlib.sha256(b).hexdigest()==wanted['sha256'],'ZIP source payload mismatch');scan(dest+'!'+info.filename,b);members.append({'path':info.filename,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'zipExternalMode':info.external_attr>>16})
   zip_report.append({'path':dest,'archiveSha256':sha(file),'allEntryCrcShaSizeVerified':True,'entries':members})
 save(OUT/'HISTORICAL_SOURCE_ZIP_REVIEW.json',{'passed':True,'allSourceZipsReviewed':len(zip_report),'zipEntries':sum(len(r['entries'])for r in zip_report),'archives':zip_report,'noExtraction':True})
 save(OUT/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'scope':'Bounded known marker scan, not a general secret absence guarantee','copiedFiles':len(rows),'allZipPayloadsScanned':True,'findings':findings,'passed':not findings});require(not findings,'Known credential marker findings retained for review')
 external={}
 for dirname in ['release-metadata-r1','local-native-validation-r1']:
  root=OUT.parent/dirname
  for name in ['MANIFEST.json','CLOSED.json']:
   f=root/name;external[str(f.relative_to(OUT.parent))]=row(f)
 fixtures=BASE/'cpu-idle-cloud-preparation-r2';external_runtime={}
 for f in [fixtures/'owned_linux_base_8eeb.py',fixtures/'shutdown_warning.py',fixtures/'candidate/release/current-stopped-original-state.json',BASE/'remote.py']:external_runtime[str(f)]=row(f)
 save(OUT/'EXTERNAL_CLOSED_BINDINGS.json',{'alreadyArchivedNoDuplicateMetadataJarBundle':external,'stageGuardExternalFixtureDependenciesNotIncludedInOriginalGuardZip':external_runtime,'closeGuardReleaseFixtureCopy':'preparation/release.template.json','historicalControllerBodyBindings':'preparation/guards-r1 andguards-r2/registered-sources.zip; actual failed andsuccessful source snapshots retained','noCloudResultsOrRootReadyReleaseIncluded':True,'note':'External fixture dependencies are exact current closed byte references; original guard registrations did not capture their bodies. They are not claimed to be new actual release evidence.'})
 (OUT/'README.md').write_text("""# Closed CPU long-cut cloud preparation

This is the frozen source/preparation snapshot with scope `DRAFT_ROOT_FREEZE_PENDING`. It records no CPU benchmark execution or result. Later root ready-release, staging, launch, collection and raw measurements are excluded even if they exist elsewhere.

`preparation/` preserves the final27file stage map, manifestf4025d2c, controller1d4103af, exact9authoritative parser/test copies and mapping, all three historical guard attempts and original source ZIPs. Local guards17/19/23 passed; the final23 comprises19stageable controller plus4localmetadata tests. The byte-exact parser copies separately passed33guards. Linux staging must run52tests; localmetadata4 are not cloud commands.

`peer-review/r1` records the three findings against b3af: missing observation SHA/PID crossbindings and discarded prerequisite proof semantics. `r2` independently rehashes all27files and closes those findings against1d4103af. The historical findings are retained.

`stage-launch/` is the closed d4b8 helper draft. Its first synthetic guard attempt failed an assertion; attempts2/3 passed, final24guards. `close-probe/` preserves2ae474 and13synthetic guards. These are source/control-plane guards, not actual root-freeze validation, Linux staging, remote observation or authorization to start work. Synthetic fixtures are explicitly separate from actual release evidence.

The local native remains functional-only with26late arrivals and schedulerTimingValidfalse. The future CPU controller/parser default remains strict, with no diagnostic scheduler bypass. No stable500/s, maximum throughput, zero latency, independent-host UDP or100M result follows from this preparation.

The six-input metadata JAR/class/source bundle and actual Linux metadata/identity proof are already archived under the sibling `release-metadata-r1`; exact closed-file hashes are bound without duplicating the bundle. Full native/auditor proof is already in `local-native-validation-r1`. No original state, PG data, SSH key, environment file, cloud job, or sparse recording tree is included.

Source SHA/size/modes/owners are checked before/after copying. ZIP entries are fully CRC/SHA checked without extraction, and known credential markers are reviewed. Guard ZIPs preserve the exact original registered source set; external fixture dependencies omitted by historical registrations are disclosed by exact current closed reference, rather than retroactively claiming their original capture. Documentation/provenance was updated after final code tests; all tested code/fixture inputs stayed byte-identical.

MANIFEST covers every regular file/directory/mode/owner in this proof except only itself andCLOSED. CLOSED binds that manifest; archive helper execution metadata is retained in `archiver/`.
""")
 save(HERE/'COPY_COMPLETE.json',{'passed':True,'copiedInputFiles':len(rows),'copiedInputBytes':sum(v['bytes'] for v in rows.values()),'zipArchives':len(zip_report),'zipEntries':sum(len(r['entries'])for r in zip_report),'knownMarkerFindings':len(findings),'output':str(OUT),'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeBytes':shutil.disk_usage(WORKSPACE).free})
 print(json.dumps(json.loads((HERE/'COPY_COMPLETE.json').read_text())))
if __name__=='__main__':main()
