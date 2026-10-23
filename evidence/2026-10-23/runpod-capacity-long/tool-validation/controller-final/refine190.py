import campaign as c,json,pathlib,subprocess,sys
c.OUT=pathlib.Path('evidence/2026-10-23/runpod-capacity-long').resolve();c.PROFILE='extended-190k-128';c.COMMON.update({'VECTOR_OUTBOX_CAPACITY':'524288','VECTOR_MAX_HEAP':'2g','VECTOR_STATE_PROFILE':'capacity-190k-v1'})
node=json.loads((c.remote.ROOT/'current-release.json').read_text());assert node['revision']==json.loads((pathlib.Path(__file__).resolve().parent/'release190.json').read_text())['revision'];c.save(c.OUT/'deployment.json',node)
import hashlib
rate=int(sys.argv[1]);phase=sys.argv[2];rep=int(sys.argv[3]);assert 6334<=rate<=19000 and phase in ['refine','confirm'] and 1<=rep<=10
ident=f'l-{phase}-{rate}-w128-r{rep}'
summary_path=c.OUT/'analysis/summary.json';previous=json.loads(summary_path.read_text())
plan={'registeredAt':c.now(),'id':ident,'rate':rate,'arrivals':190000,'workers':128,'phase':'long-'+phase,'repetition':rep,'decisionBasedOnCompletedSummarySha256':hashlib.sha256(summary_path.read_bytes()).hexdigest(),'completedTrialsAtDecision':[r['id'] for r in previous['trials']],'reason':'Adaptive interval refinement or boundary confirmation after completed fixed-configuration screen; preserve all outcomes, keep pre-registered stability criteria and exact node/load/profile/seed unchanged'}
c.save(c.OUT/f'adaptive-plan-{ident}.json',plan)
d=c.trial(ident,rate,190000,128,plan['phase'],rep);assert d and d['passed'],'Correctness failed'
assert json.loads((c.OUT/'runs'/ident/'fixed-leader-check.json').read_text())['passed']
subprocess.run([sys.executable,'-B','scripts/verify-capacity-config.py',str(c.OUT)],check=True)
subprocess.run([sys.executable,'-B','scripts/analyze-capacity.py','--runs-dir',str(c.OUT/'runs'),'--output-dir',str(c.OUT/'analysis')],check=True)
