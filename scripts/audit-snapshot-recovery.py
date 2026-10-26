#!/usr/bin/env python3
"""Audit archived snapshot comparisons and an independent integer-account delta.

The binary prefix parser checks counters/accounts and payload checksum, not the
complete order/producer schema. Native full canonical replay remains separate.
"""
import argparse,hashlib,json,struct,tarfile
from pathlib import Path

def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as stream:
  for b in iter(lambda:stream.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def prefix(data):
 assert len(data)>=112 and hashlib.sha256(data[:-32]).digest()==data[-32:],'snapshot checksum'
 header=struct.unpack_from('>7i6qI',data)
 assert header[0:2]==(0x564d4331,2) and 0<header[-1]<=header[3] and 80+40*header[-1]<len(data)-32
 accounts={}
 for i in range(header[-1]):
  account,*balances=struct.unpack_from('>5q',data,80+40*i)
  assert account>0 and account not in accounts and min(balances)>=0;accounts[account]=balances
 assert sum(v[0]+v[1]for v in accounts.values())==header[11]
 assert sum(v[2]+v[3]for v in accounts.values())==header[12]
 return {'configuration':header[:7],'command':header[7],'event':header[8],'market':header[9],'nextOrder':header[10],'totalBase':header[11],'totalQuote':header[12],'accounts':accounts}
def audit(folder,expected_before):
 proof=json.loads((folder/'PRIVATE_ASSET_VERIFIED.json').read_text());assert proof['allOriginalMembersVerified'] and proof['authenticatedFullDownloadVerified']
 archive=folder/proof['name'];assert archive.stat().st_size==proof['bytes']and sha(archive)==proof['sha256']
 required={f'comparison-evidence/arm-{i}-snapshot.bin'for i in range(1,5)}|{'comparison-evidence/result.json','cold-proof-evidence/proof.json','cold-proof-evidence/first-fresh-accepted.json','cold-proof-evidence/restored-before.bin','cold-proof-evidence/restored-after.bin'}
 values={};pins={};manifest=None
 with tarfile.open(archive,'r|gz')as tape:
  for member in tape:
   if member.name=='MEMBER_MANIFEST.json':assert manifest is None;manifest=json.load(tape.extractfile(member))['files'];continue
   if member.name not in required:continue
   assert member.isfile()and member.name not in values and manifest is not None
   data=tape.extractfile(member).read();digest=hashlib.sha256(data).hexdigest();assert {'bytes':len(data),'sha256':digest}==manifest[member.name];pins[member.name]=manifest[member.name]
   if member.name.endswith('-snapshot.bin'):
    assert digest==expected_before;prefix(data);values[member.name]=digest
   elif member.name.endswith('.bin'):values[member.name]=prefix(data)
   else:values[member.name]=json.loads(data)
 assert set(values)==required
 comparison=values['comparison-evidence/result.json'];arms=comparison['arms'];assert len(arms)==4 and comparison['allFourTransfersQualified']
 assert [x['readWindow']for x in arms]==[0,32,0,32]
 assert {x['leaderBefore']for x in arms}|{x['leaderAfter']for x in arms}=={0}
 for i,x in enumerate(arms,1):
  assert x['passed']and x['sameLeader']and x['snapshotSha256']==expected_before and x['bytes']==pins[f'comparison-evidence/arm-{i}-snapshot.bin']['bytes']and x['elapsedNanos']>0
 before=values['cold-proof-evidence/restored-before.bin'];after=values['cold-proof-evidence/restored-after.bin'];native=values['cold-proof-evidence/proof.json'];marker=values['cold-proof-evidence/first-fresh-accepted.json']
 assert pins['cold-proof-evidence/restored-before.bin']['sha256']==expected_before==native['expectedBeforeSha256']==native['restoredBeforeSha256']
 assert pins['cold-proof-evidence/restored-after.bin']['sha256']==native['restoredAfterSha256'] and native['passed']and native['snapshotReadWindow']==32
 assert before['configuration']==after['configuration']and before['totalBase']==after['totalBase']and before['totalQuote']==after['totalQuote']
 assert before['command']==180295 and after['command']==180296==marker['commandSeq']==native['freshCommandSeq']and native['cachedOriginalResultSeq']==180295
 assert after['event']==before['event']+2 and after['market']==before['market']+2 and after['nextOrder']==before['nextOrder']+1
 buyer=1_000_100+(180128%128)%64;seller=1_000_001
 expected={k:list(v)for k,v in before['accounts'].items()};expected[buyer][0]+=1;expected[buyer][2]-=10_000;expected[seller][1]-=1;expected[seller][2]+=10_000
 assert expected==after['accounts'],'independent integer settlement delta differs'
 ratios=[arms[a]['elapsedNanos']/arms[b]['elapsedNanos']for a,b in [(0,1),(2,3)]]
 assert comparison['bothPairedReadDurationsLower']==all(r>1 for r in ratios)
 return dict(scope='private-verified native snapshot bytes; independent Python checksum/counter/account-prefix audit, not a full second matching model or physical-fault test',sourceAsset=proof,inputs=pins,sameStateAllFourReads=True,readSpeedupRatios=ratios,independentSettlementDeltaPassed=True,buyer=buyer,seller=seller,priceTicks=10000,quantityLots=1,originalCommandSeq=before['command'],freshCommandSeq=after['command'],freshSingleRpcNs=marker['rpcNanos'],noBusinessLatencyDistributionOrRecoveryRtoClaim=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('archive_folder',type=Path);p.add_argument('--expected-before-sha256',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args();r=audit(a.archive_folder,a.expected_before_sha256)
 with a.output.open('x')as out:json.dump(r,out,indent=2);out.write('\n')
 print(json.dumps({k:v for k,v in r.items()if k not in ['inputs','sourceAsset']}))
