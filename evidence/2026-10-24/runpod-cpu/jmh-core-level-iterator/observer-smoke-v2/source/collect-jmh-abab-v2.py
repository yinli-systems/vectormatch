"""Read-only collection of the registered completed r2; never launches a job."""
import pathlib,sys,json,base64,tarfile,io,hashlib
BASE=pathlib.Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
OUT=REPO/'evidence/2026-10-24/runpod-cpu/jmh-core-level-iterator/attempts/r2'
assert not (OUT/'raw').exists() and not (OUT/'raw.tar.gz').exists(), 'Collection already materialized; inspect same attempt'
code='''from pathlib import Path
import json,hashlib,tarfile,io,base64,platform
assert platform.node()=='ed6c0673f5cb'
root=Path('/opt/vectormatch-cpu/runs/cpu-jmh-level-iterator-abab-r2')
receipt=json.loads((root/'receipt.json').read_text())
assert receipt['passed'] and len(receipt['stages'])==4
for n in ('A1','B1','A2','B2'):
 v=json.loads((root/(n+'-verification.json')).read_text())
 p=json.loads((root/(n+'-owned-process-summary.json')).read_text())
 assert v['passed'] and v['cleanup']['passed'] and p['forkIdentitiesObserved']==45
 assert all(x['stopped'] for x in p['records'])
files={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in root.iterdir() if p.is_file()}
data=io.BytesIO()
with tarfile.open(fileobj=data,mode='w:gz') as t:
 for name in sorted(files):t.add(root/name,arcname=name,recursive=False)
print(json.dumps({'files':files,'archiveSha256':hashlib.sha256(data.getvalue()).hexdigest(),'data':base64.b64encode(data.getvalue()).decode()}))
'''
p=remote.run('python3 -B -',input=code,timeout=60);assert p.returncode==0,p.stderr
r=json.loads(p.stdout);data=base64.b64decode(r.pop('data'));assert hashlib.sha256(data).hexdigest()==r['archiveSha256']
contents={}
with tarfile.open(fileobj=io.BytesIO(data)) as t:
 for m in t:
  assert m.isfile() and pathlib.PurePosixPath(m.name).name==m.name and m.name in r['files'] and m.name not in contents
  b=t.extractfile(m).read();assert len(b)==r['files'][m.name]['bytes'] and hashlib.sha256(b).hexdigest()==r['files'][m.name]['sha256'];contents[m.name]=b
assert set(contents)==set(r['files'])
plan=json.loads(contents['plan.json']);assert plan==json.loads((OUT/'registration.json').read_text())
assert hashlib.sha256(contents['worker.py']).hexdigest()==plan['workerSha256']
for n in ('A1','B1','A2','B2'):
 v=json.loads(contents[n+'-verification.json'])
 for name,h in v['rawFilesSha256'].items():assert hashlib.sha256(contents[name]).hexdigest()==h
with (OUT/'raw.tar.gz').open('xb') as f:f.write(data)
(OUT/'raw').mkdir()
for name,b in contents.items():
 with (OUT/'raw'/name).open('xb') as f:f.write(b)
with (OUT/'collection-verification.json').open('x') as f:json.dump({'downloadVerified':True,'experimentPassed':True,'fourStagesAll45ForksObservedAndStopped':True,'archive':r,'sourceSha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()},f,indent=2);f.write('\n')
print(json.dumps({'preserved':True,'passed':True,'files':len(contents),'archiveBytes':len(data),'archiveSha256':r['archiveSha256']}))
