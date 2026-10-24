import pathlib,json,base64,sys,hashlib,os,socket,tarfile,importlib.util,subprocess,time,traceback,re
c=json.loads(base64.b64decode(sys.argv[1]));root=pathlib.Path(c['root']);assert str(root)=='/opt/vectormatch-cpu/tools/cpu-jfr-attach-probe-r1'and socket.gethostname()=='33ace3d92505'and not root.exists()
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,x):
 with p.open('x')as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
assert sha(c['java'])==c['javaSha256']and sha(c['jcmd']['canonicalPath'])==c['jcmd']['jcmdSha256']
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:name=pathlib.Path(os.fsdecode((p/'cmdline').read_bytes().split(b'\0')[0])).name
 except (FileNotFoundError,ProcessLookupError):continue
 assert name not in ['java','javaw','postgres','postmaster'],'Foreign JVM/SQL active'
for p in root.parents:assert p.is_dir()and not p.is_symlink()
os.umask(0o077);root.mkdir(mode=0o700);raw=sys.stdin.buffer.read(1024*1024+1);assert len(raw)<=1024*1024 and hashlib.sha256(raw).hexdigest()==c['bundleSha256'];(root/'input-bundle.tar.gz').write_bytes(raw);seen=set()
with tarfile.open(root/'input-bundle.tar.gz','r:gz')as t:
 for member in t:
  assert member.isfile()and member.name in c['rows']and member.name not in seen and '/'not in member.name;row=c['rows'][member.name];body=t.extractfile(member).read();assert member.size==row['bytes']and hashlib.sha256(body).hexdigest()==row['sha256'];p=root/member.name;p.write_bytes(body);p.chmod(row['mode']);seen.add(member.name)
assert seen==set(c['rows']);assert sha(root/'owned_linux_base_8eeb.py')=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87'
spec=importlib.util.spec_from_file_location('owned',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.enable_pidfd();handles=[];identities=[];env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'}
def identity(child,args):
 for unused in range(100):
  current=b.process_identity(child.pid)
  if current is not None and current['arguments']==args:assert current['commandSha256']==b.argv_digest(args);return current
  if child.poll()is not None:break
  time.sleep(.005)
 raise RuntimeError('Exact child exec identity unavailable')
def owned_tool(label,args):
 with(root/(label+'.stdout')).open('xb')as out,(root/(label+'.stderr')).open('xb')as err:child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env,start_new_session=True)
 handles.append(child);record=identity(child,args);identities.append(record);save(root/(label+'-identity.json'),record)
 try:status=child.wait(timeout=15)
 except subprocess.TimeoutExpired:b.stop_owned(record,10);child.wait(timeout=2);raise
 text=(root/(label+'.stdout')).read_text();error=(root/(label+'.stderr')).read_text();save(root/(label+'-execution.json'),dict(exitCode=status,strictPidAbsent=not pathlib.Path('/proc',str(child.pid)).exists()))
 assert status==0 and not re.search(r'unknown argument|could not|exception|error|failed',text+'\n'+error,re.I),'jcmd rejected diagnostic command'
 return text
args=[c['java'],'-Xmx64m','-cp',str(root),'AttachForceProbe',str(root)]
with(root/'probe.stdout').open('xb')as out,(root/'probe.stderr').open('xb')as err:child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env=env,start_new_session=True)
handles.append(child);record=None;error=None
try:
 record=identity(child,args);identities.append(record);save(root/'probe-identity.json',record)
 end=time.monotonic()+10
 while not(root/'ready').exists():assert child.poll()is None and time.monotonic()<end;time.sleep(.01)
 assert(root/'ready').read_text()==str(child.pid);repository=root/'repository';repository.mkdir(mode=0o700)
 cmd=[c['jcmd']['canonicalPath'],'-J-Xmx64m',str(child.pid)]
 configured=owned_tool('configure',cmd+['JFR.configure','repositorypath='+str(repository),'maxchunksize=1m']);assert str(repository)in configured
 assert b.matching_identity(record)is not None
 started=owned_tool('start',cmd+['JFR.start','name=vectormatch-force-probe','settings='+str(root/'force-only.jfc'),'filename='+str(root/'probe.jfr'),'dumponexit=true','maxsize=8m','disk=true']);assert 'Started recording'in started
 assert b.matching_identity(record)is not None;(root/'go').write_text('authorised synthetic32KiB force probe\n');child.wait(timeout=20);assert child.returncode==0 and json.loads((root/'completed.json').read_text())['passed']
except BaseException as caught:error=repr(caught);save(root/'FAILURE.json',dict(error=error,traceback=traceback.format_exc()));raise
finally:
 for handle in handles:
  if handle.poll()is None:
   known=next((r for r in identities if r['pid']==handle.pid),None)
   assert known is not None,'No unverified PID signal allowed';b.stop_owned(known,10);handle.wait(timeout=2)
 closure=dict(allOwnedStrictlyPidAbsent=all(not pathlib.Path('/proc',str(h.pid)).exists()for h in handles),forcedKill=False,allOriginalFilesRetained=True,identities=identities);save(root/'CLOSURE.json',closure)
assert closure['allOwnedStrictlyPidAbsent']and(root/'probe.jfr').stat().st_size<=16*1024*1024
result=dict(passed=True,syntheticForceCalls=4,recordingBytes=(root/'probe.jfr').stat().st_size,recordingSha256=sha(root/'probe.jfr'),jcmdAttachOnExactOwnedPidSupported=True,allOwnedStrictlyPidAbsent=True,noClusterOrOrdersStarted=True,root=str(root));save(root/'SUCCESS.json',result);print(json.dumps(result))
