from pathlib import Path
import datetime,gzip,hashlib,json,stat,tarfile
w=Path.cwd();base=w/'build/window-validation/native-r1';root=Path(json.loads((base/'registration.json').read_text())['pairRoot']);out=base/'native-archive';out.mkdir()
assert json.loads((root/'pair-completion.json').read_text())['passed'] is True
assert all(json.loads((root/f'window-{i}/completion.json').read_text())['allOwnedStopped'] is True for i in (1,8))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
files={};dirs={}
for p in sorted(root.rglob('*')):
 s=p.lstat();n=p.relative_to(root).as_posix();assert not stat.S_ISLNK(s.st_mode)
 if stat.S_ISDIR(s.st_mode):dirs[n]={'mode':stat.S_IMODE(s.st_mode)}
 else:
  assert stat.S_ISREG(s.st_mode);files[n]={'bytes':s.st_size,'mode':stat.S_IMODE(s.st_mode),'sha256':sha(p)}
archive=out/'native-state.tar.gz'
with archive.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
 for n in sorted(set(files)|set(dirs)):tar.add(root/n,arcname=n,recursive=False)
readfiles={};readdirs={}
with tarfile.open(archive,'r|gz') as tar:
 for m in tar:
  if m.isdir():readdirs[m.name]={'mode':m.mode}
  else:
   assert m.isfile();f=tar.extractfile(m);h=hashlib.sha256();count=0
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b);count+=len(b)
   readfiles[m.name]={'bytes':count,'mode':m.mode,'sha256':h.hexdigest()}
assert readfiles==files and readdirs==dirs
result={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceRoot':str(root),'rootMode':stat.S_IMODE(root.stat().st_mode),'allOwnedStopped':True,'originalsRetained':True,'fileCount':len(files),'directoryCount':len(dirs),'logicalBytes':sum(v['bytes'] for v in files.values()),'gzipBytes':archive.stat().st_size,'gzipSha256':sha(archive),'allFileBytesModesAndDirectoriesReadBack':True,'files':files,'directories':dirs,'scope':'Complete local stopped six-node-process pair trees; sparse zero bytes preserved through compressed logical-byte tar; no cloud or independent durability claim'}
with (out/'manifest.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['files','directories']}))
