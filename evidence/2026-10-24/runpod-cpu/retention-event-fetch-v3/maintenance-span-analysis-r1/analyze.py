from pathlib import Path
import csv,json,hashlib,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs={};reports=[]
def pin(p):inputs[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p))
for arm in range(1,5):
 root=B/('cpu-event-fetch-arm-%d-collection-r1'%arm)/'collection/raw-files/job/idle-arm';m=root/'load/maintenance';q=m/'logical-rpc-timings.csv';pin(q)
 with q.open() as f:rows=list(csv.DictReader(f))
 assert rows and all(x['completed']=='true' for x in rows)
 groups={};controls=[]
 for row in rows:
  lo=int(row['start_monotonic_ns']);hi=int(row['end_monotonic_ns']);assert hi-lo==int(row['elapsed_ns']) and hi>=lo
  if row['kind'] in ['ArchiveChunk','FetchEvents']:groups.setdefault((int(row['read_phase_generation']),row['kind']),[]).append((lo,hi))
  else:assert row['kind'] in ['PrepareArchive','ArchiveCommit','EventAck'];controls.append((lo,hi,row['kind']))
 assert len(groups)==24 and len(controls)==36
 phases=[dict(generation=g,kind=k,startNs=min(x[0] for x in v),endNs=max(x[1] for x in v),rpcs=len(v)) for (g,k),v in sorted(groups.items())]
 cycles=[]
 for n in range(1,13):
  p=m/('cycle-%d.verified.txt'%n);pin(p);d=dict(line.split('=',1) for line in p.read_text().splitlines() if '=' in line);lo=int(d['cycleStartedMonotonicNs']);hi=int(d['cycleEndedMonotonicNs'])
  ps=[x for x in phases if x['startNs']>=lo and x['endNs']<=hi];cs=[(a,b,k) for a,b,k in controls if a>=lo and b<=hi]
  assert len(ps)==2 and len(cs)==3
  intervals=sorted([(x['startNs'],x['endNs']) for x in ps]+[(a,b) for a,b,k in cs]);assert all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:]))
  bykind={x['kind']:x['endNs']-x['startNs'] for x in ps};control=sum(b-a for a,b,k in cs);remainder=hi-lo-sum(bykind.values())-control;assert remainder>=0
  cycles.append(dict(cycle=n,cycleNs=hi-lo,readPhaseSpanNs=bykind,serializedControlRpcNs=control,outsideReadPhaseAndControlRpcIntervalsNs=remainder))
 total=sum(x['cycleNs'] for x in cycles);reads={k:sum(x['readPhaseSpanNs'][k] for x in cycles) for k in ['ArchiveChunk','FetchEvents']};other=sum(x['outsideReadPhaseAndControlRpcIntervalsNs'] for x in cycles);control=sum(x['serializedControlRpcNs'] for x in cycles)
 reports.append(dict(arm=arm,page=16 if arm in[1,3] else 32,readWindow=8,cycleWallNs=total,readPhaseSpansNs=reads,serializedControlRpcNs=control,outsideReadPhaseAndControlRpcIntervalsNs=other,readSpanShare=sum(reads.values())/total,otherShare=other/total,cycles=cycles))
for n,row in inputs.items():p=Path(n);assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Offline interval decomposition of four previously qualified raw event-page arms; no new benchmark',arms=reports,inputs=inputs,limitations=['Read spans are lower bounds from first reservation to last coordinator completion, not exact bank lifetime','RPC spans include waiting/transport/server/scheduling/evidence work; no pure server/network/fsync attribution','Remainder includes all work outside measured intervals and cannot uniquely be called fsync','No causal window32 improvement, hardware counter, throughput ceiling, hard realtime or100M claim'])
with (O/'ANALYSIS.json').open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps([dict(arm=x['arm'],cycleWallNs=x['cycleWallNs'],readPhaseSpansNs=x['readPhaseSpansNs'],serializedControlRpcNs=x['serializedControlRpcNs'],remainderNs=x['outsideReadPhaseAndControlRpcIntervalsNs'],readSpanShare=x['readSpanShare'],otherShare=x['otherShare']) for x in reports]))
