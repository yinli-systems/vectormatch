#!/usr/bin/env python3
"""Plot every closed comparison and every minute; never omit a failed gate."""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser();p.add_argument('summary',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
s=json.loads(a.summary.read_text());r=s['results'];a.output.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,3,figsize=(15,4.8),layout='constrained')
for ax,names,title in [(axes[0],['path-a1','path-b1','path-a2','path-b2'],'No business vs matching | 30 s, 100/s'),(axes[1],['idle-a1','idle-b1','idle-a2','idle-b2'],'Replica park 1 ms vs 100 us | 60 s, 100/s')]:
 values=[r[n]['fullLatency']['p99Us']/1000 if r[n]['fullLatency'] else 0 for n in names]
 bars=ax.bar(range(4),values,color=['#7e8b99','#2d7f9d']*2)
 for b,v,n in zip(bars,values,names):ax.text(b.get_x()+b.get_width()/2,v+.02*max(values),f'{v:.2f}'if r[n]['fullLatency']else'undefined',ha='center',fontsize=9)
 ax.set_xticks(range(4),['A1','B1','A2','B2']);ax.set_ylabel('All-original scheduled-to-reply p99 (ms)');ax.set_title(title,fontsize=11);ax.set_ylim(0,max(values)*1.22);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
long=r['sustained-r1'];minutes=long['minuteWindows'];ax=axes[2]
vals=[x['latency']['p99Us']/1000 if x['latency']else float('nan')for x in minutes]
ax.plot(range(1,len(vals)+1),vals,'o-',color='#2d7f9d',markersize=3);ax.axhline(25,color='#b4443e',ls='--',label='Registered 25 ms gate')
ax.set_xlabel('Minute');ax.set_ylabel('All-original p99 (ms)');ax.set_title('One uninterrupted 30-minute matching window',fontsize=11);ax.legend(fontsize=8);ax.grid(alpha=.2)
fig.suptitle('VectorMatch | three same-host UDP JVMs + independent load JVM | G1, sync2',fontsize=14)
fig.supxlabel('Bounded IOC fixture. NOOP has no trading semantics. Memory-only source tape during arrivals. Not independent physical nodes.',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('replicated-path-probe.'+ext),dpi=160)
