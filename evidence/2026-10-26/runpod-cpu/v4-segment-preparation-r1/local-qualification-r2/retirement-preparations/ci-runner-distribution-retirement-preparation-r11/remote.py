from pathlib import Path,PurePosixPath
import hashlib,tarfile,os,stat,json,shutil,time
base=Path('/opt/vectormatch-cpu/ci');out=base/'runner-distribution-cache-retirement-r11';assert not out.exists()
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:argv=(p/'cmdline').read_bytes().split(b'\0');name=Path(os.fsdecode(argv[0])).name
 except(FileNotFoundError,ProcessLookupError):continue
 assert name not in ('java','javaw','postgres','postmaster','Runner.Listener','Runner.Worker'),name
archive=base/'production-correctness-r1/runner.tar.gz'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
assert archive.stat().st_size==227944224 and sha(archive)=='08e9ccb3604d2462c24b5e33604dc30810296ca15cc65f23cffd4317eb144c37'
expected={}
with tarfile.open(archive)as t:
 for member in t:
  path=PurePosixPath(member.name);name=path.as_posix()
  if not name.startswith(('bin/','externals/'))or member.isdir():continue
  assert not path.is_absolute()and '..'not in path.parts
  if member.isfile():
   h=hashlib.sha256();f=t.extractfile(member)
   for block in iter(lambda:f.read(1024**2),b''):h.update(block)
   expected[name]=dict(type='file',bytes=member.size,sha256=h.hexdigest())
  elif member.issym():expected[name]=dict(type='symlink',target=member.linkname)
  else:raise AssertionError('unexpected package member type')
assert len(expected)>100
selections=[];roots=[]
for n in [23]:
 root=base/('production-correctness-r'+str(n));runner=root/'runner'
 assert not(runner/'.runner').exists()and not(runner/'.credentials').exists()
 seen={};allocated=0
 for directory in ('bin','externals'):
  target=runner/directory;assert target.is_dir()and not target.is_symlink();roots.append(target)
  for parent,dirs,files in os.walk(target,followlinks=False):
   for entry in list(dirs)+files:
    p=Path(parent)/entry;s=p.lstat();label=p.relative_to(runner).as_posix()
    if stat.S_ISLNK(s.st_mode):seen[label]=dict(type='symlink',target=os.readlink(p))
    elif stat.S_ISREG(s.st_mode):seen[label]=dict(type='file',bytes=s.st_size,sha256=sha(p));allocated+=s.st_blocks*512
    else:assert stat.S_ISDIR(s.st_mode)
 assert seen==expected,'distribution changed;refuse retirement '+str(n)
 selections.append(dict(attempt=n,paths=[str(runner/'bin'),str(runner/'externals')],allPackageBodiesMatched=len(seen),allocatedBytes=allocated))
protected={}
for p in (base/'collections').glob('*/complete-code-compiled-tests-and-public-logs.tar.gz'):protected[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p))
assert len(protected)==22
out.mkdir();before=dict(atUTC=time.time(),freeBytes=shutil.disk_usage(base).free,archiveSha256=sha(archive),selections=selections,originalPackageMemberPins=expected,protectedOriginalCollectionArchives=protected,noCredentialsOrWorktreeOrCompiledTestsOrLogsOrNativeEvidenceSelected=True)
(out/'BEFORE.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
for target in roots:
 assert target.parent.name=='runner'and target.name in ('bin','externals')and target.is_dir()and not target.is_symlink()
 shutil.rmtree(target)
assert all(not p.exists()for p in roots)
for name,pin in protected.items():p=Path(name);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
result=dict(passed=True,freeBefore=before['freeBytes'],freeAfter=shutil.disk_usage(base).free,retiredAllocatedBytes=sum(x['allocatedBytes']for x in selections),retiredDistributionDirectories=len(roots),protectedOriginalCollectionsUnchanged=len(protected),allSelectedBodiesByteEqualPinnedReconstructibleDistribution=True,noStorageFloorLowered=True,noAppStateOrEvidenceDeleted=True)
(out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
