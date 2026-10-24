import pathlib,platform,json,hashlib
assert platform.node()=='ed6c0673f5cb'
r=pathlib.Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r1');result=json.loads((r/'BUILD_RESULT.json').read_text())
assert not result['passed'] and all(not x['remainingProcessGroupMembers'] for x in result['commands'])
names=['BUILD_PLAN.json','BUILD_RESULT.json','build/config.log']+[str(p.relative_to(r)) for p in sorted((r/'logs').glob('*.log'))]
files={}
for name in names:
 p=r/name;assert p.is_file() and not p.is_symlink() and p.stat().st_size<=2*1024**2
 files[name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'text':p.read_text(errors='strict')}
print(json.dumps({'result':result,'files':files}))
