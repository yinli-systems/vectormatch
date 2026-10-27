from pathlib import Path
import sys,json,time,fcntl,traceback
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,close_case,archive_closed

def retire(case):
 proof=archive_closed.retire(case)
 if c.PLAN['cases'][case]['driverMedium']=='tmpfs':
  code='CASE='+repr(case)+'\nROOT='+repr(c.ROOT)+'\n'+r'''
from pathlib import Path
import json
p=Path('/dev/shm/vectormatch-probe-layout-20261027-r1-'+CASE)
owner=json.loads((p/'OWNER.json').read_text());assert owner['case']==CASE and owner['root']==ROOT
for role in range(4):assert (Path(ROOT)/'experiments'/CASE/('node%d-g0'%role)/'EXIT.json').is_file()
# Driver dirDeleteOnShutdown must already have removed every role. No recursive deletion.
assert {f.name for f in p.iterdir()}=={'OWNER.json'}
(p/'OWNER.json').unlink();p.rmdir();print(json.dumps({'ownedTmpfsRootRemoved':str(p),'durableStateRemoved':False}))
'''
  c.save(P/(case+'-TMPFS_CLOSED.json'),c.checked(code))
 return proof

def main():
 audits={}
 for case in list(c.PLAN['cases'])[:-1]:
  spec=c.PLAN['cases'][case];c.run(case,'G1',spec['seconds'],True)
  audits[case]=close_case.close(case);retire(case)
 promote=True
 for a,b in [('layout-a1','layout-b1'),('layout-a2','layout-b2')]:
  aa,bb=audits[a],audits[b];g=bb['gates']
  if not all(g[k]for k in ['allAccepted','noUnknown','sourceTimingValid','leaderFixed','inWindow99Percent'])or aa['fullLatency']is None or bb['fullLatency']is None or bb['fullLatency']['p99Us']>aa['fullLatency']['p99Us']*.9 or bb['fullLatency']['p999Us']>aa['fullLatency']['p999Us']:promote=False
 c.save(P/'SELECTION.json',{'promotedTmpfs':promote,'policy':c.PLAN['selection']})
 if promote:
  c.run('sustained-r1','G1',1800,False);audits['sustained-r1']=close_case.close('sustained-r1');retire('sustained-r1')
 c.save(P/'COMPLETE.json',{'originalArmsClosed':len(audits),'promotedTmpfs':promote,'longRunSkippedByPrecommittedPolicy':not promote,'longGatePassed':audits['sustained-r1']['registeredGatePass']if promote else None})
if __name__=='__main__':
 with(P/'CONTROLLER.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:main()
  except BaseException as e:
   c.save(P/('FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
