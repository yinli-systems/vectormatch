#!/usr/bin/env python3
"""Read-only verification of complete VectorMatch JMH fresh/cache case matrices."""
import argparse,hashlib,itertools,json,math
from pathlib import Path

def verify(registration,raw):
    plan=json.loads(Path(registration).read_text());raw=Path(raw)
    assert json.loads((raw/'plan.json').read_text())==plan,'Registered plan changed'
    assert hashlib.sha256((raw/'worker.py').read_bytes()).hexdigest()==plan['workerSha256'],'Worker changed'
    receipt=json.loads((raw/'receipt.json').read_text());assert receipt['passed'] is True,'CPU job failed'
    output=[]
    prefix='io.vectormatch.bench.jmh.'
    fresh={ (prefix+'FreshMatchingBenchmark.matchBatch',(('initialPriceLevels',str(d)),('tradesPerCommand',str(t)))) for d,t in itertools.product((1,100,10000),(1,10,100))}
    fresh|={ (prefix+'FreshPlaceCancelBenchmark.lifecycleBatch',(('action',a),('initialPriceLevels',str(d)))) for a,d in itertools.product(('PLACE','CANCEL'),(1,100,10000))}
    key=lambda r:(r['benchmark'],tuple(sorted(r.get('params',{}).items())))
    for stage in plan['stages']:
        path=raw/(stage['id']+'.json');rows=json.loads(path.read_text());assert len(rows)==stage['expectedCases'],'Case count'
        keys=[key(r) for r in rows];assert len(set(keys))==len(keys),'Duplicate benchmark/parameters'
        expected=fresh | {(prefix+'DedupCacheBenchmark.replayBatch',())} if stage['expectedCases']==16 else fresh if stage['expectedCases']==15 else {(prefix+'FreshMatchingBenchmark.matchBatch',(('initialPriceLevels','100'),('tradesPerCommand','10')))}
        assert set(keys)==expected,'Missing/unexpected benchmark parameter combination'
        recorded=json.loads((raw/(stage['id']+'-verification.json')).read_text())
        assert recorded['passed'] and recorded['resultSha256']==hashlib.sha256(path.read_bytes()).hexdigest()
        assert recorded['logSha256']==hashlib.sha256((raw/(stage['id']+'.log')).read_bytes()).hexdigest()
        for row in rows:
            assert row['forks']==stage['forks'] and row['threads']==1
            assert row['warmupIterations']==stage['warmup'] and row['measurementIterations']==stage['measurement']
            assert row['jmhVersion']=='1.37' and row['jdkVersion']=='21.0.13'
            assert row['jvmArgs']==['-Xms2g','-Xmx2g']
            metric=row['primaryMetric'];assert len(metric['rawData'])==stage['forks']
            assert all(len(f)==stage['measurement'] for f in metric['rawData'])
            vals=[v for fork in metric['rawData'] for v in fork];assert all(math.isfinite(v) and v>0 for v in vals)
            assert math.isclose(sum(vals)/len(vals),metric['score'],rel_tol=1e-10),'Mean differs from every raw observation'
            cache='.DedupCacheBenchmark.' in row['benchmark']
            assert row['mode']==('thrpt' if cache else 'ss')
            assert metric['scoreUnit']==('ops/s' if cache else 'us/op')
        output.append({'stage':stage['id'],'cases':len(rows),'forks':stage['forks'],'warmupIterations':stage['warmup'],'passed':True,'resultSha256':recorded['resultSha256']})
    assert len(receipt['stages'])==len(output),'Incomplete receipt stage set'
    return {'passed':True,'jobId':plan['jobId'],'stages':output,'scope':'Fresh64-command normalized batch means only; cached replay is not new-command capacity.'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--registration',type=Path,required=True);p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=verify(a.registration,a.raw)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(result))
