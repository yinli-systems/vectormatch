from pathlib import Path
import json,csv,hashlib,datetime,math
B=Path('runtime/cloud/cpu-20261024');P=B/'long-cut-backlog-preparation-r1';h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();q=P/'actual-analysis-attempt-r2/derived/result.json';assert h(q)=='b04a9bb0522ecea58813f8d539ca02eb240e7cc19112ff91236a7626d45ba80a';v=json.loads(q.read_text());assert h(P/'SOURCE_FROZEN.json')=='c2df2dc7dff560bc5807bfdbf94d8626392d8f698eb1570bbce936a62b2ca36a'
for name,x in v['inputClosure'].items():p=Path(x['path']);assert p.stat().st_size==x['bytes']and h(p)==x['sha256'],name
rows=list(csv.DictReader(Path(v['inputClosure']['arrivals']['path']).open()));assert len(rows)==33792;cfg=json.loads(Path(v['inputClosure']['configuration']['path']).read_text());origin=cfg['scheduledOriginMonotonicNs'];window=67584000000
cols={'scheduledDue':'scheduled_offset_ns','released':'arrival_offset_ns','dispatched':'dispatch_offset_ns','positiveOffered':'first_successful_offer_return_offset_ns','knownAccepted':'reply_completion_offset_ns'}
def counts(t):
 d={k:sum(int(r[n])<=t for r in rows)for k,n in cols.items()};d.update(offsetNs=t,notYetScheduled=len(rows)-d['scheduledDue'],scheduledNotReleased=d['scheduledDue']-d['released'],releasedNotDispatched=d['released']-d['dispatched'],dispatchedNotYetPositivelyOffered=d['dispatched']-d['positiveOffered'],positivelyOfferedAwaitingReply=d['positiveOffered']-d['knownAccepted'],dispatchedAwaitingReply=d['dispatched']-d['knownAccepted'],releasedNotFullyConfirmed=d['released']-d['knownAccepted'],scheduledDueNotConfirmed=d['scheduledDue']-d['knownAccepted']);return d
cycles=[]
for n in range(1,13):
 text=Path(v['inputClosure']['cycle-'+str(n)]['path']).read_text();kv=dict(x.split('=',1)for x in text.splitlines()if'='in x);actual=v['all12Cycles'][n-1];record={'cycle':n}
 for label,key in [('atCycleStart','cycleStartedMonotonicNs'),('atCycleEnd','cycleEndedMonotonicNs')]:
  d=counts(int(kv[key])-origin);assert all(d[k]==actual[label][k]for k in d),(n,label);record[label]=d
 cycles.append(record)
series=[x for x in cycles if 2<=x['cycle']<=11];fully=[x for x in series if x['atCycleEnd']['offsetNs']<=window];assert [x['cycle']for x in fully]==list(range(2,11));first,last=fully[0]['atCycleEnd'],fully[-1]['atCycleEnd'];span=last['offsetNs']-first['offsetNs'];completed=last['knownAccepted']-first['knownAccepted'];released=last['released']-first['released'];drift=last['releasedNotFullyConfirmed']-first['releasedNotFullyConfirmed'];assert drift==released-completed==-4
ends=[x['atCycleEnd']['releasedNotDispatched']for x in fully];starts=[x['atCycleStart']['releasedNotDispatched']for x in fully];assert ends==[316,287,301,312,299,297,293,293,312]and starts==[3,4,3,3,3,2,2,2,2]
lat=sorted(int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns'])for r in rows);assert lat[math.ceil(.99*len(lat))-1]==554293743
for name,x in v['inputClosure'].items():assert h(Path(x['path']))==x['sha256'],name
out={'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceResultSha256':h(q),'inputFilesRehashed':len(v['inputClosure']),'all12StartAndEndTimestampBucketCountsIndependentlyEqual':True,'fullyOfferedEndCutNumbers':[x['cycle']for x in fully],'fullyOfferedIntervalCount':len(fully)-1,'spanNs':span,'confirmedOrders':completed,'confirmedPerSecond':completed/(span/1e9),'releasedOrders':released,'releasedPerSecond':released/(span/1e9),'releasedNotFullyConfirmedDrift':drift,'releasedNotDispatchedAtEnds':ends,'releasedNotDispatchedAtStarts':starts,'allArrivalP99Ns':554293743,'cut11EndsAfterScheduledWindow':cycles[10]['atCycleEnd']['offsetNs']>window,'all12CycleCounts':cycles,'physicalOwnerQueueOccupancyClaimed':False,'maximumThroughputOrInfiniteStabilityClaimed':False}
p=B/'long-cut-root-recompute-r1/ROOT_REVIEW.json';p.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:x for k,x in out.items()if k!='all12CycleCounts'}))
