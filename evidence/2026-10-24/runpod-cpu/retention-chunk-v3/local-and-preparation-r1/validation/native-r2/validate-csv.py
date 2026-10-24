from pathlib import Path
import csv,json,math,hashlib,datetime
work=Path.cwd();base=work/'cluster/build/retention-chunk-native-attempts';out=work/'build/chunk-validation/native-r2';records=[]
for p in sorted(base.glob('attempt-*/chunk-*/load/load-result.json')):
 d=json.loads(p.read_text());load=p.parent;rows=list(csv.DictReader((load/'arrivals.csv').open()));assert len(rows)==6400
 latencies=[];orders=set();late=[]
 for i,row in enumerate(rows):
  assert int(row['arrival_index'])==i and int(row['worker'])==i%128 and int(row['request_seq'])==1+i//128 and row['producer']=='load-w'+str(i%128)
  assert row['status']=='APPLIED' and row['result_code']=='ACCEPTED' and row['unknown_observed_offset_ns']==''
  keys=['scheduled_offset_ns','arrival_offset_ns','dispatch_offset_ns','submit_offset_ns','first_wire_offer_call_offset_ns','first_successful_offer_return_offset_ns','reply_completion_offset_ns'];times=[int(row[k]) for k in keys];assert times==sorted(times),(i,times)
  assert int(row['scheduled_offset_ns'])==i*1_000_000_000//500
  order=int(row['order_id']);assert order not in orders;orders.add(order);latencies.append(times[-1]-times[0]);lateness=times[1]-times[0]
  if lateness>20_000_000:late.append({'arrivalIndex':i,'latenessNs':lateness})
 assert orders==set(range(2,6402));p99=sorted(latencies)[math.ceil(.99*6400)-1];assert p99==d['allArrivalP99Ns']==d['acceptedOrderConditionalP99Ns']
 assert len(late)==d['schedulerLatenessOver20ms'];obs=json.loads((load/'transport-observations.json').read_text());terms=set()
 for sample in obs:
  assert sample['leaderMemberId']==0;terms.add(sample['leadershipTermId'])
  for e in sample['newLeaderEvents']:assert e['leaderMemberId']==0 and e['leadershipTermId']==sample['leadershipTermId']
 assert len(terms)==1;owner=json.loads((load/'owner-after-close.json').read_text());assert owner['ownerThreadAlive'] is False
 rpc=list(csv.DictReader((load/'maintenance/logical-rpc-timings.csv').open()));assert len(rpc)==d['maintenanceRpcMetrics']['logicalRpcCount'];assert all(r['completed']=='true' and int(r['end_monotonic_ns'])-int(r['start_monotonic_ns'])==int(r['elapsed_ns']) for r in rpc)
 records.append({'arm':p.parents[1].name,'arrivals':len(rows),'perArrivalIdentityTimestampOrderAndAll6400DistinctOrderIdsPassed':True,'allArrivalAcceptedP99NsIndependentlyRecomputed':p99,'schedulerTimingValid':d['schedulerTimingValid'],'lateOver20ms':late,'maintenanceCycles':d['maintenanceCycles'],'logicalMaintenanceRpcs':len(rpc),'actualTransportSamples':len(obs),'actualFixedLeader':0,'actualObservedTerms':sorted(terms),'arrivalCsvSha256':hashlib.sha256((load/'arrivals.csv').read_bytes()).hexdigest(),'loadResultSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'scope':'Single local fixedcap4 chunk functional pair; no CPU ABAB or speedup claim'})
with (out/'independent-csv-validation.json').open('x') as f:json.dump({'capturedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'arms':records},f,indent=2);f.write('\n')
print(json.dumps(records))
