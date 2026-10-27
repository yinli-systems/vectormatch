from pathlib import Path
import tarfile,csv,io,json,math,hashlib,datetime,sys,re

def parse_java_instant(value):
 match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z',value)
 if not match:raise ValueError('invalid Java Instant UTC timestamp')
 whole=datetime.datetime.strptime(match.group(1),'%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()
 fraction=match.group(2)
 return whole+(int(fraction)/10**len(fraction)if fraction else 0)
def quantiles(values):
 if not values:return None
 v=sorted(values);n=len(v)
 return {'count':n,'p50Ns':v[(50*n+99)//100-1],'p99Ns':v[(99*n+99)//100-1],'p999Ns':v[(999*n+999)//1000-1],'maxNs':v[-1]}
def analyse(archive,output):
 archive=Path(archive);output=Path(output);assert not output.exists();output.mkdir()
 meta={};accepted=[];post=[];queue=[];scheduling=[];counts={};backlog=[];telemetry=[];rows=0
 wanted={'native/registration.json','native/load/configuration.json','native/load/load-result.json','native/capacity-correctness-result.json','native/completion.json','raw-audit/RESULT.json','complete.json','environment.json','java.exit.json'}
 with tarfile.open(archive,'r|gz')as t:
  for m in t:
   if not m.isfile():continue
   stream=t.extractfile(m)
   if m.name in wanted:
    assert m.size<4*1024**2;value=json.load(stream);meta[m.name]=value;(output/m.name.replace('/','__')).write_text(json.dumps(value,indent=2)+'\n')
   elif m.name=='native/load/arrivals.csv':
    for r in csv.DictReader(line.decode('utf-8') for line in stream):
     assert int(r['arrival_index'])==rows;rows+=1;counts[r['status']]=counts.get(r['status'],0)+1
     scheduling.append(int(r['arrival_offset_ns'])-int(r['scheduled_offset_ns']))
     if r['status']=='APPLIED'and r['result_code']=='ACCEPTED':
      accepted.append(int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns']))
      if r['first_wire_offer_call_offset_ns']:
       first=int(r['first_wire_offer_call_offset_ns']);post.append(int(r['reply_completion_offset_ns'])-first);queue.append(first-int(r['scheduled_offset_ns']))
   elif m.name=='native/load/backlog.csv':backlog=[{k:int(v)for k,v in r.items()}for r in csv.DictReader(line.decode('utf-8') for line in stream)]
   elif m.name=='java.resources.jsonl':telemetry=[json.loads(line)for line in stream]
 assert set(meta)==wanted
 config=meta['native/load/configuration.json'];s=meta['native/load/load-result.json'];reg=meta['native/registration.json'];audit=meta['raw-audit/RESULT.json']
 assert rows==config['arrivals']==s['scheduledArrivals']and len(accepted)==s['confirmedAcceptedUniqueOrders']and audit['passed']and meta['complete.json']['passed']and meta['native/completion.json']['allOwnedStopped']
 all_accepted=len(accepted)==rows and s['notSent']==s['unknownFinal']==s['serverRejected']==s['duplicateOrOutOfRangeAcceptedOrderIds']==0
 q=quantiles(accepted);assert (q['p99Ns']if all_accepted else None)==s['allArrivalP99Ns']
 start=parse_java_instant(config['scheduledOriginUTC']);inside=[r for r in telemetry if start<=r['epoch']<=start+20]
 # CPU deltas use only samples strictly within the arrival window. Samples are sparse, not an entire-run CPU attribution.
 cpu=[]
 if len(inside)>=2:
  left,right=inside[0],inside[-1];duration=right['epoch']-left['epoch'];l={(v['identity']['pid'],v['identity']['startTicks']):v for v in left['processes']}
  for v in right['processes']:
   key=(v['identity']['pid'],v['identity']['startTicks'])
   if key not in l or'stat'not in v or'stat'not in l[key]:continue
   b=l[key]['stat'].split(') ',1)[1].split();e=v['stat'].split(') ',1)[1].split();ticks=int(e[11])+int(e[12])-int(b[11])-int(b[12])
   # USER_HZ is recorded by the worker; never assume the controller host clock rate.
   hz=meta['environment.json']['clockTicksPerSecond'];cpu.append({'pid':key[0],'comm':v['identity']['comm'],'cpuSeconds':ticks/hz,'sampleWindowSeconds':duration,'meanCores':ticks/hz/duration})
 window_backlog=[r for r in backlog if 0<=r['offset_ns']<=20_000_000_000]
 result={'sourceCommit':meta['environment.json']['sourceCommit'],'ratePerSecond':config['ratePerSecond'],'policy':config['fileWorkDispatchPolicy'],'rows':rows,'accepted':len(accepted),'statusCounts':counts,'allArrivalLatency':q if all_accepted else None,'acceptedConditionalLatency':q,'postFirstOfferConditionalLatency':quantiles(post),'plannedToFirstOfferConditionalLatency':quantiles(queue),'schedulerLateness':quantiles(scheduling),'schedulerTimingValid':s['schedulerTimingValid'],'notSent':s['notSent'],'unknownObserved':s['unknownObserved'],'unknownFinal':s['unknownFinal'],'rejected':s['serverRejected'],'inWindowGoodputPerSecond':s['arrivalWindowGoodputPerSecond'],'peakSampledQueueInArrivalWindow':max((r['queued']for r in window_backlog),default=None),'peakSampledPendingInArrivalWindow':max((r['pending']for r in window_backlog),default=None),'lastArrivalWindowBacklogSample':window_backlog[-1]if window_backlog else None,'postWindowDrainNs':s['totalSourceDrainNs'],'insideWindowCpu':cpu,'allRawAuditAndThreeNodeColdRestorePassed':meta['native/capacity-correctness-result.json']['passed']and audit['passed'],'finiteGatePassed':all_accepted and s['schedulerTimingValid']and s['arrivalWindowGoodputPerSecond']>=config['ratePerSecond']*.99,'replicatedSustainedProof':False,'independentHosts':False,'allArrivalP99UndefinedIfAnyPlannedAcceptanceMissing':True,'measurementScope':'20-second finite arrival window; A/B fresh state; all cohorts share the same frozen artifact; no endurance or SLA claim'}
 (output/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':print(json.dumps(analyse(sys.argv[1],sys.argv[2])))
