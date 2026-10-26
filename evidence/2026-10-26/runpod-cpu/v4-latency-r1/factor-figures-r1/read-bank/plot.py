from pathlib import Path
import sys,json,subprocess,hashlib,datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';factor=sys.argv[1];assert factor in ('agent-idle','read-bank');O=B/f'v4-latency-{factor}-figure-r2';assert not O.exists()
proof=json.loads((B/f'v4-latency-{factor}-comparison-private-proof-r1/PRIVATE_PUSH.json').read_text());assert proof['passed']and proof['allFourRawPrivatelyVerified']
path=f'evidence/2026-10-26/runpod-cpu/v4-latency-r1/{factor}-comparison-r1/RESULT.json';body=subprocess.check_output(['git','-C',str(W),'show',proof['commit']+':'+path]);result=json.loads(body);assert result['passed']and result['factor']==factor
arms=['c1','d1','c2','d2'];points=[result['points'][a]for a in arms];colors=['#3b5b8a','#087e8b','#3b5b8a','#087e8b'];labels=[a.upper()for a in arms]
plt.rcParams.update({'font.size':10,'figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
fig,axes=plt.subplots(1,2,figsize=(10.8,4.6),gridspec_kw={'width_ratios':[1,1]})
for ax,key,title in [(axes[0],'globalP99Ns','All-arrival accepted p99'),(axes[1],'postOfferP99Ns','Post-offer p99')]:
 for i,p in enumerate(points):
  if p[key]is None:ax.text(i,.02,'undefined',transform=ax.get_xaxis_transform(),ha='center',fontsize=9,rotation=90);continue
  value=p[key]/1e6;ax.bar(i,value,color=colors[i],width=.62);ax.text(i,value,f'{value:.2f}',ha='center',va='bottom',fontsize=10)
 ax.set_xticks(range(4),labels);ax.set_title(title,loc='left',fontsize=12);ax.set_ylabel('Milliseconds');ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True);ax.set_ylim(0,max(p[key]/1e6 for p in points if p[key]is not None)*1.22)
axes[0].axhline(10,color='#ac3939',linestyle=':',linewidth=1);axes[0].text(3.5,10,'10 ms global target',ha='right',va='bottom',color='#ac3939',fontsize=8)
if factor=='agent-idle':title='V4 agent idle comparison';subtitle='C: explicit 1 ms | D: explicit 100 us | read-bank CLOSED in all arms'
else:title='V4 dispatch between read batches';subtitle='C: CLOSED | D: BOUNDED_TURN | explicit agent 100 us in all arms'
fig.suptitle(title,x=.08,ha='left',y=.98,fontweight='bold',fontsize=16);fig.text(.08,.88,subtitle,fontsize=10,color='#444444')
fig.text(.08,.12,'Actual artifact dcfeeb81 | 4,000 arrivals/s | leader 0 | sync 2 | owner poll 1 ms | one physical CPU host',fontsize=9,color='#444444')
fig.text(.08,.075,'Each bar is one fresh 20-second lineage; no pooled percentiles or confidence interval. All original outcomes are retained.',fontsize=8.5,color='#444444')
fig.text(.08,.035,'In-window goodput: '+', '.join(a.upper()+' '+str(p['goodput'])+'/s'for a,p in zip(arms,points))+'. No sustained SLA or default promotion.',fontsize=8.5,color='#444444')
fig.subplots_adjust(left=.08,right=.98,top=.78,bottom=.24,wspace=.28);O.mkdir()
for ext in ['png','svg']:fig.savefig(O/(factor+'.'+ext),dpi=180)
plt.close(fig);pins={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in O.iterdir()}
(O/'PROVENANCE.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),matplotlibVersion=matplotlib.__version__,privateReportCommit=proof['commit'],actualGitResultPath=path,actualGitResultSha256=hashlib.sha256(body).hexdigest(),files=pins,noNewBenchmark=True),indent=2,sort_keys=True)+'\n');print(dict(passed=True,png=str(O/(factor+'.png'))))
