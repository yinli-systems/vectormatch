"""Continue only after the original long run, audit and private archive are closed."""
from pathlib import Path
import subprocess,time,json,sys
P=Path(__file__).resolve().parent;S=P.parents[1]/'client-index-sizing-20261027-r1/cloud'
# P = .../replicated-sustained-20261027-r3/cloud; its grandparent is benchmarks.
S=P.parent.parent/'client-index-sizing-20261027-r1/cloud'
until=time.monotonic()+3600
while not(P/'SUSTAINED_CLOSED.json').exists():
 assert time.monotonic()<until,'long-run closure wait deadline'
 assert not list(P.glob('FAILURE-*.json')),'original long controller failed; inspect preserved original, never rerun it'
 time.sleep(10)
for folder,name in [(P,'diagnose_closed.py'),(P,'restore.py'),(S,'stage.py'),(S,'campaign.py')]:
 print(json.dumps({'stage':'follow_on_start','script':str(folder/name),'epoch':time.time()}),flush=True)
 subprocess.run([sys.executable,'-B',str(folder/name)],cwd=folder,check=True)
(P/'FOLLOW_ON_COMPLETE.json').write_text(json.dumps({'sustainedAndRestoreClosed':True,'allSizingArmsClosed':True,'epoch':time.time()},indent=2)+'\n')
