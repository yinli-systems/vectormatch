#!/usr/bin/env python3
"""Collect clone receipt and inspect PG control read-only; never starts recovery."""
from pathlib import Path
import json
import hashlib
import sys

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
sys.path.insert(0,str(BASE));import remote
PROOF=REPO/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-native-clone-r1'
with (PROOF/Path(__file__).name).open('xb') as f:f.write(Path(__file__).read_bytes())
code='''import pathlib,platform,json,hashlib,subprocess,shutil
assert platform.node()=='ed6c0673f5cb'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
root=pathlib.Path('/opt/vectormatch-cpu/restorations/original-native-r1')
assert not any(p.is_symlink() for p in [root]+list(root.parents))
receipt=json.loads((root/'restoration-receipt.json').read_text())
assert receipt['execute'] and receipt['scriptSha256']=='536a630b319c6a190f6e0a624c674382f0c69cf7219ab24e0066e9d887415598' and len(receipt['results'])==len(receipt['nodes'])==3
count=logical=allocated=0
for node,result in zip(receipt['nodes'],receipt['results']):
 assert result['passed'] and set(result['files'])==set(node['inventory'])
 destination=pathlib.Path(node['destination']);assert destination==root/('node'+str(node['node']))
 assert {str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}==set(node['inventory'])
 for name,expected in node['inventory'].items():
  p=destination/name;assert p.is_file() and not p.is_symlink() and p.stat().st_size==expected['bytes'] and result['files'][name]['sha256']==expected['sha256']
 count+=len(result['files']);logical+=result['logicalBytes'];allocated+=result['allocatedBytes']
assert count==1041 and logical==3701302583
pg=root/'node2/runtime/postgres18';inventory=receipt['nodes'][2]['inventory']
critical=['PG_VERSION','global/pg_control']
before={name:sha(pg/name) for name in critical}
for name,value in before.items():assert value==inventory['runtime/postgres18/'+name]['sha256']
tool=pathlib.Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r3/install/bin/pg_controldata')
assert sha(tool)=='0b9c8705202342b508bbe3944f151338a11cfa2ca4f62c1e014de5f0a5ecf26b'
argv=[str(tool),str(pg)]
result=subprocess.run(argv,capture_output=True,text=True,timeout=15,env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'})
after={name:sha(pg/name) for name in critical};assert after==before
fields={key.strip():value.strip() for key,sep,value in (line.partition(':') for line in result.stdout.splitlines()) if sep}
control={'readOnly':True,'argv':argv,'toolSha256':sha(tool),'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'fields':fields,'criticalFilesBeforeSha256':before,'criticalFilesAfterSha256':after,'pgVersionFile':(pg/'PG_VERSION').read_text().strip(),'databaseServerStarted':False,'ownershipMigrated':False,'scope':'Exact stopped clone;fullfile SHAreadback was performed by frozen extractor. This collector checks everyfile inventory/size andrehashes PG criticalfiles aroundreadonlycontrol inspection. No SQL/recovery/locale orprojector lineage validation.'}
control['validControlReadback']=result.returncode==0 and result.stderr=='' and fields.get('pg_control version number')=='1800' and control['pgVersionFile']=='18'
summary={'cloneComplete':True,'files':count,'logicalBytes':logical,'allocatedBytes':allocated,'freeBytes':shutil.disk_usage(root).free,'databaseControlState':fields.get('Database cluster state'),'databaseSystemIdentifier':fields.get('Database system identifier'),'controlReadbackValid':control['validControlReadback'],'allOriginalBackupsPreserved':True,'databaseServerStarted':False}
with (root/'readonly-inspection-r1.json').open('x') as f:json.dump({'summary':summary,'control':control},f,indent=2)
print(json.dumps({'receipt':receipt,'control':control,'summary':summary}))
'''
(PROOF/'remote-inspection.py').write_text(code)
r=remote.run('python3 -B -',input=code,timeout=40)
(PROOF/'inspection-transport.json').write_text(json.dumps({'returnCode':r.returncode,'stderr':r.stderr},indent=2)+'\n');assert r.returncode==0,r.stderr
v=json.loads(r.stdout)
for name,key in (('restoration-receipt.json','receipt'),('pg-control-readonly.json','control'),('summary.json','summary')):
    with (PROOF/name).open('x') as f:json.dump(v[key],f,indent=2);f.write('\n')
assert v['control']['validControlReadback'],'PG control mismatch or warning;keepclone,no server startup'
print(json.dumps(v['summary']))
