from pathlib import Path
import sys,json,csv,struct,collections,bisect,hashlib,datetime,math
native=Path(sys.argv[1]).resolve();audit=Path(sys.argv[2]).resolve();output=Path(sys.argv[3]).resolve();assert not output.exists();output.mkdir()
state=native/'state' if (native/'state').is_dir() else native;load=state/'load'
verified=json.loads((audit/'RESULT.json').read_text());assert verified['passed']
def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
for name,pin in verified['inputs'].items():
 candidates=[load/name,load/'writer'/name];found=[p for p in candidates if p.is_file()];assert len(found)==1;path=found[0];assert path.stat().st_size==pin['bytes']and sha(path)==pin['sha256']
c=json.loads((load/'configuration.json').read_text());summary=json.loads((load/'load-result.json').read_text());origin=c['scheduledOriginMonotonicNs'];end=origin+20000000000
with(load/'arrivals.csv').open()as f:arrivals=list(csv.DictReader(f))
assert len(arrivals)==c['arrivals'];groups=collections.defaultdict(list);counts=collections.Counter();phase_rows=[]
with(load/'maintenance-v4.bin').open('rb')as f:
 assert f.read(8)==struct.pack('>Ii',0x564d5434,1)
 previous=-1;number=0
 while True:
  raw=f.read(24)
  if not raw:break
  assert len(raw)==24;kind,ordinal,ns,size=struct.unpack('>iqqi',raw);assert ordinal==number+1 and ns>=previous and 0<size<=12288;previous=ns;number+=1;body=f.read(size);assert len(body)==size
  if kind==3:
   row=json.loads(body)
   if 'from'in row:phase_rows.append((ns,row))
phases=[(ns,row['to'])for ns,row in phase_rows];times=[ns for ns,_ in phases]
def phase_at(ns):
 index=bisect.bisect_right(times,ns)-1;return phases[index][1] if index>=0 else 'INITIALIZING'
accepted_admission_phase=collections.Counter()
for row in arrivals:
 counts[row['status']]+=1
 if row['status']!='APPLIED' or row['result_code']!='ACCEPTED':continue
 get=lambda name:int(row[name])
 intervals={'scheduledToReply':('scheduled_offset_ns','reply_completion_offset_ns'),'scheduledToDispatch':('scheduled_offset_ns','dispatch_offset_ns'),'dispatchToSubmit':('dispatch_offset_ns','submit_offset_ns'),'submitToFirstOfferCall':('submit_offset_ns','first_wire_offer_call_offset_ns'),'firstPositiveOfferReturnToReply':('first_successful_offer_return_offset_ns','reply_completion_offset_ns')}
 for label,(a,b)in intervals.items():
  value=get(b)-get(a);assert value>=0,(label,value);groups[label].append(value)
 accepted_admission_phase[phase_at(origin+get('first_successful_offer_return_offset_ns'))]+=1
assert len(groups['scheduledToReply'])==verified['confirmedAcceptedTrades']
def distribution(values):
 if not values:return None
 ordered=sorted(values);return dict(count=len(ordered),p50Ns=ordered[math.ceil(.5*len(ordered))-1],p99Ns=ordered[math.ceil(.99*len(ordered))-1],maximumNs=ordered[-1],meanNs=sum(ordered)/len(ordered))
latencies={label:distribution(values)for label,values in groups.items()}
if summary['allArrivalP99Ns']is not None:assert latencies['scheduledToReply']['p99Ns']==summary['allArrivalP99Ns']
phase_ns=collections.Counter();cycles=[];cycle=None
for (ns,row),(next_ns,_)in zip(phase_rows,phase_rows[1:]):
 overlap=max(0,min(next_ns,end)-max(ns,origin));phase_ns[row['to']]+=overlap
for ns,row in phase_rows:
 if row['from']=='IDLE'and row['to']=='PREPARE_WAIT':assert cycle is None;cycle=dict(startedMonotonicNs=ns,startOffsetNs=ns-origin)
 if row['to']=='IDLE'and row['from']!='INITIALIZING':
  assert cycle is not None;cycle.update(endedMonotonicNs=ns,endOffsetNs=ns-origin,durationNs=ns-cycle['startedMonotonicNs']);cycles.append(cycle);cycle=None
assert cycle is None and len(cycles)==summary['maintenanceCycles']
with(load/'backlog.csv').open()as f:backlog=list(csv.DictReader(f))
window_samples=[r for r in backlog if 0<=int(r['offset_ns'])<=20000000000]
backlog_metrics=dict(samplesInsideArrivalWindow=len(window_samples),maximumSampledQueued=max((int(r['queued'])for r in window_samples),default=0),maximumSampledPending=max((int(r['pending'])for r in window_samples),default=0),sampling='Approximately one second plus actual allocated-directory observer time;not a continuous maximum. Per-worker high water is reported separately by source.',sourcePerWorkerQueueHighWater=summary['maximumObservedQueueSizePerWorker'])
cpu={}
if(native/'observations.jsonl').is_file():
 owners={}
 for path in native.glob('owned-observed-*.json'):
  r=json.loads(path.read_text());owners[r['pid'],r['startTicks']]=r
 samples=collections.defaultdict(list)
 with(native/'observations.jsonl').open()as f:
  for line in f:
   r=json.loads(line);ns=r.get('monotonicNs')
   if ns is None or not origin<=ns<=end:continue
   for process in r['live']:
    if 'userTicks'in process:samples[process['pid'],process['startTicks']].append((ns,process['userTicks']+process['kernelTicks'],r['clockTicksPerSecond'],process.get('residentBytes')))
 for key,values in samples.items():
  if len(values)<2:continue
  first,last=values[0],values[-1];assert last[0]>first[0]and last[1]>=first[1]and last[2]==first[2]
  cpu[str(key[0])]=dict(startTicks=key[1],role=owners.get(key,{}).get('role','parent'),member=owners.get(key,{}).get('member'),samples=len(values),coveredSeconds=(last[0]-first[0])/1e9,averageCpuCores=(last[1]-first[1])/first[2]/((last[0]-first[0])/1e9),maximumSampledResidentBytes=max(x[3]for x in values if x[3]is not None))
finite_gate=summary['scheduledArrivals']==summary['releasedArrivals']==summary['confirmedAcceptedUniqueOrders'] and all(summary[k]==0 for k in ['notSent','unknownObserved','unknownFinal','serverRejected','duplicateOrOutOfRangeAcceptedOrderIds'])and summary['schedulerTimingValid']and summary['arrivalWindowGoodputPerSecond']>=.99*c['ratePerSecond']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)),configuration=dict(ratePerSecond=c['ratePerSecond'],policy=c['fileWorkDispatchPolicy'],profile=c['profileSha256'],code=c['actualCodeSha256'],activeLoadWorkers=127,cut=1536,readWindow=32,page=32,chunk=6144,windowSeconds=20),finiteAcceptanceGate=finite_gate,tenMillisecondP99TargetMet=summary['allArrivalP99Ns']is not None and summary['allArrivalP99Ns']<=10000000,allArrivalAcceptedP99Ns=summary['allArrivalP99Ns'],arrivalWindowGoodputPerSecond=summary['arrivalWindowGoodputPerSecond'],latencyDistributionsConditionalOnAccepted=latencies,acceptedFirstPositiveOfferReturnByObservedCoordinatorPhase=dict(accepted_admission_phase),observedCoordinatorPhaseNsInsideArrivalWindow=dict(phase_ns),maintenanceCycles=cycles,backlog=backlog_metrics,cpuInsideArrivalWindow=cpu,independentAuditResultSha256=sha(audit/'RESULT.json'),scope='Finite point only;post-offer includes replication,polling,reply encoding and client observation. Phase durations are caller-observed. CPU deltas use first/last in-window samples,not full-window interpolation. No HFT,hard real-time,long-run stability or100M certification.')
(output/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['maintenanceCycles','scope']}))
