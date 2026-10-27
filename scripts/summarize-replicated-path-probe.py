#!/usr/bin/env python3
"""Verify thin receipts and compare every preregistered original arm, including failures."""
from pathlib import Path
import argparse,json,hashlib

def summarize(root):
 root=Path(root);prep=root/'preparation';plan=json.loads((prep/'PLAN.json').read_text());candidate=json.loads((prep/'CANDIDATE.json').read_text());selection=json.loads((root/'SELECTION.json').read_text());results={};assets=[]
 previous_end=None
 for case,spec in plan['cases'].items():
  d=root/case;manifest=json.loads((d/'ARCHIVE_MEMBER_MANIFEST.json').read_text())['files'];asset=json.loads((d/'PRIVATE_ASSET_VERIFIED.json').read_text())
  assert asset['authenticatedFullDownloadVerified'] and asset['allOriginalMembersVerified'] and asset['privateDraftRelease']==423510304
  assert asset['closedNativeRoot'].endswith('/'+case);assets.append(asset['assetId'])
  for f in d.iterdir():
   name=f.name.replace('__','/')
   if name in manifest:
    b=f.read_bytes();v=manifest[name];assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256'],str(f)
  a=json.loads((d/'AUDIT.json').read_text());w=json.loads((d/'evidence__window.json').read_text())
  assert a['case']==case and a['mode']==spec['mode'] and a['rate']==spec['rate'] and a['seconds']==spec['seconds'] and a['originals']==spec['rate']*spec['seconds']
  assert w['archiveSyncLevel']==2 and not w['sourceRecordsDurableDuringWindow']
  park=selection['selectedMaxParkNs'] if case=='sustained-r1' else spec['maxParkNs']
  starts=[];ends=[]
  for role in range(4):
   launch=json.loads((d/f'node{role}-g0__LAUNCH.json').read_text());argv=launch['argv'];assert launch['candidate']==candidate and launch['boot']==plan['boot']
   assert argv[:3]==['taskset','-c',','.join(map(str,plan['cpuSets'][role]))]
   assert '-Xms1g'in argv and '-Xmx2g'in argv and '-XX:ActiveProcessorCount=4'in argv and '-XX:+UseG1GC'in argv
   if role<3:
    assert '-Dvectormatch.node.dataPathMaxParkNs='+str(park) in argv and '-Daeron.cluster.appointed.leader.id=0'in argv
    i=argv.index('io.vectormatch.cluster.ReplicatedPathProbeNode');assert argv[i+1]==spec['mode'] and argv[-7:]==[str(plan['portBase']),'2','524288','127.0.0.1,127.0.0.1,127.0.0.1','capacity-190k-v1','131072','SHARED']
   else:
    i=argv.index('io.vectormatch.cluster.ReplicatedPathProbe');assert argv[i+2:]==[str(plan['portBase']),str(spec['rate']),str(spec['seconds']),spec['mode']]
   exited=json.loads((d/f'node{role}-g0__EXIT.json').read_text());assert exited['returncode']in[0,143]
   starts.append(launch['startedUTC']);ends.append(exited['completedUTC'])
  assert previous_end is None or previous_end<=min(starts)
  previous_end=max(ends)
  a['replicaMaxParkNs']=park;results[case]=a
 assert len(assets)==len(set(assets))==11
 pairs=[];promote=True
 for a,b in [('idle-a1','idle-b1'),('idle-a2','idle-b2')]:
  x,y=results[a],results[b];g=y['gates'];passed=all(g[k]for k in ['allAccepted','noUnknown','sourceTimingValid','leaderFixed','inWindow99Percent'])and x['fullLatency']is not None and y['fullLatency']is not None
  passed=bool(passed and y['fullLatency']['p99Us']<=x['fullLatency']['p99Us']*.9 and y['fullLatency']['p999Us']<=x['fullLatency']['p999Us'])
  pairs.append(dict(a=a,b=b,criteriaPassed=passed,p99RatioBoverA=y['fullLatency']['p99Us']/x['fullLatency']['p99Us']if x['fullLatency']and y['fullLatency']else None));promote &= passed
 assert selection['selectedMaxParkNs']==(100000 if promote else 1000000) and selection['bothPairedCriteriaPassed']==promote
 return dict(sourceCommit=candidate['sourceCommit'],scope=plan['scope'],all11OriginalArmsVerified=True,selection=selection,pairedComparisons=pairs,results=results,allPrivateAssetIds=assets)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=summarize(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'verified':v['all11OriginalArmsVerified'],'selection':v['selection'],'pairs':v['pairedComparisons']}))
