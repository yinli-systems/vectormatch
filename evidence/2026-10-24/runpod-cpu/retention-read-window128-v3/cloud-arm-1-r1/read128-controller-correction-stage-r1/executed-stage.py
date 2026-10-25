import pathlib,json,base64,hashlib,os,socket,tarfile,importlib.util
c=json.loads(base64.b64decode(__import__('sys').argv[1]));root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');assert socket.gethostname()=='33ace3d92505';s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);assert hashlib.sha256((root/'FROZEN.json').read_bytes()).hexdigest()==c['oldFreezeSha256'];completed=json.loads((root/'arm-1/completion.json').read_text());assert completed['passed']and completed['allOwnedStopped']and not(root/'arm-2').exists()
for p in(root/'arm-1').glob('identity-observation-*.json'):
 r=json.loads(p.read_text())['kernelIdentity'];assert not(pathlib.Path('/proc')/str(r['pid'])).exists()
for name,row in c['old']['files'].items():
 p=root/name;assert p.stat().st_size==row['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
backup=root/'controller-revision-1';backup.mkdir(mode=0o700)
for name in ['campaign.py','capacity_validators.py','FROZEN.json']:
 body=(root/name).read_bytes();q=backup/name
 with q.open('xb')as f:f.write(body);f.flush();os.fsync(f.fileno())
 q.chmod(0o644)
raw=__import__('sys').stdin.buffer.read(1024*1024+1);assert len(raw)<=1024*1024 and hashlib.sha256(raw).hexdigest()==c['bundleSha256'];bundle=root/'source-revision-2.tar.gz';bundle.write_bytes(raw);seen=set()
with tarfile.open(bundle,'r:gz')as t:
 for m in t:
  assert m.isfile()and '/'not in m.name and m.name not in seen and m.name in set(c['new']['files'])|{'FROZEN.json'};data=t.extractfile(m).read();pin=c['new']['files'].get(m.name);h=hashlib.sha256(data).hexdigest()
  if pin:assert len(data)==m.size==pin['bytes']and h==pin['sha256']and m.mode==pin['mode']
  else:assert h==c['newFreezeSha256']
  p=root/m.name
  if p.exists():
   if m.name in ['campaign.py','capacity_validators.py','FROZEN.json']:
    tmp=root/(m.name+'.revision2');assert not tmp.exists()
    with tmp.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
    tmp.chmod(0o644);os.replace(tmp,p)
   else:assert p.read_bytes()==data
  else:
   with p.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
   p.chmod(0o644)
  seen.add(m.name)
assert seen==set(c['new']['files'])|{'FROZEN.json'}
for name,pin in c['new']['files'].items():
 p=root/name;assert p.stat().st_size==pin['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']and p.stat().st_mode&0o777==pin['mode']
print(json.dumps(dict(passed=True,oldOriginalBodiesBackedUp=True,newSourceFreezeSha256=c['newFreezeSha256'],noJavaStarted=True,noNativeOrderOrArtifactChanged=True)))
