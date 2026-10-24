#!/usr/bin/env python3
"""Fresh work directory for the one-flag-corrected two-tool build."""
from pathlib import Path
import base64
import hashlib
import json
import shlex
import sys

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
sys.path.insert(0,str(BASE));import remote
proof=REPO/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg18-native-tools-r2'
correction=json.loads((proof/'correction.json').read_text())
assert json.loads((proof/'offline-guards-r2.json').read_text())['exitCode']==0
b=BASE/'pg18-tools-builder-r2/build-pg18-tools.py'
assert hashlib.sha256(b.read_bytes()).hexdigest()==correction['newBuilderSha256']
with (proof/Path(__file__).name).open('xb') as f:f.write(Path(__file__).read_bytes())
request={'source':base64.b64encode(b.read_bytes()).decode(),'sha256':correction['newBuilderSha256']}
code='''import pathlib,platform,json,hashlib,base64,importlib.util,shutil
assert platform.node()=='ed6c0673f5cb'
old=pathlib.Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r1');v=json.loads((old/'BUILD_RESULT.json').read_text())
assert not v['passed'] and all(not x['remainingProcessGroupMembers'] for x in v['commands'])
assert 'argument required for --with-ssl option' in (old/'logs/configure.log').read_text()
t=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-builder-r2');assert not any(p.is_symlink() for p in [t]+list(t.parents)) and not t.exists()
t.mkdir()
b=t/'build-pg18-tools.py'
with b.open('xb') as f:f.write(base64.b64decode(REQUEST['source']))
assert hashlib.sha256(b.read_bytes()).hexdigest()==REQUEST['sha256']
spec=importlib.util.spec_from_file_location('pg_builder',b);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not m.benchmark_processes() and shutil.disk_usage(t).free>3*1024**3
source=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-source-r1/postgresql-18.6.tar.bz2')
plan=m.plan(source,'/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r2')
with (t/'staging-plan.json').open('x') as f:json.dump(plan,f,indent=2)
print(json.dumps(plan))
'''
(proof/'stage.py').write_text(code)
r=remote.run('python3 -B -',input='REQUEST='+repr(request)+'\n'+code,timeout=25)
(proof/'stage-transport.json').write_text(json.dumps({'returnCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');assert r.returncode==0,r.stderr
cmd=['python3','-B','/opt/vectormatch-cpu/preparation/pg18-builder-r2/build-pg18-tools.py','--source','/opt/vectormatch-cpu/preparation/pg18-source-r1/postgresql-18.6.tar.bz2','--work-dir','/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r2','--execute','--benchmark-idle-confirmed']
with (proof/'invocation.json').open('x') as f:json.dump({'argv':cmd,'scope':'Fresh2toolbuild after oneflag correction;oldfailedworkretained;noPGDATA/server/initdb'},f,indent=2)
r=remote.run(' '.join(shlex.quote(v) for v in cmd),timeout=1600)
(proof/'build.stdout').write_text(r.stdout);(proof/'build.stderr').write_text(r.stderr)
(proof/'transport.json').write_text(json.dumps({'returnCode':r.returncode},indent=2)+'\n')
print(json.dumps({'returnCode':r.returncode,'stdoutTail':r.stdout[-1500:],'stderrTail':r.stderr[-1500:]}))
assert r.returncode==0,'Build failed;retain partial;never resubmit same attempt'
