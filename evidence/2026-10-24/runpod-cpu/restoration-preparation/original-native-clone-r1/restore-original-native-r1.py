#!/usr/bin/env python3
"""Single-attempt exact original native clone; never starts services/databases."""
from pathlib import Path
import hashlib
import json
import shlex
import sys

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
sys.path.insert(0,str(BASE));import remote
SCRIPT=BASE/'sparse-restore-native.py';SCRIPT_SHA='536a630b319c6a190f6e0a624c674382f0c69cf7219ab24e0066e9d887415598'
STAGE='/opt/vectormatch-cpu/preparation/original-native-source-r1'
DEST='/opt/vectormatch-cpu/restorations/original-native-r1'
PROOF=REPO/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-native-clone-r1'
ARCHIVES=('066c3b54a445e16461115f7324f6f9201d1cb4a33195246d0fab4134579a418a','d3458616f0e59d8861b5ba6a073db51fe6bac7656f627d78d8ca5821fe0e180b','dd04517a84ec035f0a804979cc4d45b0f67192a7729c907ba2f367f35a03105b')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(SCRIPT)==SCRIPT_SHA
files=[(SCRIPT,'sparse-restore-native.py')];inventories=[]
for node,digest in enumerate(ARCHIVES):
    rel='runtime/cloud/optimization-20261024/gpu-to-cpu/backups/node'+str(node)+'-original-state.tar.gz'
    source=REPO/rel;assert sha(source)==digest;files.append((source,rel))
    rel='evidence/2026-10-23/runpod-optimization/gpu-to-cpu/node'+str(node)+'-pre-stop-state.json'
    source=REPO/rel;v=json.loads(source.read_text());assert v['node']==node and v['allOwnedStopped'] and v['originalRolesStopped'];files.append((source,rel))
    inventories.append({'node':node,'archiveSha256':digest,'stoppedInventorySha256':sha(source),'files':len(v['files']),'logicalBytes':sum(x['bytes'] for x in v['files'].values())})
PROOF.mkdir(exist_ok=False)
for source,name in ((Path(__file__),Path(__file__).name),(SCRIPT,SCRIPT.name)):(PROOF/name).write_bytes(source.read_bytes())
plan={'stage':STAGE,'destination':DEST,'scope':'Exact stopped native clone only;new directories;noPGDATA/server/initdb execution;originalbytes+backups preserved;no ownership migration','files':{name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p,name in files},'nodes':inventories}
(PROOF/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
code='''import pathlib,platform,json,shutil
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu');active=[]
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\\0')
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
'''
(PROOF/'stage.py').write_text(code)
r=remote.run('python3 -B -',input='REQUEST='+repr(plan)+'\n'+code,timeout=25)
(PROOF/'stage-transport.json').write_text(json.dumps({'returnCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');assert r.returncode==0,r.stderr
uploads=[]
for source,name in files:
    r=remote.upload(source,STAGE+'/'+name);uploads.append({'name':name,'returnCode':r.returncode,'stderr':r.stderr.decode()})
    (PROOF/'uploads.json').write_text(json.dumps(uploads,indent=2)+'\n');assert r.returncode==0,'Transfer failed;partial retained,no retry'
verify='''import pathlib,json,hashlib
root=pathlib.Path(REQUEST['stage'])
for name,expected in REQUEST['files'].items():
 p=root/name;assert p.is_file() and not p.is_symlink() and p.stat().st_size==expected['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==expected['sha256']
print(json.dumps({'passed':True,'uploadedFilesVerified':len(REQUEST['files'])}))
'''
r=remote.run('python3 -B -',input='REQUEST='+repr(plan)+'\n'+verify,timeout=25);assert r.returncode==0,r.stderr
(PROOF/'staged-file-verification.json').write_text(r.stdout)
cmd=['python3','-B',STAGE+'/sparse-restore-native.py','--repo',STAGE,'--destination',DEST,'--execute']
(PROOF/'invocation.json').write_text(json.dumps({'argv':cmd},indent=2)+'\n')
r=remote.run(' '.join(shlex.quote(v) for v in cmd),timeout=300)
(PROOF/'restore.stdout').write_text(r.stdout);(PROOF/'restore.stderr').write_text(r.stderr)
(PROOF/'transport.json').write_text(json.dumps({'returnCode':r.returncode},indent=2)+'\n')
print(r.stdout);print(r.stderr);assert r.returncode==0,'Originalclone failed;partial retained;never reissue sameidentity'
