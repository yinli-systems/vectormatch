"""Independent finite-window descriptive comparison; stdlib only, no cloud actions.

Config: {"mode":"formal"|"two-arm-diagnostic", "arms":[
 {"arm":1,"collection":"relative/or/absolute/path","rootReview":"path"}, ...]}.
All paths resolve relative to the config. Outputs are CREATE_NEW, including failure.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import json
import math
import re
from pathlib import Path

RELEASE_SHA='c2df0427bea0cdd8575ee3130adf4ff4aa43c65fca0a5458ed0c7c8c1eea4676'
CONTROLLER_SHA='07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c'
PARK=(1000000,100000,1000000,100000)
INPUTS={}


def require(value, reason):
    if not value: raise ValueError(reason)


def digest(path):
    path=Path(path).resolve(); h=hashlib.sha256(); size=0
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):
            size+=len(block);require(size<=64*1024**2,'Individual comparison input exceeds64MiB')
            h.update(block)
    value={'bytes':size,'sha256':h.hexdigest()}
    if str(path) in INPUTS:require(INPUTS[str(path)]==value,'Comparison input changed')
    INPUTS[str(path)]=value;return value


def read_json(path):
    digest(path);return json.loads(Path(path).read_text())


def read_csv(path):
    digest(path)
    with Path(path).open(newline='') as f:
        rows=list(csv.DictReader(f))
    require(all(None not in r and all(v is not None for v in r.values()) for r in rows),'Malformed CSV width')
    return rows


def q(values, fraction):
    return sorted(values)[math.ceil(len(values)*fraction)-1] if values else None


def distribution(values):
    return {'count':len(values),'minNs':min(values) if values else None,'p50Ns':q(values,.5),
            'p99Ns':q(values,.99),'maxNs':max(values) if values else None}


def optional_int(value):return int(value) if value not in ('',None) else None


def arrival_metrics(rows,config):
    n=config['arrivals'];window_ns=round(config['windowSeconds']*1e9)
    require(len(rows)==n and [int(r['arrival_index']) for r in rows]==list(range(n)),'All planned arrivals in exact index order required')
    accepted=[];completed=[];predispatch=[];dispatch_offer=[];offer_reply=[];lateness=[];orders=set();identities=set();unknown=not_sent=rejects=within=0
    for i,r in enumerate(rows):
        scheduled=int(r['scheduled_offset_ns']);arrival=optional_int(r['arrival_offset_ns'])
        dispatch=optional_int(r['dispatch_offset_ns']);offer=optional_int(r['first_successful_offer_return_offset_ns'])
        end=optional_int(r['reply_completion_offset_ns'])
        require(scheduled==i*1000000000//config['ratePerSecond'],'Scheduled arrival differs from fixed rate')
        identity=(r['producer'],int(r['request_seq']));require(identity not in identities,'Duplicate producer/request identity');identities.add(identity)
        require(int(r['worker'])==i%config['logicalWorkers'],'Worker assignment differs')
        if arrival is not None:require(arrival>=scheduled,'Early arrival');lateness.append(arrival-scheduled)
        if dispatch is not None:require(dispatch>=scheduled,'Early dispatch');predispatch.append(dispatch-scheduled)
        if dispatch is not None and offer is not None:require(offer>=dispatch,'Successful offer precedes dispatch');dispatch_offer.append(offer-dispatch)
        if offer is not None and end is not None:require(end>=offer,'Reply precedes successful offer return');offer_reply.append(end-offer)
        unknown+=int(r['unknown_observed_offset_ns']!='' or r['status'].startswith('UNKNOWN'))
        not_sent+=int(r['status']=='NOT_SENT')
        if r['status']=='APPLIED':
            require(end is not None and end>=scheduled,'Applied reply lacks finite end');completed.append(end-scheduled)
            if r['result_code']=='ACCEPTED':
                order=int(r['order_id']);require(order not in orders,'Duplicate accepted order identity');orders.add(order)
                accepted.append(end-scheduled);within+=int(end<window_ns)
            else:rejects+=1
    all_accepted=len(accepted)==n and not unknown and not not_sent and not rejects and len(lateness)==n
    return {'arrivals':n,'confirmedAcceptedUniqueOrders':len(accepted),'completedReplies':len(completed),
        'notSent':not_sent,'unknownObservedOrFinal':unknown,'serverRejected':rejects,
        'acceptedWithinArrivalWindow':within,'arrivalWindowGoodputPerSecond':within/config['windowSeconds'],
        'allArrivalAcceptedOrderP99Ns':q(accepted,.99) if all_accepted else None,
        'acceptedConditionalLatency':distribution(accepted),'completedReplyConditionalLatency':distribution(completed),
        'scheduledToDispatch':distribution(predispatch),'dispatchToSuccessfulOfferReturn':distribution(dispatch_offer),'successfulOfferReturnToReply':distribution(offer_reply),
        'schedulerLateness':distribution(lateness),'schedulerLatenessOver20ms':sum(v>20000000 for v in lateness),
        'schedulerTimingValid':len(lateness)==n and all(v<=20000000 for v in lateness),
        'allArrivalP99Policy':'Finite distinct ACCEPTED order for every planned arrival; null on any notSent/unknown/reject/unreleased',
        'percentileMethod':'nearest rank ceil(p*N), scheduled arrival to reply completion; not batch-normalized'}


def require_success_metrics(metrics,summary):
    for key in ('notSent','unknownObservedOrFinal','serverRejected'):require(metrics[key]==0,'Nonzero CSV '+key)
    require(metrics['allArrivalAcceptedOrderP99Ns'] is not None,'All-arrival percentile is undefined')
    for computed,reported in [('confirmedAcceptedUniqueOrders','confirmedAcceptedUniqueOrders'),
            ('acceptedWithinArrivalWindow','acceptedOrdersInArrivalWindow'),('allArrivalAcceptedOrderP99Ns','allArrivalP99Ns'),
            ('schedulerLatenessOver20ms','schedulerLatenessOver20ms'),('schedulerTimingValid','schedulerTimingValid')]:
        require(metrics[computed]==summary[reported],'Raw CSV and source summary differ: '+reported)
    require(summary['unknownObserved']==summary['unknownFinal']==summary['serverAdmissionRejectedObserved']==summary['serverNotAttemptedObserved']==0,'Reported unknown/admission rejection/notattempted')
    require(metrics['schedulerTimingValid'],'Scheduler timing invalid; retain trial but no successful comparison')
    require(math.isclose(metrics['arrivalWindowGoodputPerSecond'],summary['arrivalWindowGoodputPerSecond'],rel_tol=1e-12),'Goodput differs')
    require(metrics['acceptedConditionalLatency']['p99Ns']==summary['acceptedOrderConditionalP99Ns'],'Conditional p99 differs')


def normalized_config(config):
    result=dict(config)
    for key in ('retentionIdleSelection','lineage','scheduledOriginUTC','scheduledOriginMonotonicNs'):result.pop(key)
    return result


def physical_frame_metrics(frames,arrivals,rpcs):
    members=collections.defaultdict(set)
    for row in arrivals:
        if row['correlation_id']!='':members[int(row['correlation_id'])].add(int(row['batch_index']))
    maintenance={int(row['correlation_id']) for row in rpcs}
    require(not set(members)&maintenance,'Business/maintenance correlation reused')
    require(len({int(row['correlation_id']) for row in frames})==len(frames),'Duplicate physical request correlation')
    require({int(row['correlation_id']) for row in frames}==set(members)|maintenance,'Physical request correlation coverage differs')
    batches=collections.Counter()
    for row in frames:
        correlation=int(row['correlation_id'])
        if correlation not in members:continue
        count=int(row['members']);require(members[correlation]==set(range(count)),'Business frame member indexes differ')
        batches[count]+=1
    require(sum(n*count for n,count in batches.items())==len(arrivals),'Business frames do not cover all planned commands')
    return {'uniqueRequests':len(frames),'businessFrames':sum(batches.values()),'maintenanceFrames':len(maintenance),
        'businessBatchSizeCounts':dict(sorted(batches.items())),'meanCommandsPerBusinessFrame':len(arrivals)/sum(batches.values()),
        'classification':'Disjoint original arrival and logical-maintenance correlation sets; members=1 alone is not a business discriminator'}


def validate_arm_set(arms,mode):
    require(mode in ('formal','two-arm-diagnostic'),'Explicit supported comparison mode required')
    require([v['arm'] for v in arms]==([1,2,3,4] if mode=='formal' else [1,2]),'Missing, duplicate or unordered arms; formal requires all4')


def validate_policy(policy,maximum,node):
    counts={'driver-shared':1,'archive-shared':2,'consensus':2,'service':2} if node>=0 else {'owner-driver-shared':1}
    require(policy['schema']=='retention-idle-actual-v2' and policy['node']==node and policy['selection']['maximumParkNs']==maximum,'Actual idle scope/selection differs')
    require(policy['instancesDistinct'] is True and policy['expectedConsumptionCounts']==policy['observedConsumptionCounts']==counts,'Actual idle consumption counts differ')
    entries=policy['instances'];require(len(entries)==sum(counts.values()) and {v['instanceOrdinal'] for v in entries}==set(range(1,len(entries)+1)),'Idle instance ordinals/number differ')
    for role,bound in counts.items():
        selected=[v for v in entries if v['role']==role]
        require({v['roleConsumptionOrdinal'] for v in selected}==set(range(1,bound+1)) and len(selected)==bound,'Per-role consumption ordinal differs')
        for value in selected:
            require(value['roleConsumptionBound']==bound and value['strategyClass']=='org.agrona.concurrent.BackoffIdleStrategy'
                and value['maximumSpins']==10 and value['maximumYields']==(5 if 'driver' in role else 20)
                and value['minimumParkNs']==1000 and value['maximumParkNs']==maximum,'Configured actual instance tuple differs')
    require(all(policy[k] is False for k in ('sleepDurationMeasured','hardRealtimeGuaranteed','runningAgentThreadCountIndependentlyObserved')),'Idle scope falsely promotes runtime observations')
    return {'node':node,'pid':policy['pid'],'factoryCreations':len(entries),'perRoleCreations':counts,
            'configuredMaximumParkNs':maximum,'actualSleepOrThreadAssignmentMeasured':False}


def cpu_window(samples,role,start,end):
    intervals=[];rejected=0;rss=[];threads=[];writes=[]
    for a,b in zip(samples,samples[1:]):
        t0,t1=a['monotonicNs'],b['monotonicNs']
        if t0<start or t1>end:continue
        ra=next((v for v in a['owned'] if v['role']==role),None);rb=next((v for v in b['owned'] if v['role']==role),None)
        if not ra or not rb or not ra.get('available') or not rb.get('available'):rejected+=1;continue
        if any(ra[k]!=rb[k] for k in ('pid','startTicks','commandSha256')):rejected+=1;continue
        hz=a['clockTicksPerSecond'];dt=t1-t0;ticks=rb['userTicks']+rb['systemTicks']-ra['userTicks']-ra['systemTicks']
        if hz!=b['clockTicksPerSecond'] or dt<=0 or ticks<0:rejected+=1;continue
        intervals.append({'startMonotonicNs':t0,'endMonotonicNs':t1,'cpuSeconds':ticks/hz})
        for v in (ra,rb):
            value=v.get('status',{}).get('VmRSSBytes')
            if value is not None:rss.append(value)
            value=v.get('status',{}).get('Threads')
            if value is not None:threads.append(value)
        wa=ra.get('io',{}).get('write_bytes');wb=rb.get('io',{}).get('write_bytes')
        if wa is not None and wb is not None and wb>=wa:writes.append(wb-wa)
    covered=sum(v['endMonotonicNs']-v['startMonotonicNs'] for v in intervals);cpu=sum(v['cpuSeconds'] for v in intervals)
    return {'role':role,'requestedStartMonotonicNs':start,'requestedEndMonotonicNs':end,'requestedSeconds':(end-start)/1e9,
        'coveredSeconds':covered/1e9,'coverageFraction':covered/(end-start) if end>start else None,
        'cpuSeconds':cpu if intervals else None,'meanOccupiedCoresOverCoveredIntervals':cpu/(covered/1e9) if covered else None,
        'intervals':intervals,'rejectedInteriorAdjacentIntervals':rejected,'maxSampledRssBytes':max(rss) if rss else None,
        'maxSampledThreads':max(threads) if threads else None,'kernelWriteBytesDelta':sum(writes) if writes else None,
        'kernelWriteIntervals':len(writes),'scope':'Per-process cumulative CPU tick deltas on adjacent complete interior samples, not per-thread/exclusive CPU or pure fsync; missing is null; no quota normalization'}


def utc_ns(value):
    match=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(?:Z|\+00:00)',value)
    require(match is not None,'Strict UTC timestamp required')
    seconds=int(datetime.datetime.strptime(match[1],'%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp())
    return seconds*1000000000+int((match[2] or '').ljust(9,'0'))


def clock_alignment(samples,config):
    origin_utc=utc_ns(config['scheduledOriginUTC']);origin_mono=config['scheduledOriginMonotonicNs']
    errors=[abs((utc_ns(s['atUtc'])-origin_utc)-(s['monotonicNs']-origin_mono)) for s in samples]
    return {'passed':bool(errors) and max(errors)<=100000000,'maximumUtcVersusMonotonicOffsetDifferenceNs':max(errors) if errors else None,
        'thresholdNs':100000000,'samples':len(errors),'scope':'Coarse same-host clock-domain consistency check; separate sample field reads, not exact capture-time calibration. CPU uses monotonic adjacent intervals.'}


def bound_receipt(path,root_review):
    value=digest(path)
    require(any(v==value for v in root_review['inputs'].values()),'Independent root review does not bind '+str(path))


def analyze_arm(spec,base):
    number=spec['arm'];maximum=PARK[number-1];root=(base/spec['collection']).resolve();review_path=(base/spec['rootReview']).resolve()
    # Read SUCCESS first. No partially collected arm is admitted or scanned.
    success=read_json(root/'SUCCESS.json');require(success['passed'] is True and success['arm']==number and success['allFailuresRetained'] is True,'Arm collection not successfully closed')
    review=read_json(review_path)
    require(review['passed'] is True and review['arm']==number and review['allFullOuterMembersVerified'] is True and review['allRawInputsUnchanged'] is True,'Full independent root review required')
    for rel in ('SUCCESS.json','raw/result.json','native/result.json','finalized/LOCAL_COLLECTION_COMPLETE.json'):bound_receipt(root/rel,review)
    closed=read_json(root/'root-controller-closed.json')
    require(closed['rootVerified'] is True and closed['allOwnedStopped'] is True and closed['controllerIdentityGone'] is True
        and closed['arm']==number and closed['maximumParkNs']==maximum and closed['frozenReleaseSha256']==RELEASE_SHA
        and closed['controllerSha256']==CONTROLLER_SHA,'Exact closed controller proof required')
    final=read_json(root/'finalized/LOCAL_COLLECTION_COMPLETE.json')
    require(final['passed'] is True and final['localFullMemberShaBytesModesOwnersEmptyDirsVerified'] is True
        and final['allClosedRoundRawFilesAndErrorReceiptsRetained'] is True and final['nestedFullVerificationPending'] is False,'Full closed-byte collection required')
    raw=read_json(root/'raw/result.json');native=read_json(root/'native/result.json')
    require(raw['passed'] is True and native['passed'] is True and raw['releaseSha256']==native['releaseSha256']==RELEASE_SHA,'Native/raw source gate differs')
    for rel,value in raw['inputs'].items():
        path=(root/'collection'/rel).resolve();require(path.is_relative_to((root/'collection').resolve()),'Unsafe raw input path')
        require(digest(path)==value,'Previously audited raw input changed: '+rel)
    job=root/'collection/raw-files/job';arm=job/'idle-arm';load=arm/'load'
    release_path=job/'release.json';release=read_json(release_path);require(digest(release_path)['sha256']==RELEASE_SHA,'Ready release bytes differ')
    jars={Path(name).name:value for name,value in release['artifacts'].items()}
    require(len(jars)==4,'Exactly4 frozen runtime JARs required')
    for name,value in jars.items():require(digest(root/'native/actual-runtime-artifacts'/name)==value,'Actual runtime JAR differs')
    config=read_json(load/'configuration.json');summary=read_json(load/'load-result.json');registration=read_json(arm/'registration.json')
    require(config['actualCodeSha256']==registration['codeSha256']==release['codeFingerprint']
        and config['profileSha256']==registration['profileSha256']==release['profileFingerprint'],'Actual source/profile fingerprint differs')
    require(config['retentionIdleSelection']==summary['retentionIdleSelection']==registration['retentionIdleSelection']
        and config['retentionIdleSelection']['maximumParkNs']==maximum,'Selected requested park differs')
    require(config['arrivals']==6400 and config['ratePerSecond']==500 and config['windowSeconds']==12.8
        and config['readWindow']==8 and config['batchCap']==4 and config['archiveChunkBytes']==6144 and config['eventFetchCount']==16
        and config['logicalWorkers']==128 and config['taskQueueCapacityPerWorker']==64 and config['physicalSessions']==config['sharedMediaDrivers']==1
        and config['arrivalClockPausesForMaintenance'] is False and registration['appointedLeader']==0 and registration['sync']==2 and registration['ports']==42000,'Fixed configuration differs')
    arrival_rows=read_csv(load/'arrivals.csv');metrics=arrival_metrics(arrival_rows,config);require_success_metrics(metrics,summary)
    require(metrics['allArrivalAcceptedOrderP99Ns']==review['arms'][0]['allArrivalP99Ns'],'Independent root percentile differs')
    cycles=[]
    for cycle in (1,2,3):
        path=load/('maintenance/cycle-%d.verified.txt'%cycle);digest(path)
        fields=dict(s.split('=',1) for s in path.read_text().splitlines() if s)
        require(fields['forceAndReadbackBeforeBothAcks']=='true' and int(fields['readWindow'])==8,'Cycle durable fences/readwindow differ')
        start=int(fields['cycleStartedMonotonicNs']);end=int(fields['cycleEndedMonotonicNs']);require(end>=start,'Negative cycle duration')
        cycles.append({'cycle':cycle,'startMonotonicNs':start,'endMonotonicNs':end,'wallNs':end-start,
            'logicalRpcCount':int(fields['logicalRpcCountAtEnd'])-int(fields['logicalRpcCountAtStart'])})
    rpc=read_csv(load/'maintenance/logical-rpc-timings.csv');phases=[]
    for generation in range(1,7):
        selected=[r for r in rpc if int(r['read_phase_generation'])==generation]
        require(selected and all(r['completed']=='true' for r in selected),'Missing/incomplete read phase')
        phases.append({'generation':generation,'kind':selected[0]['kind'],'logicalRpcs':len(selected),
            'reservationToCoordinatorRecordedEndWallNs':max(int(r['end_monotonic_ns']) for r in selected)-min(int(r['start_monotonic_ns']) for r in selected),
            'observedLowerBoundNotExactLeaseLifetime':True})
    owner=read_json(load/'owner-after-close.json')
    policies=[validate_policy(read_json(arm/('node-%d/idle-observations/idle-000.actual.json'%n)),maximum,n) for n in range(3)]
    policies.append(validate_policy(owner['transportObservation']['retentionIdlePolicy'],maximum,-1))
    require(sum(v['factoryCreations'] for v in policies)==22,'Expected22 uniquely scoped actual factory creations')
    frame_metrics=physical_frame_metrics(read_csv(load/'physical-request-index.csv'),arrival_rows,rpc)
    frame_metrics['sourcePhysicalOfferTapeCounts']={k:summary['physicalOfferTape'][k] for k in ('physicalOfferAttempts','successfulPhysicalAdmissions','negativePhysicalOffers','recordedReplies')}
    digest(job/'owned-cpu-rss-io-1hz.jsonl');samples=[json.loads(s) for s in (job/'owned-cpu-rss-io-1hz.jsonl').read_text().splitlines()]
    origin=config['scheduledOriginMonotonicNs'];end=origin+round(config['windowSeconds']*1e9)
    alignment=clock_alignment(samples,config)
    cpu=[cpu_window(samples,role,origin,end) for role in ['window-8-node-0','window-8-node-1','window-8-node-2','pilot-parent']] if alignment['passed'] else None
    available=[s['monotonicNs'] for s in samples if any(v['role']=='pilot-parent' and v.get('available') for v in s['owned'])]
    parent_span=cpu_window(samples,'pilot-parent',min(available),max(available)) if len(available)>=2 else None
    return {'arm':number,'maximumParkNs':maximum,'lineage':config['lineage'],'config':config,'registration':registration,
        'jars':jars,'releaseSha256':RELEASE_SHA,'metrics':metrics,'cycles':cycles,'maintenanceCycleWallNs':sum(v['wallNs'] for v in cycles),
        'readPhases':phases,'overlappingLogicalRpcElapsedSumNsNotWallTime':sum(int(r['elapsed_ns']) for r in rpc),
        'physicalFrames':frame_metrics,
        'idleFactoryCreationObservations':policies,'uniqueActualFactoryCreations':22,
        'warningReports':[v['logClassification'] for v in raw['arms'][0]['nodeLogs']],
        'warningsRetained':sum(v['logClassification']['warningPairCount'] for v in raw['arms'][0]['nodeLogs']),
        'cpuSamplingClockAlignment':alignment,'cpuOverArrivalExposure':cpu,'parentEntireObservedSpanIncludingSetupDrainAndClose':parent_span,
        'rawFiniteClassificationPreserved':raw['arms'][0]['classification'],'rootReviewSha256':digest(review_path)['sha256']}


def compare(config,path):
    validate_arm_set(config['arms'],config['mode']);arms=[analyze_arm(s,path.parent) for s in config['arms']]
    require(len({a['lineage'] for a in arms})==len(arms),'Each arm needs a fresh distinct lineage')
    baseline=normalized_config(arms[0]['config'])
    baseline_reg={k:v for k,v in arms[0]['registration'].items() if k not in ('lineage','retentionIdleSelection')}
    for arm in arms:
        require(normalized_config(arm['config'])==baseline,'Configuration changed beyond park/lineage/origin')
        require({k:v for k,v in arm['registration'].items() if k not in ('lineage','retentionIdleSelection')}==baseline_reg,'Registration changed beyond park/lineage')
        require(arm['jars']==arms[0]['jars'],'Artifacts differ between arms')
    pairs=[]
    for index in range(0,len(arms),2):
        a,b=arms[index:index+2];pairs.append({'arms':[a['arm'],b['arm']],
            'p99Ratio100usOver1ms':b['metrics']['allArrivalAcceptedOrderP99Ns']/a['metrics']['allArrivalAcceptedOrderP99Ns'],
            'maintenanceWallRatio100usOver1ms':b['maintenanceCycleWallNs']/a['maintenanceCycleWallNs'],
            'scope':'Finite paired descriptive ratio; not statistical significance, sustained capacity or unique causal attribution'})
    for name,value in list(INPUTS.items()):require(digest(Path(name))==value,'Input changed before publication')
    return {'passed':True,'mode':config['mode'],'formalFourArmComparisonComplete':config['mode']=='formal','arms':arms,'pairedDescriptiveRatios':pairs,
        'limitations':['6400 arrivals/12.8s and three maintenance cycles per arm; no sustained capacity or SLA claim.',
            'All-arrival scheduled-to-accepted p99 differs from conditional accepted/completed-reply p99; undefined when any arrival is missing/rejected/unknown.',
            'Overlapping per-RPC elapsed sums are not maintenance wall time. Phase spans are lower-bound observations of lease lifetime.',
            'Idle factory creations/tuples are observed; sleep duration and private runner-thread assignment are not measured.',
            'CPU tick counters are coarse sampled process aggregates. Each role keeps its own covered intervals; parent entire-span includes setup/drain/close. No uniform CPU sum, pure fsync claim, quota normalization or unique cause.',
            'Qualified warnings and existing failed source/native wrapper attempts remain retained; this derived comparison never changes original gates.'],
        'inputs':dict(INPUTS),'scriptSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    require(not args.output.exists(),'Output already exists')
    try:result=compare(read_json(args.config),args.config.resolve())
    except Exception as error:
        result={'passed':False,'errorType':type(error).__name__,'error':str(error),'inputs':dict(INPUTS),'noOriginalGateChanged':True}
        with args.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
        raise
    with args.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'passed':True,'mode':result['mode'],'arms':len(result['arms']),'output':str(args.output)}))


if __name__=='__main__':main()
