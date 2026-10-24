from pathlib import Path
import json,hashlib,csv,math,datetime
B=Path(__file__).resolve().parent.parent;P=B/'current-read32-abab-comparison-r1/COMPARISON.json';O=B/'current-read32-abab-root-comparison-review-r1';assert not O.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
x=json.loads(P.read_text());assert x['passed']and x['allInputsUnchanged']and len(x['observations'])==4 and len(x['pairs'])==2
for name,row in x['inputs'].items():
 p=Path(name);assert p.stat().st_size==row['bytes']and sha(p)==row['sha256']
verified=[];plans=[]
for i,obs in enumerate(x['observations'],1):
 assert obs['arm']==i and obs['readWindow']==(8,32,8,32)[i-1]
 run=B/('current-read32-arm-%d-collection-r%d'%(i,2 if i==1 else 1))
 with (run/'collection/raw-files/job/idle-arm/load/arrivals.csv').open()as f:rows=list(csv.DictReader(f))
 assert len(rows)==33792 and len({r['arrival_index'] for r in rows})==33792
 values=sorted(int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns'])for r in rows)
 p99=values[math.ceil(.99*len(values))-1];assert p99==obs['rawMetrics']['allArrivalP99Ns']
 assert all(r['status']=='APPLIED'and r['result_code']=='ACCEPTED'and r['reply_replayed']=='false'for r in rows)
 raw=json.loads((run/'raw/result.json').read_text());assert raw['arms'][0]['rawMetrics']==obs['rawMetrics']and raw['arms'][0]['totalMaintenanceCycleNs']==obs['totalMaintenanceCycleNs']
 plan=json.loads((run/'collection/raw-files/job/idle-arm/load/admission-plan.json').read_text());assert plan.pop('requestedReadWindow')==(8,32,8,32)[i-1];plans.append(plan)
 verified.append(dict(arm=i,p99Ns=p99,maintenanceWallNs=obs['totalMaintenanceCycleNs']))
assert all(p==plans[0]for p in plans)
for old,new,pair in zip(verified[::2],verified[1::2],x['pairs']):
 assert (pair['baselineArm'],pair['treatmentArm'])==(old['arm'],new['arm'])
 assert pair['p99ReductionFraction']==1-new['p99Ns']/old['p99Ns']
 assert pair['maintenanceWallReductionFraction']==1-new['maintenanceWallNs']/old['maintenanceWallNs']
 assert pair['arrivalWindowGoodputDelta']==0
O.mkdir();(O/'ROOT_REVIEW.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),comparisonSha256=sha(P),sourceSha256=sha(Path(__file__)),fullFourCsvP99Recomputed=True,allInputBodiesStillUnchanged=True,identicalPlansApartFromSelectedReadWindow=True,observations=verified,pairs=x['pairs'],noNewBenchmark=True,capacityCeilingProven=False,hardRealtimeProven=False),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,observations=verified,pairs=x['pairs'])))
