from pathlib import Path
import csv,hashlib,json
P=Path(__file__).resolve().parent;E=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards/evidence/2026-10-27/client-index-sizing-r1');end=1089073;results=[]
for name in ['sizing-250000-a1','sizing-250000-b1','sizing-250000-a2','sizing-250000-b2']:
 p=P/('diagnostic-'+name);proof=json.loads((E/'diagnosis'/name/'PROVENANCE.json').read_text());h=hashlib.sha256();count=0
 with(p/'server-outcomes.csv').open()as f:
  for row in csv.DictReader(f):
   i=int(row['index'])
   if i>end:break
   assert i==count and row['accepted']=='true','missing or rejected original before compared growth event'
   h.update((','.join(row[k]for k in ['index','accepted','remaining','trades'])+'\n').encode());count+=1
 assert count==end+1
 results.append({'case':name,'prefixOriginals':count,'prefixIncludesGrowthOriginalIndex':end,'noMissingOrRejectedInPrefix':True,'canonicalPrefixResultSha256':h.hexdigest(),'commandsSha256':proof['sourceMembers']['native/commands.csv']['sha256'],'serverOutcomesSha256':proof['sourceMembers']['native/server-outcomes.csv']['sha256'],'sourceAssetId':proof['sourcePrivateAsset']['assetId']})
assert len({r['commandsSha256']for r in results})==len({r['canonicalPrefixResultSha256']for r in results})==1
v={'allFourOriginalPrefixesIdentical':True,'scope':'identical ordered input corpus and accepted/remaining/trade-count prefix through the resize original; full independent trade/balance replay is archived separately for each arm','rows':results}
(E/'diagnosis/PREFIX_EQUIVALENCE.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'allFourOriginalPrefixesIdentical':True,'prefixCommandsPerArm':end+1}))
