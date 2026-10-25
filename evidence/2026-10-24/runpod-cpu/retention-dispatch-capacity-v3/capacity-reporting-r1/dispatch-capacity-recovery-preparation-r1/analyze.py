from pathlib import Path
from bisect import bisect_right
import sys,json,csv,hashlib,datetime

B=Path(__file__).resolve().parent.parent;rate=int(sys.argv[1]);assert rate in(4000,6000,7000,7500,8000)
O=B/f'dispatch-capacity-{rate}-cut-recovery-r1';assert not O.exists()
root=B/f'dispatch-capacity-{rate}-root-review-r1';load=root/f'materialized/attempt-{rate}/idle-arm/load'
inputs={};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):inputs[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p));return p
def read(p):return json.loads(pin(p).read_text())
r=read(root/'ROOT_REVIEW.json');raw=read(root/'RAW_AUDIT.json');ready=read(root/'READINESS_REVIEW.json')
assert r['passed']and r['nativeControlPassed']and raw['passed']and ready['passed']
assert r['unknownObserved']==r['unknownFinal']==0
cfg=read(load/'configuration.json');arrived=[];dispatched=[];accepted=[];terminals=[]
waiting_start=[];waiting_end=[];queue_full=0
with pin(load/'arrivals.csv').open()as f:
    for index,row in enumerate(csv.DictReader(f)):
        assert int(row['arrival_index'])==index
        a=int(row['arrival_offset_ns']);end=int(row['reply_completion_offset_ns']);assert end>=a
        arrived.append(a);terminals.append(end)
        if row['status']=='APPLIED'and row['result_code']=='ACCEPTED':accepted.append(end)
        if row['dispatch_offset_ns']:
            d=int(row['dispatch_offset_ns']);assert a<=d<=end
            waiting_start.append(a);waiting_end.append(d);dispatched.append(d)
        elif row['status']=='NOT_SENT'and row['not_sent_reason']=='1':
            queue_full+=1;assert a==end and int(row['admitted_physical_offers'])==0
        else:
            assert row['status']=='NOT_SENT';waiting_start.append(a);waiting_end.append(end)
assert index+1==rate*20 and len(accepted)==r['confirmedAcceptedUniqueOrders']
for v in (arrived,dispatched,accepted,terminals,waiting_start,waiting_end):v.sort()
assert len(waiting_start)==len(waiting_end)
def pending_at(t):return bisect_right(arrived,t)-bisect_right(terminals,t)
def waiting_at(t):return bisect_right(waiting_start,t)-bisect_right(waiting_end,t)
cycles=[]
for p in sorted((load/'maintenance').glob('cycle-*.verified.txt')):
    v=dict(line.split('=',1)for line in pin(p).read_text().splitlines())
    start=int(v['cycleStartedMonotonicNs'])-cfg['scheduledOriginMonotonicNs']
    end=int(v['cycleEndedMonotonicNs'])-cfg['scheduledOriginMonotonicNs']
    first,last=int(v['firstCommandSeq']),int(v['throughCommandSeq'])
    cycles.append(dict(cycle=int(v['cycle']),startNs=start,endNs=end,first=first,through=last,
        setupFreeFullCut=first>3 and last-first+1==3072,
        waitingAtEnd=waiting_at(end),unfinishedAtEnd=pending_at(end)))
cycles.sort(key=lambda v:v['cycle'])
assert len(cycles)==r['maintenanceCycles']and all(a['endNs']<=b['startNs']for a,b in zip(cycles,cycles[1:]))
intervals=[]
for a,b in zip(cycles,cycles[1:]):
    if not(a['setupFreeFullCut']and b['setupFreeFullCut']and 0<=a['endNs']<b['endNs']<=20*10**9):continue
    left,right=a['endNs'],b['startNs'];value=minimum=waiting_at(left)
    changes={}
    for t in waiting_start[bisect_right(waiting_start,left):bisect_right(waiting_start,right)]:changes[t]=changes.get(t,0)+1
    for t in waiting_end[bisect_right(waiting_end,left):bisect_right(waiting_end,right)]:changes[t]=changes.get(t,0)-1
    for t,delta in sorted(changes.items()):value+=delta;assert value>=0;minimum=min(minimum,value)
    assert value==waiting_at(right)
    duration=b['endNs']-left
    released=bisect_right(arrived,b['endNs'])-bisect_right(arrived,left)
    completed=bisect_right(terminals,b['endNs'])-bisect_right(terminals,left)
    assert b['unfinishedAtEnd']-a['unfinishedAtEnd']==released-completed
    intervals.append(dict(fromCycle=a['cycle'],toCycle=b['cycle'],startNs=left,endNs=b['endNs'],durationNs=duration,
        released=released,terminal=completed,accepted=bisect_right(accepted,b['endNs'])-bisect_right(accepted,left),
        unfinishedStart=a['unfinishedAtEnd'],unfinishedEnd=b['unfinishedAtEnd'],
        waitingStart=a['waitingAtEnd'],waitingEnd=b['waitingAtEnd'],minimumWaitingDuringActiveDispatch=minimum,
        reachedZeroRecordedWaiting=minimum==0))
assert intervals
assert all(Path(n).stat().st_size==p['bytes']and sha(Path(n))==p['sha256']for n,p in inputs.items())
O.mkdir();report=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),rate=rate,
    queueFullArrivalsExcludedFromWaiting=queue_full,fullOfferedEquivalentCutIntervals=len(intervals),
    intervalsReachingZeroRecordedWaiting=sum(v['reachedZeroRecordedWaiting']for v in intervals),
    firstUnfinished=intervals[0]['unfinishedStart'],lastUnfinished=intervals[-1]['unfinishedEnd'],
    firstWaiting=intervals[0]['waitingStart'],lastWaiting=intervals[-1]['waitingEnd'],
    intervals=intervals,allMaintenanceBoundaries=cycles,inputs=inputs,sourceSha256=sha(Path(__file__)),
    scope='Recorded arrival/dispatch/terminal timestamps reconstruct released-awaiting-dispatch and unfinished logical requests,not exact physical queue occupancy. QUEUE_FULL never enters the waiting series. Only adjacent setup-free3072-command full cuts whose end boundaries remain within the arrival window are compared;post-arrival drain is excluded. Zero waiting between cuts is a finite recovery observation,not a sustained-capacity or realtime guarantee.')
(O/'RECOVERY.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items()if k not in ('inputs','intervals','allMaintenanceBoundaries')}))
