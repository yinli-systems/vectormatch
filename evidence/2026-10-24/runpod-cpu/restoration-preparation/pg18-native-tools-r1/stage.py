import pathlib,platform,json,importlib.util,hashlib,shutil
assert platform.node()=='ed6c0673f5cb'
dep=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-dependencies-r1');assert json.loads((dep/'post-install-readback-r1.json').read_text())['passed']
b=dep/'build-pg18-tools.py';assert hashlib.sha256(b.read_bytes()).hexdigest()=='453555f88e563123d299609fa8e1bb88e0f5645e80c4cf51173da8040f1c98fc'
spec=importlib.util.spec_from_file_location('pg_builder',b);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not m.benchmark_processes()
t=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-source-r1');assert not any(p.is_symlink() for p in [t]+list(t.parents))
assert not t.exists() and not pathlib.Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r1').exists()
assert m.filesystem_type(t.parent)=='overlay' and shutil.disk_usage(t.parent).free>3*1024**3
t.mkdir()
with (t/'staging-attempted.json').open('x') as f:json.dump({'sourceSha256':'555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f','sourceBytes':22632314,'freshBenchmarkIdleObserved':True,'databaseDataTouched':False},f,indent=2)
print(json.dumps({'stagedDirectory':str(t),'freshBenchmarkIdleObserved':True}))
