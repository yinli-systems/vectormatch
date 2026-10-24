"""Deploy the committed evidence index only; verify existing frontend bytes."""
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

BASE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / 'runpod-20261023'))
import remote

root = pathlib.Path.cwd()
revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
index = root / 'evidence/index.json'
data = index.read_bytes()
assert data == subprocess.check_output(['git', 'show', revision + ':evidence/index.json'])
sha = hashlib.sha256(data).hexdigest()
web = {str(p.relative_to(root / 'web/dist')): hashlib.sha256(p.read_bytes()).hexdigest()
       for p in (root / 'web/dist').rglob('*') if p.is_file()}
assert 'index.html' in web
target = '/opt/vectormatch/probe/optimization-index-' + sha + '.json'
result = remote.upload(2, index, target)
assert result.returncode == 0, result.stderr
code = 'TARGET=' + repr(target) + '\nSHA=' + repr(sha) + '\nWEB=' + repr(web) + '\n' + '''
import pathlib,hashlib,json,datetime
source=pathlib.Path(TARGET)
assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA
for name,expected in WEB.items():
    path=pathlib.Path('/opt/vectormatch/web/dist')/name
    assert hashlib.sha256(path.read_bytes()).hexdigest()==expected,name
index=pathlib.Path('/opt/vectormatch/evidence/index.json')
previous=index.read_bytes()
previousSha=hashlib.sha256(previous).hexdigest()
backup=index.parent/('index-before-optimization-'+previousSha+'.json')
if backup.exists():assert backup.read_bytes()==previous
else:
    with backup.open('xb') as f:f.write(previous)
temporary=index.with_suffix('.optimization.tmp')
with temporary.open('xb') as f:f.write(source.read_bytes())
temporary.replace(index)
assert hashlib.sha256(index.read_bytes()).hexdigest()==SHA
print(json.dumps({'passed':True,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'evidenceIndexSha256':SHA,'previousIndexSha256':previousSha,'previousIndexBackup':str(backup),
 'frontendFilesVerified':len(WEB),'frontendUnchanged':True}))
'''
result = remote.run(2, 'python3 -B -', input=code, timeout=45)
assert result.returncode == 0, result.stdout + result.stderr
receipt = json.loads(result.stdout)
receipt.update({'indexRevision': revision, 'sourceSha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
                'scope': 'Committed evidence index only. Existing frontend bytes verified; original backend release and state remain separately pinned.'})
out = root / 'evidence/2026-10-23/runpod-optimization/restoration'
out.mkdir(parents=True, exist_ok=True)
with (out / 'evidence-index-deployment.json').open('x') as f:
    json.dump(receipt, f, indent=2)
    f.write('\n')
print(json.dumps(receipt), flush=True)
