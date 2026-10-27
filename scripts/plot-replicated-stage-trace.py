#!/usr/bin/env python3
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('summary',type=Path);p.add_argument('output',type=Path);a=p.parse_args();s=json.loads(a.summary.read_text());r=s['results'];a.output.mkdir(parents=True,exist_ok=True)
fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained');plt.rcParams.update({'font.size':10})
names=['trace-a1','trace-b1','trace-a2','trace-b2'];vals=[r[n]['fullLatency']['p99Us']/1000 for n in names]
bars=axes[0].bar(range(4),vals,color=['#7e8b99','#2d7f9d']*2)
for b,v in zip(bars,vals):axes[0].text(b.get_x()+b.get_width()/2,v+.3,f'{v:.2f}',ha='center')
axes[0].set_xticks(range(4),['A1 OFF','B1 ON','A2 OFF','B2 ON']);axes[0].set_ylabel('All-original p99 (ms)');axes[0].set_ylim(0,max(vals)*1.2);axes[0].set_title('Observer controls | 30 s at 100/s')
groups=[('Source + ingress',['source_schedule','source_queue','ingress_delivery','ingress_processing'],'#9aabb7'),('Durability / replication gate',['replication_durability_gate'],'#2d7f9d'),('Commit + dispatch',['commit_after_gate','service_dispatch'],'#e0b461'),('Business to reply',['business_to_reply_offer'],'#b86455'),('Reply + client',['reply_delivery','client_finalize'],'#93b58c')]
bottom=[0.,0.]
for label,keys,color in groups:
 vals=[100*sum(r[n]['stages']['slowestOnePercent']['phaseShare'][k]for k in keys)for n in ['trace-b1','trace-b2']]
 axes[1].bar([0,1],vals,bottom=bottom,label=label,color=color)
 if label=='Durability / replication gate':
  for i,v in enumerate(vals):axes[1].text(i,bottom[i]+v/2,f'{v:.1f}%',ha='center',color='white',weight='bold')
 bottom=[x+y for x,y in zip(bottom,vals)]
axes[1].set_xticks([0,1],['B1: slowest 30','B2: slowest 30']);axes[1].set_ylabel('Share of summed complete latency (%)');axes[1].set_ylim(0,100);axes[1].set_title('Exact per-request additive phases');axes[1].legend(loc='center left',bbox_to_anchor=(1,0.5),fontsize=8)
fig.suptitle('VectorMatch | same-host replicated path | G1, sync2, fixed leader',fontsize=14)
fig.supxlabel('All 12,000 comparison originals accepted. Exact log positions and one kernel clock; observer effects are not proven negligible.',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('replicated-stage-trace.'+ext),dpi=160)
