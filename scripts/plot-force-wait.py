#!/usr/bin/env python3
"""Plot observer controls and sampled kernel wait locations without inventing durations."""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('summary',type=Path);p.add_argument('output',type=Path);a=p.parse_args();r=json.loads(a.summary.read_text())['results'];a.output.mkdir(parents=True,exist_ok=True)
fig,axes=plt.subplots(1,2,figsize=(13.7,5.5),layout='constrained')
names=['observer-a1','observer-b1','observer-a2','observer-b2'];labels=['A1 OFF','B1 ON','A2 OFF','B2 ON']
for offset,key,label,color in [(-.19,'p99Us','p99','#24778f'),(.19,'p999Us','p99.9','#8eacb6')]:
 vals=[r[n]['fullLatency'][key]/1000 for n in names];bars=axes[0].bar([i+offset for i in range(4)],vals,width=.36,label=label,color=color)
 for b,v in zip(bars,vals):axes[0].annotate(f'{v:.1f}',(b.get_x()+b.get_width()/2,v),xytext=(0,4),textcoords='offset points',ha='center',fontsize=9)
axes[0].set_xticks(range(4),labels);axes[0].set_ylabel('All-original latency (ms)');axes[0].set_ylim(0,140);axes[0].set_title('Observer controls: opposite paired directions');axes[0].legend()
locations=['xlog_wait_on_iclog','xlog_wait','folio_wait_bit_common','__flush_workqueue','submit_bio_wait','md_flush_request']
for offset,name,label,color in [(-.19,'observer-b1','B1','#24778f'),(.19,'observer-b2','B2','#bc864b')]:
 counts=r[name]['forceWait']['uniqueCriticalBlockedWaitLocations'];axes[1].barh([i+offset for i in range(len(locations))],[counts.get(k,0)for k in locations],height=.36,label=label,color=color)
axes[1].set_yticks(range(len(locations)),locations);axes[1].invert_yaxis();axes[1].set_xlabel('D-state samples in unique original-critical forces (counts)');axes[1].set_title('Observed blocking paths: counts are not durations');axes[1].legend()
fig.suptitle('VectorMatch | force diagnostics | same host, sync2, 100/s, 60 seconds per arm',fontsize=13)
fig.supxlabel('Slowest 1% request-associated force: off-CPU lower bound 99.528% / 99.661%. Exact runqueue/storage durations unavailable.',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('force-wait.'+ext),dpi=160)
