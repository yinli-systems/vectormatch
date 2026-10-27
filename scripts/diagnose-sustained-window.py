#!/usr/bin/env python3
"""Diagnose a fully closed soak using original same-clock request and checkpoint rows.

Do not rescale JFR CPU fractions by an assumed host/vCPU count. Process CPU uses
recorded Linux ticks, and its enclosing sample interval is reported explicitly.
"""
from pathlib import Path
import argparse,csv,json,hashlib,math,datetime,bisect,re

def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def qs(xs):
 s=sorted(xs)
 return {k:s[max(0,math.ceil(len(s)*v)-1)]/1000 if s else None for k,v in [('p50Us',.5),('p99Us',.99),('p999Us',.999),('maxUs',1)]}
def utc(s):return datetime.datetime.fromisoformat(re.sub(r'(\.\d{6})\d+',r'\1',s).replace('Z','+00:00')).timestamp()
def diagnose(root,host_measurement):
 root=Path(root);manifest=json.loads((root/'MEMBER_MANIFEST.json').read_text())['files']
 def verified(n):
  p=root/n;v=manifest[n];assert not p.is_symlink()and p.is_file()and p.stat().st_size==v['bytes']and sha(p)==v['sha256'];return p
 def read(n):return json.loads(verified(n).read_text())
 r=read('evidence/result.json');host=json.loads(Path(host_measurement).read_text());host['sourceReceiptSha256']=sha(Path(host_measurement));hz=host['clockTicksPerSecond'];assert isinstance(hz,int)and hz>0
 rows=list(csv.DictReader(verified('evidence/arrivals.csv').open()));intents=list(csv.DictReader(verified('evidence/soak-intents.csv').open()));forces=list(csv.DictReader(verified('evidence/soak-ledger-forces.csv').open()))
 assert len(rows)==len(intents)==r['scheduledArrivals']
 intents={int(x['index']):x for x in intents};assert len(intents)==len(rows)
 start=utc(r['scheduledOriginUtcApproximate']);end=start+r['arrivalWindowSeconds'];roles=[]
 for i in range(4):
  launch=read(f'node{i}-g0/LAUNCH.json');assert launch['boot']==host['bootId']
  metrics=[json.loads(x)for x in verified(f'node{i}-g0/metrics.jsonl').open()]
  assert all(x['childPid']==launch['pid']for x in metrics)
  before=max((x for x in metrics if x['utc']<=start),key=lambda x:x['utc']);after=min((x for x in metrics if x['utc']>=end),key=lambda x:x['utc'])
  def ticks(x):
   s=x['childStat'].split(') ',1)[1].split();assert s[19]==launch['startTicks'];return int(s[11])+int(s[12])
  cpu=(ticks(after)-ticks(before))/hz;span=after['utc']-before['utc'];assert cpu>=0 and span>=r['arrivalWindowSeconds']
  gc=[];force=[];jfr=[]
  for line in verified(f'telemetry/node{i}-g0/jfr-events.jsonl').open():
   x=json.loads(line)
   if x['type']=='READY':continue
   epoch=utc(x['start'])
   if start<=epoch<end:
    minute=int((epoch-start)//60)
    if x['type']=='jdk.GCPhasePause':gc.append((minute,x['durationNs']))
    if x['type']=='jdk.FileForce':force.append((minute,x['durationNs']))
    if x['type']=='jdk.CPULoad':jfr.append(x['jvmUser']+x['jvmSystem'])
  roles.append(dict(role=i,processCpuSeconds=cpu,enclosingSampleSeconds=span,meanCpuCoresInEnclosingSample=cpu/span,cpuMethod='delta /proc/PID/stat user+system ticks divided by observed SC_CLK_TCK and enclosing wall interval',jfrCpuFractionMaxAsRecorded=max(jfr,default=None),streamedGcPauses=qs([d for _,d in gc]),streamedFileForces=qs([d for _,d in force]),streamScope='streamed events in approximate UTC arrival window; final JFR tail is reconciled separately by the full sustained auditor',minuteEvents=[dict(minute=m,forceCount=sum(k==m for k,_ in force),forceMaxUs=max((d/1000 for k,d in force if k==m),default=0),gcPauseCount=sum(k==m for k,_ in gc),gcPauseMaxUs=max((d/1000 for k,d in gc if k==m),default=0))for m in range(math.ceil(r['arrivalWindowSeconds']/60))]))
 intervals=sorted((int(x['checkpoint_offset_ns']),int(x['checkpoint_offset_ns'])+int(x['force_duration_ns']))for x in forces);ends=[b for _,b in intervals]
 assert all(a<=b for a,b in intervals)and all(b<=c for (_,b),(c,_)in zip(intervals,intervals[1:]))
 details=[];delay=[];slow=overlapping_slow=0
 for x in rows:
  i=int(x['index']);planned=int(x['planned_offset_ns']);enqueued=planned+int(x['scheduler_lateness_ns']);intent=int(intents[i]['intent_offset_ns']);assert intent>=enqueued
  d=intent-enqueued;delay.append(d);j=bisect.bisect_right(ends,enqueued);overlap=0
  while j<len(intervals)and intervals[j][0]<intent:
   a,b=intervals[j];overlap+=max(0,min(b,intent)-max(a,enqueued));j+=1
  latency=int(x['scheduled_to_confirmed_ns'])if x['outcome']=='CONFIRMED_ACCEPTED'else None
  if latency is not None and latency>25_000_000:
   slow+=1;overlapping_slow+=overlap>0
  if d>1_000_000:details.append(dict(index=i,preIntentRecordDelayNs=d,overlapWithRecordedCheckpointForceNs=overlap,scheduledToConfirmedNs=latency))
 component={k:qs([int(x[k])for x in rows if x[k]!=''])for k in ['scheduler_lateness_ns','queue_delay_ns','initial_execute_rtt_ns','scheduled_to_confirmed_ns']}
 return dict(scope='Observational diagnosis of the closed native window; same-JVM checkpoint overlap is not a randomized intervention',seconds=r['arrivalWindowSeconds'],originals=len(rows),roles=roles,componentLatencies=component,queueDelayIncludesIntentRecorderAndWorkerWait=True,preIntentRecordDelay=qs(delay),preIntentDelaysAbove1ms=details,acceptedAbove25ms=slow,acceptedAbove25msWithRecordedCheckpointForceOverlap=overlapping_slow,checkpointForceDuration=qs([int(x['force_duration_ns'])for x in forces]),sourceRowsSha256=manifest['evidence/arrivals.csv']['sha256'],sameClockSourceAndCheckpointOffsets=True,separateQuantilesNotAdditive=True,clockTicksProvenance=host)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--host-measurement',type=Path,required=True);a=p.parse_args();v=diagnose(a.root,a.host_measurement);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:v[k]for k in ['seconds','originals','componentLatencies','preIntentRecordDelay','acceptedAbove25ms','acceptedAbove25msWithRecordedCheckpointForceOverlap']}))
