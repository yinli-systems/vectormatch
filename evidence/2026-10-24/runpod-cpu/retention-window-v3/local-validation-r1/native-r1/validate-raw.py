from pathlib import Path
import csv,json,math,hashlib,collections,datetime
w=Path.cwd();o=w/'build/window-validation/native-r1';reg=json.loads((o/'registration.json').read_text());pair=Path(reg['pairRoot']);results={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for selected in (1,8):
 arm=pair/f'window-{selected}';load=arm/'load';s=json.loads((load/'load-result.json').read_text());c=json.loads((load/'configuration.json').read_text());owner=json.loads((load/'owner-after-close.json').read_text())
 assert json.loads((arm/'completion.json').read_text())['allOwnedStopped'] is True
 assert json.loads((arm/'functional-result.json').read_text())['allThreeSnapshotLogsMatched'] is True
 assert s['readWindow']==c['readWindow']==owner['selectedReadWindow']==selected
 assert owner['closed'] is True and owner['ownerThreadAlive'] is False and owner['readOnlyRetained']==0
 rows=list(csv.DictReader((load/'arrivals.csv').open()));assert len(rows)==6400
 orders=set();latencies=[];window=0;late=0
 for expected,row in enumerate(rows):
  i=int(row['arrival_index']);assert i==expected;assert int(row['worker'])==i%128;assert row['producer']=='load-w'+str(i%128);assert int(row['request_seq'])==i//128+1
  assert row['status']=='APPLIED' and row['result_code']=='ACCEPTED' and row['unknown_observed_offset_ns']==''
  times=[int(row[k]) for k in ['scheduled_offset_ns','arrival_offset_ns','dispatch_offset_ns','submit_offset_ns','first_wire_offer_call_offset_ns','first_successful_offer_return_offset_ns','reply_completion_offset_ns']]
  assert all(a<=b for a,b in zip(times,times[1:]));latencies.append(times[-1]-times[0]);late+=times[1]-times[0]>20_000_000;window+=times[-1]<=12_800_000_000
  order=int(row['order_id']);assert order>0 and order not in orders;orders.add(order)
 p99=sorted(latencies)[math.ceil(.99*len(latencies))-1];assert p99==s['allArrivalAcceptedOrderP99Ns'];assert window==s['acceptedOrdersInArrivalWindow'];assert late==s['schedulerLatenessOver20ms']==0
 timing=list(csv.DictReader((load/'maintenance/logical-rpc-timings.csv').open()));assert len(timing)==s['maintenanceRpcMetrics']['logicalRpcCount']==1298
 counts=collections.Counter();phases={};corrs=set();readrows=[];controls=[]
 for row in timing:
  corr=int(row['correlation_id']);assert corr not in corrs;corrs.add(corr);counts[row['kind']]+=1;assert row['completed']=='true'
  start,end,elapsed=map(int,[row['start_monotonic_ns'],row['end_monotonic_ns'],row['elapsed_ns']]);assert end-start==elapsed>=0
  if row['kind'] in ('ArchiveChunk','FetchEvents'):
   phase=int(row['read_phase_generation']);assert phase>0 and int(row['read_window'])==selected
   armed=int(row['armed_monotonic_ns']);done=int(row['owner_reply_completed_ns']);assert start<=armed<=done<=end
   info=phases.setdefault(phase,{'kind':row['kind'],'start':start,'end':end});assert info['kind']==row['kind'];info['end']=max(info['end'],end);readrows.append(row)
  else:
   assert row['read_phase_generation']=='0' and row['read_window']=='0' and row['armed_monotonic_ns']==row['owner_reply_completed_ns']=='';controls.append((start,end))
 assert counts=={'PrepareArchive':3,'ArchiveChunk':488,'FetchEvents':801,'ArchiveCommit':3,'EventAck':3}
 for start,end in controls:
  assert all(end<=phase['start'] or start>=phase['end'] for phase in phases.values())
 first={}
 for row in csv.DictReader((load/'physical-offer-codes.csv').open()):
  if int(row['return_code'])>=0:first.setdefault(int(row['correlation_id']),int(row['offset_ns']))
 origin=s['scheduledOriginMonotonicNs'];events=[]
 for row in readrows:
  begin=first[int(row['correlation_id'])]+origin;end=int(row['owner_reply_completed_ns']);assert begin<=end
  events.extend([(begin,1),(end,-1)])
 depth=peak=0
 for timestamp,delta in sorted(events,key=lambda e:(e[0],e[1])):depth+=delta;peak=max(peak,depth);assert 0<=depth<=selected
 assert depth==0 and peak==selected
 assert owner['readOnlyOfferedAwaitingReplyHighWater']==selected and owner['readOnlyRetainedHighWater']==selected
 assert owner['readOnlySubmitted']==owner['readOnlyCompleted']==len(readrows)==1289
 plan=json.loads((load/'admission-plan.json').read_text());assert plan['requestedReadWindow']==selected
 result={'acceptedUniqueOrders':len(orders),'allArrivalAcceptedOrderP99Ns':p99,'schedulerLateOver20ms':late,'arrivalWindowAcceptedOrders':window,'arrivalWindowGoodputPerSecond':window/12.8,'maintenanceCycles':s['maintenanceCycles'],'logicalMaintenanceRpcCounts':dict(counts),'phaseCount':len(phases),'observedPositiveReturnToCallbackOverlapPeak':peak,'retainedCreditHighWater':owner['readOnlyRetainedHighWater'],'offeredAwaitingReplyHighWater':owner['readOnlyOfferedAwaitingReplyHighWater'],'scope':'Independent finite raw CSV recount; overlap is tape positive-return observation to owner callback observation, not internal Aeron/network residence. Sum of overlapping per-RPC elapsed times is not maintenance wall time. Local functional proof only.'}
 results[str(selected)]=result
output={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runnerSha256':sha(o/'validate-raw.py'),'nativeRegistrationSha256':sha(o/'registration.json'),'results':results,'passed':True}
with (o/'independent-raw-validation.json').open('x') as f:json.dump(output,f,indent=2);f.write('\n')
print(json.dumps(output))
