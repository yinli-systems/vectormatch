"""Plot every registered idle comparison trial, including loss and conditional tails."""
from pathlib import Path
import json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
REPO=Path(__file__).resolve().parents[3];root=REPO/'evidence/2026-10-24/runpod-cpu/node-idle-abab/comparison'
p=root/'comparison.json';r=json.loads(p.read_text());assert r['passed'];rows=r['rows'];assert [x['stage'] for x in rows]==['A1','B1','A2','B2']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,3,figsize=(13,4.6));x=np.arange(4);colors=['#6685a2','#db7638','#6685a2','#db7638']
for a in axes:a.set_xticks(x,[q['stage'] for q in rows]);a.grid(axis='y',alpha=.15);a.set_axisbelow(True)
g=[q['windowGoodputPerSecond'] for q in rows];axes[0].bar(x,g,color=colors);axes[0].axhline(18000,color='#333',linestyle='--',linewidth=1);axes[0].set_ylabel('Accepted inside arrival window / second');axes[0].set_ylim(0,20300)
for i,v in enumerate(g):axes[0].text(i,v+180,f'{v:,.0f}',ha='center',fontsize=9)
v=[q['conditionalAcceptedP99Millis'] for q in rows];axes[1].bar(x,v,color=colors);axes[1].set_ylabel('Accepted-only p99 (ms)');axes[1].set_ylim(0,max(v)*1.23)
for i,q in enumerate(rows):
 axes[1].text(i,v[i]+9,f'{v[i]:.1f}',ha='center');axes[1].text(i,v[i]+32,'all-arrival N/A' if q['allOfferedAcceptedP99Millis'] is None else 'all arrivals accepted',ha='center',fontsize=7)
miss=[q['notSent'] for q in rows];axes[2].bar(x,miss,color=colors);axes[2].set_ylabel('Not sent / 350,000 arrivals');axes[2].set_ylim(0,max(miss)*1.24)
for i,v in enumerate(miss):axes[2].text(i,v+150,f'{v:,}',ha='center')
fig.suptitle('VectorMatch: same18k arrival rate, node max park1ms (A) vs100us (B)',fontsize=13,y=.99)
fig.text(.055,.025,'All four350k-arrival trials retained;source433,leader0,sync2,W128/Q64,mux1,one CPU host/three JVMs/loopback UDP.\nInitial/final UNKNOWN0. A1 loses arrivals,so its all-arrival accepted p99 is unavailable. Finite windows;not a sustained ceiling or realtime SLA.',fontsize=9)
fig.subplots_adjust(left=.07,right=.985,top=.87,bottom=.22,wspace=.31)
files={}
for ext in ('png','svg'):
 target=root/('node-idle-abab.'+ext);assert not target.exists();fig.savefig(target,dpi=160);files[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
with (root/'plot-inputs.json').open('x') as f:json.dump({'inputSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'files':files},f,indent=2);f.write('\n')
(root/'plot-idle-abab.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'stages':4,'figures':list(files)}))
