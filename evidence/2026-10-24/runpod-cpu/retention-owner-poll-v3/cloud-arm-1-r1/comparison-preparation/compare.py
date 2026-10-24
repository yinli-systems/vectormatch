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
    arm=x['arms'][0];arrival=run/'collection/raw-files/job/idle-arm/load/arrivals.csv'
    for f in [raw,success,arrival]:inputs[str(f)]=dict(bytes=f.stat().st_size,sha256=sha(f))
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
    observations.append(dict(arm=x['arm'],ownerPollMaximumParkNs=x['ownerPollMaximumParkNs'],serverDriverMaximumParkNs=x['serverDriverMaximumParkNs'],
        sourceCommit=x['sourceCommit'],releaseSha256=x['releaseSha256'],codeFingerprint=arm['config']['actualCodeSha256'],
        rawMetrics=arm['rawMetrics'],observedBacklogHighWater=arm['observedBacklogHighWater'],totalMaintenanceCycleNs=arm['totalMaintenanceCycleNs'],
        rpcKinds=arm['rpcKinds'],processTelemetry=x['telemetry'],cohorts=cohorts))
assert len({x['arm'] for x in observations})==len(observations)
assert len({(x['sourceCommit'],x['releaseSha256'],x['codeFingerprint']) for x in observations})==1
pairs=[]
by_arm={x['arm']:x for x in observations}
for baseline,treatment in [(1,2),(3,4)]:
    if baseline not in by_arm or treatment not in by_arm:continue
    old,new=by_arm[baseline],by_arm[treatment];assert (old['ownerPollMaximumParkNs'],new['ownerPollMaximumParkNs'])==(1000000,100000)
    pairs.append(dict(baselineArm=baseline,treatmentArm=treatment,
        p99ReductionFraction=1-new['rawMetrics']['allArrivalP99Ns']/old['rawMetrics']['allArrivalP99Ns'],
        maintenanceWallReductionFraction=1-new['totalMaintenanceCycleNs']/old['totalMaintenanceCycleNs'],
        arrivalWindowGoodputDelta=new['rawMetrics']['arrivalWindowGoodputPerSecond']-old['rawMetrics']['arrivalWindowGoodputPerSecond']))
assert all(Path(k).stat().st_size==v['bytes'] and sha(Path(k))==v['sha256'] for k,v in inputs.items())
a.output.mkdir(parents=True)
result=dict(schemaVersion=1,passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),observations=observations,pairs=pairs,
    inputs=inputs,sourceSha256=sha(Path(__file__)),allInputsUnchanged=True,capacityLimitProven=False,hardRealtimeProven=False,
    scope='Finite same-new-artifact owner polling observations at500orders/s; same-row timestamp partition, coarse observed-span CPU, no isolated network/server bottleneck or capacity claim.')
with (a.output/'COMPARISON.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(dict(passed=True,observations=[{k:x[k] for k in ['arm','ownerPollMaximumParkNs','rawMetrics','totalMaintenanceCycleNs']} for x in observations],pairs=pairs)))
