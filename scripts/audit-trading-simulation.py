#!/usr/bin/env python3
"""Independently re-count full raw attempts/events and evaluate the registered pairs."""
import argparse,csv,hashlib,json,math,pathlib

def require(ok,message):
    if not ok: raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def quantiles(values):
    values.sort();return {k:values[math.ceil(len(values)*q)-1] for k,q in [('p50',.5),('p99',.99),('p999',.999),('max',1)]}

def canonical_intent(record):
    # JSON object order is not business identity (Java Map.of order varies by JVM).
    return json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')+b'\n'

def audit(path):
    config=json.loads((path/'configuration.json').read_text());result=json.loads((path/'result.json').read_text())
    cycles=config['cycles'];count=cycles*16
    require(result['passed'] is True and not(path/'failure.json').exists(),'Native simulation failed')
    require(result['attempts']==count and result['unresolved']==0,'Missing or unresolved attempts')
    lat=[];service=[];lag=[];counts={};retries=trades=0;outcomes=hashlib.sha256()
    with (path/'samples.csv').open()as f:
        for i,row in enumerate(csv.DictReader(f)):
            require(int(row['index'])==i,'Noncontiguous sample index')
            counts[row['code']]=counts.get(row['code'],0)+1
            replay=row['replayed']=='true';retries+=int(replay)
            if not replay:trades+=int(row['trades'])
            lat.append(int(row['scheduled_ns']));service.append(int(row['service_ns']));lag.append(int(row['dispatch_lag_ns']))
            require(min(lat[-1],service[-1],lag[-1])>=0,'Negative timing')
            outcomes.update(json.dumps({k:v for k,v in row.items() if k not in ['scheduled_ns','service_ns','dispatch_lag_ns']},sort_keys=True).encode()+b'\n')
    require(len(lat)==count,'Partial samples')
    require(counts=={'ACCEPTED':11*cycles,'REJECTED':4*cycles,'IDEMPOTENCY_CONFLICT':cycles},'Outcome population differs')
    require(retries==cycles and trades==4*cycles,'Replay counted as fresh trade or trade lost')
    for name,values in [('scheduledToCompletedNs',lat),('serviceNs',service),('dispatchLagNs',lag)]:
        require(quantiles(values)==result[name],'Raw percentiles differ: '+name)
    identity=hashlib.sha256()
    with (path/'intents.jsonl').open()as f:
        intents=0
        for i,line in enumerate(f):
            record=json.loads(line);require(record['index']==i,'Noncontiguous original intent');intents+=1
            identity.update(canonical_intent(record))
    require(intents==count,'Partial original trace')
    events=fill_count=lots=notional=0
    with (path/'events.jsonl').open()as f:
        for line in f:
            e=json.loads(line);events+=1
            require(e['eventSeq']==events+4 and e['marketSeq']==events,'Event stream gap')
            if e['type']=='TRADE':
                fill_count+=1;lots+=e['quantityLots'];notional+=e['quantityLots']*e['priceTicks']
    require((events,fill_count,lots,notional)==(16*cycles,4*cycles,15*cycles,149970*cycles),'Independent fill/settlement aggregate differs')
    snapshot=path/'final-snapshot.bin'
    # The canonical snapshot contains a SHA-256 suffix; stateHash() hashes the full encoding.
    raw=snapshot.read_bytes();require(hashlib.sha256(raw[:-32]).digest()==raw[-32:],'Snapshot checksum')
    require(sha(snapshot)==result['stateHash'],'State hash differs')
    return dict(result=result,configuration=config,originalTraceSha256=sha(path/'intents.jsonl'),
                canonicalIntentSha256=identity.hexdigest(),
                outcomesSha256=outcomes.hexdigest(),eventsSha256=sha(path/'events.jsonl'),snapshotSha256=sha(snapshot),
                checkedSamples=count,checkedEvents=events,checkedUniqueTrades=fill_count)

def compare(arms):
    names=['A1','B1','A2','B2'];require(set(arms)==set(names),'Four registered arms required')
    first=arms['A1']
    for arm in arms.values():
        for key in ['canonicalIntentSha256','outcomesSha256','eventsSha256','snapshotSha256']:
            require(arm[key]==first[key],'A/B business evidence differs: '+key)
        for key in ['mode','cycles','plannedAttempts','rate','portBase','scope','java','arrivalModel']:
            require(arm['configuration'][key]==first['configuration'][key],'A/B configuration differs: '+key)
        require(arm['configuration']['cycles']==20000 and arm['configuration']['rate']==20000,'Unregistered workload')
    pairs=[]
    for a,b in [('A1','B1'),('A2','B2')]:
        x,y=arms[a]['result'],arms[b]['result']
        gate=dict(serviceP99AtLeastFivePercentLower=y['serviceNs']['p99']<=x['serviceNs']['p99']*.95,
                  scheduledP99NoWorse=y['scheduledToCompletedNs']['p99']<=x['scheduledToCompletedNs']['p99'],
                  scheduledP999NoWorse=y['scheduledToCompletedNs']['p999']<=x['scheduledToCompletedNs']['p999'],
                  inWindowCountNoLower=y['completedInArrivalWindow']>=x['completedInArrivalWindow'])
        pairs.append(dict(baseline=a,candidate=b,gates=gate,passed=all(gate.values())))
    return dict(businessEvidenceIdentical=True,pairs=pairs,promotionPassed=all(p['passed']for p in pairs),arms=arms)

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('--output',required=True,type=pathlib.Path);args=p.parse_args()
    result=compare({n:audit(args.root/n)for n in ['A1','B1','A2','B2']})
    with args.output.open('x')as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(promotionPassed=result['promotionPassed'],pairs=result['pairs'])))

if __name__=='__main__':main()
