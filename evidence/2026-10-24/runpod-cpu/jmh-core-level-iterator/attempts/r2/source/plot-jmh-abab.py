"""Static all-case comparison; points are fork means, never per-order quantiles."""
import argparse,json,pathlib,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--attempt',type=pathlib.Path,required=True);args=p.parse_args()
source=args.attempt/'comparison.json';report=json.loads(source.read_text());assert report['passed']
rows=sorted(report['cases'],key=lambda r:(r['benchmark'],int(r['params']['initialPriceLevels']),int(r['params'].get('tradesPerCommand','0')),r['params'].get('action','')))
assert len(rows)==15
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
fig,(a,b)=plt.subplots(2,1,figsize=(15,8.5),sharex=True,gridspec_kw={'height_ratios':[1.25,1]})
colors={'A':'#3366aa','B':'#db683c'};x=np.arange(len(rows));labels=[]
for i,r in enumerate(rows):
 q=r['params'];action='MATCH' if 'FreshMatchingBenchmark' in r['benchmark'] else q['action'];labels.append(action+'\nlevels '+q['initialPriceLevels']+('\ntrades '+q['tradesPerCommand'] if action=='MATCH' else ''))
 if r['declaredTarget']:
  for axis in (a,b):axis.axvspan(i-.46,i+.46,color='#edf4e8',zorder=0)
 for g,offset in [('A',-.16),('B',.16)]:
  vals=sum((r['stages'][g+str(j)]['forkMeans'] for j in (1,2)),[]);assert len(vals)==6
  a.scatter(i+offset+np.linspace(-.055,.055,6),vals,s=15,color=colors[g],alpha=.55,zorder=2)
  a.plot(i+offset,r[g+'mean'],marker='_',markersize=16,markeredgewidth=2.5,color=colors[g],zorder=3)
 b.scatter(i-.12,r['pair1BoverA'],marker='o',color='#586d80',s=30,label='B1/A1' if i==0 else None)
 b.scatter(i+.12,r['pair2BoverA'],marker='s',color='#9b6b9e',s=30,label='B2/A2' if i==0 else None)
 b.scatter(i,r['BoverA'],marker='D',color='#202a34',s=23,label='All 6 forks/group' if i==0 else None)
a.set_yscale('log');a.set_ylabel('Microseconds / normalized command\n64-command SingleShot batch (log scale)')
a.plot([],[],marker='o',linestyle='',color=colors['A'],label='A: original; all 6 fork means')
a.plot([],[],marker='o',linestyle='',color=colors['B'],label='B: FIFO iterator; all 6 fork means')
a.legend(loc='upper left',ncol=2);a.grid(axis='y',alpha=.15)
b.axhline(1,color='#222',linewidth=1,linestyle='--');b.set_ylabel('Measured time B / A\nBelow 1 = lower time');b.legend(loc='upper left',ncol=3);b.grid(axis='y',alpha=.15)
b.set_xticks(x,labels);b.set_xlim(-.65,len(rows)-.35)
fig.suptitle('VectorMatch CPU core: complete A/B/A/B, all 15 cases and 180 forks',fontsize=15,y=.98)
fig.text(.055,.025,'Green shading: four targets declared before execution. Marks retain every fork; horizontal ticks show group means.\n500 warmup / 10 measurement batches per fork; one thread, 2 GiB heap. Same host and observer. No outliers removed. Not per-order p99 or replicated capacity.',fontsize=9)
fig.subplots_adjust(left=.08,right=.985,top=.93,bottom=.17,hspace=.08)
outputs={}
for ext in ('png','svg'):
 target=args.attempt/('all-case-comparison.'+ext);assert not target.exists();fig.savefig(target,dpi=155);outputs[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
with (args.attempt/'plot-inputs.json').open('x') as f:json.dump({'comparisonSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'sourceSha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'outputs':outputs},f,indent=2);f.write('\n')
print(json.dumps({'cases':15,'forks':180,'files':list(outputs)}))
