from pathlib import Path
import sys,json,fcntl,time,traceback
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,close_case,archive_closed
with(P/'CONTROLLER.lock').open('a')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  audits={}
  for case,spec in c.PLAN['cases'].items():
   c.run(case,'G1',spec['seconds'],True)
   audits[case]=close_case.close(case);archive_closed.retire(case)
  c.save(P/'COMPLETE.json',{'allSixOriginalArmsClosed':True,'allOriginalStagesVerified':all(v['stages'].get('allOriginalsJoined',0)==v['originals']for n,v in audits.items()if c.PLAN['cases'][n]['traceEnabled'])})
 except BaseException as e:
  c.save(P/('FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
