from pathlib import Path
import json,hashlib,copy,datetime,sys

R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';count=int(sys.argv[1]);assert count in(2,3,4,5)
O=B/f'dispatch-capacity-ui-derivation-first-{count}-r1';assert not O.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before_path=R/'evidence/index.json';before=json.loads(before_path.read_text());before_sha=sha(before_path)
curve_path=B/f'dispatch-capacity-first-{count}-curve-analysis-r1/CURVE.json'
curve=json.loads(curve_path.read_text());assert curve['passed']and curve['allInputBodiesUnchanged']
assert len(before['runs'])==44 and len(before['capacityCohorts'])==19 and len(curve['observations'])==count
assert [r['rate']for r in curve['observations']]==[4000,6000,7000,7500,8000][:count]
assert all(Path(n).stat().st_size==p['bytes']and sha(Path(n))==p['sha256']for n,p in curve['inputs'].items())
data=copy.deepcopy(before);points=[]
for r in curve['observations']:
    rate=r['rate'];identity=f'cpu-rotating-fine-{rate}'
    scope=f"{r['planned']:,} planned · {r['accepted']:,} accepted · {r['notSent']} not sent · finite 20s"
    data['runs'].append(dict(id=identity,label=f'CPU rotating dispatch · {rate:,}/s · finite capacity point',
        scope=scope,model='One CPU host · three JVMs · loopback UDP · one physical session',commands=r['planned'],
        throughput=r['goodput'],p50Millis=r['allArrivalAcceptedP50Ns']/1e6 if r['allArrivalAcceptedP50Ns']is not None else None,
        p99Millis=r['allArrivalAcceptedP99Ns']/1e6 if r['allArrivalAcceptedP99Ns']is not None else None,
        unknown=r['finalUnknown'],correctnessPassed=True,
        durability='sync2 replicated log; exact-prefix force and full readback before both ACKs',
        artifactPath=f'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-{rate}-r1/README.md',timestamp=r['scheduledOriginUTC'],
        limitations=[
            f"One fresh20s lineage. {r['accepted']}/{r['planned']} accepted; {r['notSent']} notSent; rejected/observed UNKNOWN/final UNKNOWN={r['rejected']}/{r['observedUnknown']}/{r['finalUnknown']}. Confirmed inside the arrival window: {r['goodput']}/s ({100*r['windowConfirmationFraction']:.4f}%).",
            f"Accepted-only conditional p99={r['conditionalAcceptedP99Ns']/1e6:.6f}ms. "+('Every original arrival was accepted,so global accepted percentiles exist.'if r['allArrivalAcceptedP99Ns']is not None else'Missing successful arrivals make global accepted percentiles unavailable;conditional values do not replace them.'),
            f"Recorded waiting reaches zero between maintenance cuts in {r['intervalsReachingZeroRecordedWaiting']}/{r['fullOfferedCutIntervals']} fully offered equivalent intervals. This is reconstructed from all original arrival/dispatch timestamps,not exact physical queue occupancy or a sustained-capacity proof.",
            f"Sampled total queue high-water {r['sampledBacklogHighWater']};per-worker observed queue high-water {r['perWorkerQueueHighWater']}. One-second aggregate sampling can alias maintenance cycles and does not establish the true instantaneous global maximum.",
            'New source566dd2fa/code2b8d7594. ROTATING_CONTINUE,leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64. Both original-PID all-member2s readiness gates and5s pre-load warm-up passed;no JFR. One physical session is not128 physical connections.',
            f"Complete original native,CSV,wire/frame/index/offer,identity/result,source and readiness bodies privately verified at {r['privateCommit']}. Compressed original scopes retain every byte/member/mode/owner/directory. Earlier failed local planner qualification remains archived.",
            'Finite progression gate '+('met.'if r['finiteProgressionGateMet']else'not met;load escalation stops.')+' Separate20s trials,not sustained capacity,statistical significance,hard realtime or any100M target. Historical cohorts remain separate.'
        ]))
    points.append(dict(id=identity,rate=rate,workers=128,goodput=r['goodput'],p99Millis=r['conditionalAcceptedP99Ns']/1e6,
        clientNotSent=r['notSent'],rejected=r['rejected'],serverErrors=0,unknown=r['observedUnknown'],unresolved=r['finalUnknown'],
        allOfferedAcceptedP99Millis=r['allArrivalAcceptedP99Ns']/1e6 if r['allArrivalAcceptedP99Ns']is not None else None,
        drainSeconds=r['drainNs']/1e9,classification='FINITE_20S_GATE_MET'if r['finiteProgressionGateMet']else'OBSERVED_OVERLOAD_FINITE_WINDOW',
        peakBacklog=r['sampledBacklogHighWater'],valid=True,stable=r['finiteProgressionGateMet'],windowSeconds=20))
data['capacityCohorts'].append(dict(id='cpu-rotating-fine-566dd2fa-20s',title='CPU rotating dispatch · fine rates · finite20s',
    updatedAt=curve['observations'][-1]['scheduledOriginUTC'],
    scope='One CPU host / three JVMs / loopback UDP.128 logical workers,one physical session. Fixed leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64. Original-PID readiness around setup/5s warm-up;no JFR. Each point is one separate20s lineage. Stable markers mean only the documented finite exploration gate;neither a sustained throughput ceiling nor an SLA. Full original compressed scopes privately verified.',
    reportPath='docs/DISPATCH_CAPACITY_RESULTS.md',configurationFingerprint=curve['codeFingerprint'],points=points))
assert data['runs'][:44]==before['runs']and data['capacityCohorts'][:19]==before['capacityCohorts']and data['capacity']==before['capacity']
assert sha(before_path)==before_sha
O.mkdir();(O/'index-before.json').write_bytes(before_path.read_bytes())
(O/'index-derived.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
(O/'DERIVATION.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    records=44+count,cohorts=20,curveSha256=sha(curve_path),curvePath=str(curve_path),sourceSha256=sha(Path(__file__)),
    previousIndexSha256=before_sha,derivedSha256=sha(O/'index-derived.json'),all44PriorRecordsAnd19CohortsAndLegacyCapacityPreserved=True,
    noMissingGlobalPercentileImputation=True,noLiveIndexMutation=True),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,records=44+count,cohorts=20,derivedSha256=sha(O/'index-derived.json'))))
