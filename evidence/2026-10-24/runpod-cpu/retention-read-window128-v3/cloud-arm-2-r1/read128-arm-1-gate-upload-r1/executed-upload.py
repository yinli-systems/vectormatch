import pathlib,sys,base64,hashlib,os,json
body=base64.b64decode(sys.argv[1]);sha=sys.argv[2];arm=int(sys.argv[3]);assert arm in(1,2,3)and hashlib.sha256(body).hexdigest()==sha
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');p=root/('arm-'+str(arm)+'-gate.json');assert root.is_dir()and not root.is_symlink()and not p.exists();x=json.loads(body);assert x['passed']and x['arm']==arm
with p.open('xb')as f:f.write(body);f.flush();os.fsync(f.fileno())
p.chmod(0o600);assert p.read_bytes()==body and p.stat().st_mode&0o777==0o600;print(json.dumps(dict(passed=True,arm=arm,sha256=sha,mode=384,noWorkloadLaunched=True)))
