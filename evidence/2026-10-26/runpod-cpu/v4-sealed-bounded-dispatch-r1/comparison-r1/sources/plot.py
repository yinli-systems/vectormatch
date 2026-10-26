from pathlib import Path
import json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
B=Path(__file__).resolve().parent.parent;P=B/'v4-sealed-bounded-dispatch-comparison-r1/RESULT.json';r=json.loads(P.read_text());assert r['passed']and r['allFourRawPrivatelyVerified'];O=B/'v4-sealed-bounded-figure-r1';assert not O.exists();O.mkdir()
arms=['c1','d1','c2','d2'];colors=['#526d91','#00887c','#526d91','#00887c'];labels=['C1\nClosed','D1\nBounded turn','C2\nClosed','D2\nBounded turn'];x=np.arange(4)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
fig,axes=plt.subplots(1,2,figsize=(12,5.8));fig.subplots_adjust(left=.07,right=.98,top=.77,bottom=.28,wspace=.25)
for ax,key,title in [(axes[0],'globalP99Ns','All-arrival scheduled-to-reply p99'),(axes[1],'postOfferP99Ns','Positive-offer-return-to-reply p99')]:
 values=[None if r['points'][a][key]is None else r['points'][a][key]/1e6 for a in arms];valid=[n for n,v in enumerate(values)if v is not None]
 ax.bar(valid,[values[n]for n in valid],color=[colors[n]for n in valid],width=.63);ax.set_xticks(x,labels);ax.set_title(title,pad=12,fontsize=11);ax.set_ylabel('Milliseconds');ax.set_axisbelow(True);ax.grid(axis='y',alpha=.16);ax.set_ylim(0,max([v for v in values if v is not None]+[1])*1.25)
 for n,v in enumerate(values):
  if v is None:ax.text(n,2,'undefined',ha='center',rotation=90)
  else:ax.text(n,v+ax.get_ylim()[1]*.025,f'{v:.2f}',ha='center')
axes[0].axhline(5,color='#a44a42',linestyle='--',linewidth=1);axes[0].text(-.45,6,'5ms sustained target',color='#a44a42',fontsize=8)
fig.suptitle('Sealed read-bank dispatch: native paired results',x=.07,y=.96,ha='left',fontsize=17,fontweight='bold')
fig.text(.07,.86,'Artifact a21a720d | leader 0 / sync2 | 4,000 scheduled/s | separate 20s lineages | no JFR',fontsize=10,color='#444444')
fig.text(.07,.16,'Accepted per arm: '+', '.join(str(r['points'][a]['accepted'])for a in arms)+'; complete per-arm losses remain in the report.',fontsize=10)
fig.text(.07,.105,'Both registered pair criteria pass: '+str(r['registeredBothPairsPassed'])+'. No default promotion or pooled percentile.',fontsize=9)
fig.text(.07,.06,'Three UDP JVMs share one CPU host. Runtime handshakes are counted. No sustained SLA or media durability proof.',fontsize=9,color='#555555')
for ext in ['png','svg']:fig.savefig(O/('sealed-bounded-dispatch.'+ext),dpi=170,facecolor='white')
plt.close(fig);(O/'PROVENANCE.json').write_text(json.dumps(dict(passed=True,resultSha256=hashlib.sha256(P.read_bytes()).hexdigest(),sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),armsKeptSeparate=True,noPooledPercentileOrInventedConfidenceInterval=True),indent=2)+'\n')
