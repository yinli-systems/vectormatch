import pathlib,sys,json,tarfile,hashlib,io,base64
BASE=pathlib.Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
OUT=REPO/'evidence/2026-10-24/runpod-cpu/jmh-core-level-iterator/observer-smoke-v2'
code='''from pathlib import Path
import json,hashlib,tarfile,base64,io
root=Path('/opt/vectormatch-cpu/runs/cpu-jmh-observer-smoke-v2-r1');v=json.loads((root/'verification.json').read_text());assert v['passed'] and v['observedForks']==3 and v['nonMainForksObserved']>0 and v['cleanupPassed']
f={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()};b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w:gz') as t:
 for n in f:t.add(root/n,arcname=n,recursive=False)
print(json.dumps({'files':f,'sha256':hashlib.sha256(b.getvalue()).hexdigest(),'data':base64.b64encode(b.getvalue()).decode()}))
'''
r=remote.run('python3 -B -',input=code,timeout=45);assert r.returncode==0,r.stderr
r=json.loads(r.stdout);data=base64.b64decode(r.pop('data'));assert hashlib.sha256(data).hexdigest()==r['sha256'];(OUT/'raw.tar.gz').write_bytes(data);(OUT/'raw').mkdir(exist_ok=False)
with tarfile.open(fileobj=io.BytesIO(data)) as t:
 for m in t:
  assert m.isfile() and pathlib.PurePosixPath(m.name).name==m.name and m.name in r['files'];b=t.extractfile(m).read();assert hashlib.sha256(b).hexdigest()==r['files'][m.name];(OUT/'raw'/m.name).write_bytes(b)
v=json.loads((OUT/'raw/verification.json').read_text());assert v['workerSha256']==hashlib.sha256((BASE/'jmh-abab-worker-v2.py').read_bytes()).hexdigest();(OUT/'verification.json').write_text(json.dumps(v,indent=2)+'\n');(OUT/'download.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'passed':True,'observedForks':3,'nonMainForksObserved':v['nonMainForksObserved']}))
