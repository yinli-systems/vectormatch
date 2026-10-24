"""Summarize all four preregistered node-only trials using their pinned gates."""
from pathlib import Path
import importlib.util,json,hashlib
BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
spec=importlib.util.spec_from_file_location('fixed_cpu_idle_controller',BASE/'capacity_idle.py');C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
plan_path=REPO/'evidence/2026-10-24/runpod-cpu/registrations'/ (C.MATRIX_ID+'.json')
plan=C.validate_matrix(C.read(plan_path));matrix=REPO/'evidence/2026-10-24/runpod-cpu/matrices'/C.MATRIX_ID
points=C.completed_prefix(matrix,plan,4);assert len(points)==4
rows=[]
for point,child in zip(points,plan['trialPlans']):
 local=Path(point['analysisDirectory']);s=local/'analysis/summary.json';x=C.read(s)['trials'][0];d=x['derived'];trial=local/'raw/evidence/runs'/child['jobId']
 receipt=C.read(matrix/'point-executions'/child['jobId']/'receipt.json');assert receipt['passed'] and receipt['point']==point
 config=local/'raw/pinned-tools/scripts/verify-capacity-config.py'
 assert sha(config)==child['tools']['scripts/verify-capacity-config.py']['sha256']
 verifier=C.import_file('idle_config_'+child['task']['stage'],config)
 idle=C.actual_idle_check(child,verifier,trial)
 assert idle['passed'] and all(n['distinctInstanceCount']==11 for n in idle['nodes'])
 assert x['measurementValid'] and d['unknownAtInitialDeadline']==d['unknownUnresolved']==0
 telemetry=C.read(local/'analysis/cpu-telemetry.json');proc=telemetry['processes']
 rows.append({'stage':child['task']['stage'],'nodeMaxParkNs':child['task']['nodeMaxParkNs'],
  'jobId':child['jobId'],'valid':x['measurementValid'],'finiteStable':x['observedStableWindow'],
  'windowGoodputPerSecond':d['arrivalWindowGoodputPerSecond'],'acceptedIncludingDrain':d['confirmedAccepted'],
  'notSent':d['clientNotSent'],'conditionalAcceptedP99Millis':d['latency']['conditionalAccepted']['p99Millis'],
  'allOfferedAcceptedP99Millis':d['allOfferedAcceptedP99Millis'],'drainSeconds':d['drainSeconds'],
  'initialUnknown':d['unknownAtInitialDeadline'],'finalUnknown':d['unknownUnresolved'],
  'peakObservedOutstanding':x['backlog']['peakObservedOutstanding'],
  'averageLogicalCores':{n:v.get('averageLogicalCores') for n,v in proc.items()},
  'observedProcessRssMaxBytes':{n:v.get('rssBytes',{}).get('maxObserved') for n,v in proc.items()},
  'analysisSha256':sha(s),'telemetrySha256':sha(local/'analysis/cpu-telemetry.json'),
  'completeArchiveSha256':point['completion']['archive']['sha256'],'idleInstanceVerification':idle})
out=REPO/'evidence/2026-10-24/runpod-cpu/node-idle-abab/comparison';out.mkdir(exist_ok=False)
r={'passed':True,'matrixId':C.MATRIX_ID,'matrixPlanSha256':plan['matrixPlanSha256'],'sourceSha256':sha(__file__),
 'rows':rows,'scope':'Single CPU host,threeJVM,loopbackUDP,source433,leader0,sync2,2gheaps,350kfresharrivals/19.444s,W128,Q64,mux1,MTU1248. FixedA1/B1/A2/B2;onlynode maxPark1ms/100us varies. All owned processes stopped and complete archives verified. Per-trial finite observations,not a sustained ceiling or production SLA. A1 has dropped arrivals,so its all-arrivalp99 is null;conditional accepted tails remain explicitly conditional.'}
with (out/'comparison.json').open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
lines=['# Fixed18k node-only max-park A/B/A/B','','All four registered trials passed canonical,asset,leader,configuration,actual idle-instance,raw-arrival and owned-stop/archive checks. Each uses350kfresh arrivals in separate test state. Node maximum park alone changes;the client scheduler/driver/owner remain fixed.','','|Stage|Node max park|Window confirmed/s|Not sent|Accepted-only p99 ms|All-arrival accepted p99 ms|Drain ms|Finite stable|','|---|---:|---:|---:|---:|---:|---:|---|']
for q in rows:
 tail='N/A' if q['allOfferedAcceptedP99Millis'] is None else f"{q['allOfferedAcceptedP99Millis']:.3f}"
 lines.append(f"|{q['stage']}|{q['nodeMaxParkNs']/1000:.0f}us|{q['windowGoodputPerSecond']:.3f}|{q['notSent']}|{q['conditionalAcceptedP99Millis']:.3f}|{tail}|{q['drainSeconds']*1000:.3f}|{q['finiteStable']}|")
lines+=['','Initial/final UNKNOWN0 in all4. The all-offered accepted p99 is unavailable for A1 because10,412arrivals were not sent;the conditional tail must not replace it. Every paired repetition remains reported. These windows measure the deployed client+replicated path on one host,not three-machine fault isolation,HTTP/PG/WS delivery,100M/s or absolute real-time behavior.','','CPU means and sampled RSS per owned process,all input/archive SHA and all33actual idle-instance proofs pertrial appear in [comparison](comparison.json). Sampling spans only observations inside the approximate arrival window and cannot establish individual-order causes. The namespace/cgroup is shared,so it is never counted three times.','','![All four registered trials](node-idle-abab.png)']
with (out/'README.md').open('x') as f:f.write('\n'.join(lines)+'\n')
(out/'summarize-idle-abab.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'passed':True,'output':str(out),'stages':[q['stage'] for q in rows]}))
