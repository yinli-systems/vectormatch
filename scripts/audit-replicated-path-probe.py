#!/usr/bin/env python3
"""Recompute the bounded diagnostic from all original frames and same-clock times."""
from pathlib import Path
import argparse,base64,collections,csv,datetime,decimal,hashlib,json,math,re,struct,subprocess

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def qs(v):
 s=sorted(v)
 return {k:s[max(0,math.ceil(len(s)*p)-1)]/1000 if s else None for k,p in [('p50Us',.5),('p99Us',.99),('p999Us',.999),('maxUs',1)]}
def epoch(s):return datetime.datetime.fromisoformat(re.sub(r'(\.\d{6})\d+',r'\1',s).replace('Z','+00:00')).timestamp()
class Frame:
 def __init__(self,s):self.b=base64.b64decode(s,validate=True);self.p=0
 def read(self,f):
  f='>'+f;n=struct.calcsize(f);v=struct.unpack_from(f,self.b,self.p);self.p+=n;return v[0] if len(v)==1 else v
 def string(self):
  n=self.read('i');assert 0<=n<=1024;v=self.b[self.p:self.p+n].decode();self.p+=n;return v
 def header(self,kind):assert self.read('i')==0x564d5731 and self.read('h')==2;v=self.read('q');assert self.read('B')==kind;return v
 def end(self):assert self.p==len(self.b)
def audit(root,jfr):
 root=Path(root);manifest=json.loads((root/'MEMBER_MANIFEST.json').read_text())['files']
 for name,v in manifest.items():
  p=root/name;assert not p.is_symlink() and p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],name
 w=json.loads((root/'evidence/window.json').read_text());correct=json.loads((root/'evidence/correctness.json').read_text())
 rows=list(csv.DictReader((root/'evidence/samples.csv').open()));assert len(rows)==w['planned']==w['rate']*w['seconds']
 counts=collections.Counter();lat=[];rtt=[];late=[];sendwait=[];within=0;offered={};accepted=[];sent=0
 for i,r in enumerate(rows):
  assert int(r['index'])==i and int(r['planned_offset_ns'])==i*10**9//w['rate']
  command=Frame(r['command_base64']);corr=command.header(2);assert corr==int(r['correlation'])
  assert command.read('q')==1 and command.string()=='probe-buyer' and command.read('q')==i+2
  assert command.string()=='probe-'+str(i) and command.read('B')==0 and command.read('q')==10000 and command.read('q')==1 and command.read('B')==1;command.end()
  planned=int(r['planned_offset_ns']);release=int(r['released_offset_ns']);assert release>=planned;late.append(release-planned)
  status=r['outcome'];assert status in ['ACCEPTED','REJECTED','NOT_SENT','UNKNOWN'];counts[status]+=1
  if r['offered_offset_ns']:
   sent+=1;offer=int(r['offered_offset_ns']);assert offer>=release and corr>0 and corr not in offered;offered[corr]=r;sendwait.append(offer-release)
  if status=='ACCEPTED':
   assert r['offered_offset_ns'] and r['reply_base64'];confirm=int(r['confirmed_offset_ns']);assert confirm>=offer
   reply=Frame(r['reply_base64']);assert reply.header(1)==corr and reply.read('?') and reply.read('B')==0 and reply.string()=='accepted'
   cmd,order,remaining,trades=reply.read('qqqi');replayed=reply.read('?');seq,events,market=reply.read('qqq');assert reply.string()==reply.string()=='';reply.end()
   if w['mode']=='MATCHING':assert (cmd,order,remaining,trades,replayed,seq,events,market)==(259+sent,257+sent,0,1,False,259+sent,515+2*sent,513+2*sent)
   else:assert (cmd,order,remaining,trades,replayed,seq,events,market)==(0,0,0,0,False,0,0,0)
   lat.append(confirm-planned);rtt.append(confirm-offer);accepted.append((planned,confirm));within+=confirm<w['seconds']*10**9
  elif status=='NOT_SENT':assert not r['offered_offset_ns'] and not r['reply_base64']
 all_ok=counts['ACCEPTED']==len(rows);minutes=[]
 for minute in range(math.ceil(w['seconds']/60)):
  group=[r for r in rows if int(r['planned_offset_ns'])//(60*10**9)==minute];values=[int(r['confirmed_offset_ns'])-int(r['planned_offset_ns']) for r in group if r['outcome']=='ACCEPTED']
  minutes.append(dict(minute=minute,planned=len(group),accepted=len(values),latency=qs(values) if len(values)==len(group) else None))
 workers=[]
 for role in range(3):
  selected=[r for r in csv.DictReader((root/f'worker-{role}.csv').open()) if int(r['session'])==w['sessionId'] and int(r['correlation'])in offered]
  assert len(selected)==len(offered) and {int(r['correlation'])for r in selected}==set(offered)
  for r in selected:assert int(r['request_bytes'])==len(base64.b64decode(offered[int(r['correlation'])]['command_base64']))
  workers.append(dict(role=role,originalCallbacks=len(selected),callbackDuration=qs([int(r['worker_duration_ns'])for r in selected])))
 if w['mode']=='MATCHING':assert all(correct[k]for k in ['matchingResultsAgree','canonicalStateAgrees','invariantsPassed']) and sha(root/'evidence/reference-final.bin')==sha(root/'evidence/cluster-final.bin')
 else:assert correct['noopSentinelsVerified'] and not correct['tradingCorrectnessClaimed']
 start=w['approximateStartEpochMs']/1000;end=start+w['seconds'];telemetry=[]
 types=['jdk.FileForce','jdk.FileWrite','jdk.GarbageCollection','jdk.GCPhasePause','jdk.CPULoad','jdk.DataLoss']
 for role in range(4):
  folder=root/f'telemetry/node{role}-g0';closed=json.loads((folder/'CLOSED.json').read_text());assert not closed['captureFailed']
  stream=collections.Counter();lines=list(folder.joinpath('jfr-events.jsonl').open());assert len(lines)==closed['events']
  for line in lines:
   e=json.loads(line)
   if e['type']=='READY':continue
   assert e['type']in types and e['type']!='jdk.DataLoss'
   stream[(e['type'],e['start'],e['durationNs'],max(-1,e['threadId']) if e['threadId']>0 else -1,e.get('path',''))]+=1
  raw=json.loads(subprocess.check_output([str(jfr),'print','--json','--events',','.join(types),str(folder/'final-buffered-tail.jfr')],timeout=180));tail=collections.Counter()
  for event in raw['recording']['events']:
   kind=event['type'];v=event['values'];path=v.get('path')or'';assert kind!='jdk.DataLoss'
   scope=f'/{root.name}/'+('evidence'if role==3 else'state')
   if kind in ['jdk.FileForce','jdk.FileWrite'] and scope not in path:continue
   duration=v.get('duration','PT0S');m=re.fullmatch(r'PT([0-9.]+)S',duration);assert m
   thread=(v.get('eventThread')or{}).get('javaThreadId',-1)
   tail[(kind,v['startTime'],int(decimal.Decimal(m[1])*10**9),thread if thread>0 else -1,path)]+=1
  union=stream|tail;force=[];gc=[]
  for k,n in union.items():
   if start<=epoch(k[1])<end:
    if k[0]=='jdk.FileForce':force.extend([k[2]]*n)
    if k[0]=='jdk.GCPhasePause':gc.extend([k[2]]*n)
  metrics=[json.loads(l)for l in(root/f'node{role}-g0/metrics.jsonl').open()]
  before=max((x for x in metrics if x['utc']<=start),key=lambda x:x['utc']);after=min((x for x in metrics if x['utc']>=end),key=lambda x:x['utc'])
  launch=json.loads((root/f'node{role}-g0/LAUNCH.json').read_text());assert json.loads((root/f'node{role}-g0/EXIT.json').read_text())['returncode'] in [0,143]
  def ticks(x):
   s=x['childStat'].split(') ',1)[1].split();assert s[19]==launch['startTicks'];return int(s[11])+int(s[12])
  cpu=(ticks(after)-ticks(before))/json.loads((root/'host.json').read_text())['clockTicksPerSecond'];span=after['utc']-before['utc']
  telemetry.append(dict(role=role,cpuSeconds=cpu,enclosingSeconds=span,meanCpuCores=cpu/span,fileForceCount=len(force),fileForce=qs(force),gcPauseCount=len(gc),gcPause=qs(gc),tailOnlyEvents=sum((tail-stream).values()),maxMetricGapSeconds=max(b['utc']-a['utc']for a,b in zip(metrics,metrics[1:]))))
 points=sorted([(int(r['planned_offset_ns']),1)for r in rows]+[(c,-1)for p,c in accepted],key=lambda x:(x[0],-x[1]));live=peak=0
 for _,d in points:live+=d;peak=max(peak,live)
 assert live==len(rows)-len(accepted)
 gates=dict(allAccepted=all_ok,noUnknown=counts['UNKNOWN']==0,sourceTimingValid=max(late)<=20_000_000,leaderFixed=w['leaderChangeObservations']==0,inWindow99Percent=within>=.99*len(rows),p99AtMost25ms=all_ok and qs(lat)['p99Us']<=25000,p999AtMost100ms=all_ok and qs(lat)['p999Us']<=100000,everyMinuteP99AtMost25ms=all(x['latency']and x['latency']['p99Us']<=25000 for x in minutes))
 return dict(case=root.name,mode=w['mode'],seconds=w['seconds'],rate=w['rate'],originals=len(rows),counts=dict(counts),fullLatency=qs(lat)if all_ok else None,conditionalAcceptedLatency=qs(lat),offerToReply=qs(rtt),releaseLateness=qs(late),releaseToOffer=qs(sendwait),sourceLateAbove20ms=sum(x>20_000_000 for x in late),confirmedInWindow=within,inWindowGoodput=within/w['seconds'],maxPlannedNotConfirmed=peak,remainingUnconfirmed=live,workers=workers,telemetry=telemetry,minuteWindows=minutes,gates=gates,registeredGatePass=all(gates.values()),correctness=correct,allRawMembersVerified=True,sourceRowsSha256=sha(root/'evidence/samples.csv'),sourceRecordsDurableDuringWindow=False,physicalFaultDomainClaimed=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--jfr',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=audit(a.root,a.jfr);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:v[k]for k in ['case','counts','fullLatency','sourceLateAbove20ms','registeredGatePass']}))
