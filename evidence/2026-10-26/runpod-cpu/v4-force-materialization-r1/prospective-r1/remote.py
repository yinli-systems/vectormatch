from pathlib import Path
import json,sys,os,socket,shutil,hashlib,base64,subprocess,time,importlib.util,tarfile
c=json.load(sys.stdin);phase=c['phase'];assert phase in ['qualification','c1','d1','c2','d2']
root=Path('/opt/vectormatch-cpu/experiments/v4-force-materialization-r1');baseline=c['baseline']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def environment():
 assert socket.gethostname()==baseline['host']and Path('/proc/sys/kernel/random/boot_id').read_text().strip()==baseline['bootId']
 assert sorted(os.sched_getaffinity(0))==baseline['affinity']and Path('/sys/fs/cgroup/cpu.max').read_text()==baseline['cpuMax']and Path('/sys/fs/cgroup/memory.max').read_text()==baseline['memoryMax']
 assert all(not Path(p).exists()for p in baseline['absentProtectedPaths'])
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:a=(p/'cmdline').read_bytes().split(bytes([0]));name=Path(os.fsdecode(a[0])).name
  except(FileNotFoundError,ProcessLookupError):continue
  assert name not in('java','javac','javaw','postgres','postmaster','Runner.Listener','Runner.Worker'),name
 assert sha(Path(c['java']))==c['javaSha256']and sha(Path(c['java']).parent.parent/'release')==c['releaseSha256']
 assert shutil.disk_usage(root.parent).free>=3*1024**3+384*1024**2
environment();os.umask(0o077)
if phase=='qualification':
 assert not root.exists();root.mkdir(mode=0o700);(root/'inputs').mkdir()
 for n,pin in c['files'].items():
  p=Path(n);assert not p.is_absolute()and'..'not in p.parts;b=base64.b64decode(pin['body']);assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256'];target=root/'inputs'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
else:
 assert root.is_dir()and not root.is_symlink();previous={'c1':'qualification','d1':'c1','c2':'d1','d2':'c2'}[phase]
 assert json.loads((root/(previous+'-MANIFEST.json')).read_text())['passed']
for n,pin in c['files'].items():assert sha(root/'inputs'/n)==pin['sha256']
spec=importlib.util.spec_from_file_location('qualified_base',root/'inputs/owned_linux_base_8eeb.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.enable_pidfd()
spec=importlib.util.spec_from_file_location('scope_tar',root/'inputs/scope_tar.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
out=root/(phase+'-control');assert not out.exists();out.mkdir();base.save(out/'REGISTRATION.json',dict(phase=phase,sourcePins={n:{k:v for k,v in p.items()if k!='body'}for n,p in c['files'].items()},standaloneOnly=True,applicationStateNeverOpened=True))
cases=[('q-sparse','sparse',1,4),('q-materialized','materialized',1,4)]if phase=='qualification'else[(phase,'sparse'if phase[0]=='c'else'materialized',128,3000)]
results=[];records=[]
for name,mode,mib,steps in cases:
 environment();target=root/name;assert not target.exists()
 args=[c['java'],'-Xms128m','-Xmx128m','-cp',str(root/'inputs/classes'),'ForceMaterializationProbe',str(target),mode,str(mib),str(steps)]
 env={k:v for k,v in os.environ.items()if k not in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']}
 with(out/(name+'.stdout')).open('xb')as stdout,(out/(name+'.stderr')).open('xb')as stderr:p=subprocess.Popen(args,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
 record=None
 for unused in range(200):
  identity=base.process_identity(p.pid)
  if identity is not None and identity['arguments']==args:record=identity;break
  if p.poll()is not None:break
  time.sleep(.005)
 assert record is not None,'Identity unproven;no unregistered signal';base.save(out/(name+'-STARTED.json'),record);records.append(record)
 try:
  deadline=time.monotonic()+90
  while not(target/'READY.json').exists():
   assert p.poll()is None and time.monotonic()<deadline,'initialization failed/deadline';assert shutil.disk_usage(root).free>=1024**3;time.sleep(.02)
  ready=json.loads((target/'READY.json').read_text());assert ready['pid']==record['pid']and ready['mode']==mode
  observations=[]
  for n in range(3):
   path=target/('writer-'+str(n)+'.bin');st=path.stat();assert not path.is_symlink()and st.st_size==mib*1024**2
   allocated=st.st_blocks*512;assert (allocated>=st.st_size)if mode=='materialized'else(allocated<st.st_size)
   observations.append(dict(name=path.name,bytes=st.st_size,allocatedBytes=allocated,device=st.st_dev,inode=st.st_ino))
  base.save(out/(name+'-READY_STAT.json'),dict(ready=ready,files=observations));assert base.matching_identity(record) is not None
  (target/'GO').write_text('qualified same-filesystem standalone experiment\n')
  deadline=time.monotonic()+180
  while p.poll()is None:
   assert time.monotonic()<deadline,'workload deadline';assert shutil.disk_usage(root).free>=1024**3;time.sleep(.1)
  assert p.wait(timeout=5)==0,(out/(name+'.stderr')).read_text()
 finally:
  if p.poll()is None:base.stop_owned(record,5);p.wait(timeout=5)
 assert base.matching_identity(record)is None and not Path('/proc',str(record['pid'])).exists()
 r=json.loads((target/'RESULT.json').read_text());assert r['passed']and r['mode']==mode and len(r['writers'])==3
 assert all(w['force']['count']==steps and w['fullReadbackBytes']==mib*1024**2 for w in r['writers']);results.append(r)
if phase=='qualification':assert [w['fullReadbackSha256']for w in results[0]['writers']]==[w['fullReadbackSha256']for w in results[1]['writers']]
environment()
for n,pin in c['files'].items():assert sha(root/'inputs'/n)==pin['sha256']
base.save(out/'RESULT.json',dict(passed=True,phase=phase,results=results,ownedProcesses=records,strictOwnedProcessesAbsent=True,noApplicationStateOpened=True,sourceInputsUnchanged=True,freeBytesAfter=shutil.disk_usage(root).free))
paths={'control':out};paths.update({name:root/name for name,mode,mib,steps in cases});scopes={name:scope.tree(path)for name,path in paths.items()}
collection=Path('/opt/vectormatch-cpu/collections')/('v4-force-materialization-'+phase+'-r1');assert not collection.exists();collection.mkdir();archive=collection/'complete-original-files.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1)as t:
 for name,path in paths.items():t.add(path,arcname='original/'+name)
review=scope.verify(archive,scopes);assert all(scope.tree(path)==scopes[name]for name,path in paths.items())
manifest=dict(passed=True,phase=phase,results=results,sourceScopes=scopes,everyOriginalMemberVerified=review,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),strictOwnedProcessesAbsent=True,noNativeTradingPerformanceClaim=True)
base.save(root/(phase+'-MANIFEST.json'),manifest);print(json.dumps(manifest))
