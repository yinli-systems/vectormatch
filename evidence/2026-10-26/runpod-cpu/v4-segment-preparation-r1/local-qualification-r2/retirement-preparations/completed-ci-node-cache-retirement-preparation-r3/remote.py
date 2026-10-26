from pathlib import Path
import hashlib,os,stat,shutil,json,socket,time
assert socket.gethostname()=='33ace3d92505';base=Path('/opt/vectormatch-cpu/ci');out=base/'completed-node-cache-retirement-r3';assert not out.exists()
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:argv=(p/'cmdline').read_bytes().split(b'\0');name=Path(os.fsdecode(argv[0])).name
 except(FileNotFoundError,ProcessLookupError):continue
 assert name not in('java','javaw','postgres','postmaster','Runner.Listener','Runner.Worker'),name
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def tree(root):
 result={}
 for parent,dirs,files in os.walk(root,followlinks=False):
  for name in list(dirs)+files:
   p=Path(parent)/name;s=p.lstat();label=p.relative_to(root).as_posix()
   if stat.S_ISDIR(s.st_mode):result[label]=dict(type='directory')
   elif stat.S_ISLNK(s.st_mode):
    assert os.path.commonpath([str(root),str(p.resolve())])==str(root)
    result[label]=dict(type='symlink',target=os.readlink(p))
   else:assert stat.S_ISREG(s.st_mode);result[label]=dict(type='file',bytes=s.st_size,sha256=sha(p))
 return result
canonical=base/'production-correctness-r21/toolcache/node/24.22.1/x64';assert canonical.is_dir()and not canonical.is_symlink()
reference=tree(canonical);assert len(reference)>100
selected=[]
for n in [3,4,5,6,22,23]:
 root=base/('production-correctness-r'+str(n));target=root/'toolcache/node/24.22.1/x64'
 assert not(root/'runner/.runner').exists()and not(root/'runner/.credentials').exists()
 assert target.is_dir()and not target.is_symlink()and tree(target)==reference,'node image differs;refuse all retirement'
 selected.append(dict(attempt=n,path=str(target),allocatedBytes=sum(p.lstat().st_blocks*512 for p in [target,*target.rglob('*')]),allBodiesEqualRetainedCanonical=True))
protected={str(p):dict(bytes=p.stat().st_size,sha256=sha(p))for p in(base/'collections').glob('*/complete-code-compiled-tests-and-public-logs.tar.gz')};assert len(protected)==22
out.mkdir();before=dict(atUTC=time.time(),freeBytes=shutil.disk_usage(base).free,canonicalRoot=str(canonical),canonicalPins=reference,selections=selected,protectedAll22CiArchives=protected,noClassesSourceLogsResultsKeysOrApplicationSelected=True);(out/'BEFORE.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
for row in selected:
 target=Path(row['path']);assert target.name=='x64'and target.parent.name=='24.22.1'and target.parent.parent.name=='node'and tree(target)==reference;shutil.rmtree(target)
assert tree(canonical)==reference and all(not Path(row['path']).exists()for row in selected)
for name,pin in protected.items():p=Path(name);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
result=dict(passed=True,retiredDirectories=len(selected),retiredAllocatedBytes=sum(r['allocatedBytes']for r in selected),freeBefore=before['freeBytes'],freeAfter=shutil.disk_usage(base).free,retainedCanonicalUnchanged=True,all22OriginalCiArchivesUnchanged=True,noApplicationOrRawEvidenceDeleted=True,noDiskFloorLowered=True)
(out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
