"""Read-only post-experiment exact-identity closure; never signals a PID."""
from pathlib import Path
import sys,json,hashlib
BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
OUT=REPO/'evidence/2026-10-24/runpod-cpu/jmh-core-level-iterator/attempts/r2'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
code='''from pathlib import Path
import json,hashlib,platform,datetime
assert platform.node()=='ed6c0673f5cb'
r=Path('/opt/vectormatch-cpu/runs/cpu-jmh-level-iterator-abab-r2')
receipt=json.loads((r/'receipt.json').read_text());assert receipt['passed'] and len(receipt['stages'])==4
checks=[]
def stopped(record,label):
 p=Path('/proc')/str(record['pid']);state='absent'
 try:
  fields=(p/'stat').read_text().rsplit(')',1)[1].split()
  if fields[0]=='Z':state='zombie'
  else:
   actual={'startTicks':int(fields[19]),'commandSha256':hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()}
   expected={'startTicks':record['startTicks'],'commandSha256':record.get('commandSha256',record.get('actualCommandSha256'))}
   assert actual!=expected,'Owned process is still running: '+label
   state='old identity absent; PID reused'
 except FileNotFoundError:pass
 checks.append({'label':label,'pid':record['pid'],'startTicks':record['startTicks'],'state':state,'stopped':True})
launch=json.loads(Path('/workspace/vectormatch-cpu/bootstrap/cpu-jmh-level-iterator-abab-r2/launch.json').read_text());stopped(launch,'controller')
for name in ('A1','B1','A2','B2'):
 s=json.loads((r/(name+'-owned-process-summary.json')).read_text());assert s['forkIdentitiesObserved']==45
 for record in s['records']:
  assert record['stopped'];stopped(record,name+':'+record['kind'])
assert len([x for x in checks if x['label'].endswith(':fork')])==180
print(json.dumps({'passed':True,'allOwnedIdentitiesStoppedNow':True,'verifiedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'receiptSha256':hashlib.sha256((r/'receipt.json').read_bytes()).hexdigest(),'checks':checks,'scope':'Only this registered controller, four JMH runners and their180 recorded measured forks. No process enumeration outside owned identities; no signals.'}))
'''
p=remote.run('python3 -B -',input=code,timeout=30);assert p.returncode==0,p.stderr
r=json.loads(p.stdout);assert r['passed'] and r['receiptSha256']==sha(OUT/'raw/receipt.json');r['sourceSha256']=sha(__file__)
with (OUT/'stopped-before-capacity.json').open('x') as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps({'passed':True,'ownedIdentitiesStoppedNow':len(r['checks'])}))
