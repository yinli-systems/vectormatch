#!/usr/bin/env python3
"""Single-attempt fixed official source build of pg_controldata and pg_config."""
from pathlib import Path
import hashlib
import json
import shlex
import sys

BASE=Path(__file__).resolve().parent
REPO=BASE.parents[2]
sys.path.insert(0,str(BASE))
import remote
source=BASE/'app-restore-build/pg18-tools-source/postgresql-18.6.tar.bz2'
source_sha='555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f'
builder='/opt/vectormatch-cpu/preparation/pg18-dependencies-r1/build-pg18-tools.py'
target='/opt/vectormatch-cpu/preparation/pg18-source-r1'
work='/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r1'
assert source.stat().st_size==22632314 and hashlib.sha256(source.read_bytes()).hexdigest()==source_sha
proof=REPO/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg18-native-tools-r1'
proof.mkdir(exist_ok=False)
(proof/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
stage='''import pathlib,platform,json,importlib.util,hashlib,shutil
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
'''
(proof/'stage.py').write_text(stage)
r=remote.run('python3 -B -',input=stage,timeout=20)
(proof/'stage-transport.json').write_text(json.dumps({'returnCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n')
assert r.returncode==0,r.stderr
r=remote.upload(source,target+'/postgresql-18.6.tar.bz2')
(proof/'upload-transport.json').write_text(json.dumps({'returnCode':r.returncode,'stdout':r.stdout.decode(),'stderr':r.stderr.decode()},indent=2)+'\n')
assert r.returncode==0,r.stderr
cmd=['python3','-B',builder,'--source',target+'/postgresql-18.6.tar.bz2','--work-dir',work,'--execute','--benchmark-idle-confirmed']
(proof/'invocation.json').write_text(json.dumps({'argv':cmd,'sourceSha256':source_sha,'scope':'Only2native tools;noPGDATAargument,noinitdb/server target;single attempt;querysameworkresultontransportfailure'},indent=2)+'\n')
r=remote.run(' '.join(shlex.quote(v) for v in cmd),timeout=1600)
(proof/'build.stdout').write_text(r.stdout)
(proof/'build.stderr').write_text(r.stderr)
(proof/'transport.json').write_text(json.dumps({'returnCode':r.returncode},indent=2)+'\n')
print(json.dumps({'returnCode':r.returncode,'stdoutTail':r.stdout[-1500:],'stderrTail':r.stderr[-1500:]}))
assert r.returncode==0,'Build failed;partial kept;do not resubmit'
