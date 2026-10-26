from pathlib import Path
import json,sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
B=Path(__file__).resolve().parent.parent;A=B/'interbank-v4-worktree/evidence/2026-10-26/runpod-cpu/v4-jfr-diagnostic-r1/results-r1'
rows=[json.loads((B/f'v4-jfr-{f}-{r}-{a}-summary-r1/RESULT.json').read_text())for f,r,a in [('qualification',500,'q1'),('diagnostic',4000,'x1')]]
fig,axs=plt.subplots(1,2,figsize=(12,4.8),layout='constrained');colors=['#3267a8','#de9b37','#548e70']
for ax,r in zip(axs,rows):
 ps=sorted([p for p in r['profiles']if p['role'].startswith('original-')],key=lambda p:p['role']);x=np.arange(3)
 for delta,key,label,color in [(-.24,'archiveSegmentForceTotalNs','Segment force(true)',colors[0]),(0,'archiveSegmentWriteTotalNs','Segment write',colors[1]),(.24,None,'GC pause',colors[2])]:
  vals=[(p[key]if key else p['gcPauseEvents']['totalNs'])/1e9 for p in ps]
  bars=ax.bar(x+delta,vals,.23,label=label,color=color)
  ax.bar_label(bars,labels=[f'{v:.3f}'for v in vals],fontsize=8,padding=3)
 ax.set_xticks(x,['Node 0','Node 1','Node 2']);ax.set_ylim(0,22);ax.set_ylabel('Elapsed seconds per node (20-second window)');ax.set_title(f'{r["ratePerSecond"]:,}/s instrumented diagnostic\nRequest p99 {r["allArrivalAcceptedP99Ns"]/1e6:.2f} ms');ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
fig.suptitle('Archive force dominates measured file API elapsed time',fontsize=15)
fig.supxlabel('Blue: segment force(true); orange: segment write; green: GC pause. Overlapping across nodes.\nNot physical-device latency, a capacity improvement, or a sustained SLA.',fontsize=9)
for suffix in ['png','svg']:fig.savefig(A/('force-path.'+suffix),dpi=160)
