import campaign as c,json,pathlib,subprocess,sys
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-capacity-extended').resolve();c.PROFILE='extended-90k';c.COMMON['VECTOR_OUTBOX_CAPACITY']='262144'
plan=[{'id':f'x-refine-{rate:04d}-w64','rate':rate,'arrivals':90000,'workers':64,'phase':'extended-refine','repetition':1} for rate in (7200,7600)]
c.save(c.OUT/'refinement-plan.json',{'registeredAt':c.now(),'reason':'W64 stable6400, overloaded8000; refine unchanged profile before repeated edge trials','trials':plan})
for p in plan:
 d=c.trial(p['id'],p['rate'],p['arrivals'],p['workers'],p['phase'],p['repetition']);assert d and d['passed']
 assert json.loads((c.OUT/'runs'/p['id']/'fixed-leader-check.json').read_text())['passed']
 subprocess.run([sys.executable,'-B','scripts/verify-capacity-config.py',str(c.OUT)],check=True)
 subprocess.run([sys.executable,'-B','scripts/analyze-capacity.py','--runs-dir',str(c.OUT/'runs'),'--output-dir',str(c.OUT/'analysis')],check=True)
