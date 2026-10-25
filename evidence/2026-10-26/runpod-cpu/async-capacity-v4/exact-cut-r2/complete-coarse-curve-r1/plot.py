from pathlib import Path
import sys,json,hashlib,subprocess,datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter
import numpy as np
B=Path(__file__).resolve().parent.parent;W=B/'async-maintenance-v4-worktree';through=int(sys.argv[1]);assert through in(2000,4000,6000)
rates=[r for r in[500,1000,2000,4000,6000]if r<=through];O=B/('async-v4-cut-gate-curve-through-'+str(through)+'-figure-r3');assert not O.exists()
records={};provenance={};common=None;outcomes=dict(notSent=0,unknownObserved=0,unknownFinal=0,rejected=0)
for rate in rates:
 proof=json.loads((B/('async-v4-cut-gate-'+str(rate)+'-report-private-proof-r1/PRIVATE_PUSH.json')).read_text());assert proof['passed']and proof['private']and proof['allFourNativeAssetsPreviouslyFullyDownloadedAndMemberVerified']
 path='evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2/rate-'+str(rate)+'-comparison-r1/RESULT.json';body=subprocess.check_output(['git','-C',str(W),'show',proof['commit']+':'+path]);result=json.loads(body);assert result['passed']
 config=dict(result['commonConfiguration']);assert config.pop('ratePerSecond')==rate
 if common is None:common=config
 assert config==common and config['code']=='65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69'
 records[rate]=result;provenance[rate]=dict(privateReportCommit=proof['commit'],resultGitPath=path,resultSha256=hashlib.sha256(body).hexdigest(),allFourFiniteGatesPassed=result['allFourFiniteGatesPassed'])
 for p in result['points'].values():
  for name in outcomes:outcomes[name]+=p[name]
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none','figure.facecolor':'white'})
fig,axes=plt.subplots(3,1,figsize=(11.7,9.6),sharex=True,gridspec_kw={'height_ratios':[1,1.1,1]});styles={'c1':('#3b5b8a','o','-','PAUSE C1'),'c2':('#3b5b8a','s','--','PAUSE C2'),'d1':('#087e8b','o','-','CONTINUE D1'),'d2':('#087e8b','s','--','CONTINUE D2')}
for arm,(color,marker,line,label)in styles.items():
 p=[records[r]['points'][arm]for r in rates]
 axes[0].plot(rates,[x['goodput']for x in p],color=color,marker=marker,linestyle=line,label=label,markersize=5,linewidth=1.5,alpha=.85)
 axes[1].plot(rates,[np.nan if x['p99Ns']is None else x['p99Ns']/1e6 for x in p],color=color,marker=marker,linestyle=line,markersize=5,linewidth=1.5,alpha=.85)
 axes[2].plot(rates,[x['afterOfferP99Ns']/1e6 for x in p],color=color,marker=marker,linestyle=line,markersize=5,linewidth=1.5,alpha=.85)
axes[0].plot(rates,rates,color='#777777',linestyle=':',linewidth=1,label='Offered rate')
axes[1].axhline(10,color='#ac3939',linestyle=':',linewidth=1);axes[1].text(rates[-1],10,' 10 ms engineering target',color='#ac3939',va='bottom',ha='right',fontsize=9)
axes[0].set_ylabel('Confirmed inside window / s');axes[1].set_ylabel('All-arrival accepted p99 (ms)');axes[2].set_ylabel('Post-offer p99 (ms)');axes[2].set_xlabel('Scheduled arrival rate / s')
missing=[arm.upper()+' @ '+format(rate,',')+'/s'for rate in rates for arm,p in records[rate]['points'].items()if p['p99Ns']is None]
if missing:axes[1].text(.02,.94,'Undefined global p99: '+', '.join(missing),transform=axes[1].transAxes,va='top',fontsize=9,color='#3b5b8a',bbox=dict(facecolor='white',edgecolor='none',alpha=.85))
axes[0].legend(ncol=5,loc='upper left',frameon=False,fontsize=9);axes[0].set_ylim(bottom=0);axes[1].set_ylim(bottom=0);axes[2].set_ylim(bottom=0)
for ax in axes:ax.grid(axis='both',alpha=.18);ax.xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'));ax.yaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
axes[2].set_xticks(rates);axes[2].set_xlim(max(0,rates[0]-200),rates[-1]+max(200,.05*rates[-1]))
fig.suptitle('VectorMatch | exact-cut V4 finite capacity',fontsize=17,fontweight='bold',x=.09,ha='left',y=.985)
fig.text(.09,.945,'Same artifact 65c41d519ea7 | leader 0 | sync 2 | 127 active load producers | three JVMs on one CPU host',fontsize=10,color='#444444')
fig.text(.09,.045,'Each dot is one 20-second fresh lineage. Lines connect the same repetition; no percentile pooling or confidence interval.',fontsize=9,color='#444444')
fig.text(.09,.028,'Post-offer includes replicated execution, polling and reply delivery. These observations do not establish long-run capacity or an SLA.',fontsize=9,color='#444444')
fig.text(.09,.011,'Across plotted points: not sent '+str(outcomes['notSent'])+'; observed / final unknown '+str(outcomes['unknownObserved'])+' / '+str(outcomes['unknownFinal'])+'; rejects '+str(outcomes['rejected'])+'. Undefined global p99 values are omitted.',fontsize=9,color='#444444')
fig.subplots_adjust(left=.09,right=.97,top=.91,bottom=.10,hspace=.24);O.mkdir()
for ext in ['png','svg']:fig.savefig(O/('exact-cut-v4-through-'+str(through)+'.'+ext),dpi=180)
plt.close(fig)
(O/'PROVENANCE.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),matplotlib=matplotlib.__version__,numpy=np.__version__,rates=rates,commonConfiguration=common,privatePublishedInputs=provenance,aggregateOutcomeCounts=outcomes,allPlottedRunPercentilesRemainSeparate=True,noNewBenchmarkOrCpuAction=True,files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in sorted(O.iterdir())if p.is_file()}),indent=2,sort_keys=True)+chr(10));print(json.dumps(dict(passed=True,rates=rates,png=str(O/('exact-cut-v4-through-'+str(through)+'.png')))))
