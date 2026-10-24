import collections,csv,hashlib,json,math,pathlib,statistics
BASE=pathlib.Path(__file__).resolve().parent
WORK=BASE/'retention-capacity-v3-worktree'
RAW=WORK/'cluster/build/retention-capacity-native-attempts/attempt-05c870af-a152-435b-ba44-ffcbbd6c0b61'
OUT=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/retention-capacity-v3/root-arrival-rpc-audit'
OUT.mkdir(parents=True,exist_ok=False)
results=[]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for cap in (1,4):
 load=RAW/('cap-'+str(cap))/'load';arrivals=load/'arrivals.csv';timings=load/'maintenance/logical-rpc-timings.csv'
 result=json.loads((load/'load-result.json').read_text());rows=list(csv.DictReader(arrivals.open()))
 assert len(rows)==6400 and [int(r['arrival_index']) for r in rows]==list(range(6400))
 ids=set();latencies=[];late=[];in_window=0;window_ns=12_800_000_000
 for i,r in enumerate(rows):
  assert int(r['worker'])==i%128 and int(r['request_seq'])==1+i//128 and r['producer']=='load-w'+str(i%128)
  assert r['status']=='APPLIED' and r['result_code']=='ACCEPTED' and not r['unknown_observed_offset_ns']
  order=int(r['order_id']);assert order not in ids and 2<=order<=6401;ids.add(order)
  scheduled=int(r['scheduled_offset_ns']);arrival=int(r['arrival_offset_ns']);end=int(r['reply_completion_offset_ns']);start=int(r['dispatch_offset_ns'])
  assert scheduled==i*2_000_000 and scheduled<=arrival<=start<=int(r['first_wire_offer_call_offset_ns'])<=int(r['first_physical_admission_offset_ns'])<=end
  latencies.append(end-scheduled);late.append(arrival-scheduled);in_window+=end<=window_ns
 p99=sorted(latencies)[math.ceil(.99*len(latencies))-1]
 assert p99==result['allArrivalP99Ns']==result['allArrivalAcceptedOrderP99Ns']
 assert in_window==result['acceptedOrdersInArrivalWindow'] and in_window/(window_ns/1e9)==result['arrivalWindowGoodputPerSecond']
 assert sum(v>20_000_000 for v in late)==result['schedulerLatenessOver20ms']
 rpc=list(csv.DictReader(timings.open()));groups=collections.defaultdict(list)
 for n,r in enumerate(rpc,1):
  elapsed=int(r['end_monotonic_ns'])-int(r['start_monotonic_ns']);assert int(r['rpc'])==n and elapsed==int(r['elapsed_ns']) and elapsed>=0 and r['completed']=='true'
  groups[r['kind']].append(elapsed)
 assert len(rpc)==1785 and {k:len(v) for k,v in groups.items()}=={'PrepareArchive':3,'ArchiveChunk':975,'FetchEvents':801,'ArchiveCommit':3,'EventAck':3}
 kinds={k:{'count':len(v),'elapsedNs':sum(v),'medianNs':statistics.median(v),'p99Ns':sorted(v)[math.ceil(.99*len(v))-1]} for k,v in groups.items()}
 total=sum(sum(v) for v in groups.values());read_ns=sum(kinds[k]['elapsedNs'] for k in ('ArchiveChunk','FetchEvents'))
 results.append({'batchCap':cap,'arrivals':len(rows),'uniqueAcceptedOrders':len(ids),'allArrivalAcceptedP99Ns':p99,'lateOver20ms':sum(v>20_000_000 for v in late),'schedulerValid':result['schedulerTimingValid'],
                 'arrivalWindowGoodputPerSecond':result['arrivalWindowGoodputPerSecond'],'totalSourceDrainNs':result['totalSourceDrainNs'],'logicalRpcCount':len(rpc),'rpcKinds':kinds,
                 'totalRpcElapsedNs':total,'archiveChunkAndFetchElapsedFraction':read_ns/total,'inputSha256':{p.name:digest(p) for p in (arrivals,timings,load/'load-result.json')},
                 'scope':'Local Mac functional pilot. RPC intervals include client, scheduling, network, replication, service, and evidence work; not pure fsync. One scheduler-invalid arm prevents valid capacity A/B claim.'})
receipt={'passed':True,'sourceCommit':'4102446b333573efde2b33a0eb53a8177575bad5','arms':results,'cpuCloudMeasurement':False,'performanceImprovementProven':False}
(OUT/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');(OUT/pathlib.Path(__file__).name).write_bytes(pathlib.Path(__file__).read_bytes())
print(json.dumps({'passed':True,'arms':[{'cap':r['batchCap'],'p99Ms':r['allArrivalAcceptedP99Ns']/1e6,'rpcSeconds':r['totalRpcElapsedNs']/1e9,'readRpcFraction':r['archiveChunkAndFetchElapsedFraction']} for r in results]}))
