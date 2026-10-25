from pathlib import Path
import json,sys,tarfile,hashlib,csv,io,struct,bisect,collections,math,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';rate=int(sys.argv[1]);O=B/('async-v4-cut-gate-'+str(rate)+'-phase-overlap-r1');assert not O.exists()
def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
results={};pins={}
for arm in ['c1','d1','c2','d2']:
 root=B/('async-v4-cut-gate-'+str(rate)+'-'+arm+'-closure-r1');archive=root/'complete-native-point-and-independent-audit.tar.gz';verified=json.loads((root/'VERIFIED.json').read_text());assert verified['passed']and verified['independentAuditPassed']and sha(archive)==verified['archiveSha256']
 with tarfile.open(archive)as tar:
  configuration=json.load(tar.extractfile('original/point/state/load/configuration.json'));rows=list(csv.DictReader(io.TextIOWrapper(tar.extractfile('original/point/state/load/arrivals.csv'),encoding='ascii')));stream=tar.extractfile('original/point/state/load/maintenance-v4.bin');assert stream.read(8)==struct.pack('>Ii',0x564d5434,1);phases=[];number=0;last=-1
  while True:
   raw=stream.read(24)
   if not raw:break
   kind,ordinal,ns,n=struct.unpack('>iqqi',raw);assert ordinal==number+1 and ns>=last and 0<n<=12288;number+=1;last=ns;body=stream.read(n);assert len(body)==n
   if kind==3:
    value=json.loads(body)
    if 'from'in value:phases.append((ns,value['to']))
 assert configuration['actualCodeSha256']=='65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69'
 assert len(rows)==rate*20;origin=configuration['scheduledOriginMonotonicNs'];times=[ns for ns,_ in phases];allowed={'IDLE'}if arm.startswith('c')else{'IDLE','VERIFY_WAIT','FILE_WAIT'}
 def overlap(first,end):
  assert first<=end;out=collections.Counter();index=bisect.bisect_right(times,first)-1;assert index>=0
  while first<end:
   stop=min(end,times[index+1]if index+1<len(times)else end);out[phases[index][1]]+=stop-first;first=stop;index+=1
  return out
 accepted=[];by_worker={};wait_sum=collections.Counter();previous_inflight_sum=0
 for row in rows:
  if row['status']!='APPLIED' or row['result_code']!='ACCEPTED':continue
  arrival=origin+int(row['arrival_offset_ns']);dispatch=origin+int(row['dispatch_offset_ns']);scheduled=origin+int(row['scheduled_offset_ns']);reply=origin+int(row['reply_completion_offset_ns']);assert scheduled<=arrival<=dispatch<=reply
  parts=overlap(arrival,dispatch);assert sum(parts.values())==dispatch-arrival;wait_sum.update(parts)
  worker=int(row['worker']);previous=by_worker.get(worker);active=0
  if previous is not None:
   assert previous[0]<=dispatch;active=max(0,min(dispatch,previous[1])-max(arrival,previous[0]))
  previous_inflight_sum+=active;by_worker[worker]=(origin+int(row['submit_offset_ns']),reply)
  accepted.append(dict(latency=reply-scheduled,queueNs=dispatch-arrival,phaseNs=parts,previousSameWorkerInFlightOverlapNs=active))
 assert accepted;top=sorted(accepted,key=lambda r:r['latency'],reverse=True)[:math.ceil(.01*len(accepted))];top_parts=collections.Counter()
 for row in top:top_parts.update(row['phaseNs'])
 total_queue=sum(wait_sum.values());top_queue=sum(row['queueNs']for row in top)
 results[arm]=dict(policy=configuration['fileWorkDispatchPolicy'],accepted=len(accepted),allAcceptedArrivalToDispatchWaitNs=total_queue,allAcceptedQueueWaitByPhaseNs=dict(wait_sum),previousSameWorkerInFlightOverlapNs=previous_inflight_sum,allAcceptedWaitOverlappingBusinessForbiddenPhasesNs=sum(n for phase,n in wait_sum.items()if phase not in allowed),slowestOnePercent=dict(count=len(top),minimumEndToEndLatencyNs=min(r['latency']for r in top),arrivalToDispatchWaitNs=top_queue,queueWaitByPhaseNs=dict(top_parts),fractionOfQueueWaitOverlappingBusinessForbiddenPhases=sum(n for phase,n in top_parts.items()if phase not in allowed)/top_queue if top_queue else None,previousSameWorkerInFlightOverlapNs=sum(r['previousSameWorkerInFlightOverlapNs']for r in top)))
 pins[arm]=dict(archiveBytes=archive.stat().st_size,sha256=verified['archiveSha256'])
O.mkdir();result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)),rate=rate,points=results,originalArchivePins=pins,scope='Read-only temporal overlap from actual per-arrival and coordinator phase timestamps. Overlapping wait is not an independent causal attribution;phases and prior in-flight overlap must not be added. This does not isolate network,fsync,GC or server execution latency.')
(O/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+chr(10));print(json.dumps(result))
