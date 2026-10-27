from pathlib import Path
import json,subprocess,hashlib,tarfile,csv,io,heapq
P=Path(__file__).resolve().parent;E=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards/evidence/2026-10-27/process-isolation-r1');GH='/Users/kevin/.local/bin/gh'
for name in ['collector-250000-b1','collector-250000-b2']:
 p=P/('diagnostic-'+name);p.mkdir(exist_ok=True);proof=json.loads((E/name/'PRIVATE_ASSET_VERIFIED.json').read_text());a=p/'original.tar.gz'
 if not a.exists():
  with a.open('xb')as out:q=subprocess.run([GH,'api','-H','Accept: application/octet-stream','repos/yinli-systems/vectormatch/releases/assets/'+str(proof['assetId'])],stdout=out,check=True,timeout=300)
 assert a.stat().st_size==proof['bytes']and hashlib.sha256(a.read_bytes()).hexdigest()==proof['sha256']
 with tarfile.open(a,'r:gz')as t:
  m=json.load(t.extractfile('MEMBER_MANIFEST.json'))['files']
  for n in ['native/server-outcomes.csv','native/commands.csv','native/business-gc.log']:
   raw=t.extractfile(n).read();assert hashlib.sha256(raw).hexdigest()==m[n]['sha256'];(p/Path(n).name).write_bytes(raw)
 setup=0;kind={}
 with(p/'commands.csv').open()as f:
  for r in csv.DictReader(f):
   if r['phase']=='SETUP':setup+=r['kind']!='CANCEL'
   else:kind[int(r['index'])]=r['kind']
 count=setup;slow=[];top=[]
 with(p/'server-outcomes.csv').open()as f:
  for r in csv.DictReader(f):
   i=int(r['index']);duration=int(r['worker_end_ns'])-int(r['worker_start_ns']);accepted=r['accepted']=='true'
   if accepted and kind[i]!='CANCEL':count+=1
   if duration>1_000_000:slow.append(dict(index=i,kind=kind[i],accepted=accepted,serviceNs=duration,retainedOrdersAfter=count,workerStart=int(r['worker_start_ns']),workerEnd=int(r['worker_end_ns']),crossedDefaultHashMapThreshold=accepted and kind[i]!='CANCEL'and count>1 and count-1 in [int(.75*2**n)for n in range(4,28)]))
 report={'case':name,'sourceArchiveSha256':proof['sha256'],'verifiedMembers':{n:m[n]for n in ['native/server-outcomes.csv','native/commands.csv','native/business-gc.log']},'setupOrders':setup,'retainedOrdersFinal':count,'slowAbove1ms':slow,'scope':'Counts accepted non-cancel native originals plus setup; no JVM stack sample; resize attribution remains inference until matched intervention'}
 (p/'DIAGNOSIS.json').write_text(json.dumps(report,indent=2)+'\n');print(name,json.dumps(slow),flush=True)
