from pathlib import Path
import csv, datetime, hashlib, json, math, sys

B = Path(__file__).resolve().parent.parent
rates = [int(x) for x in sys.argv[2:]]
O = Path(sys.argv[1]).resolve()
assert not O.exists() and rates and sorted(set(rates)) == rates
inputs = {}

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def pin(p):
    inputs[str(p)] = dict(bytes=p.stat().st_size, sha256=sha(p))
    return p

def read(p):
    return json.loads(pin(p).read_text())

def quantile(values, fraction):
    return sorted(values)[math.ceil(len(values)*fraction)-1] if values else None

observations = []
for rate in rates:
    root = B / ('ready-shared-capacity-%d-root-review-r1' % rate)
    load = root / ('materialized/attempt-%d/idle-arm/load' % rate)
    review = read(root/'ROOT_REVIEW.json')
    raw = read(root/'RAW_AUDIT.json')
    push = read(B/('ready-shared-capacity-%d-private-proof-r1/PRIVATE_PUSH.json' % rate))
    readiness = read(root/'READINESS_REVIEW.json')
    assert readiness['passed'] and push['allMemberReadinessGatesIndependentlyVerified'] and push['readinessReviewSha256']==sha(root/'READINESS_REVIEW.json')
    cfg = read(load/'configuration.json')
    summary = read(load/'load-result.json')
    assert review['passed'] and raw['passed'] and push['passed'] and push['private']
    assert push['allOriginalNativeAndRawEvidencePushed'] and push['remoteCommitVerified']
    assert push['rawAuditSha256'] == sha(root/'RAW_AUDIT.json')
    assert push['rootReviewSha256'] == sha(root/'ROOT_REVIEW.json')
    assert cfg['actualCodeSha256'] == raw['codeFingerprint'] == '1a9ee9586e83c32d6ddab3cf89e927b6ecbb2639b30dab506f8b43c2c774f494'
    assert cfg['ratePerSecond'] == rate and cfg['arrivals'] == rate*20
    assert cfg['readWindow'] == 128 and cfg['eventFetchCount'] == 32
    assert cfg['physicalSessions'] == 1 and cfg['logicalWorkers'] == 128
    with pin(load/'arrivals.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == rate*20
    accepted = [r for r in rows if r['status']=='APPLIED' and r['result_code']=='ACCEPTED']
    latency = lambda r: int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns'])
    assert quantile([latency(r) for r in accepted], .99) == review['acceptedOrderConditionalP99Ns']
    cycles = []
    for p in sorted((load/'maintenance').glob('cycle-*.verified.txt')):
        fields = dict(line.split('=',1) for line in pin(p).read_text().splitlines())
        assert fields['forceAndReadbackBeforeBothAcks'] == 'true'
        cycles.append((int(fields['cycleStartedMonotonicNs'])-cfg['scheduledOriginMonotonicNs'],
                       int(fields['cycleEndedMonotonicNs'])-cfg['scheduledOriginMonotonicNs']))
    cycles.sort()
    assert len(cycles) == review['maintenanceCycles']
    assert all(0 <= start <= end for start,end in cycles)
    assert all(a[1] <= b[0] for a,b in zip(cycles,cycles[1:]))
    with pin(load/'backlog.csv').open() as f:
        backlog = list(csv.DictReader(f))
    tail = sorted(accepted, key=latency, reverse=True)[:math.ceil(len(accepted)*.01)]
    tail_ns = sum(latency(r) for r in tail)
    predispatch = sum(int(r['dispatch_offset_ns'])-int(r['scheduled_offset_ns']) for r in tail)
    overlap = sum(max(0,min(int(r['dispatch_offset_ns']),end)-max(int(r['arrival_offset_ns']),start))
                  for r in tail for start,end in cycles)
    buckets = []
    for second in range(20):
        start,end = second*10**9,(second+1)*10**9
        cohort = [r for r in rows if start <= int(r['scheduled_offset_ns']) < end]
        ok = [r for r in cohort if r['status']=='APPLIED' and r['result_code']=='ACCEPTED']
        completions = sum(start <= int(r['reply_completion_offset_ns']) < end for r in accepted)
        sample = [r for r in backlog if start <= int(r['offset_ns']) < end]
        buckets.append(dict(second=second,scheduled=len(cohort),eventuallyAccepted=len(ok),
                            acceptedCompletionsInWallSecond=completions,
                            allScheduledAcceptedP99Ns=quantile([latency(r) for r in ok],.99) if len(ok)==len(cohort) else None,
                            sampledQueueHighWater=max((int(r['queued']) for r in sample),default=None)))
    assert sum(b['scheduled'] for b in buckets) == rate*20
    assert sum(b['acceptedCompletionsInWallSecond'] for b in buckets) == review['acceptedWithinArrivalWindow']
    observations.append(dict(rate=rate,arrivals=rate*20,windowSeconds=20,nativeControlPassed=push.get('nativeControlPassed',True),performanceQualified=push.get('performanceQualified',True),nativeControlErrors=push.get('nativeControlErrors',[]),
        accepted=review['confirmedAcceptedUniqueOrders'],goodput=review['arrivalWindowGoodputPerSecond'],
        allArrivalP50Ns=review['allArrivalP50Ns'],allArrivalP99Ns=review['allArrivalP99Ns'],
        conditionalAcceptedP99Ns=review['acceptedOrderConditionalP99Ns'],
        notSent=review['notSent'],rejected=review['serverRejected'],unknownObserved=review['unknownObserved'],
        unknownFinal=review['unknownFinal'],schedulerTimingValid=review['schedulerTimingValid'],
        schedulerMaxLatenessNs=summary['schedulerMaxLatenessNs'],
        windowConfirmationFraction=review['windowConfirmationFraction'],
        sampledQueueHighWater=review['sampledBacklogHighWater'],
        lastKnownReplyDrainNs=summary['lastKnownReplyDrainNs'],totalSourceDrainNs=summary['totalSourceDrainNs'],
        maintenanceCycles=len(cycles),maintenanceWallNs=sum(end-start for start,end in cycles),
        maintenanceWallInsideArrivalWindowNs=sum(max(0,min(end,20*10**9)-max(start,0)) for start,end in cycles),
        actualReadRegistryHighWater=summary['physicalOfferTape']['readOnlyRawRegistryHighWater'],
        slowestOnePercentRows=len(tail),slowestOnePercentPredispatchShare=predispatch/tail_ns if tail_ns else None,
        slowestOnePercentQueueMaintenanceOverlapShare=overlap/tail_ns if tail_ns else None,
        finiteProgressionPermitted=push['finiteProgressionPermitted'],privateEvidenceCommit=push['commit'],
        wallSecondBuckets=buckets))

assert all(Path(n).stat().st_size==r['bytes'] and sha(Path(n))==r['sha256'] for n,r in inputs.items())
O.mkdir(parents=True)
report = dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              sourceSha256=sha(Path(__file__)),inputs=inputs,observations=observations,
              scope='One unchangede5ac8f7c application,read128,page32,leader0,sync2,batch4,chunk6144,owner1ms,driver100us,W128Q64,one physical session,two original all-member2s readiness gates around setup/5s warmup,no JFR. Three JVMs on one CPU host over loopback UDP. Fresh20s lineages are finite exploration, not sustained capacity or cumulative endurance. Tail timestamp overlap is descriptive, not isolated causation.',
              noSustainedCapacityHardRealtimeOr100MClaim=True)
(O/'CURVE.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,observations=[{k:v for k,v in o.items() if k!='wallSecondBuckets'} for o in observations])))
