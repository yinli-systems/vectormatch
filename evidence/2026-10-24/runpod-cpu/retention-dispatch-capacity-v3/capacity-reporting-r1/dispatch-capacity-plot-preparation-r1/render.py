from pathlib import Path
import sys,os,json,hashlib,csv,datetime
B=Path(__file__).resolve().parent.parent;count=int(sys.argv[1]);assert count in(2,3,4,5)
O=B/f'dispatch-capacity-first-{count}-figures-r1';assert not O.exists();O.mkdir()
os.environ['MPLCONFIGDIR']=str(O/'mplconfig');sys.path.insert(0,str(B/'plot-tools-install-r1/lib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
P=B/f'dispatch-capacity-first-{count}-curve-analysis-r1/CURVE.json';pin=sha(P)
report=json.loads(P.read_text());rows=report['observations'];assert report['passed']and len(rows)==count
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(13,8));rates=[r['rate']for r in rows]
for ax in axes.flat:
    ax.set_xticks(rates,[f'{v/1000:g}k'for v in rates]);ax.grid(alpha=.18);ax.set_axisbelow(True);ax.set_xlabel('Scheduled arrivals / second')
axes[0,0].plot(rates,rates,':',color='#777',label='offered')
axes[0,0].plot(rates,[r['goodput']for r in rows],color='#157f73',marker='o',label='confirmed inside20s')
axes[0,0].set_ylabel('Orders / second');axes[0,0].legend(fontsize=9)
axes[0,1].plot(rates,[r['allArrivalAcceptedP99Ns']/1e6 if r['allArrivalAcceptedP99Ns']is not None else float('nan')for r in rows],color='#157f73',marker='o',label='all-arrival accepted p99')
for r in rows:
    if r['allArrivalAcceptedP99Ns']is None:axes[0,1].scatter(r['rate'],r['conditionalAcceptedP99Ns']/1e6,facecolors='none',edgecolors='#c97924',s=75)
axes[0,1].set_ylabel('Scheduled-to-reply p99 (ms)');axes[0,1].set_ylim(bottom=0);axes[0,1].legend(fontsize=9)
axes[1,0].plot(rates,[100*r['windowConfirmationFraction']for r in rows],color='#526e91',marker='o')
axes[1,0].axhline(99,color='#777',linestyle=':',label='finite progression gate')
axes[1,0].set_ylabel('Confirmed within arrival window (%)');axes[1,0].set_ylim(min(98,min(100*r['windowConfirmationFraction']for r in rows)-.5),100.5);axes[1,0].legend(fontsize=9)
fractions=[100*r['intervalsReachingZeroRecordedWaiting']/r['fullOfferedCutIntervals']for r in rows]
axes[1,1].bar(range(count),fractions,color=['#157f73'if r['finiteProgressionGateMet']else'#c97924'for r in rows],width=.6)
axes[1,1].set_xticks(range(count),[f'{v/1000:g}k'for v in rates]);axes[1,1].set_ylabel('Equivalent intervals reaching zero waiting (%)');axes[1,1].set_ylim(0,120)
axes[1,1].set_xlim(-.6,count-.4)
for i,r in enumerate(rows):
    axes[0,0].annotate(f"{r['goodput']:,.2f}",(r['rate'],r['goodput']),xytext=(0,9),textcoords='offset points',ha='center',fontsize=9)
    axes[0,1].annotate(f"{r['conditionalAcceptedP99Ns']/1e6:.1f}"+(' conditional'if r['allArrivalAcceptedP99Ns']is None else''),(r['rate'],r['conditionalAcceptedP99Ns']/1e6),xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
    axes[1,1].text(i,fractions[i]+3,f"{r['intervalsReachingZeroRecordedWaiting']}/{r['fullOfferedCutIntervals']}",ha='center')
fig.suptitle('VectorMatch: rotating dispatch, fine maintained capacity curve',fontsize=15)
fig.text(.075,.025,'One fresh20s lineage per point;source566dd2fa/code2b8d7594,leader0,sync2,read128/page32,batch4,W128/Q64.\n'
         'One CPU host / three JVMs / loopback UDP / one physical session. Recorded waiting is not exact physical queue occupancy.\n'
         'Finite gates and within-window recovery are not sustained capacity,statistical significance,hard realtime or100M proof. Hollow tails exclude missing arrivals.',fontsize=9)
fig.subplots_adjust(left=.08,right=.97,top=.9,bottom=.18,hspace=.34,wspace=.29)
files={}
for ext in ('png','svg','pdf'):
    p=O/('dispatch-capacity.'+ext);fig.savefig(p,dpi=160);files[p.name]=dict(bytes=p.stat().st_size,sha256=sha(p))
with(O/'plot-source.csv').open('x',newline='')as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
files['plot-source.csv']=dict(bytes=(O/'plot-source.csv').stat().st_size,sha256=sha(O/'plot-source.csv'))
assert sha(P)==pin
(O/'FIGURES.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    inputSha256=pin,sourceSha256=sha(Path(__file__)),matplotlibVersion=matplotlib.__version__,pointCount=count,
    outputs=files,allOriginalOutcomeCountsMapped=True,noMissingGlobalPercentileImputation=True),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,pointCount=count,files=list(files))))
