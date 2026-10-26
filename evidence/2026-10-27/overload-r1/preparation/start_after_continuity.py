from pathlib import Path
import json,time,subprocess,sys,os,hashlib,traceback
P=Path(__file__).resolve().parent;A=P.parent/'anchored-continuity-20261027-r1';W=P.parent.parent.parent/'worktrees/production-soak-shards'
expected=json.loads((P/'ORCHESTRATION_INPUTS.json').read_text());start=time.monotonic()
try:
 while not(A/'campaign.complete.json').exists():
  assert not(A/'campaign.resume-r3.failure.json').exists(),'original continuity controller failed; dependent work stays stopped'
  assert time.monotonic()-start<3600,'continuity wait bound reached; no remote work launched'
  time.sleep(15)
 for n,v in expected['files'].items():assert hashlib.sha256((P/n).read_bytes()).hexdigest()==v['sha256'],'orchestration changed after registration: '+n
 assert json.loads((A/'campaign.complete.json').read_text())['acceptedTotal']==100000000
 chain=A/'CHAIN_THROUGH_100M.json';assert not chain.exists()
 subprocess.run([sys.executable,str(W/'scripts/audit-anchored-chain.py'),str(A),'--expected','100000000','--output',str(chain)],check=True)
 subprocess.run([sys.executable,str(P/'retire_closed_duplicates.py')],check=True)
 subprocess.run([sys.executable,str(P/'campaign.py')],check=True)
except BaseException as e:
 (P/'SEQUENCE_FAILURE.json').write_text(json.dumps({'failure':repr(e),'traceback':traceback.format_exc(),'epoch':time.time()},indent=2)+'\n');raise
