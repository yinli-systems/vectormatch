#!/usr/bin/env python3
"""Verify every original stage-probe arm and report both observer-effect pairs."""
from pathlib import Path
import argparse,json,hashlib

def summarize(root):
 root=Path(root);prep=root/'preparation';plan=json.loads((prep/'PLAN.json').read_text());candidate=json.loads((prep/'CANDIDATE.json').read_text());complete=json.loads((root/'COMPLETE.json').read_text())
 assert complete['allSixOriginalArmsClosed'] and complete['allOriginalStagesVerified']
 results={};assets=[];state={};previous_end=None
 for case,spec in plan['cases'].items():
  d=root/case;manifest=json.loads((d/'ARCHIVE_MEMBER_MANIFEST.json').read_text())['files'];asset=json.loads((d/'PRIVATE_ASSET_VERIFIED.json').read_text());assets.append(asset['assetId'])
  assert asset['authenticatedFullDownloadVerified'] and asset['allOriginalMembersVerified'] and asset['privateDraftRelease']==423510304 and asset['closedNativeRoot'].endswith('/'+case)
  for f in d.iterdir():
   name=f.name.replace('__','/')
   if name in manifest:
    b=f.read_bytes();assert len(b)==manifest[name]['bytes'] and hashlib.sha256(b).hexdigest()==manifest[name]['sha256']
  a=json.loads((d/'AUDIT.json').read_text());assert a['case']==case and a['originals']==spec['rate']*spec['seconds'] and a['counts']=={'ACCEPTED':a['originals']}
  assert a['stages']['recording']==spec['traceEnabled'] and a['stages']['sameKernelClockVerified']
  if spec['traceEnabled']:assert a['stages']['allOriginalsJoined']==a['originals'] and a['stages']['sumOfStagesEqualsFullLatency'] and 'stage-attribution.csv'in manifest
  starts=[];ends=[]
  for role in range(4):
   launch=json.loads((d/f'node{role}-g0__LAUNCH.json').read_text());argv=launch['argv'];assert launch['candidate']==candidate and launch['boot']==plan['boot']
   assert argv[:3]==['taskset','-c',','.join(map(str,plan['cpuSets'][role]))] and '-Xms1g'in argv and '-Xmx2g'in argv and '-XX:+UseG1GC'in argv and '-XX:ActiveProcessorCount=4'in argv
   assert '-Dvectormatch.stage.trace='+str(spec['traceEnabled']).lower()in argv and '-Dvectormatch.stage.capacity=1048576'in argv
   assert argv[argv.index('-cp')+1].endswith('/stage-patch.jar:'+asset['closedNativeRoot'].rsplit('/experiments/',1)[0]+'/lib/*')
   if role<3:assert '-Dvectormatch.node.dataPathMaxParkNs=1000000'in argv and '-Daeron.cluster.appointed.leader.id=0'in argv and argv[-7:]==[str(plan['portBase']),'2','524288','127.0.0.1,127.0.0.1,127.0.0.1','capacity-190k-v1','131072','SHARED']
   else:
    i=argv.index('io.vectormatch.cluster.ReplicatedPathProbe');assert argv[i+2:]==[str(plan['portBase']),str(spec['rate']),str(spec['seconds']),'MATCHING']
   exited=json.loads((d/f'node{role}-g0__EXIT.json').read_text());assert exited['returncode']in[0,143];starts.append(launch['startedUTC']);ends.append(exited['completedUTC'])
  assert previous_end is None or previous_end<=min(starts);previous_end=max(ends)
  state[case]=manifest['evidence/cluster-final.bin']['sha256'];results[case]=a
 assert len(set(assets))==len(assets)==6 and state['functional-off']==state['functional-on']
 assert len({state[n]for n in ['trace-a1','trace-b1','trace-a2','trace-b2']})==1
 pairs=[]
 for a,b in [('trace-a1','trace-b1'),('trace-a2','trace-b2')]:
  pairs.append({'a':a,'b':b,'p99RatioOnOverOff':results[b]['fullLatency']['p99Us']/results[a]['fullLatency']['p99Us'],'p999RatioOnOverOff':results[b]['fullLatency']['p999Us']/results[a]['fullLatency']['p999Us'],'meanCpuCoresOff':sum(t['meanCpuCores']for t in results[a]['telemetry']),'meanCpuCoresOn':sum(t['meanCpuCores']for t in results[b]['telemetry'])})
 return {'sourceCommit':candidate['sourceCommit'],'allSixOriginalArmsVerified':True,'observerEffectPairs':pairs,'finalStateHashes':state,'results':results,'privateAssetIds':assets,'scope':plan['scope']}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=summarize(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'verified':True,'observerEffectPairs':v['observerEffectPairs']}))
