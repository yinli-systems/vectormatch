from pathlib import Path
import sys,hashlib,json,tarfile,subprocess,shlex,shutil
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c

files={}
for f in sorted(P.rglob('*')):
 if not f.is_file()or f.suffix=='.pyc' or f.name.endswith(('.stdout','.stderr','.lock')):continue
 if f.parent!=P and f.parent.name!='lib':continue
 files[str(f.relative_to(P))]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
(P/'SOURCE_FILES.json').write_text(json.dumps(files,indent=2)+'\n')
a=P.parent/'cloud-package.tar.gz'
with tarfile.open(a,'x:gz')as t:
 for n in [*files,'SOURCE_FILES.json']:t.add(P/n,arcname=n)
sha=hashlib.sha256(a.read_bytes()).hexdigest()
code='ROOT='+repr(c.ROOT)+'\nBOOT='+repr(c.PLAN['boot'])+'\nSHA='+repr(sha)+'\n'+r'''
from pathlib import Path
import sys,json,tarfile,hashlib,shutil,io,socket
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java','Java active before staging'
 except(FileNotFoundError,ProcessLookupError):pass
assert shutil.disk_usage('/opt/vectormatch-cpu').free>3_300_000_000
sockets=[]
for i in range(3):
 for offset in range(1,6):
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',26000+i*100+offset));sockets.append(s)
for s in sockets:s.close()
r=Path(ROOT);r.mkdir(exist_ok=False);(r/'experiments').mkdir()
b=sys.stdin.buffer.read();assert hashlib.sha256(b).hexdigest()==SHA
with tarfile.open(fileobj=io.BytesIO(b),mode='r:gz')as t:
 for m in t:
  p=Path(m.name);assert m.isfile()and not p.is_absolute()and'..'not in p.parts
  f=r/p;f.parent.mkdir(parents=True,exist_ok=True);f.open('xb').write(t.extractfile(m).read())
files=json.loads((r/'SOURCE_FILES.json').read_text())
for n,v in files.items():assert hashlib.sha256((r/n).read_bytes()).hexdigest()==v['sha256']
print(json.dumps({'verifiedFiles':len(files),'packageSha256':SHA,'free':shutil.disk_usage(r).free,'noJavaBeforeStaging':True,'portsFree':True}))
'''
with a.open('rb')as inp:q=subprocess.run(c.remote.sshargs()+['python3 -c '+shlex.quote(code)],stdin=inp,capture_output=True,timeout=120)
assert q.returncode==0,q.stderr.decode();v=json.loads(q.stdout);c.save(P/'STAGED.json',v);print(v)
