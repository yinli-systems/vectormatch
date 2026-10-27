from pathlib import Path
import sys,json,time,traceback,hashlib
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P))
from campaign import archive,analyse,retire,copy_index,launch,wait,progress,save
assert json.loads((P/'LOCAL_VERIFIED_MATERIALIZATION_RETIREMENT_COMPLETE.json').read_text())['onlyByteVerifiedDerivedCopiesRetired']
assert json.loads((P/'7000-a1.worker-closed.json').read_text())['complete']=={'passed':True,'rawAuditPassed':True}
assert json.loads((P/'FAILURE.json').read_text())['failure']=="AssertionError('local exact compressed admission refused')"
registration={'epoch':time.time(),'resumeOnlyClosedNativeA1Archive':True,'noNativeA1Rerun':True,'sameFrozenCandidate':json.loads((P/'CANDIDATE.json').read_text()),'unchangedPointOrder':['7000-a1','7000-b1','7000-a2','7000-b2','8000-a1','8000-b1','8000-a2','8000-b2']}
save('RESUME_REGISTRATION.json',registration)
try:
 for name in registration['unchangedPointOrder']:
  if name=='7000-a1':v=json.loads((P/'7000-a1.worker-closed.json').read_text())['complete']
  else:progress({'stage':'launch','point':name});launch(name);v=wait(name)
  proof=archive(name)
  if v['passed']:
   result=analyse(P/('archive-'+name)/proof['name'],P/('analysis-'+name));progress({'stage':'audited','point':name,'goodput':result['inWindowGoodputPerSecond'],'notSent':result['notSent'],'globalP99Ns':result['allArrivalLatency']['p99Ns']if result['allArrivalLatency']else None})
  copy_index(name);assert v['passed'],'failed correctness/closure; original evidence retained'
  retire(name);copy_index(name);progress({'stage':'private_full_raw_verified','point':name})
 save('COMPLETE.json',{'allEightFiniteOverloadPointsClosed':True,'sustainedProof':False,'localArchivePauseRetained':True,'epoch':time.time()})
except BaseException as e:
 save('RESUME_FAILURE.json',{'failure':repr(e),'traceback':traceback.format_exc(),'epoch':time.time()});raise
