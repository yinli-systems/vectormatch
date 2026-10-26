from pathlib import Path
import hashlib,os,stat,shutil,json,socket,time
assert socket.gethostname()=='33ace3d92505';base=Path('/opt/vectormatch-cpu/ci');out=base/'completed-jdk-cache-retirement-r7';assert not out.exists()
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:argv=(p/'cmdline').read_bytes().split(b'\0');name=Path(os.fsdecode(argv[0])).name
 except(FileNotFoundError,ProcessLookupError):continue
 assert name not in('java','javaw','postgres','postmaster','Runner.Listener','Runner.Worker'),name
canonical=Path('/opt/vectormatch-cpu/tools/jdk-21.0.13+9');assert canonical.is_dir()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def tree(root):
 result={}
 for p in sorted(root.rglob('*')):
  if not p.is_file():continue
  assert os.path.commonpath([str(root.resolve()),str(p.resolve())])==str(root.resolve())
  result[p.relative_to(root).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
 return result
reference=tree(canonical);assert len(reference)==454
selected=[]
for n in [23]:
 root=base/('production-correctness-r'+str(n));target=root/'toolcache/Java_Temurin-Hotspot_jdk/21.0.13-9.0.LTS/x64'
 assert not(root/'runner/.runner').exists()and not(root/'runner/.credentials').exists()
 assert target.is_dir()and not target.is_symlink()and os.path.commonpath([str(root.resolve()),str(target.resolve())])==str(root.resolve())
 assert os.path.commonpath([str(target.resolve()),str(canonical.resolve())])!=str(target.resolve())
 assert tree(target)==reference,'JDK cache differs;refuse all retirement'
 allocated=sum(p.lstat().st_blocks*512 for p in [target,*target.rglob('*')]);selected.append(dict(attempt=n,path=str(target),allocatedBytes=allocated,all454FileBodiesMatch=True))
protected={str(p):dict(bytes=p.stat().st_size,sha256=sha(p))for p in(base/'collections').glob('*/complete-code-compiled-tests-and-public-logs.tar.gz')};assert len(protected)==22
native={str(p):dict(bytes=p.stat().st_size,sha256=sha(p))for p in Path('/opt/vectormatch-cpu/collections').glob('async-v4-capacity-500-*-r1/complete-native-point-and-independent-audit.tar.gz')};assert len(native)==4
out.mkdir();before=dict(atUTC=time.time(),freeBytes=shutil.disk_usage(base).free,referenceRoot=str(canonical),all454ReferenceFilePins=reference,selections=selected,protectedAll22OriginalCiCollections=protected,protectedFourCompleteNativeCollections=native,noApplicationStateOrEvidenceSourceOrLogOrKeySelected=True);(out/'BEFORE.json').write_text(json.dumps(before,indent=2,sort_keys=True)+chr(10))
for row in selected:
 target=Path(row['path']);assert target.name=='x64'and target.parent.name=='21.0.13-9.0.LTS'and target.parent.parent.name=='Java_Temurin-Hotspot_jdk'and not target.is_symlink();shutil.rmtree(target)
assert all(not Path(row['path']).exists()for row in selected)and tree(canonical)==reference
for name,pin in {**protected,**native}.items():
 p=Path(name);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
result=dict(passed=True,retiredDirectories=len(selected),retiredAllocatedBytes=sum(r['allocatedBytes']for r in selected),freeBefore=before['freeBytes'],freeAfter=shutil.disk_usage(base).free,canonicalRuntimeJdkAll454BodiesUnchanged=True,all22OriginalCiAndFourNativeCollectionsUnchanged=True,noApplicationOrRawEvidenceDeleted=True,noDiskFloorLowered=True)
(out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+chr(10));print(json.dumps(result))
