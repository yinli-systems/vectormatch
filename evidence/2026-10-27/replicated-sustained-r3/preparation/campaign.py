from pathlib import Path
import sys,json,time,fcntl,traceback
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,close_case,archive_closed

def main():
 audits={}
 for case,collector in c.PLAN['qualifiedCases'].items():
  c.run(case,collector,30,True);audits[case]=close_case.close(case)
  assert audits[case]['applicationCorrectnessPassed'],'qualification correctness failed'
  archive_closed.retire(case)
 good=True
 for a,b in [('qual-a1','qual-b1'),('qual-a2','qual-b2')]:
  aa,bb=audits[a],audits[b]
  good=good and all(v for k,v in bb['registeredGates'].items()if k!='sustainedWindow30To60Minutes')and not bb['minuteP99Above25ms']and bb['p99Us']<=aa['p99Us']
  # Source rate and counts are identical; full accepted original stream plus all replies within window are checked from result.
  ar=json.loads((close_case.E/a/'evidence__result.json').read_text());br=json.loads((close_case.E/b/'evidence__result.json').read_text())
  good=good and br['confirmedWithinArrivalWindowPerSecond']>=ar['confirmedWithinArrivalWindowPerSecond']
 collector='GEN_ZGC'if good else'G1'
 selection={'selected':collector,'criteria':c.PLAN['selection'],'qualifiedComparisonPassed':bool(good),'cases':list(audits)};c.save(P/'SELECTION.json',selection);c.progress({'stage':'long_selection',**selection})
 c.run('sustained-r1',collector,1800,False);audit=close_case.close('sustained-r1')
 c.save(P/'SUSTAINED_CLOSED.json',{'collector':collector,'audited':True,'rawPrivateVerified':True,'audit':audit})
if __name__=='__main__':
 with(P/'CONTROLLER.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:main()
  except BaseException as e:
   c.save(P/('FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
