from pathlib import Path
import sys,json,hashlib,subprocess,shlex
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import archive_closed as archive
LONG=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/benchmarks/replicated-sustained-20261027-r3/cloud')
assert json.loads((LONG/'RESTORE_CLOSED.json').read_text())['functionalPassed']
a=P.parent/'cloud-package.tar.gz';plan=json.loads((P/'PACKAGE.json').read_text());assert a.stat().st_size==plan['bytes']and hashlib.sha256(a.read_bytes()).hexdigest()==plan['sha256']
code='ROOT='+repr(archive.ROOT)+'\nSHA='+repr(plan['sha256'])+'\n'+r'''
from pathlib import Path
import sys,tarfile,io,hashlib,shutil,json
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java'
 except(FileNotFoundError,ProcessLookupError):pass
assert shutil.disk_usage('/opt/vectormatch-cpu').free>3_300_000_000
r=Path(ROOT);r.mkdir(exist_ok=False);b=sys.stdin.buffer.read();assert hashlib.sha256(b).hexdigest()==SHA
with tarfile.open(fileobj=io.BytesIO(b),mode='r:gz')as t:
 for m in t:
  n=Path(m.name);assert m.isfile()and not n.is_absolute()and'..'not in n.parts
  f=r/n;f.parent.mkdir(parents=True,exist_ok=True);f.open('xb').write(t.extractfile(m).read())
files={**json.loads((r/'CANDIDATE.json').read_text())['files'],**json.loads((r/'SOURCE_FILES.json').read_text())}
for n,v in files.items():assert (r/n).stat().st_size==v['bytes']and hashlib.sha256((r/n).read_bytes()).hexdigest()==v['sha256']
print(json.dumps({'verifiedFiles':len(files),'packageSha256':SHA,'free':shutil.disk_usage(r).free,'allPreviousTestJavaStopped':True}))
'''
with a.open('rb')as inp:q=subprocess.run(archive.remote.sshargs()+['python3 -c '+shlex.quote(code)],stdin=inp,capture_output=True,timeout=120)
assert q.returncode==0,q.stderr.decode();(P/'STAGED.json').write_bytes(q.stdout);print(q.stdout.decode())
