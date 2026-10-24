import pathlib,platform,json,shutil
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu');active=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\0')
 except FileNotFoundError:continue
 if args and args[0].split(b'/')[-1]==b'java' and any(a.startswith((b'io.vectormatch.',b'org.openjdk.jmh.',b'ForcePathProbe')) for a in args):active.append(int(p.name))
assert not active and shutil.disk_usage(root).free>3*1024**3
stage=pathlib.Path(REQUEST['stage']);dest=pathlib.Path(REQUEST['destination'])
assert not any(p.is_symlink() for p in [stage,dest]+list(stage.parents)+list(dest.parents))
assert not stage.exists() and not dest.exists()
stage.mkdir(mode=0o700);dest.parent.mkdir(mode=0o700,exist_ok=True)
for name in REQUEST['files']:(stage/name).parent.mkdir(parents=True,exist_ok=True)
with (stage/'PLAN.json').open('x') as f:json.dump(REQUEST,f,indent=2)
print(json.dumps({'passed':True,'freshProjectJvmsIdle':True,'freeBytes':shutil.disk_usage(root).free}))
