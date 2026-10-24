from pathlib import Path
import json,csv,math,hashlib,datetime
B=Path(__file__).resolve().parent.parent;O=Path(__file__).resolve().parent;output=O/'ANALYSIS.json';assert not output.exists();inputs={};observations=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):inputs[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p));return p
def load(p):return json.loads(pin(p).read_text())
for label,stem,attempt in [('500','first','500'),('1000','rate-1000','1000')]:
 R=B/('current-maintained-capacity-'+stem+'-root-review-r1');L=R/('materialized/attempt-'+attempt+'/idle-arm/load');root=load(R/'ROOT_REVIEW.json');cfg=load(L/'configuration.json');summary=load(L/'load-result.json')
 with pin(L/'arrivals.csv').open()as f:arrivals=list(csv.DictReader(f))
 with pin(L/'maintenance/logical-rpc-timings.csv').open()as f:rpcs=list(csv.DictReader(f))
 cycles=[]
 for path in sorted((L/'maintenance').glob('cycle-*.verified.txt')):
  row=dict(line.split('=',1)for line in pin(path).read_text().splitlines());begin=int(row['cycleStartedMonotonicNs']);end=int(row['cycleEndedMonotonicNs']);first=int(row['logicalRpcCountAtStart']);last=int(row['logicalRpcCountAtEnd']);rows=[r for r in rpcs if first<int(r['rpc'])<=last];assert len(rows)==last-first and all(r['completed']=='true'for r in rows)
  by={}
  for kind in ['PrepareArchive','ArchiveChunk','FetchEvents','ArchiveCommit','EventAck']:
   group=[r for r in rows if r['kind']==kind];assert group;by[kind]=(min(int(r['start_monotonic_ns'])for r in group),max(int(r['end_monotonic_ns'])for r in group))
  edges=[begin,*sum(([a,b]for a,b in by.values()),[]),end];parts=[edges[i+1]-edges[i]for i in range(len(edges)-1)];assert all(v>=0 for v in parts)and sum(parts)==end-begin
  names=['beforePrepare','prepareSpan','prepareToArchiveReadGap','archiveReadSpanIncludingWaveGaps','archiveReadToEventReadGapIncludingVerifyAndWriter','eventReadSpanIncludingWaveGaps','eventReadToCommitGapIncludingVerifyAndWriter','archiveCommitSpan','commitToEventAckGap','eventAckSpan','afterEventAck'];assert len(parts)==len(names)
  cycles.append(dict(cycle=int(row['cycle']),startNs=begin,endNs=end,wallNs=end-begin,partsNs=dict(zip(names,parts))))
 ranked=sorted(arrivals,key=lambda r:int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns']),reverse=True);cohort=ranked[:math.ceil(.01*len(ranked))];total=sum(int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns'])for r in cohort);before=sum(int(r['dispatch_offset_ns'])-int(r['scheduled_offset_ns'])for r in cohort);overlap=sum(max(0,min(int(r['dispatch_offset_ns']),c['endNs']-cfg['scheduledOriginMonotonicNs'])-max(int(r['arrival_offset_ns']),c['startNs']-cfg['scheduledOriginMonotonicNs']))for r in cohort for c in cycles)
 telemetryPath=pin(O/('telemetry-'+label+'.jsonl'));telemetry=[json.loads(l)for l in telemetryPath.open()];roles={}
 for row in telemetry:
  for p in row['owned']:
   if p['available']:roles.setdefault(p['role'],[]).append((row['monotonicNs'],row['clockTicksPerSecond'],p))
 cpu={}
 for role,rows in roles.items():
  a,z=rows[0],rows[-1];elapsed=(z[0]-a[0])/1e9;ticks=(z[2]['userTicks']+z[2]['systemTicks'])-(a[2]['userTicks']+a[2]['systemTicks']);cpu[role]=dict(sampleSpanSeconds=elapsed,sampledProcessCpuSeconds=ticks/a[1],averageCoresAcrossSampleSpan=ticks/a[1]/elapsed,writeBytesDelta=z[2]['io']['write_bytes']-a[2]['io']['write_bytes'],writeSyscallDelta=z[2]['io']['syscw']-a[2]['io']['syscw'],maximumObservedVmRSSBytes=max(r[2]['status']['VmRSSBytes']for r in rows))
 first=telemetry[0]['global']['aggregateCpuTicks'];last=telemetry[-1]['global']['aggregateCpuTicks'];diff=[b-a for a,b in zip(first,last)];globalIOWait=diff[4]/sum(diff);sums={name:sum(c['partsNs'][name]for c in cycles)for name in cycles[0]['partsNs']}
 observations.append(dict(offeredRate=int(label),arrivals=root['plannedArrivals'],allArrivalP99Ns=root['allArrivalP99Ns'],arrivalWindowGoodputPerSecond=root['arrivalWindowGoodputPerSecond'],sampledBacklogHighWater=root['sampledBacklogHighWater'],maintenanceTotalWallNs=sum(c['wallNs']for c in cycles),phaseSumsNs=sums,cycles=cycles,slowestOnePercent=dict(count=len(cohort),sumScheduledToReplyNs=total,beforeDispatchShare=before/total,queueMaintenanceOverlapShare=overlap/total,overlapNotSufficientToProveCausation=True),ownedProcessCpuAndIo=cpu,wholeHostIoWaitTickShare=globalIOWait,wholeHostCountersDoNotIsolateOurStorageCost=True))
assert all(Path(n).stat().st_size==pin['bytes']and sha(Path(n))==pin['sha256']for n,pin in inputs.items());output.write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)),inputs=inputs,allInputsUnchanged=True,observations=observations,scope='Same artifact500vs1000 offered-load observations; phase spans disjoint within each cycle, not summed overlapping RPC elapsed. CPU spans include setup/finalisation. No isolated disk/network/server causality or capacity ceiling.'),indent=2,sort_keys=True)+'\n');print(json.dumps([dict(rate=r['offeredRate'],maintenanceSeconds=r['maintenanceTotalWallNs']/1e9,phasesSeconds={k:v/1e9 for k,v in r['phaseSumsNs'].items()},tail=r['slowestOnePercent'],cpu=r['ownedProcessCpuAndIo'],wholeHostIoWaitTickShare=r['wholeHostIoWaitTickShare'])for r in observations]))
