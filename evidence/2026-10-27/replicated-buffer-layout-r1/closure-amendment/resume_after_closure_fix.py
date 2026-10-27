"""Resume the frozen cohort without repeating the already-completed qualification."""
from pathlib import Path
import sys,json,time,fcntl,traceback
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P))
import controller as c, campaign
original_run=c.run
def resume_run(case,*args,**kwargs):
 if case!='functional-a':return original_run(case,*args,**kwargs)
 proof=c.checked('ROOT='+repr(c.ROOT)+'\n'+r'''
from pathlib import Path
import json,hashlib
p=Path(ROOT)/'experiments/functional-a'
assert all((p/f'node{i}-g0/EXIT.json').is_file()for i in range(4))
for name,v in json.loads((p/'PRE_AMENDMENT_ORIGINAL_HASHES.json').read_text())['files'].items():
 f=p/name;assert f.stat().st_size==v['bytes'] and hashlib.sha256(f.read_bytes()).hexdigest()==v['sha256']
print(json.dumps({'retainedOriginalCase':'functional-a','allPreAmendmentOriginalHashesMatch':True,'workloadRerun':False}))
''',120)
 c.save(P/'ORIGINAL_QUALIFICATION_RETAINED.json',proof)
 print(json.dumps(proof),flush=True)
c.run=resume_run
with(P/'CONTROLLER.lock').open('a')as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 try:
  campaign.main()
  c.save(P/'RESUMED_COMPLETE.json',{'closed':True,'originalQualificationRetained':True,'epoch':time.time()})
 except BaseException as e:
  c.save(P/('RESUME_FAILURE-'+str(time.time_ns())+'.json'),{'error':repr(e),'traceback':traceback.format_exc()});raise
