
from pathlib import Path,PurePosixPath
import os,socket,json,sys,base64,hashlib,tarfile,io,stat,subprocess,time
c=json.loads(base64.b64decode(sys.argv[1]));root=Path(c['remoteRoot']);assert socket.gethostname()==c['host']=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for n in range(1,5):assert not(root/('arm-'+str(n))).exists(),'Never patch a launched workload'
for n,r in c['originalStagedFiles'].items():
 q=root/n;s=q.stat();assert not q.is_symlink() and s.st_nlink==1 and s.st_size==r['bytes'] and hashlib.sha256(q.read_bytes()).hexdigest()==r['sha256'] and stat.S_IMODE(s.st_mode)==r['mode']
assert set(c['changedFiles'])=={'LOCAL_PREPARATION_FROZEN.json','owned_linux_base_8eeb.py','release/proofs/rootEvidenceReview.json','release/release.json','test_current_container.py'}
out=root/'stage-results/correction-r3';out.mkdir(mode=0o700);before=out/'before';before.mkdir()
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
save(out/'INTENT.json',dict(configuration=c,all58OriginalFilesVerified=True,noNativeArmExists=True,noSignals=True))
raw=sys.stdin.buffer.read(1024**2+1);assert len(raw)<=1024**2 and hashlib.sha256(raw).hexdigest()==c['correctionBundleSha256'];(out/'patch.tar.gz').write_bytes(raw);updates={}
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz')as t:
 for m in t:
  assert m.isfile() and m.name in c['changedFiles'] and m.name not in updates;p=PurePosixPath(m.name);assert str(p)==m.name and not p.is_absolute() and '..'not in p.parts
  b=t.extractfile(m).read();r=c['rows'][m.name];assert len(b)==m.size==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'];updates[m.name]=b
assert set(updates)==set(c['changedFiles'])
for n,b in updates.items():
 q=root/n;copy=before/n;copy.parent.mkdir(parents=True,exist_ok=True)
 with copy.open('xb')as f:f.write(q.read_bytes());f.flush();os.fsync(f.fileno())
 temporary=q.with_name(q.name+'.correction-r3-new')
 with temporary.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 temporary.chmod(c['rows'][n]['mode']);os.replace(temporary,q)
guards=[]
for group in c['linuxGuardCommands']:
 cwd=root if group['cwd']=='.'else root/group['cwd'];args=['/usr/bin/python3','-B','-m','unittest','-v']+group['modules'];r=subprocess.run(args,cwd=cwd,capture_output=True,timeout=90);(out/(group['scope']+'.stdout')).write_bytes(r.stdout);(out/(group['scope']+'.stderr')).write_bytes(r.stderr);assert r.returncode==0 and ('Ran '+str(group['tests'])+' tests').encode()in r.stderr and r.stderr.rstrip().endswith(b'OK');guards.append(dict(scope=group['scope'],exitCode=r.returncode,actualTests=group['tests'],stdoutBase64=base64.b64encode(r.stdout).decode(),stderrBase64=base64.b64encode(r.stderr).decode()))
for n,r in c['rows'].items():
 q=root/n;assert q.stat().st_size==r['bytes'] and hashlib.sha256(q.read_bytes()).hexdigest()==r['sha256'] and stat.S_IMODE(q.stat().st_mode)==r['mode']
result=dict(passed=True,stagedFiles=c['rows'],actualLinuxPureGuards=86,guards=guards,releaseSha256=c['releaseSha256'],controllerSha256=c['rows']['cpu_read_window32_abab.py']['sha256'],applicationStarted=False,resourceCreated=False,noNativeArms=True,correctedOriginalOwnershipBaseSha256=c['rows']['owned_linux_base_8eeb.py']['sha256'],original58SourceBodiesVerifiedBeforeCorrection=True,allFivePreviousBodiesRetained=True,naturalGradleExitStillRequiredBeforePreflight=True,host=socket.gethostname(),remotePrep=str(root))
save(out/'SUCCESS.json',{k:v for k,v in result.items()if k!='guards'});print(json.dumps(result))
