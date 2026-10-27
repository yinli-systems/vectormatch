#!/usr/bin/env python3
"""Verify original observer arms, exact native joins and both ON/OFF comparisons."""
from pathlib import Path
import argparse,json,hashlib

def summarize(root):
 root=Path(root);prep=root/'preparation';plan=json.loads((prep/'PLAN.json').read_text());candidate=json.loads((prep/'CANDIDATE.json').read_text());complete=json.loads((root/'COMPLETE.json').read_text())
 assert complete['allSixOriginalArmsClosed'] and complete['allOriginalStagesVerified'] and complete['allEnabledForceJoinsVerified'] and not complete['defaultPromoted']
 cases=list(plan['cases']);assert complete['cases']==cases and len(cases)==6
 results={};states={};assets=[];signatures={};previous_end=None
 for case in complete['cases']:
  d=root/case;spec=plan['cases'][case];manifest=json.loads((d/'ARCHIVE_MEMBER_MANIFEST.json').read_text())['files'];asset=json.loads((d/'PRIVATE_ASSET_VERIFIED.json').read_text());assets.append(asset['assetId'])
  assert asset['authenticatedFullDownloadVerified'] and asset['allOriginalMembersVerified'] and asset['privateDraftRelease']==423510304 and asset['closedNativeRoot'].endswith('/'+case)
  for f in d.iterdir():
   name=f.name.replace('__','/')
   if name in manifest:
    b=f.read_bytes();assert len(b)==manifest[name]['bytes'] and hashlib.sha256(b).hexdigest()==manifest[name]['sha256']
  v=json.loads((d/'AUDIT.json').read_text());assert v['case']==case and v['originals']==spec['rate']*spec['seconds'] and v['counts']=={'ACCEPTED':v['originals']}
  assert v['stages']['recording'] and v['stages']['allOriginalsJoined']==v['originals'] and v['stages']['sumOfStagesEqualsFullLatency'] and v['stages']['sameKernelClockVerified']
  assert v['forceWait']['enabled']==spec['forceWait']
  if spec['forceWait']:assert v['forceWait']['allOriginalsJoined']==v['originals'] and v['forceWait']['allForceEventsMatchStages']
  starts=[];ends=[];signatures[case]=[]
  for role in range(4):
   launch=json.loads((d/f'node{role}-g0__LAUNCH.json').read_text());argv=launch['argv'];assert launch['candidate']==candidate and launch['boot']==plan['boot']
   assert argv[:3]==['taskset','-c',','.join(map(str,plan['cpuSets'][role]))] and '-Xms1g'in argv and '-Xmx2g'in argv and '-XX:+UseG1GC'in argv and '-XX:ActiveProcessorCount=4'in argv
   assert '-Dvectormatch.stage.trace=true'in argv and '-Dvectormatch.stage.preallocate=false'in argv and '-Dvectormatch.forceWait.enabled='+str(spec['forceWait']).lower()in argv and '-Dvectormatch.stage.capacity=1048576'in argv
   if role<3:assert '-Dvectormatch.node.dataPathMaxParkNs=1000000'in argv and '-Daeron.cluster.appointed.leader.id=0'in argv and argv[-7:]==[str(plan['portBase']),'2','524288','127.0.0.1,127.0.0.1,127.0.0.1','capacity-190k-v1','131072','SHARED']
   else:
    i=argv.index('io.vectormatch.cluster.ReplicatedPathProbe');assert argv[i+2:]==[str(plan['portBase']),str(spec['rate']),str(spec['seconds']),'MATCHING']
   signatures[case].append([s.replace('/'+case+'/', '/ARM/')for s in argv if not s.startswith('-Dvectormatch.forceWait.enabled=')])
   exited=json.loads((d/f'node{role}-g0__EXIT.json').read_text());assert exited['returncode']in[0,143];starts.append(launch['startedUTC']);ends.append(exited['completedUTC'])
  assert previous_end is None or previous_end<=min(starts);previous_end=max(ends);states[case]=manifest['evidence/cluster-final.bin']['sha256'];results[case]=v
 assert len(set(assets))==len(assets) and states[cases[0]]==states[cases[1]]
 assert len({states[c]for c in cases[2:6]})==1 and all(signatures[c]==signatures[cases[2]]for c in cases[2:6])
 pairs=[]
 for a,b in [(cases[2],cases[3]),(cases[4],cases[5])]:
  x,y=results[a],results[b];q=y['fullLatency']['p99Us']/x['fullLatency']['p99Us'];qq=y['fullLatency']['p999Us']/x['fullLatency']['p999Us'];g=x['registeredGatePass']and y['registeredGatePass']
  pairs.append(dict(a=a,b=b,p99Ratio=q,p999Ratio=qq,bothGates=g,meanCpuCoresOff=sum(t['meanCpuCores']for t in x['telemetry']),meanCpuCoresOn=sum(t['meanCpuCores']for t in y['telemetry'])))
 return {'allOriginalArchivesVerified':True,'sourceCommit':candidate['sourceCommit'],'configurationIdenticalExceptForceDiagnostics':True,'pairs':pairs,'complete':complete,'results':results,'stateHashes':states,'privateAssets':assets,'scope':plan['scope']}


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=summarize(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'verified':True,'pairs':v['pairs'],'complete':v['complete']}))
