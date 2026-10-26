#!/usr/bin/env python3
"""Supplement a fully verified sustained-soak audit with arrival-window diagnosis."""
from pathlib import Path
import json,csv,hashlib,datetime,math,collections,re,argparse
parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();R=args.root.resolve()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def q(v,p):return sorted(v)[max(0,math.ceil(len(v)*p)-1)] if v else None
def utc(t):return datetime.datetime.fromisoformat(re.sub(r'(\.\d{6})\d+',r'\1',t).replace('Z','+00:00')).timestamp()
manifest=json.loads((R/'MEMBER_MANIFEST.json').read_text())['files']
for name in ['evidence/result.json','evidence/arrivals.csv']+[f'{prefix}/node{i}-g0/{suffix}' if prefix else f'node{i}-g0/{suffix}' for i in range(4) for prefix,suffix in [('telemetry','jfr-events.jsonl'),('','metrics.jsonl')]]:
 f=R/name;assert f.is_file() and not f.is_symlink() and f.stat().st_size==manifest[name]['bytes'] and sha(f)==manifest[name]['sha256']
r=json.loads((R/'evidence/result.json').read_text());start=utc(r['scheduledOriginUtcApproximate']);end=start+r['arrivalWindowSeconds'];roles=[]
for role in range(4):
 f=R/f'telemetry/node{role}-g0/jfr-events.jsonl';cpu=[];force=[];pauses=[]
 for line in f.open():
  x=json.loads(line)
  if x['type']=='READY':continue
  t=utc(x['start'])
  if x['type']=='jdk.CPULoad':cpu.append((t,x))
  if start<=t<end:
   if x['type']=='jdk.FileForce':force.append(x['durationNs'])
   if x['type']=='jdk.GCPhasePause':pauses.append(x['durationNs'])
 cpu.sort(key=lambda x:x[0]);weighted=covered=0;values=[]
 # JFR CPULoad is a normalized utilization observation for the preceding event interval.
 for (previous,_),(t,x)in zip(cpu,cpu[1:]):
  width=max(0,min(t,end)-max(previous,start))
  if width:
   value=x['jvmUser']+x['jvmSystem'];weighted+=width*value;covered+=width;values.append(value)
 assert abs(covered-(end-start))<0.001
 metrics=[json.loads(l)for l in(R/f'node{role}-g0/metrics.jsonl').open()];inside=[x for x in metrics if start<=x['utc']<end]
 def udp(x):
  lines=x['udp'].splitlines();j=next(i for i,l in enumerate(lines)if l.startswith('Udp:'))
  return dict(zip(lines[j].split()[1:],map(int,lines[j+1].split()[1:])))
 before=udp(inside[0]);after=udp(inside[-1]);threads=[int(x['childStat'].split(') ',1)[1].split()[17])for x in inside]
 roles.append(dict(role=role,sourceSha256=sha(f),jfrTimeWeightedJvmFractionOfTwoVcpus=weighted/covered,estimatedMeanCpuCores=2*weighted/covered,jfrCpuP99Fraction=q(values,.99),threadMin=min(threads),threadMax=max(threads),forceCount=len(force),forceP99Us=q(force,.99)/1000,forceMaxUs=max(force)/1000,gcPauseCount=len(pauses),gcPauseMaxUs=max(pauses,default=0)/1000,udpWindowDeltas={k:after[k]-before[k]for k in before},udpBoundaryScope='first and last metrics fully inside the window; up to one sample interval excluded at each edge'))
rows=list(csv.DictReader((R/'evidence/arrivals.csv').open()));assert len(rows)==r['scheduledArrivals'] and all(x['outcome']=='CONFIRMED_ACCEPTED' for x in rows);latencies={}
for key in ['scheduler_lateness_ns','queue_delay_ns','initial_execute_rtt_ns','scheduled_to_confirmed_ns']:
 values=[int(x[key])for x in rows];latencies[key]={k:q(values,p)/1000 for k,p in [('p50Us',.5),('p99Us',.99),('p999Us',.999)]}
points=[]
for x in rows:points.extend([(int(x['planned_offset_ns']),1),(int(x['confirmed_offset_ns']),-1)])
points.sort(key=lambda x:(x[0],-x[1]));live=peak=0
for _,delta in points:live+=delta;peak=max(peak,live)
assert live==0
out=dict(scope='arrival-window CPU observations and streamed JFR events; observational diagnosis, no causal ABAB claim',startUtc=r['scheduledOriginUtcApproximate'],seconds=r['arrivalWindowSeconds'],roles=roles,latencyComponents=latencies,maxScheduledNotYetConfirmed=peak,allSamples=len(rows),sourceArrivalsSha256=sha(R/'evidence/arrivals.csv'),separateComponentPercentilesAreNotAdditive=True)
args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
