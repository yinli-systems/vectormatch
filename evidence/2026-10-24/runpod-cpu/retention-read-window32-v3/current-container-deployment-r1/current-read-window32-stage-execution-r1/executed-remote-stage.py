
from pathlib import Path,PurePosixPath
import sys,json,base64,hashlib,os,socket,tarfile,shutil,subprocess,stat,time
c=json.loads(base64.b64decode(sys.argv[1]));root=Path(c['remoteRoot']);assert socket.gethostname()==c['host']=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
assert root==Path('/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1') and not root.exists() and not root.is_symlink()
for p in root.parents:assert not p.is_symlink()
assert len(c['rows'])==58<=64 and sum(r['bytes']for r in c['rows'].values())<=32*1024**2
assert shutil.disk_usage('/opt/vectormatch-cpu').free>=2116076873+64*1024**2
parent=root.parent;parent.mkdir(mode=0o700,exist_ok=True);root.mkdir(mode=0o700)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 with p.open('x')as f:json.dump(d,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
results=root/'stage-results';results.mkdir(mode=0o700);save(results/'REGISTRATION.json',dict(atUTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),configuration=c,pid=os.getpid(),noJvmOrBusiness=True,noSignals=True))
bundle=root/'source-package.tar.gz';data=sys.stdin.buffer.read(32*1024**2+1);assert len(data)<=32*1024**2 and hashlib.sha256(data).hexdigest()==c['bundleSha256']
with bundle.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
seen=set()
with tarfile.open(bundle,'r:gz')as t:
 for m in t:
  n=m.name;p=PurePosixPath(n);assert m.isfile() and n in c['rows'] and n not in seen and str(p)==n and not p.is_absolute() and '..'not in p.parts
  r=c['rows'][n];body=t.extractfile(m).read();assert m.size==len(body)==r['bytes'] and hashlib.sha256(body).hexdigest()==r['sha256'] and m.mode&0o777==r['mode'];seen.add(n)
assert seen==set(c['rows'])
with tarfile.open(bundle,'r:gz')as t:
 for m in t:
  q=root/m.name;q.parent.mkdir(parents=True,exist_ok=True)
  for p in(q,*q.parents):assert not p.is_symlink()
  with q.open('xb')as f:f.write(t.extractfile(m).read())
  q.chmod(c['rows'][m.name]['mode'])
guards=[]
for group in c['linuxGuardCommands']:
 cwd=root if group['cwd']=='.'else root/group['cwd'];args=['/usr/bin/python3','-B','-m','unittest','-v']+group['modules'];r=subprocess.run(args,cwd=cwd,capture_output=True,timeout=90)
 (results/(group['scope']+'.stdout')).write_bytes(r.stdout);(results/(group['scope']+'.stderr')).write_bytes(r.stderr)
 record=dict(scope=group['scope'],arguments=args,cwd=str(cwd),exitCode=r.returncode,stdoutSha256=hashlib.sha256(r.stdout).hexdigest(),stderrSha256=hashlib.sha256(r.stderr).hexdigest(),expectedTests=group['tests']);save(results/(group['scope']+'.execution.json'),record)
 assert r.returncode==0 and ('Ran '+str(group['tests'])+' tests').encode()in r.stderr and r.stderr.rstrip().endswith(b'OK')
 guards.append(dict(record,stdoutBase64=base64.b64encode(r.stdout).decode(),stderrBase64=base64.b64encode(r.stderr).decode()))
for n,r in c['rows'].items():
 q=root/n;assert q.is_file() and not q.is_symlink() and q.stat().st_size==r['bytes'] and sha(q)==r['sha256'] and stat.S_IMODE(q.stat().st_mode)==r['mode']
assert sha(root/'release/release.json')==c['releaseSha256']
result=dict(passed=True,host=socket.gethostname(),root=str(root),stagedFiles=c['rows'],actualLinuxPureGuards=85,guards=guards,releaseSha256=c['releaseSha256'],noBenchmarkOrJvmStarted=True,naturalGradleExitStillRequiredBeforePreflight=True,freeBytesAfter=shutil.disk_usage(root).free)
save(results/'SUCCESS.json',{k:v for k,v in result.items()if k!='guards'});print(json.dumps(result))
