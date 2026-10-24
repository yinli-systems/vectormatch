expected='8315396ce0386e624933bc4e359e8a80813e0e5420c2afe12bb1a31ce4d328d4'

import pathlib,hashlib,os,sys,json,platform
assert platform.node()=='ed6c0673f5cb' and platform.system()=='Linux' and os.geteuid()==0
raw=sys.stdin.buffer.read(16385);assert len(raw)<=16384 and hashlib.sha256(raw).hexdigest()==expected
x=json.loads(raw);assert x['collectionComplete'] is True and x['rootVerified'] is True and x['round']==1
p=pathlib.Path('/opt/vectormatch-cpu/preparation/window-cloud-abab-r1/release/round-1-collection-gate.json')
for parent in p.parents:assert parent.is_dir() and not parent.is_symlink()
with p.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
print(json.dumps({'passed':True,'sha256':expected,'newMetadataOnly':True,'applicationStarted':False,'ownedNativeDeleted':False}))
