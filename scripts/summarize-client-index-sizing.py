#!/usr/bin/env python3
"""Verify the frozen sizing ABAB cohort without substituting conditional latency."""
from pathlib import Path
import argparse,json,hashlib

def summary(root):
 root=Path(root);candidate=json.loads((root/'preparation/CANDIDATE.json').read_text());admission=json.loads((root/'preparation/CPU_ADMISSION.json').read_text());rows=[];assets=[]
 q=root/'qualification-r1';qm=json.loads((q/'MEMBER_MANIFEST.json').read_text())['files'];qp=json.loads((q/'PRIVATE_ASSET_VERIFIED.json').read_text());assert qp['allOriginalMembersVerified']and qp['authenticatedFullDownloadVerified']
 raw=(q/'junit__RESULT.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==qm['junit/RESULT.json']['sha256']
 for n,v in candidate['files'].items():assert qm['input-artifacts/'+n]['sha256']==v['sha256']and qm['input-artifacts/'+n]['bytes']==v['bytes']
 tests=json.loads(raw);assert tests['found']==tests['passed']==12 and all(tests[k]==0 for k in ['failed','skipped','aborted','containerFailures'])
 for rate in [100000,250000]:
  times=[];corpora=[]
  for arm in ['a1','b1','a2','b2']:
   name=f'sizing-{rate}-{arm}';p=root/name;read=lambda n:json.loads((p/n).read_text());manifest=read('MEMBER_MANIFEST.json')['files'];proof=read('PRIVATE_ASSET_VERIFIED.json');assert proof['authenticatedFullDownloadVerified']and proof['allOriginalMembersVerified']and proof['memberCount']==len(manifest);assets.append(proof)
   for n in ['native__result.json','native__configuration.json','native__backlog.json','native__business-resources.json','PYTHON_AUDIT.json','environment.json','java.launch.json','java.exit.json','complete.json']:
    b=(p/n).read_bytes();v=manifest[n.replace('__','/')];assert len(b)==v['bytes']and hashlib.sha256(b).hexdigest()==v['sha256']
   c=read('native__configuration.json');r=read('native__result.json');env=read('environment.json');launch=read('java.launch.json');sized=arm.startswith('b')
   assert manifest['inputs/CANDIDATE.json']['sha256']==hashlib.sha256((root/'preparation/CANDIDATE.json').read_bytes()).hexdigest()
   assert c['presizeClientIds']==sized and c['expectedRetainedOrderSizingHint']==(rate*5+1025 if sized else 0)
   assert c['placement']=='ISOLATED'and c['collector']=='GEN_ZGC'and c['rate']==rate and c['seconds']==5 and c['seed']==73439 and c['totalOutstandingCreditBound']==8192 and c['wireBatchLimit']==64
   assert env['sourceCommit']==candidate['sourceCommit']and env['bootId']==admission['boot']and env['affinity']==admission['chosen']
   assert all(x in launch['argv']for x in ['-Xms1g','-Xmx1g','-XX:ActiveProcessorCount=8','-XX:+UseG1GC','-Dvectormatch.comparison.presizeClientIds='+str(sized).lower()])
   assert r['correctnessPassed']and read('PYTHON_AUDIT.json')['passed']and read('complete.json')['passed']and read('java.exit.json')['groupClosed']
   assert r['planned']==r['accepted']+r['notSent']+r['businessRejected']+r['unknown']
   assert (r['allArrivalAcceptedLatencyNs']is not None)==(r['accepted']==r['planned'])
   rows.append(dict(name=name,rate=rate,arm=arm,presized=sized,planned=r['planned'],accepted=r['accepted'],notSent=r['notSent'],rejected=r['businessRejected'],unknown=r['unknown'],finiteGate=r['finiteGatePassed'],schedulerValid=r['schedulerValid'],allArrivalAcceptedLatencyNs=r['allArrivalAcceptedLatencyNs'],conditionalWorkerServiceNs=r['conditionalWorkerServiceNs'],sourceMaxLatenessMs=r['sourceLatenessNs']['max']/1e6,inWindowAcceptedGoodputPerSecond=r['inWindowAcceptedGoodputPerSecond'],backlog=read('native__backlog.json'),archive=proof))
   times.append(launch['epoch']);corpora.append(r['sourceSha256'])
  assert times==sorted(times)and len(set(times))==4 and len(set(corpora))==1
 assert len({x['assetId']for x in assets})==8
 by={x['name']:x for x in rows};pairs=[]
 for rate in [100000,250000]:
  for i in [1,2]:
   a=by[f'sizing-{rate}-a{i}'];b=by[f'sizing-{rate}-b{i}'];aq=a['allArrivalAcceptedLatencyNs'];bq=b['allArrivalAcceptedLatencyNs']
   pairs.append(dict(rate=rate,pair=i,bothSourceSchedulesValid=a['schedulerValid']and b['schedulerValid'],beforeFiniteGate=a['finiteGate'],afterFiniteGate=b['finiteGate'],beforeNotSent=a['notSent'],afterNotSent=b['notSent'],goodputNotRegressed=b['inWindowAcceptedGoodputPerSecond']>=a['inWindowAcceptedGoodputPerSecond'],fullP99RatioBeforeOverAfter=aq['p99']/bq['p99']if aq and bq else None,finiteCapacityImprovement=b['finiteGate']and b['accepted']>a['accepted']and a['schedulerValid']and b['schedulerValid']and b['inWindowAcceptedGoodputPerSecond']>=a['inWindowAcceptedGoodputPerSecond']))
 totals={k:sum(x[k]for x in rows)for k in ['planned','accepted','notSent','rejected','unknown']}
 return dict(scope='Five-second same-host TCP, mixed common flow; independent source G1, business Generational ZGC. Only initial client-index sizing changes.',sourceCommit=candidate['sourceCommit'],rows=rows,pairs=pairs,totals=totals,all250kPairsImproveFiniteCapacity=all(x['finiteCapacityImprovement']for x in pairs if x['rate']==250000),all8OriginalArmsPrivatelyArchived=True,compressedBytes=sum(x['bytes']for x in assets),sustainedCapacityProven=False,replicated=False)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();v=summary(a.root);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:v[k]for k in ['totals','pairs','all250kPairsImproveFiniteCapacity']}))
