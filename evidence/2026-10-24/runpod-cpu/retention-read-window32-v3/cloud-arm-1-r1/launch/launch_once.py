from pathlib import Path
import json,hashlib,importlib.util,shlex,datetime
B=Path(__file__).resolve().parent.parent;O=Path(__file__).resolve().parent;C=B/'current-read-window32-controller-preparation-r1';H=B/'current-read-window32-collection-preparation-r1/remote_current.py';h=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();stage=json.loads((B/'current-read-window32-stage-correction-r3/STAGE_SUCCESS.json').read_text());preflight=json.loads((B/'current-read-window32-preflight-r2/stdout.json').read_text());r=json.loads((C/'root-release-r2/release.json').read_text());assert preflight['passed']and preflight['noJavaStarted']and preflight['controllerSha256']==r['controllerSha256']and stage['releaseSha256']==h(C/'root-release-r2/release.json');rows=stage['stagedFiles'];root=stage['remotePrep'];args=['/usr/bin/python3','-B',root+'/cpu_read_window32_abab.py','--arm','1','--release-sha256',stage['releaseSha256'],'--start-new']
program='rows='+repr(rows)+'\nroot_name='+repr(root)+'\nargs='+repr(args)+'\nrelease_sha='+repr(stage['releaseSha256'])+'\n'+r'''
from pathlib import Path
import json,hashlib,os,socket,subprocess,time,stat,shutil
root=Path(root_name);assert root==Path('/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1')and socket.gethostname()=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
assert not Path('/proc/5669').exists(),'User-authorized idle daemon must remain strictly absent'
assert shutil.disk_usage(root).free>=2116076873 and not(root/'arm-1').exists()
for n,r in rows.items():
 p=root/n
 for q in(p,*p.parents):assert not q.is_symlink()
 s=p.stat();assert s.st_nlink==1 and s.st_size==r['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'] and stat.S_IMODE(s.st_mode)==r['mode']
expected=b''.join(v.encode()+b'\0'for v in args)
with(root/'arm-1-execution-register.json').open('x')as register:
 register.write(json.dumps(dict(state='INTENT_NO_PID_YET',expectedArguments=args,arm=1,frozenReleaseSha256=release_sha,noResubmission=True))+'\n');register.flush();os.fsync(register.fileno())
 with(root/'arm-1-execution.stdout').open('xb')as stdout,(root/'arm-1-execution.stderr').open('xb')as stderr:
  child=subprocess.Popen(args,cwd=root,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,close_fds=True)
 register.write(json.dumps(dict(state='SPAWNED_IDENTITY_PENDING',pid=child.pid,arm=1,noResubmission=True))+'\n');register.flush();os.fsync(register.fileno())
 proc=Path('/proc')/str(child.pid);identity=None
 for unused in range(100):
  try:
   first=(proc/'stat').read_text();f=first[first.rfind(')')+2:].split();raw=(proc/'cmdline').read_bytes();last=(proc/'stat').read_text();g=last[last.rfind(')')+2:].split()
   if raw==expected and f[19]==g[19]:identity=dict(pid=child.pid,expectedArguments=args,startUnixNs=time.time_ns(),arm=1,frozenReleaseSha256=release_sha,noResubmission=True,observedExecArgvMatches=True,startTicks=int(f[19]),observedCommandSha256=hashlib.sha256(raw).hexdigest(),stableStartTicks=True,observedState=g[0]);break
  except(FileNotFoundError,ProcessLookupError):pass
  time.sleep(.01)
 assert identity is not None,'Preserve original launch intent, do not resubmit'
 register.write(json.dumps(identity,sort_keys=True)+'\n');register.flush();os.fsync(register.fileno())
print(json.dumps(identity))
'''
(O/'executed-remote-launch.py').write_text(program);(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),oneAttemptOnly=True,expectedArguments=args,sourceSha256=h(Path(__file__)),remoteProgramSha256=hashlib.sha256(program.encode()).hexdigest(),stageSuccessSha256=h(B/'current-read-window32-stage-correction-r3/STAGE_SUCCESS.json'),actualReadOnlyPreflightSha256=h(B/'current-read-window32-preflight-r2/stdout.json'),userAuthorizedCpuSyntheticBenchmarks=True),indent=2)+'\n');spec=importlib.util.spec_from_file_location('current_read32_launch_ssh',H);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);x=m.run('python3 -B -c '+shlex.quote(program),timeout=45);(O/'stdout.json').write_text(x.stdout);(O/'stderr').write_text(x.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=x.returncode,stdoutSha256=hashlib.sha256(x.stdout.encode()).hexdigest(),stderrSha256=hashlib.sha256(x.stderr.encode()).hexdigest(),noAutomaticRetry=True),indent=2)+'\n');assert x.returncode==0;identity=json.loads(x.stdout);assert identity['observedExecArgvMatches'];print(x.stdout)
