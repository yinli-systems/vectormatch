import campaign as c,json,pathlib,subprocess,sys
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-capacity-long').resolve();c.PROFILE='extended-190k-128';c.COMMON.update({'VECTOR_OUTBOX_CAPACITY':'524288','VECTOR_MAX_HEAP':'2g','VECTOR_STATE_PROFILE':'capacity-190k-v1'})
node=json.loads((c.remote.ROOT/'current-release.json').read_text());assert node['revision']==json.loads((pathlib.Path(__file__).resolve().parent/'release190.json').read_text())['revision'];c.save(c.OUT/'deployment.json',node)
plan=[{'id':f'l-screen-{rate}-w128','rate':rate,'arrivals':min(190000,rate*30),'workers':128,'phase':'long-screen','repetition':1} for rate in [2400,8000,12000,14000,16000,19000]]
c.save(c.OUT/'screen-plan.json',{'registeredAt':c.now(),'nodeRevision':node['revision'],'trials':plan})
for p in plan:
 d=c.trial(p['id'],p['rate'],p['arrivals'],p['workers'],p['phase'],p['repetition']);assert d and d['passed'],'Correctness failed'
 assert json.loads((c.OUT/'runs'/p['id']/'fixed-leader-check.json').read_text())['passed']
 subprocess.run([sys.executable,'-B','scripts/verify-capacity-config.py',str(c.OUT)],check=True)
 subprocess.run([sys.executable,'-B','scripts/analyze-capacity.py','--runs-dir',str(c.OUT/'runs'),'--output-dir',str(c.OUT/'analysis')],check=True)
 row=next(r for r in json.loads((c.OUT/'analysis/summary.json').read_text())['trials'] if r['id']==p['id'])
 if not row['measurementValid'] or not row['observedStableWindow']:
  c.save(c.OUT/'screen-stop.json',{'timestamp':c.now(),'id':p['id'],'reason':'Retain first nonstable/invalid point, inspect and refine/repeat before more load','classification':row['classification'],'validationChecks':row['validationChecks'],'stabilityChecks':row['stabilityChecks']});break
