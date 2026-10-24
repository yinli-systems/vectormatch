#!/usr/bin/env python3
"""One bounded metadata refresh on the existing idle CPU; no package install."""
from pathlib import Path
import base64
import hashlib
import json
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import remote

builder = BASE / 'app-restore-build/pg18-tools-source/build-pg18-tools.py'
assert hashlib.sha256(builder.read_bytes()).hexdigest() == '453555f88e563123d299609fa8e1bb88e0f5645e80c4cf51173da8040f1c98fc'
proof = BASE.parents[2] / 'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg18-dependencies-r1'
proof.mkdir(exist_ok=False)
(proof / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
(proof / builder.name).write_bytes(builder.read_bytes())
request = {'builderBase64': base64.b64encode(builder.read_bytes()).decode(),
           'builderSha256': hashlib.sha256(builder.read_bytes()).hexdigest()}
code = '''import pathlib,platform,json,base64,hashlib,importlib.util,shutil,traceback
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-dependencies-r1')
assert not any(p.is_symlink() for p in [root]+list(root.parents))
assert not root.exists()
root.mkdir()
builder=root/'build-pg18-tools.py'
with builder.open('xb') as f:f.write(base64.b64decode(REQUEST['builderBase64']))
assert hashlib.sha256(builder.read_bytes()).hexdigest()==REQUEST['builderSha256']
spec=importlib.util.spec_from_file_location('pg_builder',builder);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
records=[];out={'passed':False,'hostname':platform.node(),'packageInstallAttempted':False,'databaseDataTouched':False,'commands':records,'builderSha256':REQUEST['builderSha256']}
try:
 assert not m.benchmark_processes(),'benchmark present'
 assert shutil.disk_usage(root).free>3*1024**3
 assert m.filesystem_type(root)=='overlay'
 logs=root/'logs';logs.mkdir()
 env={'PATH':m.SAFE_PATH,'LANG':'C','LC_ALL':'C','TZ':'UTC','DEBIAN_FRONTEND':'noninteractive'}
 m.run_step('apt-update',['/usr/bin/apt-get','-o','Acquire::Retries=0','-o','Acquire::http::Timeout=10','-o','Acquire::https::Timeout=10','update'],root,env,logs,records,60)
 assert not m.benchmark_processes(),'benchmark appeared'
 out['simulation']=m.run_step('apt-simulation',['/usr/bin/apt-get','-s','--no-upgrade','--no-install-recommends','--no-remove','install','bison','flex'],root,env,logs,records,30)
 out['passed']=True
except Exception as e:out['error']={'type':type(e).__name__,'message':str(e)}
finally:
 out['freeBytesAfter']=shutil.disk_usage(root).free
 with (root/'metadata-result.json').open('x') as f:json.dump(out,f,indent=2)
 out['logs']={p.name:p.read_text(errors='replace') for p in (root/'logs').glob('*.log')}
print(json.dumps(out))
'''
result = remote.run('python3 -B -', input='REQUEST=' + repr(request) + '\n' + code, timeout=110)
(proof / 'ssh-transport.json').write_text(json.dumps({'returnCode':result.returncode,'stderr':result.stderr},indent=2)+'\n')
(proof / 'remote-result.json').write_text(result.stdout)
assert result.returncode == 0, result.stderr
value = json.loads(result.stdout)
for name, content in value.get('logs', {}).items():
    assert name in ('apt-update.log','apt-simulation.log')
    (proof / name).write_text(content)
print(json.dumps({k:v for k,v in value.items() if k!='logs'}))
assert value['passed'], 'Metadata preparation failed; partial retained, no package install'
