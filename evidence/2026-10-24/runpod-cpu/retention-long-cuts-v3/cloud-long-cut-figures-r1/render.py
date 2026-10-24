"""Render only frozen derived values. No raw evidence reads or benchmark analysis."""
import argparse,csv,hashlib,io,json,os,pathlib,sys
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[4]
BASE=ROOT/'runtime/cloud/cpu-20261024'
INPUTS={
 'derived':{'path':BASE/'long-cut-backlog-preparation-r1/actual-analysis-attempt-r2/derived/result.json','name':'derived-result.json','sha256':'b04a9bb0522ecea58813f8d539ca02eb240e7cc19112ff91236a7626d45ba80a'},
 'exposure':{'path':BASE/'long-cut-backlog-preparation-r1/actual-analysis-attempt-r2/EXPOSURE_QUALIFICATION.json','name':'exposure-qualification.json','sha256':'ce7ef212d499b39ecec75dc549195e0f91498047907b2d3cac9fac9ef3ff5454'},
 'rootReview':{'path':BASE/'long-cut-root-recompute-r1/ROOT_REVIEW.json','name':'root-recompute-review.json','sha256':'6ef4b01450900744fe5c7bb5e4b406a232a4d53f793f649a2cde4f4c93713a0b'}}

def need(v,message):
 if not v:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def exclusive(path,raw):
 with path.open('xb') as f:f.write(raw)
def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--library',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--inputs',type=pathlib.Path);a=p.parse_args()
 payloads={};provenance={}
 for role,row in INPUTS.items():
  path=a.inputs/row['name'] if a.inputs is not None else row['path'];need(path.is_file() and not path.is_symlink() and path.stat().st_size<=1024**2,'Bounded frozen derived input required');b=path.read_bytes();need(sha(b)==row['sha256'],'Frozen derived input differs: '+role);payloads[role]=b;provenance[role]={'path':str(path.resolve()),'bytes':len(b),'sha256':sha(b),'portableCopy':'inputs/'+row['name']}
 data=json.loads(payloads['derived']);exposure=json.loads(payloads['exposure']);review=json.loads(payloads['rootReview'])
 need(review['passed'] is True and review['sourceResultSha256']==INPUTS['derived']['sha256'] and review['all12StartAndEndTimestampBucketCountsIndependentlyEqual'] is True,'Root independent count review required')
 need(exposure['basisResultSha256']==INPUTS['derived']['sha256'] and exposure['lastHomogeneousCutCensoredBySourceEnd']['cycle']==11 and exposure['lastHomogeneousCutCensoredBySourceEnd']['cutEndAfterSourceEnd'] is True,'Exact finite source-end qualification required')
 cycles=[r for r in data['all12Cycles'] if 2<=r['cycle']<=11];intervals=data['equivalentAdjacentCutEndIntervals'];need([r['cycle']for r in cycles]==list(range(2,12)) and [(r['fromCut'],r['toCut'])for r in intervals]==[(n,n+1)for n in range(2,11)],'Exact displayed cut and interval inventories required')
 # Direct value mapping only: no percentile, rate or backlog statistic is recomputed.
 rows=[]
 for r in cycles:
  for phase in ('Start','End'):
   key='atCycle'+phase;rows.append({'panel':'a','series':'cycle_'+phase.lower(),'cut':r['cycle'],'from_cut':'','to_cut':'','value':r[key]['releasedNotDispatched'],'unit':'original_arrivals','source_ended_censored':r['cycle']==11,'source_role':'derived','source_json_pointer':'/all12Cycles/'+str(r['cycle']-1)+'/'+key+'/releasedNotDispatched'})
 for i,r in enumerate(intervals):
  for field,label in [('knownAccepted','confirmed'),('released','released')]:rows.append({'panel':'b','series':label,'cut':'','from_cut':r['fromCut'],'to_cut':r['toCut'],'value':r['ratesPerSecond'][field],'unit':'original_orders_per_second','source_ended_censored':r['toCut']==11,'source_role':'derived','source_json_pointer':'/equivalentAdjacentCutEndIntervals/'+str(i)+'/ratesPerSecond/'+field})
 rows.append({'panel':'b','series':'offered_target','cut':'','from_cut':'','to_cut':'','value':500,'unit':'scheduled_orders_per_second','source_ended_censored':False,'source_role':'fixed_plot_parameter','source_json_pointer':'Parent specified the fixed500/s scheduled source target; not a newly estimated rate.'})
 library=a.library.resolve();need(library.is_dir(),'Explicit task-local plotting library required');os.environ['MPLBACKEND']='Agg';need(os.environ.get('MPLCONFIGDIR'),'Explicit task-local matplotlib cache directory required');sys.path.insert(0,str(library))
 import matplotlib
 need(matplotlib.__version__=='3.9.4','Pinned matplotlib3.9.4 required');matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 import numpy
 matplotlib.rcParams.update({'font.family':'DejaVu Sans','font.size':10.5,'axes.titlesize':12,'axes.labelsize':10.5,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':0.8,'xtick.labelsize':10,'ytick.labelsize':10,'legend.fontsize':10,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
 out=a.output.absolute();need(out==out.resolve() and not any(q.is_symlink() for q in (out,*out.parents)),'Unsafe figure output path');out.mkdir(mode=0o700,exist_ok=False);(out/'inputs').mkdir()
 for role,row in INPUTS.items():exclusive(out/'inputs'/row['name'],payloads[role])
 text=io.StringIO();writer=csv.DictWriter(text,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows);exclusive(out/'plot-source.csv',text.getvalue().encode())
 blue,orange,grey='#0072B2','#D55E00','#777777';fig,axes=plt.subplots(2,1,figsize=(11.8,8.7));fig.subplots_adjust(left=.10,right=.975,top=.835,bottom=.165,hspace=.56)
 fig.suptitle('Finite long-cut run: backlog and phase-matched rates',x=.10,y=.974,ha='left',fontsize=17,fontweight='semibold')
 fig.text(.10,.933,'500 scheduled orders/s  |  33,792 original arrivals  |  one host, three Aeron node processes',ha='left',fontsize=11,color='#454545')
 ax=axes[0];x=[r['cycle']for r in cycles];start=[r['atCycleStart']['releasedNotDispatched']for r in cycles];end=[r['atCycleEnd']['releasedNotDispatched']for r in cycles]
 ax.axvspan(10.5,11.45,facecolor='#F0F0F0',zorder=0)
 ax.plot(x[:-1],start[:-1],'-s',color=blue,lw=1.7,ms=5,label='At maintenance start',zorder=4)
 ax.plot(x[:-1],end[:-1],'-o',color=orange,lw=1.7,ms=5.5,label='At maintenance end',zorder=4)
 for series,marker,size in ((start,'s',5),(end,'o',8)):
  ax.plot(x[-2:],series[-2:],'--',color=grey,lw=1.2,zorder=2);ax.plot([11],[series[-1]],marker=marker,linestyle='none',ms=size,mfc='white',mec=grey,mew=1.5,zorder=6)
 ax.annotate('Cut 11 is source-ended\n(end count: 3)',xy=(11,3),xytext=(9.45,95),ha='left',fontsize=9.5,color='#666666',arrowprops={'arrowstyle':'->','color':grey,'lw':1})
 ax.set(title='(a) Released but not yet dispatched at maintenance boundaries',xlabel='Maintenance cut',ylabel='Original arrivals (count)',xlim=(1.65,11.45),ylim=(-12,370));ax.set_xticks(x);ax.grid(axis='y',color='#E4E7EB',lw=.7);ax.set_axisbelow(True);ax.legend(loc='upper left',frameon=False,ncol=2,columnspacing=2.0)
 ax.text(0,-.31,'Logical timestamp count; not physical owner queue occupancy.',transform=ax.transAxes,fontsize=9.5,color='#545454')
 ax=axes[1];xx=[r['toCut']for r in intervals];confirmed=[r['ratesPerSecond']['knownAccepted']for r in intervals];released=[r['ratesPerSecond']['released']for r in intervals]
 ax.axvspan(10.5,11.45,facecolor='#F0F0F0',zorder=0);ax.axhline(500,color='#333333',ls=':',lw=1.25,label='Scheduled target: 500/s',zorder=1)
 for values,color,marker,label in ((confirmed,blue,'o','Confirmed originals'),(released,orange,'s','Released originals')):
  ax.plot(xx[:-1],values[:-1],'-'+marker,color=color,lw=1.7,ms=5,label=label,zorder=4);ax.plot(xx[-2:],values[-2:],'--',color=grey,lw=1.2,zorder=2);ax.plot(xx[-1],values[-1],marker=marker,linestyle='none',ms=7,mfc='white',mec=grey,mew=1.5,zorder=5)
 ax.annotate('10→11 includes source stop\nrelease rate: 452.988/s',xy=(11,released[-1]),xytext=(8.35,466),ha='left',fontsize=9.5,color='#666666',arrowprops={'arrowstyle':'->','color':grey,'lw':1})
 ax.set(title='(b) Rates between adjacent maintenance cut ends',xlabel='Adjacent cut-end interval',ylabel='Original orders / second',xlim=(2.65,11.45),ylim=(445,510));ax.set_xticks(xx,labels=[str(r['fromCut'])+'→'+str(r['toCut'])for r in intervals]);ax.grid(axis='y',color='#E4E7EB',lw=.7);ax.set_axisbelow(True);ax.legend(loc='lower left',frameon=False,ncol=1)
 fig.text(.10,.094,'Intervals are (previous cut end, current cut end]. Grey hollow points are censored by the finite source stop.',fontsize=10,color='#454545')
 fig.text(.10,.059,'Fully offered span: cut ends 2→10, 49.144 s; confirmed 500.080/s, released 499.999/s; backlog drift −4.',fontsize=10,color='#454545')
 fig.text(.10,.026,'Finite observation only. The cut-11 backlog decrease does not demonstrate recovery under ongoing 500/s input.',fontsize=9.5,color='#666666')
 stem=out/'long-cut-backlog-rates';fig.savefig(str(stem)+'.png',dpi=240);fig.savefig(str(stem)+'.svg',metadata={'Date':None});fig.savefig(str(stem)+'.pdf',metadata={'CreationDate':None,'ModDate':None,'Title':'Finite long-cut run: backlog and phase-matched rates'});plt.close(fig)
 output_files={q.name:{'bytes':q.stat().st_size,'sha256':sha(q.read_bytes())}for q in sorted(out.iterdir())if q.is_file()}
 metadata={'schemaVersion':1,'scope':'STANDALONE_SCIENTIFIC_FIGURE_FROM_FROZEN_DERIVED_VALUES_ONLY','inputs':provenance,'renderSourceSha256':sha(pathlib.Path(__file__).read_bytes()),'sourceCommit':data['sourceCommit'],'codeFingerprint':data['codeFingerprint'],'releaseSha256':data['releaseSha256'],'controllerSha256':data['controllerSha256'],'analysisConfigSha256':data['configSha256'],'targetScheduledOrdersPerSecond':500,'displayedCutNumbers':x,'displayedAdjacentCutEndPairs':[[r['fromCut'],r['toCut']]for r in intervals],'censoredCut':11,'censoredInterval':[10,11],'dataCSVRows':len(rows),'plotSourcesHaveExactJsonPointers':True,'newRawEvidenceRead':False,'benchmarkStatisticsRecomputed':False,'software':{'python':sys.version,'pythonExecutable':sys.executable,'matplotlib':matplotlib.__version__,'numpy':numpy.__version__,'explicitLibrary':str(library),'backend':matplotlib.get_backend(),'font':'DejaVu Sans'},'outputs':output_files,'notes':['Counts are logical timestamp counts, not physical owner queue occupancy.','Grey hollow marks and shading identify source-ended censoring; the8fullyoffered intervals are cutEnd2→3 through9→10.','No latency quantiles or capacity ceiling are plotted or inferred.']}
 exclusive(out/'metadata.json',(json.dumps(metadata,indent=2,sort_keys=True)+'\n').encode());print(json.dumps({'passed':True,'outputs':output_files,'metadataSha256':sha((out/'metadata.json').read_bytes())},indent=2))

if __name__=='__main__':main()
