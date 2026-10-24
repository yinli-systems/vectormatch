"""Derived same-cohort latency partition; never launches a benchmark."""
from pathlib import Path
import argparse, csv, datetime, hashlib, json, math
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--run',type=Path,action='append',required=True)
p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
inputs={};observations=[]
for run in a.run:
    run=run.resolve();raw=run/'raw/result.json';success=run/'SUCCESS.json'
    x=read(raw);assert x['passed'] and read(success)['passed'] and len(x['arms'])==1
    assert x['strictSchedulerTimingAdmission'] and not x['localFunctionalDiagnosticOptIn']
    arm=x['arms'][0]
    assert x['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6' and x['releaseSha256']=='35652d5dd4175e2f7fff500147ce084a41d9ae7a3c6951b9c67374b780ec05d0'
    assert arm['config']['actualCodeSha256']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
    assert x['ownerPollMaximumParkNs']==1000000 and x['serverDriverMaximumParkNs']==100000 and x['eventFetchCount']==32 and x['readWindow']==(8,32,8,32)[x['arm']-1]
    root_path=run.parent/('current-read32-arm-%d-root-review-r1/ROOT_REVIEW.json'%x['arm']);root=read(root_path)
    assert root['passed'] and root['arm']==x['arm'] and root['allFullOuterMembersVerified'] and root['allRawInputsUnchanged'] and root['rawAuditSha256']==sha(raw)
    assert root['sameNewArtifactFunctionalQualified'] and root['allOriginalRawCanonicalAndThreeSnapshotsVerified']
    assert root['arms'][0]['allArrivalP99Ns']==arm['rawMetrics']['allArrivalP99Ns'] and root['arms'][0]['maintenanceCycleWallNs']==arm['totalMaintenanceCycleNs']
    plan_path=run/'collection/raw-files/job/idle-arm/load/admission-plan.json';plan=read(plan_path)
    assert plan['requestedReadWindow']==x['readWindow'] and plan['maxReadOnlyInFlight']==32 and plan['commonReadWindow32Envelope'] is True
    assert (arm['config']['arrivals'],arm['config']['ratePerSecond'],arm['config']['batchCap'],arm['config']['archiveChunkBytes'],arm['config']['eventFetchCount'],arm['config']['physicalSessions'])==(33792,500,4,6144,32,1)
    inputs[str(plan_path)]=dict(bytes=plan_path.stat().st_size,sha256=sha(plan_path))
    arrival=run/'collection/raw-files/job/idle-arm/load/arrivals.csv'
    for f in [raw,success,arrival,root_path]:inputs[str(f)]=dict(bytes=f.stat().st_size,sha256=sha(f))
    with arrival.open() as f:rows=list(csv.DictReader(f))
    assert len(rows)==33792 and all(r['status']=='APPLIED' and r['result_code']=='ACCEPTED' and r['reply_replayed']=='false' for r in rows)
    stamps=['scheduled_offset_ns','arrival_offset_ns','dispatch_offset_ns','submit_offset_ns','first_wire_offer_call_offset_ns','first_successful_offer_return_offset_ns','reply_completion_offset_ns']
    labels=['schedulerRelease','arrivalToDispatchIncludingQueueAndMaintenance','dispatchToSubmit','submitToFirstOfferCall','firstOfferCallToSuccessfulReturn','successfulOfferReturnToReply']
    latency=lambda r:int(r[stamps[-1]])-int(r[stamps[0]])
    ranked=sorted(rows,key=latency,reverse=True);p99=sorted(map(latency,rows))[math.ceil(.99*len(rows))-1]
    assert p99==arm['rawMetrics']['allArrivalP99Ns']
    cohorts=[]
    for n in [64,math.ceil(.01*len(rows))]:
        cohort=ranked[:n];total=sum(map(latency,cohort));parts={label:sum(int(r[right])-int(r[left]) for r in cohort) for left,right,label in zip(stamps,stamps[1:],labels)}
        assert sum(parts.values())==total
        negative={label:sum(int(r[right])<int(r[left]) for r in cohort) for left,right,label in zip(stamps,stamps[1:],labels)}
        before=sum(int(r['dispatch_offset_ns'])-int(r['scheduled_offset_ns']) for r in cohort)
        overlap=sum(max(0,min(int(r['dispatch_offset_ns']),c['endOffsetNs'])-max(int(r['arrival_offset_ns']),c['startOffsetNs'])) for r in cohort for c in arm['cycles'])
        cohorts.append(dict(sameSlowestArrivalCount=n,sumScheduledToReplyNs=total,componentSumNs=parts,negativeComponentRows=negative,
            beforeDispatchShare=before/total,queueIntervalOverlapWithMaintenanceNs=overlap,overlapDoesNotAloneProveCausation=True))
    observations.append(dict(arm=x['arm'],readWindow=x['readWindow'],eventFetchCount=x['eventFetchCount'],ownerPollMaximumParkNs=x['ownerPollMaximumParkNs'],serverDriverMaximumParkNs=x['serverDriverMaximumParkNs'],
        sourceCommit=x['sourceCommit'],releaseSha256=x['releaseSha256'],codeFingerprint=arm['config']['actualCodeSha256'],
        rawMetrics=arm['rawMetrics'],observedBacklogHighWater=arm['observedBacklogHighWater'],totalMaintenanceCycleNs=arm['totalMaintenanceCycleNs'],
        rpcKinds=arm['rpcKinds'],processTelemetry=x['telemetry'],commonPlanWithoutSelectedWindow={k:v for k,v in plan.items()if k!='requestedReadWindow'},cohorts=cohorts))
assert len(observations)in(2,4) and {x['arm']for x in observations}==set(range(1,len(observations)+1))
assert len({x['arm'] for x in observations})==len(observations)
assert len({(x['sourceCommit'],x['releaseSha256'],x['codeFingerprint']) for x in observations})==1
assert all(x['commonPlanWithoutSelectedWindow']==observations[0]['commonPlanWithoutSelectedWindow']for x in observations)
pairs=[]
by_arm={x['arm']:x for x in observations}
for baseline,treatment in [(1,2),(3,4)]:
    if baseline not in by_arm or treatment not in by_arm:continue
    old,new=by_arm[baseline],by_arm[treatment];assert (old['ownerPollMaximumParkNs'],new['ownerPollMaximumParkNs'])==(1000000,1000000) and (old['eventFetchCount'],new['eventFetchCount'])==(32,32) and (old['readWindow'],new['readWindow'])==(8,32)
    pairs.append(dict(baselineArm=baseline,treatmentArm=treatment,
        p99ReductionFraction=1-new['rawMetrics']['allArrivalP99Ns']/old['rawMetrics']['allArrivalP99Ns'],
        maintenanceWallReductionFraction=1-new['totalMaintenanceCycleNs']/old['totalMaintenanceCycleNs'],
        arrivalWindowGoodputDelta=new['rawMetrics']['arrivalWindowGoodputPerSecond']-old['rawMetrics']['arrivalWindowGoodputPerSecond']))
assert all(Path(k).stat().st_size==v['bytes'] and sha(Path(k))==v['sha256'] for k,v in inputs.items())
a.output.mkdir(parents=True)
result=dict(schemaVersion=1,passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),observations=observations,pairs=pairs,
    inputs=inputs,sourceSha256=sha(Path(__file__)),allInputsUnchanged=True,capacityLimitProven=False,hardRealtimeProven=False,
    scope='Finite same-new-artifact fixedpage32 read-window8/32 observations at500orders/s; same-row timestamp partition, no isolated network/server/disk bottleneck or capacity claim.')
with (a.output/'COMPARISON.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(dict(passed=True,observations=[{k:x[k] for k in ['arm','readWindow','eventFetchCount','ownerPollMaximumParkNs','rawMetrics','totalMaintenanceCycleNs']} for x in observations],pairs=pairs)))
