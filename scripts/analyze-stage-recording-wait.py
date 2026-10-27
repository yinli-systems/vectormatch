#!/usr/bin/env python3
"""Recompute slow-tail components and overlap with earlier recording force calls."""
from pathlib import Path
import argparse,csv,json,hashlib,math

p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
manifest=json.loads(a.manifest.read_text())['files'];inputs={}
def read(file):
 name=str(file.relative_to(a.root));v=manifest[name];data=file.read_bytes();sha=hashlib.sha256(data).hexdigest();assert len(data)==v['bytes']and sha==v['sha256'];inputs[name]=sha
 with file.open()as f:return [{k:int(v)for k,v in r.items()}for r in csv.DictReader(f)]
rows=read(a.root/'stage-attribution.csv');slow=sorted(rows,key=lambda r:r['full_latency_ns'],reverse=True)[:math.ceil(len(rows)*.01)];total=sum(r['full_latency_ns']for r in slow)
forces=[]
for role in range(3):
 events=[]
 for file in (a.root/f'stages/node{role}-g0').glob('thread-*.csv'):events.extend(e for e in read(file)if e['type']==4)
 forces.append(events)
overlap=queue=0
for row in slow:
 begin=max(row['leader_recorded_ns'],row['first_follower_ack_ns'])-row['replication_durability_gate_ns'];end=begin+row['critical_archive_delivery_and_poll_ns'];queue+=end-begin
 spans=sorted((max(begin,e['start_ns']),min(end,e['end_ns']))for e in forces[row['limiting_replica']]if e['b']==row['log_session']and e['d']<row['log_position']and e['end_ns']>begin and e['start_ns']<end)
 last=begin
 for start,stop in spans:
  overlap+=max(0,stop-max(start,last));last=max(last,stop)
out={'selectedOriginalMembersVerified':True,'inputSha256':inputs,'slowestCount':len(slow),'fullTailNs':total,'criticalPhaseShareOfFullTail':{k:sum(r[k]for r in slow)/total for k in slow[0]if k.startswith('critical_')},'archiveWaitNs':queue,'overlapWithPriorForceNs':overlap,'overlapShareOfArchiveWait':overlap/queue if queue else 0,'overlapShareOfFullTail':overlap/total,'scope':'Temporal overlap with prior force calls in the same recording. The trace does not identify packet arrival instants or exclude OS descheduling.'}
a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='inputSha256'}))
