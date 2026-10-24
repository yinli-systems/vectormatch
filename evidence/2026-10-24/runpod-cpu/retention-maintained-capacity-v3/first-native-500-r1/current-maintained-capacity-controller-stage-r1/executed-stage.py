import sys,json,base64,pathlib,tarfile,hashlib,os,socket
c=json.loads(base64.b64decode(sys.argv[1]));root=pathlib.Path(c['root']);assert str(root)=='/opt/vectormatch-cpu/experiments/maintained-capacity-first-pilot-r1'and socket.gethostname()=='33ace3d92505'and not root.exists()
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for p in root.parents:assert p.is_dir()and not p.is_symlink()
os.umask(0o077);root.mkdir(mode=0o700);bundle=root/'input-bundle.tar.gz';raw=sys.stdin.buffer.read(1024*1024+1);assert len(raw)<=1024*1024 and hashlib.sha256(raw).hexdigest()==c['bundleSha256'];bundle.write_bytes(raw);seen=set()
with tarfile.open(bundle,'r:gz')as t:
 for m in t:
  assert m.isfile()and m.name in c['rows']and m.name not in seen and '/'not in m.name and m.name not in('.','..');r=c['rows'][m.name];assert m.size==r['bytes']and m.mode==r['mode'];body=t.extractfile(m).read();assert hashlib.sha256(body).hexdigest()==r['sha256'];p=root/m.name
  with p.open('xb')as f:f.write(body);f.flush();os.fsync(f.fileno())
  p.chmod(r['mode']);seen.add(m.name)
assert seen==set(c['rows'])
for name,r in c['rows'].items():
 p=root/name;assert p.stat().st_size==r['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']and p.stat().st_mode&0o777==r['mode']
print(json.dumps(dict(passed=True,stagedFiles=c['rows'],noWorkloadLaunched=True,noExistingPathsModified=True)))
