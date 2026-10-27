from pathlib import Path
import hashlib,json,tarfile,sys
P=Path(__file__).resolve().parent;C=P/'cloud';sys.path.insert(0,str(C));import archive_closed as a
files={str(f.relative_to(C)):{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}for f in sorted(C.rglob('*'))if f.is_file()and not any(n in f.relative_to(C).parts for n in ['dist','qualification','__pycache__'])and f.name not in ['SOURCE_FILES.json','worker_head.txt','worker_body.txt']}
(C/'SOURCE_FILES.json').write_text(json.dumps(files,indent=2)+'\n')
pack=P/'cloud-package.tar.gz'
with tarfile.open(pack,'w:gz',compresslevel=1)as t:
 for f in sorted(C.rglob('*')):
  if f.is_file()and '__pycache__'not in f.parts and f.name not in ['worker_head.txt','worker_body.txt']:t.add(f,arcname=str(f.relative_to(C)),recursive=False)
v={'bytes':pack.stat().st_size,'sha256':a.sha(pack)};(P/'CLOUD_PACKAGE.json').write_text(json.dumps(v,indent=2)+'\n')
r=a.remote.run('python3 -',input='from pathlib import Path\np=Path('+repr(a.ROOT)+');p.mkdir()\n',timeout=30);assert r.returncode==0,r.stderr
r=a.remote.upload(pack,a.ROOT+'/input.tar.gz');assert r.returncode==0,r.stderr
code='BASE='+repr(a.ROOT)+'\nEXPECTED='+repr(v)+'\n'+r'''
from pathlib import Path
import hashlib,json,tarfile
b=Path(BASE);f=b/'input.tar.gz';assert f.stat().st_size==EXPECTED['bytes']and hashlib.sha256(f.read_bytes()).hexdigest()==EXPECTED['sha256']
seen=set()
with tarfile.open(f,'r:gz')as t:
 for m in t:
  assert m.isfile()and not Path(m.name).is_absolute()and'..'not in Path(m.name).parts and m.name not in seen;seen.add(m.name)
  p=b/m.name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb')as out:out.write(t.extractfile(m).read())
for n,v in json.loads((b/'CANDIDATE.json').read_text())['files'].items():
 p=b/n;assert p.stat().st_size==v['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==v['sha256']
print(json.dumps({'staged':True,'archiveSha256':EXPECTED['sha256'],'files':len(seen)}))
'''
r=a.remote.run('python3 -',input=code,timeout=60);assert r.returncode==0,r.stderr;(P/'STAGED.json').write_text(r.stdout);print(r.stdout)
