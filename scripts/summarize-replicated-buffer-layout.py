#!/usr/bin/env python3
"""Compare all original layout arms and bind actual mapped devices to unchanged state storage."""
from pathlib import Path
import argparse,json,hashlib

def summarize(root):
 root=Path(root);p=root/'preparation';plan=json.loads((p/'PLAN.json').read_text());candidate=json.loads((p/'CANDIDATE.json').read_text());selection=json.loads((root/'SELECTION.json').read_text());complete=json.loads((root/'COMPLETE.json').read_text());results={};assets=[];hashes={}
 names=list(plan['cases']) if selection['promotedTmpfs'] else list(plan['cases'])[:-1]
 for case in names:
  d=root/case;spec=plan['cases'][case];manifest=json.loads((d/'ARCHIVE_MEMBER_MANIFEST.json').read_text())['files'];asset=json.loads((d/'PRIVATE_ASSET_VERIFIED.json').read_text())
  assert asset['authenticatedFullDownloadVerified'] and asset['allOriginalMembersVerified'] and asset['privateDraftRelease']==423510304 and asset['closedNativeRoot'].endswith('/'+case);assets.append(asset['assetId'])
  for f in d.iterdir():
   name=f.name.replace('__','/')
   if name in manifest:
    b=f.read_bytes();v=manifest[name];assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256']
  a=json.loads((d/'AUDIT.json').read_text());assert a['case']==case and a['mode']=='MATCHING' and a['rate']==spec['rate'] and a['seconds']==spec['seconds']
  assert a['driverLayout']['medium']==spec['driverMedium'] and a['driverLayout']['durableStateRemainsOnOriginalOverlay']
  for role in range(4):
   launch=json.loads((d/f'node{role}-g0__LAUNCH.json').read_text());argv=launch['argv'];assert launch['candidate']==candidate and launch['boot']==plan['boot']
   assert argv[:3]==['taskset','-c',','.join(map(str,plan['cpuSets'][role]))] and '-Xms1g'in argv and '-Xmx2g'in argv and '-XX:+UseG1GC'in argv
   roots=[x for x in argv if x.startswith('-Dvectormatch.probe.driverRoot=')]
   assert len(roots)==(1 if spec['driverMedium']=='tmpfs'else 0)
   if roots:assert roots[0]=='-Dvectormatch.probe.driverRoot=/dev/shm/vectormatch-probe-layout-20261027-r1-'+case
   if role<3:
    assert '-Dvectormatch.node.dataPathMaxParkNs=1000000'in argv and '-Daeron.cluster.appointed.leader.id=0'in argv
    assert argv[-7:]==[str(plan['portBase']),'2','524288','127.0.0.1,127.0.0.1,127.0.0.1','capacity-190k-v1','131072','SHARED']
   else:
    i=argv.index('io.vectormatch.cluster.ReplicatedPathProbe');assert argv[i+2:]==[str(plan['portBase']),str(spec['rate']),str(spec['seconds']),'MATCHING']
  if spec['driverMedium']=='tmpfs':assert json.loads((root/(case+'-TMPFS_CLOSED.json')).read_text())['durableStateRemoved']is False
  hashes[case]=manifest['evidence/cluster-final.bin']['sha256'];results[case]=a
 assert len(set(assets))==len(assets)==complete['originalArmsClosed']
 assert hashes['functional-a']==hashes['functional-b']
 assert len({hashes[n]for n in ['layout-a1','layout-b1','layout-a2','layout-b2']})==1
 pairs=[];promote=True
 for a,b in [('layout-a1','layout-b1'),('layout-a2','layout-b2')]:
  x,y=results[a],results[b];g=y['gates'];passed=all(g[k]for k in ['allAccepted','noUnknown','sourceTimingValid','leaderFixed','inWindow99Percent'])and x['fullLatency']is not None and y['fullLatency']is not None
  passed=bool(passed and y['fullLatency']['p99Us']<=x['fullLatency']['p99Us']*.9 and y['fullLatency']['p999Us']<=x['fullLatency']['p999Us']);promote &= passed
  pairs.append(dict(a=a,b=b,criteriaPassed=passed,p99RatioBoverA=y['fullLatency']['p99Us']/x['fullLatency']['p99Us'] if x['fullLatency']and y['fullLatency']else None))
 assert selection['promotedTmpfs']==complete['promotedTmpfs']==promote and complete['longRunSkippedByPrecommittedPolicy']==(not promote)
 return dict(sourceCommit=candidate['sourceCommit'],allOriginalArmsVerified=True,selection=selection,pairedComparisons=pairs,finalStateHashes=hashes,results=results,privateAssetIds=assets,actualMappedDevicesVerified=True,durabilityLevelUnchanged=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=summarize(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'selection':v['selection'],'pairs':v['pairedComparisons']}))
