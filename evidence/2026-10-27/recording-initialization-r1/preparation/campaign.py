from pathlib import Path
import sys,json,fcntl,time,traceback
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,close_case,archive_closed

def final_hash(case):return json.loads((P/('archive-'+case)/'ARCHIVE_MEMBER_MANIFEST.json').read_text())['files']['evidence/cluster-final.bin']['sha256']
with(P/'CONTROLLER.lock').open('a')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  audits={};cases=list(c.PLAN['cases'])
  for case in cases[:6]:
   spec=c.PLAN['cases'][case];c.run(case,'G1',spec['seconds'],True);audits[case]=close_case.close(case);archive_closed.retire(case)
  assert final_hash(cases[0])==final_hash(cases[1])
  state_equal=len({final_hash(n)for n in cases[2:6]})==1;pairs=[]
  for a,b in [(cases[2],cases[3]),(cases[4],cases[5])]:
   x,y=audits[a],audits[b];q=y['fullLatency']['p99Us']/x['fullLatency']['p99Us'];qq=y['fullLatency']['p999Us']/x['fullLatency']['p999Us']
   base_ok=all(v for k,v in x['gates'].items()if k not in ['p99AtMost25ms','p999AtMost100ms','everyMinuteP99AtMost25ms'])
   pairs.append(dict(a=a,b=b,p99Ratio=q,p999Ratio=qq,baselineLatencyGate=x['registeredGatePass'],baselineNonLatencyGates=base_ok,candidateGate=y['registeredGatePass'],passes=state_equal and base_ok and y['registeredGatePass']and q<=.90 and qq<=1.0))
  selected=all(v['passes']for v in pairs);c.save(P/'SELECTION.json',dict(pairs=pairs,finalStateEqual=state_equal,candidateSelected=selected,rule=c.PLAN['selection']));c.progress({'stage':'selection','pairs':pairs,'candidateSelected':selected})
  if selected:
   case=cases[6];spec=c.PLAN['cases'][case];c.run(case,'G1',spec['seconds'],False);audits[case]=close_case.close(case);archive_closed.retire(case)
  c.save(P/'COMPLETE.json',dict(allOriginalArmsClosed=True,allOriginalStagesVerified=all(v['stages']['allOriginalsJoined']==v['originals']for v in audits.values()),allForceJoinsVerified=all(v['forceWait']['allOriginalsJoined']==v['originals']for v in audits.values()),cases=list(audits),candidateSelected=selected,sustainedExecuted=selected,sustainedGatePass=audits[cases[6]]['registeredGatePass']if selected else None,defaultPromoted=False))
 except BaseException as e:
  c.save(P/('FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
