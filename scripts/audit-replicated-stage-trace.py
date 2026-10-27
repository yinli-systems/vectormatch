#!/usr/bin/env python3
"""Join original requests to exact log blocks and commit gates on one attested monotonic clock."""
from pathlib import Path
import argparse,importlib.util,json,csv,collections,bisect,math

def percentile(v):
 s=sorted(v)
 return {k:s[max(0,math.ceil(len(s)*p)-1)]/1e6 if s else None for k,p in [('p50Ms',.5),('p99Ms',.99),('p999Ms',.999),('maxMs',1)]}
def audit_stages(root):
 root=Path(root);window=json.loads((root/'evidence/window.json').read_text());host=json.loads((root/'host.json').read_text())
 events=[];modes=[];namespaces=[];total=0
 for role in range(4):
  p=root/f'stages/node{role}-g0';meta=json.loads((p/'complete.json').read_text());assert meta['dropped']==0 and meta['clock']=='CLOCK_MONOTONIC'
  clock=(p/'clock.txt').read_text().splitlines();assert clock[0]=='CLOCK_MONOTONIC' and clock[1]=='boot='+host['bootId'];namespaces.append(clock[2]);modes.append(meta['recording']);rows=[]
  for f in sorted(p.glob('thread-*.csv')):
   with f.open() as inp:thread=list(csv.DictReader(inp))
   last=-1
   for row in thread:
    row={k:int(v)for k,v in row.items()};assert 1<=row['type']<=11 and row['end_ns']>=row['start_ns'];assert row['end_ns']>=last;last=row['end_ns'];rows.append(row)
  assert len(rows)==meta['rows'];total+=len(rows);events.append(rows)
  if role<3:
   origins=(root/f'node{role}-g0/class-origins.log').read_text()
   for name in ['io.aeron.cluster.ConsensusModuleAgent','io.aeron.cluster.LogPublisher','io.aeron.archive.RecordingWriter','io.aeron.archive.RecordingSession']:
    assert any(name+' source: file:'in line and '/stage-patch.jar'in line for line in origins.splitlines()),name
 assert len(set(namespaces))==1 and len(set(modes))==1
 if not modes[0]:assert total==0;return {'recording':False,'sameKernelClockVerified':True,'rows':0}
 session=window['sessionId']
 with (root/'evidence/samples.csv').open() as inp:samples=list(csv.DictReader(inp))
 def by_type(role,kind):return [e for e in events[role]if e['type']==kind]
 def request_events(role,kind,positive=False):
  out={}
  for e in by_type(role,kind):
   if e['a']==session and (not positive or e['c']>0):out.setdefault(e['b'],[]).append(e)
  return out
 ingress=request_events(0,1);append=request_events(0,2,True);service=[request_events(r,8)for r in range(3)]
 egress=request_events(0,9,True);receive=request_events(3,10);offer=request_events(3,11,True)
 commits=sorted(by_type(0,7),key=lambda e:e['c']);commit_positions=[e['c']for e in commits]
 ack={r:sorted([e for e in by_type(0,6)if e['a']==r],key=lambda e:e['c'])for r in [1,2]}
 ack_positions={r:[e['c']for e in ack[r]]for r in ack}
 # A record may contain multiple commands. Join by publication session and the
 # exact half-open (startPosition, endPosition] interval, not by nearby time.
 blocks=[];recorded=[]
 for role in range(3):
  writes={(e['a'],e['b'],e['c'],e['d']):e for e in by_type(role,3)};forces={(e['a'],e['b'],e['c'],e['d']):e for e in by_type(role,4)}
  assert len(writes)==len(by_type(role,3)) and len(forces)==len(by_type(role,4))
  groups=collections.defaultdict(list)
  for key,w in writes.items():
   assert key in forces,key
   f=forces[key];assert w['end_ns']<=f['start_ns'];groups[w['b']].append((w,f))
  groups={k:sorted(v,key=lambda t:t[0]['d'])for k,v in groups.items()};blocks.append({k:([w['d']for w,f in v],v)for k,v in groups.items()})
  rec=collections.defaultdict(list)
  for e in by_type(role,5):rec[(e['a'],e['b'])].append(e)
  rec={k:sorted(v,key=lambda e:e['c'])for k,v in rec.items()};recorded.append({k:([e['c']for e in v],v)for k,v in rec.items()})
 phases=['source_schedule','source_queue','ingress_delivery','ingress_processing','replication_durability_gate','commit_after_gate','service_dispatch','business_to_reply_offer','reply_delivery','client_finalize']
 output=[];branch=collections.Counter();critical_detail=collections.defaultdict(list)
 def one(m,c):assert len(m.get(c,[]))==1,(c,len(m.get(c,[])));return m[c][0]
 for row in samples:
  assert row['outcome']=='ACCEPTED','Stage attribution requires every original outcome; base audit preserves any failed stream.'
  c=int(row['correlation']);ip=one(ingress,c);ap=one(append,c);op=one(offer,c);eg=one(egress,c);rx=one(receive,c);sv=[one(m,c)for m in service]
  pos=ap['c'];assert all(e['c']==pos for e in sv);assert op['end_ns']<=window['originNs']+int(row['offered_offset_ns'])
  cm=commits[bisect.bisect_left(commit_positions,pos)];follower=min((ack[r][bisect.bisect_left(ack_positions[r],pos)]for r in ack),key=lambda e:e['start_ns'])
  assert cm['b']==follower['b']==ip['c'] and cm['a']==0
  replica=[]
  for role in range(3):
   ends,bs=blocks[role][ap['d']];w,f=bs[bisect.bisect_left(ends,pos)];assert w['c']<pos<=w['d']
   ends,rs=recorded[role][(w['a'],w['b'])];rec=rs[bisect.bisect_left(ends,pos)]
   assert ap['start_ns']<=w['start_ns']<=w['end_ns']<=f['start_ns']<=f['end_ns']<=rec['start_ns']
   replica.append((w,f,rec))
  leader_ready=replica[0][2]['start_ns'];follower_ready=follower['start_ns'];gate=max(leader_ready,follower_ready)
  limiting=0 if leader_ready>=follower_ready else follower['a'];branch['leader'if limiting==0 else'follower-'+str(limiting)]+=1
  planned=window['originNs']+int(row['planned_offset_ns']);release=window['originNs']+int(row['released_offset_ns']);confirm=window['originNs']+int(row['confirmed_offset_ns'])
  anchors=[planned,release,op['start_ns'],ip['start_ns'],ap['start_ns'],gate,cm['start_ns'],sv[0]['start_ns'],eg['start_ns'],rx['start_ns'],confirm]
  assert all(b>=a for a,b in zip(anchors,anchors[1:])),(c,anchors)
  values={k:b-a for k,a,b in zip(phases,anchors,anchors[1:])};assert sum(values.values())==confirm-planned
  w,f,rec=replica[limiting];details={'archive_delivery_and_poll':w['start_ns']-ap['start_ns'],'file_write':w['end_ns']-w['start_ns'],'trace_before_force':f['start_ns']-w['end_ns'],'file_force':f['end_ns']-f['start_ns'],'record_publish':rec['start_ns']-f['end_ns'],'ack_delivery':0 if limiting==0 else follower_ready-rec['start_ns']}
  assert min(details.values())>=0 and sum(details.values())==values['replication_durability_gate']
  for k,v in details.items():critical_detail[k].append(v)
  output.append({'index':int(row['index']),'correlation':c,'session':session,'log_position':pos,'log_session':ap['d'],'full_latency_ns':confirm-planned,'limiting_replica':limiting,'leader_recorded_ns':leader_ready,'first_follower_ack_ns':follower_ready,'commit_start_ns':cm['start_ns'],'commit_end_ns':cm['end_ns'],**{k+'_ns':v for k,v in values.items()},**{'critical_'+k+'_ns':v for k,v in details.items()}})
 out=root/'stage-attribution.csv'
 with out.open('x',newline='')as f:
  w=csv.DictWriter(f,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
 slow=sorted(output,key=lambda e:e['full_latency_ns'],reverse=True)[:max(1,math.ceil(len(output)*.01))]
 slow_total=sum(e['full_latency_ns']for e in slow)
 return {'recording':True,'sameKernelClockVerified':True,'timeNamespace':namespaces[0],'rows':total,'allOriginalsJoined':len(output),'exactLogBlocksVerified':True,'sumOfStagesEqualsFullLatency':True,'gateBranchCounts':dict(branch),'phaseLatency':{k:percentile([r[k+'_ns']for r in output])for k in phases},'criticalGateDetail':{k:percentile(v)for k,v in critical_detail.items()},'slowestOnePercent':{'count':len(slow),'totalLatencyNs':slow_total,'phaseShare':{k:sum(e[k+'_ns']for e in slow)/slow_total for k in phases},'criticalFileForceShare':sum(e['critical_file_force_ns']for e in slow)/slow_total,'requests':slow[:20]},'scope':'same-kernel CLOCK_MONOTONIC; commit/record publication anchored at start of their measured visibility intervals; file-force includes OS descheduling; no physical-media causal claim'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--jfr',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 sp=importlib.util.spec_from_file_location('base_audit',Path(__file__).with_name('audit-replicated-path-probe.py'));m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
 v=m.audit(a.root,a.jfr);v['stages']=audit_stages(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'case':v['case'],'latency':v['fullLatency'],'stages':{k:v['stages'][k]for k in ['recording','sameKernelClockVerified','rows']}}))
