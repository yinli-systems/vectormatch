from pathlib import Path
import json,hashlib,csv,math,datetime
B=Path(__file__).resolve().parent.parent;P=B/'read128-abab-comparison-r1/COMPARISON.json';O=B/'read128-abab-root-comparison-review-r1';assert not O.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
x=json.loads(P.read_text());assert x['passed']and x['allInputsUnchanged']and len(x['observations'])==4 and len(x['pairs'])==2
for n,pin in x['inputs'].items():p=Path(n);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
lineages=[];plans=[];observations=[]
for i,obs in enumerate(x['observations'],1):
 assert obs['arm']==i and obs['readWindow']==(32,128,32,128)[i-1];root=B/('read128-arm-%d-root-review-r1'%i);L=root/('materialized/arm-%d/idle-arm/load'%i);summary=json.loads((L/'load-result.json').read_text());cfg=json.loads((L/'configuration.json').read_text());lineages.append(cfg['lineage']);plan=json.loads((L/'admission-plan.json').read_text());assert plan.pop('requestedReadWindow')==obs['readWindow'];plans.append(plan)
 with(L/'arrivals.csv').open()as f:rows=list(csv.DictReader(f))
 assert len(rows)==20000 and {int(r['arrival_index'])for r in rows}==set(range(20000));values=sorted(int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns'])for r in rows);p99=values[math.ceil(.99*len(values))-1];p50=values[math.ceil(.5*len(values))-1];accepted=sum(int(r['reply_completion_offset_ns'])<=20000000000 for r in rows);assert(p99,p50,accepted/20)==(obs['p99Ns'],obs['p50Ns'],obs['goodput']);assert all(r['status']=='APPLIED'and r['result_code']=='ACCEPTED'and r['reply_replayed']=='false'and not r['unknown_observed_offset_ns']for r in rows)
 cycles=list((L/'maintenance').glob('cycle-*.verified.txt'));wall=0
 for p in cycles:
  row=dict(line.split('=',1)for line in p.read_text().splitlines());wall+=int(row['cycleEndedMonotonicNs'])-int(row['cycleStartedMonotonicNs']);assert row['forceAndReadbackBeforeBothAcks']=='true'
 assert len(cycles)==7 and wall==obs['maintenanceTotalWallNs'];assert summary['schedulerTimingValid']and summary['schedulerLatenessOver20ms']==0 and summary['physicalOfferTape']['readOnlyRawRegistryHighWater']==obs['actualReadRegistryHighWater'];observations.append(dict(arm=i,p99Ns=p99,p50Ns=p50,goodput=accepted/20,maintenanceNs=wall))
assert len(set(lineages))==4 and all(plan==plans[0]for plan in plans)
for old,new,pair in zip(observations[::2],observations[1::2],x['pairs']):
 assert pair['p99ReductionFraction']==1-new['p99Ns']/old['p99Ns']and pair['maintenanceWallReductionFraction']==1-new['maintenanceNs']/old['maintenanceNs']and pair['inWindowGoodputDelta']==new['goodput']-old['goodput']
O.mkdir();(O/'ROOT_REVIEW.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),comparisonSha256=sha(P),sourceSha256=sha(Path(__file__)),allFourOriginalCsvP50P99AndInWindowCountsRecomputed=True,allCyclesForceReadbackAndActualReadRegistryVerified=True,allCommonBudgetsEqualApartFromSelection=True,allInputsUnchanged=True,distinctFreshLineages=4,observations=observations,pairs=x['pairs'],noCapacityCeilingOrHardRealtimeClaim=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,observations=observations,pairs=x['pairs'])))
