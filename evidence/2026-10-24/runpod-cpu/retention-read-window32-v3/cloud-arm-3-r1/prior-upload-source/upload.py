from pathlib import Path
import sys,json,hashlib,base64,shlex,importlib.util,datetime
B=Path(__file__).resolve().parent.parent;prior=int(sys.argv[1]);assert prior in(1,2,3);P=B/('current-read32-arm-%d-prior-gate-r1'%prior);O=B/('current-read32-arm-%d-prior-upload-r1'%prior);assert not O.exists();h=lambda q:hashlib.sha256(q.read_bytes()).hexdigest();gate=json.loads((P/'collection-gate.json').read_text());push=json.loads((P/'private-push.json').read_text());assert gate['privatePushReceiptSha256']==h(P/'private-push.json')
for n in['collection-gate.json','private-push.json']:(P/n).chmod(0o600)
rows={};bodies={}
for local,kind in [('collection-gate.json','collection-gate'),('private-push.json','private-push')]:
 name='release/arm-%d-%s.json'%(prior,kind);q=P/local;rows[name]=dict(bytes=q.stat().st_size,sha256=h(q),mode=0o600);bodies[name]=base64.b64encode(q.read_bytes()).decode()
program='rows='+repr(rows)+'\nbodies='+repr(bodies)+'\n'+r'''
from pathlib import Path
import json,base64,hashlib,os,socket,stat
root=Path('/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1');assert socket.gethostname()=='33ace3d92505'and Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for name,row in rows.items():
 p=root/name
 for q in(p,*p.parents):assert not q.is_symlink()
 assert not p.exists() and p.parent==root/'release'
 data=base64.b64decode(bodies[name],validate=True);assert len(data)==row['bytes']and hashlib.sha256(data).hexdigest()==row['sha256']
for name,row in rows.items():
 p=root/name
 with p.open('xb')as f:f.write(base64.b64decode(bodies[name]));f.flush();os.fsync(f.fileno())
 p.chmod(0o600);s=p.stat();assert s.st_nlink==1 and s.st_size==row['bytes']and stat.S_IMODE(s.st_mode)==row['mode']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
print(json.dumps(dict(passed=True,uploadedFiles=rows,noWorkloadLaunched=True,noOtherPathsModified=True)))
'''
O.mkdir();(O/'executed-remote-upload.py').write_text(program);(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),prior=prior,gateSha256=h(P/'collection-gate.json'),privatePushSha256=h(P/'private-push.json'),rows=rows,noImplicitNextArm=True),indent=2)+'\n');spec=importlib.util.spec_from_file_location('current_gate_upload_connection',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);r=m.run('python3 -B -c '+shlex.quote(program),timeout=30);(O/'stdout.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode,stdoutSha256=hashlib.sha256(r.stdout.encode()).hexdigest(),stderrSha256=hashlib.sha256(r.stderr.encode()).hexdigest()),indent=2)+'\n');assert r.returncode==0;d=json.loads(r.stdout);assert d['passed']and d['uploadedFiles']==rows;print(r.stdout)
