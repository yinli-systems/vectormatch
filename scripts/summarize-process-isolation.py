#!/usr/bin/env python3
"""Rebuild finite conclusions from member-hash-bound closed experiment receipts."""
import argparse,hashlib,json
from pathlib import Path

def summary(root):
    root=Path(root);rows=[];assets=[]
    for phase in ['placement','collector']:
        for rate in [100000,250000]:
            stamps=[];hashes=[]
            for arm in ['a1','b1','a2','b2']:
                name=f'{phase}-{rate}-{arm}';p=root/name
                read=lambda n:json.loads((p/n).read_text())
                manifest=read('MEMBER_MANIFEST.json')['files'];proof=read('PRIVATE_ASSET_VERIFIED.json')
                assert proof['allOriginalMembersVerified']and proof['authenticatedFullDownloadVerified']
                assert proof['memberCount']==len(manifest)
                for n in ['native__result.json','native__backlog.json','native__business-resources.json','native__source-resources.json','native__configuration.json','PYTHON_AUDIT.json','java.launch.json','java.exit.json','complete.json']:
                    native=n.replace('__','/');raw=(p/n).read_bytes();assert len(raw)==manifest[native]['bytes']and hashlib.sha256(raw).hexdigest()==manifest[native]['sha256']
                r=read('native__result.json');b=read('native__backlog.json');c=read('native__configuration.json');audit=read('PYTHON_AUDIT.json')
                assert r['correctnessPassed']and audit['passed']and read('complete.json')['passed']and read('java.exit.json')['groupClosed']
                assert c['rate']==rate and c['seconds']==5 and c['seed']==73439 and c['totalOutstandingCreditBound']==8192 and c['wireBatchLimit']==64
                assert c['placement']==('COLOCATED'if phase=='placement'and arm.startswith('a')else'ISOLATED')
                assert c['collector']==('GEN_ZGC'if phase=='collector'and arm.startswith('b')else'G1')
                stamps.append(read('java.launch.json')['epoch']);hashes.append(r['sourceSha256']);assets.append(proof)
                rows.append(dict(name=name,phase=phase,arm=arm,rate=rate,planned=r['planned'],accepted=r['accepted'],notSent=r['notSent'],rejected=r['businessRejected'],unknown=r['unknown'],finiteGate=r['finiteGatePassed'],sourceMaxLatenessMs=r['sourceLatenessNs']['max']/1e6,allArrivalAcceptedLatencyNs=r['allArrivalAcceptedLatencyNs'],conditionalWorkerServiceNs=r['conditionalWorkerServiceNs'],inWindowAcceptedGoodputPerSecond=r['inWindowAcceptedGoodputPerSecond'],backlog=b,archiveAssetId=proof['assetId']))
            assert stamps==sorted(stamps)and len(set(stamps))==4 and len(set(hashes))==1
    by={r['name']:r for r in rows};pairs=[]
    for i in [1,2]:
        a=by[f'collector-100000-a{i}'];b=by[f'collector-100000-b{i}']
        pairs.append(dict(pair=i,p99BeforeNs=a['allArrivalAcceptedLatencyNs']['p99'],p99AfterNs=b['allArrivalAcceptedLatencyNs']['p99'],ratio=a['allArrivalAcceptedLatencyNs']['p99']/b['allArrivalAcceptedLatencyNs']['p99'],noMissingBeforeOrAfter=all(x['accepted']==x['planned']and x['unknown']==0 for x in [a,b]),goodputNotRegressed=b['inWindowAcceptedGoodputPerSecond']>=a['inWindowAcceptedGoodputPerSecond']))
    totals={k:sum(r[k]for r in rows)for k in ['planned','accepted','notSent','rejected','unknown']};assert totals['planned']==totals['accepted']+totals['notSent']+totals['rejected']+totals['unknown']
    return dict(schema='process-isolation-summary-1',scope='Same-host TCP scheduled-to-reply, finite five-second arms; no journal or replication',rows=rows,totals=totals,collector100kPairs=pairs,collector100kRepeatedFiniteImprovement=all(p['noMissingBeforeOrAfter']and p['goodputNotRegressed']and p['ratio']>1 for p in pairs),sustainedCapacityProven=False,allFiniteAssetsVerified=len(assets),finiteCompressedBytes=sum(a['bytes']for a in assets),rawBytes=sum(sum(v['bytes']for v in json.loads((root/r['name']/'MEMBER_MANIFEST.json').read_text())['files'].values())for r in rows))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();value=summary(a.root);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items()if k!='rows'}))
