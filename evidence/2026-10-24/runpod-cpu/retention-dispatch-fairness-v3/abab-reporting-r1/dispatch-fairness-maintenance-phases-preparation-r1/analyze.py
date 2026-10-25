from pathlib import Path
import csv, json, hashlib, math, sys, collections, datetime

B=Path(__file__).resolve().parent.parent
arm=int(sys.argv[1]);assert arm in (1,2,3,4)
O=B/f'dispatch-fairness-arm-{arm}-maintenance-phases-r1'
assert not O.exists()
root=B/f'dispatch-fairness-arm-{arm}-root-review-r1'
load=root/'materialized/attempt-8000/idle-arm/load'
inputs={}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):inputs[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p));return p
def read(p):return json.loads(pin(p).read_text())
def kv(p):return dict(line.split('=',1)for line in pin(p).read_text().splitlines()if '='in line)
def union(intervals):
    result=0;left=right=None
    for a,b in sorted(intervals):
        assert b>=a
        if left is None:left,right=a,b
        elif a<=right:right=max(right,b)
        else:result+=right-left;left,right=a,b
    return result+(right-left if left is not None else 0)
review=read(root/'ROOT_REVIEW.json');raw=read(root/'RAW_AUDIT.json')
proof=read(B/f'dispatch-fairness-arm-{arm}-private-proof-r1/PRIVATE_PUSH.json')
assert review['passed']and review['nativeControlPassed']and raw['passed']and proof['passed']and proof['private']and proof['allOriginalNativeAndRawEvidencePushed']
summary=read(load/'load-result.json');rows=[];by_kind=collections.defaultdict(list)
cycles=[]
for p in (load/'maintenance').glob('cycle-*.verified.txt'):
    r=kv(p);assert r['forceAndReadbackBeforeBothAcks']=='true'
    cycles.append((int(r['cycleStartedMonotonicNs']),int(r['cycleEndedMonotonicNs'])))
assert len(cycles)==summary['maintenanceCycles'] and union(cycles)==sum(b-a for a,b in cycles)
with pin(load/'maintenance/logical-rpc-timings.csv').open()as f:
    for r in csv.DictReader(f):
        assert r['completed']=='true';a,b=int(r['start_monotonic_ns']),int(r['end_monotonic_ns'])
        assert b-a==int(r['elapsed_ns']) and sum(c<=a<=b<=d for c,d in cycles)==1
        by_kind[r['kind']].append((a,b));rows.append((a,b))
assert len(rows)==summary['maintenanceRpcMetrics']['logicalRpcCount']
kind_union={k:union(v)for k,v in by_kind.items()}
assert sum(kind_union.values())==union(rows)
writer=collections.Counter();receipts=[]
for p in (load/'writer').glob('*.verified.txt'):
    r=kv(p)
    assert r['forceTrueCompleted']==r['fullReadbackVerified']=='true'
    assert p.name==r['payload']+'.verified.txt'
    entry={k:int(r[k])for k in ('bytes','writeNs','forceNs','readbackNs')}
    assert all(v>=0 for v in entry.values())
    for k,v in entry.items():writer[k]+=v
    receipts.append(dict(path=p.name,**entry))
assert len(receipts)==2*len(cycles)
wall=union(cycles);writer_sum=sum(writer[k]for k in ('writeNs','forceNs','readbackNs'))
assert union(rows)+writer_sum<=wall
for k,v in by_kind.items():
    assert len(v)==summary['maintenanceRpcMetrics']['rpcKinds'][k]['count']
    assert sum(b-a for a,b in v)==summary['maintenanceRpcMetrics']['rpcKinds'][k]['totalElapsedNs']
assert all(Path(n).stat().st_size==p['bytes']and sha(Path(n))==p['sha256']for n,p in inputs.items())
O.mkdir();r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),comparisonArm=arm,
    policy=review['dispatchOrderPolicy'],maintenanceCycles=len(cycles),maintenanceWallNs=wall,
    rpcCount=len(rows),rpcIntervalUnionNs=union(rows),rpcIntervalUnionByKindNs=kind_union,
    writerReceiptCount=len(receipts),writerRecordedTotals=dict(writer),
    residualCoordinatorAndUninstrumentedNs=wall-union(rows)-writer_sum,
    writerReceipts=receipts,inputs=inputs,sourceSha256=sha(Path(__file__)),
    scope='Original monotonic source-RPC intervals merged by union,never summed as wall time. Writer write/force/readback receipt durations are serial awaited phases disjoint from source-RPC consumption in this implementation. Residual combines coordinator verification,encoding,raw IO,queue/lease overhead and uninstrumented time;it is not isolated CPU. RPC intervals include queueing,network,service and evidence consumption;force(true) elapsed is not pure hardware latency. No new workload or optimization.')
(O/'PHASES.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in r.items()if k not in ('inputs','writerReceipts')}))
