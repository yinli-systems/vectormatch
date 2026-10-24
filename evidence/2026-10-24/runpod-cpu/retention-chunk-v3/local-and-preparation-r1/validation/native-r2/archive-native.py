from pathlib import Path
import datetime,gzip,hashlib,json,os,stat,tarfile
work=Path.cwd();base=work/'cluster/build/retention-chunk-native-attempts';out=work/'build/chunk-validation/native-success-archives';out.mkdir(exist_ok=False)
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
results=[]
for root in sorted(base.glob('attempt-*')):
 if not (root/'pair-completion.json').exists():continue
 pair=json.loads((root/'pair-completion.json').read_text());assert pair['passed'] is True
 for cap in [3072,6144]:
  c=json.loads((root/f'chunk-{cap}/completion.json').read_text());assert c['passed'] is True and c['allOwnedStopped'] is True
 dest=out/root.name;dest.mkdir();files={};dirs={}
 for p in sorted(root.rglob('*')):
  s=p.lstat();rel=p.relative_to(root).as_posix();assert not stat.S_ISLNK(s.st_mode)
  if p.is_dir():dirs[rel]={'mode':stat.S_IMODE(s.st_mode)}
  else:
   assert stat.S_ISREG(s.st_mode);files[rel]={'sha256':sha_file(p),'bytes':s.st_size,'mode':stat.S_IMODE(s.st_mode)}
 archive=dest/'native-state.tar.gz'
 with archive.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as tar:
  for rel in sorted(set(dirs)|set(files)):tar.add(root/rel,arcname=rel,recursive=False)
 read_files={};read_dirs={}
 with tarfile.open(archive,'r|gz') as tar:
  for m in tar:
   if m.isdir():read_dirs[m.name]={'mode':m.mode}
   else:
    assert m.isfile();f=tar.extractfile(m);h=hashlib.sha256();n=0
    for b in iter(lambda:f.read(1024*1024),b''):h.update(b);n+=len(b)
    read_files[m.name]={'sha256':h.hexdigest(),'bytes':n,'mode':m.mode}
 assert read_files==files and read_dirs==dirs
 manifest={'capturedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceRoot':str(root),'attemptStatus':'PASSED-local-functional','rootMode':stat.S_IMODE(root.stat().st_mode),'allOwnedStoppedFromCompletion':True,'originalsRetained':True,'fileCount':len(files),'directoryCount':len(dirs),'logicalBytes':sum(v['bytes'] for v in files.values()),'archiveBytes':archive.stat().st_size,'archiveSha256':sha_file(archive),'readbackEveryFileShaSizeModeAndDirectoryModePassed':True,'files':files,'directories':dirs,'scope':'Complete stopped native tree preserved, including sparse zero bytes in compressed tar; all file bytes/modes and directories re-read; no persistent-client or independent durability claim'}
 (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');results.append({'attempt':root.name,'manifest':str(dest/'manifest.json'),'manifestSha256':sha_file(dest/'manifest.json'),'files':len(files),'logicalBytes':manifest['logicalBytes'],'gzipBytes':manifest['archiveBytes']})
print(json.dumps(results))
