import campaign as c,json,pathlib,subprocess,sys
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-capacity-extended').resolve()
c.PROFILE='extended-90k';c.COMMON['VECTOR_OUTBOX_CAPACITY']='262144'
c.save(c.OUT/'deployment.json',json.loads((c.remote.ROOT/'current-release.json').read_text()))
c.record('extended-profile-start',release=c.RELEASE,fixedLeader=0,outboxCapacity=262144,sourceCampaign='runpod-capacity',budget=c.budget(3600))
for rate in (800,1600,2400,3200,4800,6400,8000,9000):
 ident=f'x-screen-{rate:04d}-w64'
 d=c.trial(ident,rate,min(rate*30,90000),64,'extended-screen',1)
 assert d is not None and d['passed'],'Correctness failed'
 check=json.loads((c.OUT/'runs'/ident/'fixed-leader-check.json').read_text());assert check['passed'],'Fixed leadership unverified'
 subprocess.run([sys.executable,'-B','scripts/verify-capacity-config.py',str(c.OUT)],check=True)
 subprocess.run([sys.executable,'-B','scripts/analyze-capacity.py','--runs-dir',str(c.OUT/'runs'),'--output-dir',str(c.OUT/'analysis')],check=True)
 rows=json.loads((c.OUT/'analysis/summary.json').read_text())['trials'];point=next(row for row in rows if row['id']==ident)
 c.record('extended-point-assessed',id=ident,valid=point['measurementValid'],stable=point['observedStableWindow'],classification=point['classification'])
 if not point['observedStableWindow']:
  c.save(c.OUT/'screen-stop.json',{'id':ident,'rate':rate,'valid':point['measurementValid'],'classification':point['classification'],'instruction':'Retain this point; distinguish generator invalidity from true overload, then refine and repeat both sides.'})
  break
