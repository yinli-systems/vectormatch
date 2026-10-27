from pathlib import Path
import json,subprocess,hashlib,tarfile,time,sys,shutil
P=Path(__file__).resolve().parent;W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards');E=W/'evidence/2026-10-27/client-index-sizing-r1';GH='/Users/kevin/.local/bin/gh';script=W/'scripts/diagnose-client-index-stalls.py'
for name in ['sizing-250000-a1','sizing-250000-b1','sizing-250000-a2','sizing-250000-b2']:
 until=time.monotonic()+1200;f=E/name/'PRIVATE_ASSET_VERIFIED.json'
 while not f.exists():
  assert time.monotonic()<until and not list(P.glob('FAILURE*')),'preserved native campaign needs inspection';time.sleep(10)
 proof=json.loads(f.read_text());p=P/('diagnostic-'+name);p.mkdir(exist_ok=True);a=p/'original.tar.gz'
 for attempt in range(4):
  try:
   if not a.exists():
    with a.open('xb')as out:q=subprocess.run([GH,'api','-H','Accept: application/octet-stream','repos/yinli-systems/vectormatch/releases/assets/'+str(proof['assetId'])],stdout=out,check=True,timeout=300)
   assert a.stat().st_size==proof['bytes']and hashlib.sha256(a.read_bytes()).hexdigest()==proof['sha256'];break
  except Exception:
   if a.exists():a.rename(a.with_suffix('.partial-'+str(time.time_ns())))
   if attempt==3:raise
   time.sleep(5)
 with tarfile.open(a,'r:gz')as t:
  m=json.load(t.extractfile('MEMBER_MANIFEST.json'))['files']
  for n in ['native/server-outcomes.csv','native/commands.csv']:
   f=p/Path(n).name
   if not f.exists():
    h=hashlib.sha256()
    with f.open('xb')as out:
     inp=t.extractfile(n)
     for b in iter(lambda:inp.read(1024**2),b''):out.write(b);h.update(b)
    assert f.stat().st_size==m[n]['bytes']and h.hexdigest()==m[n]['sha256']
   else:assert hashlib.sha256(f.read_bytes()).hexdigest()==m[n]['sha256']
 dest=E/'diagnosis'/name;dest.mkdir(parents=True,exist_ok=True)
 subprocess.run([sys.executable,str(script),str(p),'--output',str(dest/'DIAGNOSIS.json')],check=True)
 v={'sourcePrivateAsset':proof,'sourceMembers':{n:m[n]for n in ['native/server-outcomes.csv','native/commands.csv']},'analysisSourceSha256':hashlib.sha256(script.read_bytes()).hexdigest(),'authenticatedOriginalDownloadAndSelectedMembersVerified':True}
 (dest/'PROVENANCE.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'diagnosed':name,'largestCall':json.loads((dest/'DIAGNOSIS.json').read_text())['largestWorkerCalls'][0]}),flush=True)
 # All source originals stay in the authenticated private asset. Retire this local duplicate only.
 assert hashlib.sha256(a.read_bytes()).hexdigest()==proof['sha256'];a.unlink()
