import pathlib,platform,json,hashlib,base64
assert platform.node()=='ed6c0673f5cb'
r=pathlib.Path('/opt/vectormatch-cpu/tool-builds/pg18-two-tools-r3');v=json.loads((r/'BUILD_RESULT.json').read_text())
assert v['passed'] and all(x['exitCode']==0 and not x['remainingProcessGroupMembers'] for x in v['commands'])
names=['BUILD_PLAN.json','BUILD_RESULT.json','build/config.log','build/src/include/pg_config.h']+[str(p.relative_to(r)) for p in sorted((r/'logs').glob('*.log'))]+['install/bin/pg_controldata','install/bin/pg_config']
files={}
for name in names:
 p=r/name;assert p.is_file() and not p.is_symlink() and p.stat().st_size<=2*1024**2
 data=p.read_bytes();files[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()}
print(json.dumps({'passed':True,'files':files,'originalDataTouched':False,'toolBuildOnly':True}))
