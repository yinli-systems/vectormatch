from pathlib import Path
import sys,json,time,fcntl,traceback
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,close_case,archive_closed

def main():
 audits={}
 for case in list(c.PLAN['cases'])[:-1]:
  spec=c.PLAN['cases'][case];c.run(case,'G1',spec['seconds'],True)
  audits[case]=close_case.close(case);archive_closed.retire(case)
 selected=100000
 for a,b in [('idle-a1','idle-b1'),('idle-a2','idle-b2')]:
  aa,bb=audits[a],audits[b];g=bb['gates']
  if not all(g[k]for k in ['allAccepted','noUnknown','sourceTimingValid','leaderFixed','inWindow99Percent'])or aa['fullLatency']is None or bb['fullLatency']is None or bb['fullLatency']['p99Us']>aa['fullLatency']['p99Us']*.9 or bb['fullLatency']['p999Us']>aa['fullLatency']['p999Us']:selected=1000000
 c.save(P/'SELECTION.json',{'selectedMaxParkNs':selected,'policy':c.PLAN['selection'],'bothPairedCriteriaPassed':selected==100000})
 c.PLAN['cases']['sustained-r1']['maxParkNs']=selected
 c.run('sustained-r1','G1',1800,False);audits['sustained-r1']=close_case.close('sustained-r1');archive_closed.retire('sustained-r1')
 c.save(P/'COMPLETE.json',{'all11NativeArmsClosed':True,'selectedMaxParkNs':selected,'longGatePassed':audits['sustained-r1']['registeredGatePass']})
if __name__=='__main__':
 with(P/'CONTROLLER.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:main()
  except BaseException as e:
   c.save(P/('FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
