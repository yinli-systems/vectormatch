import campaign as c,json,pathlib,subprocess,sys
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-capacity-long').resolve();c.PROFILE='extended-190k-128';c.COMMON.update({'VECTOR_OUTBOX_CAPACITY':'524288','VECTOR_MAX_HEAP':'2g','VECTOR_STATE_PROFILE':'capacity-190k-v1'})
node=json.loads((c.remote.ROOT/'current-release.json').read_text());assert node['revision']==json.loads((pathlib.Path(__file__).resolve().parent/'release190.json').read_text())['revision'];c.save(c.OUT/'deployment.json',node)
import hashlib
plan=[{'id':'l-refine-13000-w128-r1','rate':13000,'phase':'long-refine','repetition':1}, {'id':'l-confirm-14000-w128-r2','rate':14000,'phase':'long-confirm','repetition':2}, {'id':'l-stress-16000-w128-r1','rate':16000,'phase':'long-stress-confirm','repetition':1}]
c.save(c.OUT/'boundary-plan.json',{'registeredAt':c.now(),'basedOnSummarySha256':hashlib.sha256((c.OUT/'analysis/summary.json').read_bytes()).hexdigest(),'reason':'14000/s first point failed only bounded drain (151.93ms >135.71ms) with all190k accepted. Refine13000, repeat14000 and independently check16000 for stronger overload; fixed source/config/state profile and criteria unchanged.','trials':plan,'arrivalsPerTrial':190000,'workers':128})
for p in plan:
 d=c.trial(p['id'],p['rate'],190000,128,p['phase'],p['repetition']);assert d and d['passed'],'Correctness failed'
 assert json.loads((c.OUT/'runs'/p['id']/'fixed-leader-check.json').read_text())['passed']
 subprocess.run([sys.executable,'-B','scripts/verify-capacity-config.py',str(c.OUT)],check=True)
 subprocess.run([sys.executable,'-B','scripts/analyze-capacity.py','--runs-dir',str(c.OUT/'runs'),'--output-dir',str(c.OUT/'analysis')],check=True)
 row=next(r for r in json.loads((c.OUT/'analysis/summary.json').read_text())['trials'] if r['id']==p['id'])
 assert row['measurementValid'],'Measurement invalid; stop to inspect before more load'
