#!/usr/bin/env python3
"""Plot original ABAB latency and the exact slow-request decomposition."""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('summary',type=Path);p.add_argument('output',type=Path);a=p.parse_args();s=json.loads(a.summary.read_text());r=s['results'];a.output.mkdir(parents=True,exist_ok=True)
names=['allocation-a1','allocation-b1','allocation-a2','allocation-b2'];labels=['A1 sparse','B1 reserve','A2 sparse','B2 reserve']
fig,axes=plt.subplots(1,2,figsize=(13.5,5.1),layout='constrained')
for offset,key,label,color in [(-.19,'p99Us','p99','#287e98'),(.19,'p999Us','p99.9','#94acb5')]:
 vals=[r[n]['fullLatency'][key]/1000 for n in names];bars=axes[0].bar([i+offset for i in range(4)],vals,width=.36,label=label,color=color)
 for b,v in zip(bars,vals):axes[0].annotate(f'{v:.1f}',(b.get_x()+b.get_width()/2,v),xytext=(0,3),textcoords='offset points',ha='center',fontsize=8)
axes[0].set_xticks(range(4),labels);axes[0].set_ylabel('All-original latency (ms)');axes[0].set_ylim(0,max(r[n]['fullLatency']['p999Us']/1000 for n in names)*1.2);axes[0].set_title('60 seconds per arm | 100 arrivals/s');axes[0].legend()
groups=[('Source + ingress',['source_schedule','source_queue','ingress_delivery','ingress_processing'],'#9aabb7'),('Durability / replication',['replication_durability_gate'],'#287e98'),('Commit + dispatch',['commit_after_gate','service_dispatch'],'#e0b461'),('Business to reply',['business_to_reply_offer'],'#b86455'),('Reply + client',['reply_delivery','client_finalize'],'#93b58c')];bottom=[0.]*4
for label,keys,color in groups:
 vals=[100*sum(r[n]['stages']['slowestOnePercent']['phaseShare'][k]for k in keys)for n in names];axes[1].bar(range(4),vals,bottom=bottom,label=label,color=color)
 if label=='Durability / replication':
  for i,v in enumerate(vals):axes[1].text(i,bottom[i]+v/2,f'{v:.0f}%',ha='center',color='white',weight='bold')
 bottom=[x+y for x,y in zip(bottom,vals)]
axes[1].set_xticks(range(4),labels);axes[1].set_ylabel('Share of slowest 1% total latency (%)');axes[1].set_ylim(0,100);axes[1].set_title('60 original slow requests per arm');axes[1].legend(loc='center left',bbox_to_anchor=(1,.5),fontsize=8)
fig.suptitle('VectorMatch | recording preallocation ABAB | same host, artifact and sync2',fontsize=14)
fig.supxlabel('Separate source JVM. Exact position joins; no trace loss. Finite synthetic IOC workload, not a production SLA.',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('recording-preallocation.'+ext),dpi=160)
