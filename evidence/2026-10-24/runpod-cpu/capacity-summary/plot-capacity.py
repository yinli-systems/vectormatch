"""Plot all completed CPU capacity observations without averaging invalid trials."""
from pathlib import Path
import json,hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BASE=Path(__file__).resolve().parent;ROOT=BASE.parent;rows=[];inputs={}
for p in sorted((ROOT/'capacity').glob('cpu-capacity-*/analysis/summary.json')):
 t=json.loads(p.read_text())['trials'][0];d=t['derived'];inputs[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest();rows.append({'id':t['id'],'rate':t['targetArrivalRatePerSecond'],'repetition':t['repetition'],'valid':t['measurementValid'],'stable':t['observedStableWindow'],'goodput':d['arrivalWindowGoodputPerSecond'],'accepted':d['confirmedAccepted'],'notSent':d['clientNotSent'],'unknown':d['unknownUnresolved'],'allP99':d['allOfferedAcceptedP99Millis'],'conditionalP99':d['latency']['conditionalAccepted']['p99Millis'],'drainMs':d['drainSeconds']*1000})
assert len(rows)==5
fig,axes=plt.subplots(1,3,figsize=(14,4.7),layout='constrained');colors={'stable':'#227a9c','overload':'#d4881c','invalid':'#c74646'}
for r in rows:
 typ='invalid' if not r['valid'] else 'stable' if r['stable'] else 'overload';c=colors[typ];marker='x' if typ=='invalid' else 'o' if typ=='stable' else '^';x=r['rate']/1000
 for ax,y in ((axes[0],r['goodput']/1000),(axes[2],r['notSent']/350000*100)):
  ax.scatter(x,y,color=c,marker=marker,s=65,zorder=3);ax.annotate('r'+str(r['repetition'])+(' INVALID' if typ=='invalid' else ''),(x,y),xytext=(8,16 if typ=='invalid' else -20 if r['rate']==18000 else 7 if r['repetition']==1 else -14),textcoords='offset points',fontsize=8,arrowprops={'arrowstyle':'-','color':c,'lw':.5} if r['rate']==18000 else None)
 y=r['allP99'] if r['allP99'] is not None else r['conditionalP99'];axes[1].scatter(x,y,color=c,marker=marker,s=65,facecolors='none' if typ=='overload' else c,zorder=3);axes[1].annotate('r'+str(r['repetition'])+(' accepted only' if r['allP99'] is None else ''),(x,y),xytext=(5,6),textcoords='offset points',fontsize=7)
axes[0].plot([10,27],[10,27],color='#9aa6ad',linestyle='--',linewidth=1,label='offered = confirmed');axes[0].set_ylabel('Confirmed within arrival window (k commands/s)');axes[0].set_title('Bounded client + replicated matching')
axes[1].set_ylabel('Scheduled to confirmed p99 (ms)');axes[1].set_title('Hollow triangles: accepted-only tail')
axes[2].set_ylabel('Client not sent (% of 350k arrivals)');axes[2].set_title('Admission loss is not server rejection')
for ax in axes:
 ax.set_xlabel('Offered rate (k commands/s)');ax.set_xlim(11.5,28.5);ax.grid(alpha=.17);ax.spines[['top','right']].set_visible(False)
from matplotlib.lines import Line2D
fig.legend(handles=[Line2D([0],[0],marker=m,color='none',markeredgecolor=colors[k],markerfacecolor=colors[k],label=l,markersize=7) for k,m,l in (('stable','o','valid finite stable window'),('overload','^','valid overload'),('invalid','x','INVALID generator timing'))],loc='outside lower center',ncol=3,frameon=False)
fig.suptitle('CPU cohort: one host, three JVMs, loopback UDP, sync2, W128, leader0\nFive completed trials; r2 at18k INVALID (>20ms scheduler lateness); r2 at26k NOT RUN',fontsize=11)
for ext in ('png','svg'):fig.savefig(BASE/('capacity-curve.'+ext),dpi=170)
(BASE/'plot-inputs.json').write_text(json.dumps({'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'inputs':inputs,'trials':rows,'scope':'Every completed trial retained. Invalid point is not capacity proof; hollow tails omit not-sent arrivals. Finite windows, not a sustained ceiling.'},indent=2)+'\n')
print('FIVE_TRIALS_PLOTTED_WITH_INVALID_RETAINED')
