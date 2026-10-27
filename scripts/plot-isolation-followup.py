#!/usr/bin/env python3
"""Render completed finite and sustained scopes separately; never hide omitted originals."""
from pathlib import Path
import argparse,json,csv,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser();p.add_argument('sizing_summary',type=Path);p.add_argument('sustained_root',type=Path);p.add_argument('output',type=Path);a=p.parse_args();s=json.loads(a.sizing_summary.read_text());assert not s['replicated']and not s['sustainedCapacityProven']
r=a.sustained_root;manifest=json.loads((r/'ARCHIVE_MEMBER_MANIFEST.json').read_text())['files'];minute=r/'evidence__soak-minute-windows.csv';assert hashlib.sha256(minute.read_bytes()).hexdigest()==manifest['evidence/soak-minute-windows.csv']['sha256'];windows=list(csv.DictReader(minute.open()));audit=json.loads((r/'AUDIT.json').read_text());assert len(windows)==30 and audit['completeMinuteWindows']==30
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.hashsalt':'vectormatch-isolation-followup-20261027'})
a.output.mkdir(parents=True,exist_ok=True)
fig,axes=plt.subplots(1,3,figsize=(15,5));fig.subplots_adjust(left=.06,right=.98,top=.80,bottom=.28,wspace=.30)
labels=[str(x['rate']//1000)+'K\n'+x['arm'].upper()for x in s['rows']];colors=['#d97706'if not x['presized']else'#087f8c'for x in s['rows']]
for i,row in enumerate(s['rows']):
 q=row['allArrivalAcceptedLatencyNs']
 if q:axes[0].bar(i,q['p99']/1e6,color=colors[i])
 else:axes[0].text(i,.04,'undefined',rotation=90,ha='center',va='bottom',transform=axes[0].get_xaxis_transform(),fontsize=8,color='#b91c1c')
axes[0].set_yscale('log');axes[0].set_ylabel('All-original accepted p99 (ms)');axes[0].set_title('Full-stream latency')
axes[1].bar(range(8),[x['notSent']for x in s['rows']],color=colors);axes[1].set_ylabel('Originals not sent');axes[1].set_title('Missing arrivals remain visible')
axes[2].bar(range(8),[x['conditionalWorkerServiceNs']['max']/1e6 for x in s['rows']],color=colors);axes[2].axhline(32.768,color='#6b7280',linestyle='--',linewidth=1,label='8,192 credits / 250K/s');axes[2].set_ylabel('Maximum executed business call (ms)');axes[2].set_title('Worker-local stall');axes[2].legend(fontsize=8)
for ax in axes:ax.set_xticks(range(8),labels,fontsize=8);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.suptitle('Client-index startup sizing: same-host TCP ABAB',fontsize=15,y=.96)
fig.text(.5,.08,'Orange A: lazy index  |  Teal B: pre-sized index  |  Same candidate, source G1, business Generational ZGC, 8 CPUs, 8,192 credits\nFive seconds per arm; mixed GTC / IOC / cancel. No journal, replication, or sustained-capacity claim.',ha='center',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('client-index-sizing.'+ext),dpi=160,metadata={'Date':None}if ext=='svg'else None)
plt.close(fig)
fig,ax=plt.subplots(figsize=(12,5));fig.subplots_adjust(left=.08,right=.98,top=.80,bottom=.25)
for key,label,color in [('all_offered_p50_us','p50','#64748b'),('all_offered_p99_us','p99','#087f8c'),('all_offered_p999_us','p99.9','#d97706')]:
 assert all(w[key]for w in windows);ax.plot([int(w['minute'])+1 for w in windows],[float(w[key])/1000 for w in windows],marker='.',linewidth=1.2,label=label,color=color)
ax.axhline(25,color='#b91c1c',linestyle='--',linewidth=1,label='25 ms minute p99 gate');ax.set_yscale('log');ax.set_xlabel('Completed minute of one uninterrupted arrival window');ax.set_ylabel('Scheduled arrival to confirmation (ms)');ax.set_xlim(.5,30.5);ax.set_xticks([1,5,10,15,20,25,30]);ax.grid(alpha=.2);ax.legend(ncol=4,fontsize=9)
fig.suptitle('Three replicas + independent generator: 30 minutes at 100/s',fontsize=15,y=.96)
fig.text(.5,.08,f"{audit['accepted']:,} / {audit['originals']:,} accepted  |  Fixed leader 0, sync level 2, G1  |  Strict overall gate: {audit['registeredAcceptancePassed']}\nSame host, loopback UDP: no independent physical fault-domain claim. This is a different boundary from the finite TCP experiment.",ha='center',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('replicated-sustained-r3.'+ext),dpi=160,metadata={'Date':None}if ext=='svg'else None)
plt.close(fig)
