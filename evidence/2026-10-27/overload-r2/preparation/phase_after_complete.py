from pathlib import Path
import json,sys,time,subprocess,hashlib,shutil,traceback
P=Path(__file__).resolve().parent;W=P.parent.parent.parent/'worktrees/production-soak-shards';start=time.monotonic()
try:
 while not(P/'COMPLETE.json').exists():
  assert not(P/'PARSER_RESUME_FAILURE.json').exists(),'latest controller failed; do not infer complete points'
  assert time.monotonic()-start<1800,'bounded wait for complete ABAB expired'
  time.sleep(15)
 subprocess.run([sys.executable,str(P/'compare_points.py')],check=True)
 d=P/'phase-analysis';d.mkdir();results={}
 for rate in [7000,8000]:
  for arm in ['a1','b1','a2','b2']:
   name=f'{rate}-{arm}';proof=json.loads((P/('archive-'+name)/'PRIVATE_ASSET_VERIFIED.json').read_text());assert proof['authenticatedFullDownloadVerified']and proof['allOriginalMembersVerified']
   assert shutil.disk_usage(P).free>proof['bytes']+300*1024**2
   f=d/(name+'.tar.gz')
   with f.open('xb')as out:subprocess.run(['/Users/kevin/.local/bin/gh','api','-H','Accept: application/octet-stream','repos/yinli-systems/vectormatch/releases/assets/'+str(proof['assetId'])],stdout=out,check=True,timeout=300)
   assert f.stat().st_size==proof['bytes']
   with(d/(name+'.stdout')).open('xb')as out,(d/(name+'.stderr')).open('xb')as err:subprocess.run([sys.executable,str(W/'scripts/analyse-v4-maintenance-exposure.py'),str(f),'--sha256',proof['sha256'],'--output',str(d/(name+'.json'))],stdout=out,stderr=err,check=True)
   result=json.loads((d/(name+'.json')).read_text());assert result['archiveSha256']==proof['sha256'];results[name]=result;f.unlink();print(json.dumps({'phaseAnalysed':name,'phaseNs':result['phaseNs']}),flush=True)
 (d/'COMPLETE.json').write_text(json.dumps({'allEightOriginalArchivesVerified':True,'privateOriginalsRetained':True,'results':results,'epoch':time.time()},indent=2)+'\n')
except BaseException as e:
 (P/'PHASE_FAILURE.json').write_text(json.dumps({'failure':repr(e),'traceback':traceback.format_exc(),'epoch':time.time()},indent=2)+'\n');raise
