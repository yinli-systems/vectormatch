from pathlib import Path
import json,tarfile,csv,io,hashlib,math,sys,datetime,struct,bisect,collections
B=Path(__file__).resolve().parent.parent;O=B/('v4-sealed-egress-tail-analysis-'+sys.argv[1]);assert not O.exists();arms=sys.argv[2:];assert arms and len(set(arms))==len(arms)and set(arms)<=set(['c1','d1','c2','d2']);results={}
fields=['scheduled_offset_ns','dispatch_offset_ns','submit_offset_ns','first_wire_offer_call_offset_ns','first_successful_offer_return_offset_ns','reply_completion_offset_ns']
names=['scheduledToDispatch','dispatchToSubmit','submitToFirstOfferCall','firstOfferCallToPositiveReturn','positiveReturnToReply']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
def p99(v):return sorted(v)[math.ceil(.99*len(v))-1]
for arm in arms:
 C=B/f'v4-sealed-egress-route-4000-{arm}-closure-r1';m=json.loads((C/'remote-manifest.json').read_text());verified=json.loads((C/'VERIFIED.json').read_text());assert verified['passed']and verified['nativePassed']and verified['independentAuditPassed']and verified['analysisPassed'];a=json.loads((C/'ANALYSIS.json').read_text());archive=C/'complete-native-point-and-independent-audit.tar.gz';assert sha(archive)==verified['archiveSha256'];key='state/load/arrivals.csv';pin=m['sourceScopes']['point']['files'][key]
 with tarfile.open(archive)as t:
  body=t.extractfile('original/point/'+key).read();extras={k:t.extractfile('original/point/state/load/'+k).read()for k in ['configuration.json','maintenance-v4.bin']}
 for k,v in extras.items():
  p=m['sourceScopes']['point']['files']['state/load/'+k];assert len(v)==p['bytes']and hashlib.sha256(v).hexdigest()==p['sha256']
 origin=json.loads(extras['configuration.json'])['scheduledOriginMonotonicNs'];f=io.BytesIO(extras['maintenance-v4.bin']);assert f.read(8)==struct.pack('>Ii',0x564d5434,1);phases=[];previous=-1;ordinal=0
 while True:
  header=f.read(24)
  if not header:break
  assert len(header)==24;kind,n,at,size=struct.unpack('>iqqi',header);assert n==ordinal+1 and at>=previous and 0<size<=12288;ordinal=n;previous=at;raw=f.read(size);assert len(raw)==size
  if kind==3:
   record=json.loads(raw)
   if 'from'in record:phases.append((at,record['to']))
 times=[x[0]for x in phases];assert phases

 assert len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
 rows=[];buckets={i:[]for i in range(20)}
 for expected,row in enumerate(csv.DictReader(io.StringIO(body.decode()))):
  assert int(row['arrival_index'])==expected and row['status']=='APPLIED'and row['result_code']=='ACCEPTED';values=tuple(int(row[k])for k in fields);assert all(x<=y for x,y in zip(values,values[1:]));parts=tuple(y-x for x,y in zip(values,values[1:]));total=values[-1]-values[0];assert sum(parts)==total;entry=(expected,values[0],total,parts);rows.append(entry);bucket=values[0]//1000000000;assert bucket in buckets;buckets[bucket].append(entry)
 assert len(rows)==80000 and p99([r[2]for r in rows])==a['allArrivalAcceptedP99Ns'];tail=sorted(rows,key=lambda r:(r[2],r[0]),reverse=True)[:800]
 per_second={str(k):dict(count=len(v),allArrivalP99Ns=p99([x[2]for x in v]),scheduledToDispatchP99Ns=p99([x[3][0]for x in v]),postOfferP99Ns=p99([x[3][-1]for x in v]),maximumNs=max(x[2]for x in v))for k,v in buckets.items()};assert all(x['count']==4000 for x in per_second.values())
 tail_sum=sum(r[2]for r in tail);parts={name:sum(r[3][i]for r in tail)for i,name in enumerate(names)};assert sum(parts.values())==tail_sum
 overlap=collections.Counter()
 for r in tail:
  at=origin+r[1];end=at+r[3][0];i=bisect.bisect_right(times,at)-1
  while at<end:
   while i+1<len(times)and times[i+1]<=at:i+=1
   stop=min(end,times[i+1]if i+1<len(times)else end);assert stop>at;overlap[phases[i][1]if i>=0 else'INITIALIZING']+=stop-at;at=stop;i+=1
 assert sum(overlap.values())==parts['scheduledToDispatch']
 results[arm]=dict(originalArchiveSha256=verified['archiveSha256'],originalArrivalsSha256=pin['sha256'],all80000OriginalAcceptedRowsChecked=True,perSecond=per_second,tailDefinition='Worst800 original planned arrivals by total scheduled-to-reply latency;deterministic arrival-index tie-break;not a causal model.',tailCount=800,tailTotalLatencySumNs=tail_sum,tailComponentSumsNs=parts,tailComponentFractions={k:v/tail_sum for k,v in parts.items()},tailScheduledSecondsCounts={str(k):sum(r[1]//1000000000==k for r in tail)for k in range(20)},worstOriginalArrival=dict(index=tail[0][0],scheduledNs=tail[0][1],latencyNs=tail[0][2],componentNs=dict(zip(names,tail[0][3]))),globalP99Ns=a['allArrivalAcceptedP99Ns'],callerObservedTailDispatchWaitOverlapByPhaseNs=dict(overlap),callerPhaseOverlapIsNotGcOrSchedulerCausality=True,componentPercentilesMustNotBeAdded=True,noGcOrNetworkOrSchedulerCausalityClaim=True)
O.mkdir();(O/'RESULT.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),arms=results,noRawRowsOrPerformanceOutcomesChanged=True,offlineOnly=True,sourceSha256=sha(Path(__file__))),indent=2,sort_keys=True)+'\n')
print(json.dumps({k:dict(globalP99Ns=v['globalP99Ns'],tailComponentFractions=v['tailComponentFractions'],tailScheduledSecondsCounts=v['tailScheduledSecondsCounts'])for k,v in results.items()}))
