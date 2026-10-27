#!/usr/bin/env python3
"""Join bounded own-thread force diagnostics to original commands without inventing wait times."""
from pathlib import Path
import argparse,importlib.util,json,csv,collections,bisect,math

def load(name,file):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def inspect_force(f,samples):
 assert f['outer_start']<=f['start_after']<=f['force_start']<=f['force_end']<=f['end_before']<=f['outer_end']
 cpu=f['cpu_end']-f['cpu_start'];wall=f['force_end']-f['force_start'];outer=f['outer_end']-f['outer_start'];assert 0<=cpu<=outer
 for k in ['voluntary','involuntary','minor','major']:assert f[k+'_end']>=f[k+'_start']
 valid=[s for s in samples if s['sequence']==s['sequence_after']==f['sequence'] and f['force_start']<=s['start']<=s['end']<=f['force_end']]
 states=collections.Counter(s['state_before']if s['state_before']==s['state_after']else'TRANSITION'for s in valid)
 wchan=collections.Counter(s['wchan']for s in valid if s['state_before']==s['state_after']=='D')
 # CPU counters bracket the force interval. They give CPU upper and off-CPU lower
 # bounds for that interval, not exact disk/runnable times. Keep all envelope slack.
 return dict(forceNs=wall,cpuUpperNs=min(wall,cpu),offCpuLowerNs=max(0,wall-cpu),offCpuUpperNs=min(wall,outer-cpu),counterEnvelopeSlackNs=outer-wall,
             voluntary=f['voluntary_end']-f['voluntary_start'],involuntary=f['involuntary_end']-f['involuntary_start'],validSamples=len(valid),states=dict(states),blockedWaitLocations=dict(wchan))

def audit_wait(root):
 p=Path(root);all_forces=[];per_role=[];modes=[]
 for role in range(3):
  launch=json.loads((p/f'node{role}-g0/LAUNCH.json').read_text());args=launch['argv'];flag=[s for s in args if s.startswith('-Dvectormatch.forceWait.enabled=')];assert len(flag)==1;modes.append(flag[0].endswith('=true'));directory=p/f'force-wait/node{role}-g0'
  if not modes[-1]:assert not directory.exists();continue
  clock=(directory/'clock.txt').read_text().splitlines();assert clock[:3]==(p/f'stages/node{role}-g0/clock.txt').read_text().splitlines()[:3] and clock[3:]==['schedstats=0','delayacct=0']
  force_rows=[];thread_results=[]
  for meta_file in sorted(directory.glob('thread-*-complete.json')):
   meta=json.loads(meta_file.read_text());assert meta['forces']>0 and meta['droppedForces']==meta['droppedSamples']==meta['readErrors']==meta['activeAtClose']==0 and meta['intervalNs']==500000
   prefix=meta_file.name[:-len('complete.json')]
   with(directory/(prefix+'forces.csv')).open()as inp:fs=[{k:int(v)for k,v in r.items()}for r in csv.DictReader(inp)]
   with(directory/(prefix+'samples.csv')).open()as inp:ss=[{k:int(v)if k in ['sequence','sequence_after','start','end']else v for k,v in r.items()}for r in csv.DictReader(inp)]
   assert len(fs)==meta['forces'] and len(ss)==meta['samples']
   grouped=collections.defaultdict(list);last=-1
   for s in ss:
    assert s['start']>=last and s['end']>=s['start'];last=s['end'];grouped[s['sequence']].append(s)
   for i,f in enumerate(fs):
    assert f['tid']==meta['tid'] and f['sequence']==i+1
    f['inspection']=inspect_force(f,grouped[f['sequence']]);force_rows.append(f)
   thread_results.append(meta)
  assert thread_results
  stage=[]
  for file in (p/f'stages/node{role}-g0').glob('thread-*.csv'):
   with file.open()as inp:stage.extend({k:int(v)for k,v in r.items()}for r in csv.DictReader(inp)if r['type']=='4')
  actual={(f['recording'],f['session'],f['position_start'],f['position_end'],f['force_start'],f['force_end'])for f in force_rows}
  expected={(e['a'],e['b'],e['c'],e['d'],e['start_ns'],e['end_ns'])for e in stage}
  assert len(actual)==len(force_rows) and actual==expected,'Every native row must match its exact original stage force'
  all_forces.append(force_rows);per_role.append({'role':role,'threads':thread_results})
 assert len(set(modes))==1
 if not modes[0]:return {'enabled':False,'scope':'Original stage tracing stays ON; force CPU/state diagnostics OFF'}
 groups=[]
 for rows in all_forces:
  g=collections.defaultdict(list)
  for f in rows:g[f['session']].append(f)
  g={k:sorted(v,key=lambda f:f['position_end'])for k,v in g.items()};groups.append({k:([f['position_end']for f in v],v)for k,v in g.items()})
 with(p/'stage-attribution.csv').open()as inp:originals=[{k:int(v)for k,v in r.items()}for r in csv.DictReader(inp)]
 output=[]
 for row in originals:
  ends,forces=groups[row['limiting_replica']][row['log_session']];f=forces[bisect.bisect_left(ends,row['log_position'])]
  assert f['position_start']<row['log_position']<=f['position_end'] and f['force_end']-f['force_start']==row['critical_file_force_ns']
  r=f['inspection'];output.append(dict(index=row['index'],correlation=row['correlation'],log_position=row['log_position'],replica=row['limiting_replica'],tid=f['tid'],force_sequence=f['sequence'],full_latency_ns=row['full_latency_ns'],force_ns=r['forceNs'],cpu_upper_ns=r['cpuUpperNs'],off_cpu_lower_ns=r['offCpuLowerNs'],off_cpu_upper_ns=r['offCpuUpperNs'],counter_envelope_slack_ns=r['counterEnvelopeSlackNs'],voluntary=r['voluntary'],involuntary=r['involuntary'],valid_samples=r['validSamples'],d_samples=r['states'].get('D',0),r_samples=r['states'].get('R',0),s_samples=r['states'].get('S',0),transition_samples=r['states'].get('TRANSITION',0),xfs_log_wait_samples=r['blockedWaitLocations'].get('xlog_wait_on_iclog',0)))
 with(p/'force-attribution.csv').open('x',newline='')as out:
  w=csv.DictWriter(out,fieldnames=list(output[0]));w.writeheader();w.writerows(output)
 slow=sorted(output,key=lambda r:r['full_latency_ns'],reverse=True)[:math.ceil(len(output)*.01)];total_force=sum(r['force_ns']for r in slow);sample_count=sum(r['valid_samples']for r in slow)
 def totals(rows):return {k:sum(r[k]for r in rows)for k in ['force_ns','cpu_upper_ns','off_cpu_lower_ns','off_cpu_upper_ns','counter_envelope_slack_ns','voluntary','involuntary','valid_samples','d_samples','r_samples','s_samples','transition_samples','xfs_log_wait_samples']}
 # Include unique original-critical forces as well as the per-request weighted tail.
 ids={(r['replica'],r['tid'],r['force_sequence'])for r in output};locations=collections.Counter();states=collections.Counter();unique=[]
 for role,rows in enumerate(all_forces):
  for f in rows:
   if(role,f['tid'],f['sequence'])in ids:
    unique.append(f['inspection']);locations.update(f['inspection']['blockedWaitLocations']);states.update(f['inspection']['states'])
 return {'enabled':True,'allOriginalsJoined':len(output),'nativeForces':sum(len(x)for x in all_forces),'roles':per_role,'allForceEventsMatchStages':True,'uniqueCriticalForces':len(unique),'uniqueCriticalStates':dict(states),'uniqueCriticalBlockedWaitLocations':dict(locations),'allOriginalTotals':totals(output),'slowestOnePercent':{'count':len(slow),'totals':totals(slow),'forceOffCpuLowerShare':sum(r['off_cpu_lower_ns']for r in slow)/total_force,'sampledDShare':sum(r['d_samples']for r in slow)/sample_count if sample_count else None,'sampledXfsLogWaitShare':sum(r['xfs_log_wait_samples']for r in slow)/sample_count if sample_count else None,'requests':slow[:20]},'exactRunnableWaitNs':None,'exactStorageWaitNs':None,'scope':'CPU counter envelopes bound off-CPU time. State and wchan are sampled observations, not exact duration attribution. R means running OR runnable. Schedstats/delayacct disabled; no physical-device latency claim.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--jfr',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 v=load('base','audit-replicated-path-probe.py').audit(a.root,a.jfr);v['stages']=load('stages','audit-replicated-stage-trace.py').audit_stages(a.root);v['forceWait']=audit_wait(a.root)
 a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'case':v['case'],'latency':v['fullLatency'],'forceWaitEnabled':v['forceWait']['enabled']}))
