"""Independent, read-only analysis of one fully archived instrumented point."""
from pathlib import Path
import json,sys,tarfile,hashlib,collections,math

def require(v,reason):
 if not v:raise ValueError(reason)

def identity(r):return tuple(r[k]for k in ('id','type','registration','owner','systemId','keyPrefix'))

def analyze(samples,origin,end,expected):
 require(len(samples)>=3,'fewer than three complete samples')
 require(end>origin,'invalid arrival window')
 previous=None;drivers=collections.defaultdict(list);spans=[]
 for ordinal,row in enumerate(samples,1):
  a,b=row['sampleBeginNs'],row['sampleEndNs']
  require(row['ordinal']==ordinal and a<=b,'invalid sample ordinal/span')
  require(previous is None or a>=previous,'overlapping or reversed complete samples');previous=b
  require(len(row['observers'])==3,'incomplete three-driver sample')
  pids=set()
  for o in row['observers']:
   pid=o['driverPid'];require(pid in expected and pid not in pids,'unknown or duplicate driver')
   pids.add(pid);require(o['cncFile']==expected[pid]and o['osReadOnlyMapping']is True,'driver path/read-only mismatch')
   require(a<=o['sampleBeginNs']<=o['sampleEndNs']<=b,'driver sample outside full span')
   rows=o['counters'];require(len({r['id']for r in rows})==len(rows),'duplicate counter IDs')
   drivers[pid].append(o)
  spans.append(b-a)
 require(samples[0]['sampleEndNs']<origin and samples[-1]['sampleBeginNs']>end,'arrival window not bracketed by complete samples')
 result=[]
 for pid,rows in sorted(drivers.items()):
  require(len({r['fileKey']for r in rows})==1,'original driver CnC file identity changed')
  inside=[r for r in rows if r['sampleBeginNs']>=origin and r['sampleEndNs']<=end]
  require(len(inside)>=3,'insufficient in-window observations')
  before=max((r for r in rows if r['sampleEndNs']<origin),key=lambda r:r['sampleEndNs'])
  after=min((r for r in rows if r['sampleBeginNs']>end),key=lambda r:r['sampleBeginNs'])
  maps=[{identity(r):r for r in s['counters']}for s in inside]
  stable=set(maps[0]).intersection(*(set(m)for m in maps[1:]));allkeys=set().union(*(set(m)for m in maps))
  require(any(k[1]==106 for k in stable)and any(k[1]==107 for k in stable),'missing stable archive byte/time counters')
  counters=[]
  for key in sorted(stable):
   first,last=maps[0][key],maps[-1][key];values=[m[key]['value']for m in maps]
   item=dict(identity=dict(zip(('id','type','registration','owner','systemId','keyPrefix'),key)),label=first['label'],firstValue=values[0],lastValue=values[-1],observedChange=values[-1]-values[0],minimumSampledValue=min(values),maximumSampledValue=max(values),sampleCount=len(values))
   if key[1]in (106,107):
    require(all(b>=a for a,b in zip(values,values[1:])),'stable archive cumulative counter regressed')
    item['maximumAdjacentSampleIncrease']=max(b-a for a,b in zip(values,values[1:]))
   if key[1]==105:
    bm={identity(r):r for r in before['counters']};am={identity(r):r for r in after['counters']}
    if key in bm and key in am:item['cumulativeMaximumBeforeWindow']=bm[key]['value'];item['cumulativeMaximumAfterWindow']=am[key]['value'];item['newLifetimeHighAcrossBracket']=am[key]['value']>bm[key]['value']
   counters.append(item)
  result.append(dict(driverPid=pid,cncFile=expected[pid],fileKey=rows[0]['fileKey'],completeSamples=len(rows),insideSamples=len(inside),insideFirstSampleBeginNs=inside[0]['sampleBeginNs'],insideLastSampleEndNs=inside[-1]['sampleEndNs'],insideObservationSpanNs=inside[-1]['sampleEndNs']-inside[0]['sampleBeginNs'],maximumDriverHeartbeatAgeMs=max(r['driverHeartbeatAgeMs']for r in inside),unstableRecordsSkippedInside=sum(r['unstableRecordsSkipped']for r in inside),stableCounterIdentities=len(stable),noncontinuousCounterIdentities=len(allkeys-stable),counters=counters))
 return dict(passed=True,threeOriginalDriversBracketWholeArrivalWindow=True,samples=len(samples),maximumCompleteSampleSpanNs=max(spans),maximumGapBetweenCompleteSamplesNs=max(b['sampleBeginNs']-a['sampleEndNs']for a,b in zip(samples,samples[1:])),drivers=result,limitations=['Instrumented run adds observer CPU/memory/filesystem activity; not pooled with uninstrumented baselines.','Sequential counter reads are not atomic. In-window changes cover only recorded observations, without interpolation.','A cumulative maximum is not a percentile or an arrival-scoped maximum unless a new lifetime high is observed.','Archive total write time includes write/force path; it does not isolate fsync and is not CPU time. Bytes are not a write operation count.','Temporal overlap alone does not establish that archive writes caused a particular reply delay.'])

def main():
 archive=Path(sys.argv[1]);out=Path(sys.argv[2]);require(not out.exists(),'output already exists');out.mkdir()
 with tarfile.open(archive)as t:
  def load(n):return json.load(t.extractfile('original/point/'+n))
  c=load('state/load/configuration.json');native=load('SUCCESS.json');require(native['passed'],'native diagnostic failed')
  observer=load('OBSERVER_STARTED.json');completion=load('counter-watch.jsonl.completion.json')
  require(observer['passed']and completion['passed']and completion['drivers']==3,'watcher incomplete')
  expected={r['pid']:str(Path(c['ownedRoot'] if 'ownedRoot'in c else '/opt/vectormatch-cpu/experiments/v4-counter-diagnostic-4000-x1-r1/state')/('node-'+r['member']+'/driver/cnc.dat'))for r in observer['nodeOriginals']}
  body=t.extractfile('original/point/counter-watch.jsonl').read();require(len(body)==completion['bytes'],'counter byte count differs')
  samples=[json.loads(s)for s in body.splitlines()];require(len(samples)==completion['samples'],'counter sample count differs')
  origin=c['scheduledOriginMonotonicNs'];r=analyze(samples,origin,origin+20_000_000_000,expected)
  r.update(sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rawCounterSha256=hashlib.sha256(body).hexdigest(),nativeArchiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest(),scheduledOriginMonotonicNs=origin,arrivalWindowNs=20_000_000_000,watcherCompletion=completion)
 (out/'RESULT.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
 print(json.dumps({k:v for k,v in r.items()if k not in ('drivers','limitations')}))

if __name__=='__main__':main()
