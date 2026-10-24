import pathlib,platform,json,hashlib,base64,importlib.util,shutil
assert platform.node()=='ed6c0673f5cb'
old=pathlib.Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r2');v=json.loads((old/'BUILD_RESULT.json').read_text())
assert not v['passed'] and all(not x['remainingProcessGroupMembers'] for x in v['commands'])
assert 'fatal error: utils/errcodes.h' in (old/'logs/make-pg_controldata.log').read_text()
t=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-builder-r3');assert not any(p.is_symlink() for p in [t]+list(t.parents)) and not t.exists()
t.mkdir()
b=t/'build-pg18-tools.py'
with b.open('xb') as f:f.write(base64.b64decode(REQUEST['source']))
assert hashlib.sha256(b.read_bytes()).hexdigest()==REQUEST['sha256']
spec=importlib.util.spec_from_file_location('pg_builder',b);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not m.benchmark_processes() and shutil.disk_usage(t).free>3*1024**3
source=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-source-r1/postgresql-18.6.tar.bz2')
plan=m.plan(source,'/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r3')
with (t/'staging-plan.json').open('x') as f:json.dump(plan,f,indent=2)
print(json.dumps(plan))
