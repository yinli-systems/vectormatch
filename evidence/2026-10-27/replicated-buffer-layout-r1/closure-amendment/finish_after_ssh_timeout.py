"""Close the original final arm; never submit or replay a business workload."""
from pathlib import Path
import sys,json,fcntl,time
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
import controller as c,close_case,campaign
with(P/'CONTROLLER.lock').open('a')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 s=c.status('layout-b2');assert all(r['EXIT.json']for r in s['roles'])
 close_case.close('layout-b2');campaign.retire('layout-b2')
 names=list(c.PLAN['cases'])[:-1];audits={n:json.loads((P/(n+'-AUDIT.json')).read_text())for n in names}
 promote=True
 for a,b in [('layout-a1','layout-b1'),('layout-a2','layout-b2')]:
  aa,bb=audits[a],audits[b];g=bb['gates']
  if not all(g[k]for k in ['allAccepted','noUnknown','sourceTimingValid','leaderFixed','inWindow99Percent'])or aa['fullLatency']is None or bb['fullLatency']is None or bb['fullLatency']['p99Us']>aa['fullLatency']['p99Us']*.9 or bb['fullLatency']['p999Us']>aa['fullLatency']['p999Us']:promote=False
 assert not promote,'A promoted candidate requires the registered long run before completing.'
 c.save(P/'SELECTION.json',{'promotedTmpfs':promote,'policy':c.PLAN['selection']})
 c.save(P/'COMPLETE.json',{'originalArmsClosed':len(audits),'promotedTmpfs':promote,'longRunSkippedByPrecommittedPolicy':True,'longGatePassed':None})
 c.save(P/'CLOSURE_RESUMED_COMPLETE.json',{'closed':True,'originalFinalArmRetained':True,'workloadRerun':False,'epoch':time.time()})
 print((P/'COMPLETE.json').read_text(),flush=True)
