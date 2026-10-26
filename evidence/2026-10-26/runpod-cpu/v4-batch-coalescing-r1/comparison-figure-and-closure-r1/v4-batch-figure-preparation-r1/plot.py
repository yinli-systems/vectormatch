from pathlib import Path
import json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
B=Path(__file__).resolve().parent.parent;P=B/'v4-batch-coalescing-comparison-r1/RESULT.json';r=json.loads(P.read_text());assert r['passed']and r['allFourRawPrivatelyVerified'];O=B/'v4-batch-coalescing-figure-r1';assert not O.exists();O.mkdir()
arms=['c1','d1','c2','d2'];colors=['#526d91','#00887c','#526d91','#00887c'];labels=['C1\n50us','D1\n500us','C2\n50us','D2\n500us'];x=np.arange(4)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
fig,axes=plt.subplots(1,3,figsize=(15,5.8));fig.subplots_adjust(left=.055,right=.985,top=.78,bottom=.28,wspace=.28)
series=[('Global all-arrival accepted p99','Milliseconds',[None if r['points'][a]['globalP99Ns']is None else r['points'][a]['globalP99Ns']/1e6 for a in arms]),('After positive offer return to reply p99','Milliseconds',[r['points'][a]['postOfferP99Ns']/1e6 for a in arms]),('Actual original business batch size','Mean commands per original batch',[(sum(int(k)*v for k,v in r['points'][a]['businessBatchSizeCounts'].items())/r['points'][a]['recordedDistinctBusinessBatchRequests'])for a in arms])]
for ax,(title,ylabel,values)in zip(axes,series):
 valid=[n for n,v in enumerate(values)if v is not None];ax.bar(valid,[values[n]for n in valid],color=[colors[n]for n in valid],width=.63)
 ax.set_xticks(x,labels);ax.set_title(title,pad=13,fontsize=11);ax.set_ylabel(ylabel);ax.set_axisbelow(True);ax.grid(axis='y',alpha=.16);ax.set_ylim(0,max([v for v in values if v is not None]+[1])*1.25)
 for n,v in enumerate(values):
  if v is None:ax.text(n,ax.get_ylim()[1]*.05,'undefined',ha='center',rotation=90,color='#8c2f39')
  else:ax.text(n,v+ax.get_ylim()[1]*.025,f'{v:.2f}',ha='center',fontsize=10)
axes[0].axhline(10,color='#a44a42',linestyle='--',linewidth=1);axes[0].text(-.45,10.5,'10ms global target',color='#a44a42',fontsize=8)
axes[2].set_ylim(0,4.5);axes[2].axhline(4,color='#999999',linestyle=':',linewidth=.8)
fig.suptitle('VectorMatch: bounded batch coalescing, 50us vs 500us',x=.055,y=.96,ha='left',fontsize=18,fontweight='bold')
fig.text(.055,.865,'One compiled artifact fb1068dd | fixed leader 0 / sync2 | 4,000 scheduled arrivals/s | four separate 20s lineages',fontsize=10,color='#444444')
good='; '.join(a.upper()+': '+str(r['points'][a]['goodput'])+'/s'for a in arms)
fig.text(.055,.16,'In-window accepted goodput: '+good,fontsize=10)
fig.text(.055,.105,'Both registered pair criteria passed: '+str(r['registeredBothPairsPassed'])+'. All raw assets privately verified; no pooled percentile or confidence interval.',fontsize=9)
fig.text(.055,.06,'Three UDP JVMs share one CPU host. Batch counts include 3 setup commands and are not force-call counts. No sustained SLA or default promotion.',fontsize=9,color='#555555')
for ext in ['png','svg']:fig.savefig(O/('batch-coalescing.'+ext),dpi=170,facecolor='white')
plt.close(fig)
(O/'PROVENANCE.json').write_text(json.dumps(dict(passed=True,resultPath=str(P),resultSha256=hashlib.sha256(P.read_bytes()).hexdigest(),sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),armsKeptSeparate=True,noPooledPercentilesOrInventedIntervals=True,noForceOperationCountInferred=True),indent=2)+'\n')
print('created standalone PNG and SVG from privately closed comparison')
