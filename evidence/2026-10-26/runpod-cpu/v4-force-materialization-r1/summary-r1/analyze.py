from pathlib import Path
import json,hashlib,tarfile,csv,io,sys
# Reproduction reads the complete archived originals;no sampling or pooled percentiles.
root=Path(sys.argv[1]);expected=hashlib.sha256()
for i in range(3000):expected.update(bytes(((i*31+(i>>8)*13+j*17)&255)for j in range(256))*16)
zero=bytes(1024*1024);remaining=128*1024**2-3000*4096
while remaining:
 n=min(len(zero),remaining);expected.update(zero[:n]);remaining-=n
expected=expected.hexdigest();points={}
for arm in ['c1','d1','c2','d2']:
 A=root/(arm+'-original-r1');v=json.loads((A/'VERIFIED.json').read_text());r=v['results'][0];assert v['passed']and all(w['fullReadbackSha256']==expected for w in r['writers'])
 with tarfile.open(A/'complete-original-files.tar.gz','r:gz')as t:
  ready=json.load(t.extractfile('original/control/'+arm+'-READY_STAT.json'))
  for st in ready['files']:assert (st['allocatedBytes']>=st['bytes'])if arm[0]=='d'else(st['allocatedBytes']<st['bytes'])
  for w in r['writers']:
   rows=list(csv.DictReader(io.TextIOWrapper(t.extractfile('original/'+arm+'/samples-'+str(w['writer'])+'.csv'),encoding='utf8')));assert len(rows)==3000
   for key,field in [('write','writeNs'),('force','forceNs')]:
    vals=[int(row[field])for row in rows];assert min(vals)>0;sort=sorted(vals);actual=dict(count=3000,totalNs=sum(vals),p50Ns=sort[1499],p99Ns=sort[2969],maxNs=sort[-1]);assert actual==w[key]
   for i,row in enumerate(rows):
    assert int(row['step'])==i and int(row['forceStartNs'])>=int(row['writeStartNs'])+int(row['writeNs'])
    if i:assert int(row['writeStartNs'])>=int(rows[i-1]['forceStartNs'])+int(rows[i-1]['forceNs'])
 r['independentlyReconstructedExpectedWholeFileSha256']=expected;r['all9000RawSamplesIndependentlyRecomputed']=True;points[arm]=r
pairs=[]
for a,d in [('c1','d1'),('c2','d2')]:
 comparisons=[]
 for x,y in zip(points[a]['writers'],points[d]['writers']):comparisons.append(dict(writer=x['writer'],forceP99ReductionPercent=100*(1-y['force']['p99Ns']/x['force']['p99Ns']),forceP99AtLeastTenPercentLower=y['force']['p99Ns']*10<=x['force']['p99Ns']*9,workDurationNoWorse=y['workDurationNs']<=x['workDurationNs']))
 pairs.append(dict(control=a,candidate=d,writers=comparisons,passed=all(x['forceP99AtLeastTenPercentLower']and x['workDurationNoWorse']for x in comparisons)))
result=dict(passed=True,bothRegisteredScreeningPairsPassed=all(p['passed']for p in pairs),pairs=pairs,points=points,all36000ForceAndWriteSamplesIndependentlyRecomputed=True,allTwelveFullFileExpectedHashesIndependentlyReconstructed=True,noNativeTradingPerformanceClaim=True,noDefaultPromotion=True)
assert result==json.loads((root/'summary-r1/RESULT.json').read_text())
print(json.dumps(dict(passed=True,archivedResultExactlyReproduced=True,bothRegisteredScreeningPairsPassed=result['bothRegisteredScreeningPairsPassed'])))
