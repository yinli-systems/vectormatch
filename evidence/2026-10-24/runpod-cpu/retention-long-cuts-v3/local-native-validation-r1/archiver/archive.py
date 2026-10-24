import json,hashlib,stat,shutil,datetime,sys,subprocess
from pathlib import Path
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';V=B/'retention-long-cuts-v3-worktree/runtime/long-cuts-local-validation';N=V/'native-r1';A=B/'long-native-audit-preparation-r1';D=R/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/local-native-validation-r1'
def h(p):
 s=hashlib.sha256()
 with p.open('rb')as f:
  for x in iter(lambda:f.read(1024*1024),b''):s.update(x)
 return s.hexdigest()
def js(p):return json.loads(p.read_text())
def require(v,m):
 if not v:raise AssertionError(m)
def observation(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode),'regular '+str(p));return dict(bytes=s.st_size,sha256=h(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
require(h(N/'closed-originals/manifest.json')=='b6239c05b7949f844971f2b1dd6e416ba2ce80769eff245623ad4405bacacea7','native manifest')
require(h(A/'CLOSED.json')=='b78ea54897c665fe00a422259883572f32381e4a054d19d57ba3739510634221','audit closed')
require(h(B/'long-cuts-root-native-review-r1/ROOT_REVIEW.json')=='55b3bf21ea23dca8a34bb7a1c2baaf7235cce2ddbf6ec38100fe5a0edc0dd49d','root native proof')
require(not D.exists(),'new archive only');D.mkdir(mode=0o700);(D/'archiver').mkdir()
shutil.copy2(Path(__file__),D/'archiver/archive.py')
save(D/'archiver/REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Copy closed local synthetic native and all authoritative audit attempts;9sparse recording bodies remain in full compressed original archive, no sparse extraction','nativeManifest':str(N/'closed-originals/manifest.json'),'sourceCommit':'bcf49c10b77a14708b53d3fc6c115a6a3b834408','noJavaSshBusinessOrGit':True})
bindings=[]
def copy(source,target,expected=None):
 before=observation(source)
 if expected is not None:require(all(before[k]==expected[k]for k in before),'native original differs '+str(source))
 out=D/target;out.parent.mkdir(parents=True,exist_ok=True);require(not out.exists(),'exclusive copy '+str(out));shutil.copy2(source,out)
 require(observation(source)==before==observation(out),'copy bytes/mode/owner '+str(source));bindings.append({'source':str(source),'copy':target,'observation':before})
m=js(N/'closed-originals/manifest.json');omitted=[]
for row in m['entries']:
 rel=Path(row['path']).relative_to('native');target=Path('validation/native-r1')/rel
 if row['type']=='directory':
  p=D/target;p.mkdir(parents=True,exist_ok=True);p.chmod(row['mode']);continue
 if rel.suffix=='.rec':
  require(row['bytes']==134217728 and len(rel.parts)==4 and rel.parts[0]=='arm-100000-long-cuts'and rel.parts[1]in['node-0','node-1','node-2']and rel.parts[2]=='archive','exact nine recording omission');omitted.append(row);continue
 copy(N/rel,str(target),row)
require(len(omitted)==9,'exact nine recording bodies')
for p in sorted((N/'closed-originals').iterdir()):
 require(p.is_file()and not p.is_symlink(),'closed originals regular');copy(p,str(Path('validation/native-r1/closed-originals')/p.name))
for name in ['NATIVE_VALIDATION_COMPLETE_R1.json','NATIVE_RAW_ARRIVAL_CHECK_R1.json','SOURCE_FROZEN_R1.json','LOCAL_VALIDATION_COMPLETE.json']:
 copy(V/name,'validation/'+name)
for scope,source in [('native-archive-execution',V/'native-r1-archive-execution-r1'),('auditor',A),('root-native-review',B/'long-cuts-root-native-review-r1'),('root-auditor-review',B/'long-auditor-root-source-review-r1')]:
 for p in sorted(source.rglob('*')):
  require(not p.is_symlink(),'no source symlink')
  if p.is_file():copy(p,str(Path(scope)/p.relative_to(source)))
  elif p.is_dir():(D/scope/p.relative_to(source)).mkdir(parents=True,exist_ok=True)
save(D/'COMPRESSED_NATIVE_RECORDING_BINDINGS.json',{'fullArchiveSha256':'b73ad6c3333007f6938eb6989ab528461d83b17b6d3ab0170d6d805e5c56cc3b','archive':'validation/native-r1/closed-originals/native-originals.tar.gz','all191EntriesFullyStreamVerifiedByRoot':True,'sparseExtracted':False,'omittedStandaloneDuplicateBodies':omitted,'allOther159Minus9OriginalRegularFilesCopied':True})
save(D/'SOURCE_COPY_BINDINGS.json',{'passed':True,'files':bindings,'allCopiedSourcesRehashedBeforeAndAfter':True})
(D/'README.md').write_text('''# Qualified local long-cut native validation\n\nSource `bcf49c10b77a14708b53d3fc6c115a6a3b834408`, actual JAR fingerprint `6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8`. One fresh lineage accepted all 33,792 IOC orders at the requested 500/s over 67.584 seconds. The three setup commands share the first command cut; twelve maintenance cycles contain eleven full command cuts plus the trailing three commands. Cuts 2–11 are ten equivalent setup-free cuts.\n\nThis is FUNCTIONAL/CANONICAL evidence only: the local scheduler was invalid, with 26 arrivals released over 20ms late. No CPU performance, stable capacity, hard realtime or 100M result is admitted. Unknown observed/final, rejection, notSent and node warning counts are zero. All three final snapshot logs and the same-candidate reference agree; that reference is not an independent implementation.\n\nThe original native archive includes all 191 entries, 159 regular files, 32 directories and 1,334,578,086 logical bytes. Both the authoritative auditor and root streamed every original archive member and verified SHA/bytes/modes/owners/empty directories. Nine 128MiB recording bodies are retained inside that compressed archive; they are not duplicated as standalone extracted files. All other original native regular files, including the 80 consumed inputs, are copied here.\n\nAll auditor guards, the first failed derived audit, its source freezes and the successful corrected audit are retained. The failed assertion compared an intentionally empty Business reply hash against a later Position query hash. Source sends hashes only for Position. The correction verifies empty Business hashes and the Position hash format/frontiers; no raw Position query wire was captured, so its setup hash is not independently reconstructed. Full final reference bytes and all three snapshot checks remain verified. No business run was repeated.\n\nAn archived-byte reproduction is registered separately under `reproduction-r1`; it runs Python only, with no Java, driver, SSH or business execution. The frozen runner accepts the explicitly qualified local scheduler result; its imported raw parser defaults to strict scheduler admission for any future CPU collector.\n''')
repro=D/'reproduction-r1';save(D/'REPRODUCTION_REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':[sys.executable,'-B',str(D/'auditor/run_audit.py'),'--native',str(D/'validation/native-r1'),'--output',str(repro)],'sourceSha256':h(D/'auditor/run_audit.py'),'scope':'Archived closed-byte read-only reproduction, no new benchmark'})
r=subprocess.run([sys.executable,'-B',str(D/'auditor/run_audit.py'),'--native',str(D/'validation/native-r1'),'--output',str(repro)],capture_output=True,text=True)
(D/'reproduction.stdout').write_text(r.stdout);(D/'reproduction.stderr').write_text(r.stderr);require(r.returncode==0,'archived read-only audit reproduction failed; preserve partial archive')
actual=js(repro/'result.json');original=js(A/'audit-r2/result.json');require(actual==original,'archived full result must equal original every field')
save(D/'REPRODUCTION_COMPLETE.json',{'passed':True,'allResultFieldsExactlyEqual':True,'originalAndReproducedResultSha256':h(repro/'result.json'),'noRuntimeOriginalInputsUsed':True,'sourceUnchanged':h(D/'auditor/run_audit.py')==h(A/'run_audit.py'),'benchmarkExecuted':False})
for row in bindings:require(observation(Path(row['source']))==row['observation']==observation(D/row['copy']),'final source/copy unchanged')
save(D/'archiver/COMPLETION.json',{'exitCode':0,'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceCopies':len(bindings),'originalsUnchanged':True})
files={};dirs={}
for p in sorted([D,*D.rglob('*')]):
 name=str(p.relative_to(D));s=p.lstat()
 if p.is_dir():dirs[name]={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
 else:files[name]=observation(p)
save(D/'MANIFEST.json',{'files':files,'directories':dirs,'excludes':['MANIFEST.json','CLOSED.json'],'fileCount':len(files),'logicalBytes':sum(r['bytes']for r in files.values())})
save(D/'CLOSED.json',{'passed':True,'manifestSha256':h(D/'MANIFEST.json'),'sourceCopies':len(bindings),'filesBeforeManifestAndClosed':len(files),'allOriginalsRetained':True,'full191EntryArchiveRetained':True,'all80RawAuditorInputsRetained':True,'archivedByteReproductionExactlyEqual':True,'schedulerTimingValid':False,'lateOver20ms':26,'functionalOnly':True,'sourceCodeOrBenchmarkModified':False})
print(json.dumps({'passed':True,'manifestSha256':h(D/'MANIFEST.json'),'closedSha256':h(D/'CLOSED.json'),'files':len(files)+2,'logicalBytes':sum(r['bytes']for r in files.values())}))
