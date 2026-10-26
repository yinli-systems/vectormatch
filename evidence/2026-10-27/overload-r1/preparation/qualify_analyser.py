from pathlib import Path
import sys,tempfile,tarfile,json,csv,io
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));from analyse_point import analyse
results=[]
for missing in [False,True]:
 with tempfile.TemporaryDirectory(prefix='vectormatch-analysis-check-')as td:
  r=Path(td);archive=r/'fixture.tar.gz';accepted=1 if missing else 2;p99=None if missing else 7000000
  s={'scheduledArrivals':2,'confirmedAcceptedUniqueOrders':accepted,'notSent':int(missing),'unknownFinal':0,'unknownObserved':0,'serverRejected':0,'duplicateOrOutOfRangeAcceptedOrderIds':0,'allArrivalP99Ns':p99,'schedulerTimingValid':True,'arrivalWindowGoodputPerSecond':accepted/20,'totalSourceDrainNs':0}
  docs={'native/registration.json':{},'native/load/configuration.json':{'arrivals':2,'scheduledOriginUTC':'2026-01-01T00:00:00Z','ratePerSecond':.1,'fileWorkDispatchPolicy':'PAUSE'},'native/load/load-result.json':s,'native/capacity-correctness-result.json':{'passed':True},'native/completion.json':{'allOwnedStopped':True},'raw-audit/RESULT.json':{'passed':True},'complete.json':{'passed':True},'environment.json':{'sourceCommit':'synthetic-fixture-only','clockTicksPerSecond':100},'java.exit.json':{'exitCode':0}}
  with tarfile.open(archive,'w:gz')as t:
   def add(name,body):
    body=body.encode();i=tarfile.TarInfo(name);i.size=len(body);t.addfile(i,io.BytesIO(body))
   for name,v in docs.items():add(name,json.dumps(v))
   fields=['arrival_index','arrival_offset_ns','scheduled_offset_ns','status','result_code','reply_completion_offset_ns','first_wire_offer_call_offset_ns'];f=io.StringIO();writer=csv.writer(f);writer.writerow(fields);writer.writerow([0,1000,0,'APPLIED','ACCEPTED',5000000,2000000]);writer.writerow([1,10001000,10000000,'NOT_SENT'if missing else'APPLIED',''if missing else'ACCEPTED',''if missing else 17000000,''if missing else 12000000]);add('native/load/arrivals.csv',f.getvalue());add('native/load/backlog.csv','offset_ns,queued,pending\n0,1,1\n');add('java.resources.jsonl','')
  v=analyse(archive,r/'result');assert(v['allArrivalLatency']is None)==missing;assert v['acceptedConditionalLatency']['count']==accepted;assert v['finiteGatePassed']==(not missing);assert v['postFirstOfferConditionalLatency']['p99Ns']==(3000000 if missing else 5000000)
  results.append({'missingArrival':missing,'passed':True})
(P/'ANALYSER_QUALIFICATION.json').write_text(json.dumps({'scope':'fabricated parser fixtures, not benchmark outcomes','results':results},indent=2)+'\n');print(results)
