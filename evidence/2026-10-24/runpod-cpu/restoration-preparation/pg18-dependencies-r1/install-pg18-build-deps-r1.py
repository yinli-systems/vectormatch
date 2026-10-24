#!/usr/bin/env python3
"""Install the four simulated build dependencies; never upgrade/remove packages."""
from pathlib import Path
import hashlib
import json
import sys

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import remote
proof=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg18-dependencies-r1'
meta=json.loads((proof/'remote-result.json').read_text())
assert meta['passed'] and not meta['packageInstallAttempted']
assert '0 upgraded, 4 newly installed, 0 to remove' in meta['simulation']
expected={'bison':'2:3.5.1+dfsg-1','flex':'2.6.4-6.2','m4':'1.4.18-4','libsigsegv2':'2.12-2'}
assert {x.split()[1] for x in meta['simulation'].splitlines() if x.startswith('Inst ')}==set(expected)
(proof/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
request={'metadataSha256':hashlib.sha256((proof/'remote-result.json').read_bytes()).hexdigest(),
         'expected':expected,'simulation':meta['simulation'],'builderSha256':meta['builderSha256']}
code='''import pathlib,platform,json,hashlib,importlib.util,subprocess,shutil
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-dependencies-r1')
assert not any(p.is_symlink() for p in [root]+list(root.parents))
before=json.loads((root/'metadata-result.json').read_text());assert before['passed'] and before['simulation']==REQUEST['simulation']
assert not (root/'install-attempted.json').exists() and not (root/'install-result.json').exists()
builder=root/'build-pg18-tools.py';assert hashlib.sha256(builder.read_bytes()).hexdigest()==REQUEST['builderSha256']
spec=importlib.util.spec_from_file_location('pg_builder',builder);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not m.benchmark_processes() and shutil.disk_usage(root).free>3*1024**3
args=['/usr/bin/apt-get','--assume-yes','--no-upgrade','--no-remove','--no-install-recommends','-o','Acquire::Retries=0','-o','Acquire::http::Timeout=10','install']+[k+'='+v for k,v in sorted(REQUEST['expected'].items())]
with (root/'install-attempted.json').open('x') as f:json.dump({'argv':args,'expectedVersions':REQUEST['expected'],'scope':'Build dependencies only;no PostgreSQL/data/service initialization'},f,indent=2)
records=[];result={'passed':False,'commands':records,'packageInstallAttempted':True,'expectedVersions':REQUEST['expected'],'metadataLocalArchiveSha256':REQUEST['metadataSha256'],'databaseDataTouched':False,'sourceBuildStarted':False}
try:
 env={'PATH':m.SAFE_PATH,'LANG':'C','LC_ALL':'C','TZ':'UTC','DEBIAN_FRONTEND':'noninteractive'}
 check=m.run_step('apt-exact-version-simulation',args[:1]+['-s']+[v for v in args[1:] if v!='--assume-yes'],root,env,root/'logs',records,20)
 assert {x.split()[1] for x in check.splitlines() if x.startswith('Inst ')}==set(REQUEST['expected'])
 assert '0 upgraded, 4 newly installed, 0 to remove' in check
 assert not m.benchmark_processes()
 m.run_step('apt-install-build-dependencies',args,root,env,root/'logs',records,60)
 output=m.run_step('dpkg-exact-versions',['/usr/bin/dpkg-query','-W','-f','${binary:Package}\\t${Version}\\n']+sorted(REQUEST['expected']),root,env,root/'logs',records,10)
 actual=dict(line.split('\\t') for line in output.strip().splitlines());assert actual==REQUEST['expected'],actual
 result['actualVersions']=actual
 result['passed']=True
except Exception as e:result['error']={'type':type(e).__name__,'message':str(e)}
finally:
 result['freeBytesAfter']=shutil.disk_usage(root).free
 with (root/'install-result.json').open('x') as f:json.dump(result,f,indent=2)
 result['logs']={p.name:p.read_text(errors='replace') for p in (root/'logs').glob('*.log')}
print(json.dumps(result))
'''
r=remote.run('python3 -B -',input='REQUEST='+repr(request)+'\n'+code,timeout=110)
(proof/'install-ssh-transport.json').write_text(json.dumps({'returnCode':r.returncode,'stderr':r.stderr},indent=2)+'\n')
(proof/'install-remote-result.json').write_text(r.stdout)
assert r.returncode==0,r.stderr
v=json.loads(r.stdout)
for name,content in v.get('logs',{}).items():
 assert name in ('apt-update.log','apt-simulation.log','apt-exact-version-simulation.log','apt-install-build-dependencies.log','dpkg-exact-versions.log')
 p=proof/name
 if p.exists():assert p.read_text()==content
 else:p.write_text(content)
print(json.dumps({k:x for k,x in v.items() if k!='logs'}))
assert v['passed'],'Dependency installation failed;no automatic retry;partial retained'
