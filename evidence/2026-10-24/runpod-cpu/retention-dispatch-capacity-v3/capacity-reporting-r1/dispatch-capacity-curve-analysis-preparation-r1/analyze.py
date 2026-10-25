from pathlib import Path
import sys,json,csv,hashlib,math,datetime

R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';rates=list(map(int,sys.argv[1:]))
assert len(rates)>=2 and rates==[4000,6000,7000,7500,8000][:len(rates)]
O=B/f'dispatch-capacity-first-{len(rates)}-curve-analysis-r1';assert not O.exists()
inputs={};sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):inputs[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p));return json.loads(p.read_text())
def q(values,p):return sorted(values)[math.ceil(p*len(values))-1]if values else None
observations=[];lineages=set();settings=[]
for rate in rates:
    A=R/f'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-{rate}-r1'
    inv=read(A/'INVENTORY.json');closed=read(A/'CLOSED.json');assert closed['passed']and closed['inventorySha256']==sha(A/'INVENTORY.json')
    def archived(n):
        p=A/n;pin=inv['files'][n];assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256'];return read(p)
    root=archived('root-review/ROOT_REVIEW.json');raw=archived('root-review/RAW_AUDIT.json');ready=archived('root-review/READINESS_REVIEW.json')
    cfg=archived(f'root-review/materialized/attempt-{rate}/idle-arm/load/configuration.json')
    summary=archived(f'root-review/materialized/attempt-{rate}/idle-arm/load/load-result.json')
    push=read(B/f'dispatch-capacity-{rate}-private-proof-r1/PRIVATE_PUSH.json')
    diag=read(B/f'dispatch-capacity-{rate}-bottleneck-r1/DIAGNOSIS.json')
    recovery=read(B/f'dispatch-capacity-{rate}-cut-recovery-r1/RECOVERY.json')
    assert root['passed']and root['nativeControlPassed']and raw['passed']and ready['passed']and push['passed']and push['private']and push['allOriginalNativeAndRawEvidencePushed']
    assert push['archiveInventorySha256']==sha(A/'INVENTORY.json')and push['rootReviewSha256']==sha(A/'root-review/ROOT_REVIEW.json')
    assert push['rawAuditSha256']==sha(A/'root-review/RAW_AUDIT.json')and push['readinessReviewSha256']==sha(A/'root-review/READINESS_REVIEW.json')
    assert cfg['actualCodeSha256']==push['codeFingerprint']==raw['codeFingerprint']=='2b8d7594e03f8eeeef7aaf8e07db12c3bb585ba4ba67970d065c7174420fbf68'
    assert cfg['fineDispatchCapacityPreset']and cfg['dispatchOrderPolicy']=='ROTATING_CONTINUE'and cfg['arrivals']==rate*20 and cfg['ratePerSecond']==rate
    assert cfg['lineage']not in lineages;lineages.add(cfg['lineage'])
    fixed={k:cfg[k]for k in ('readWindow','eventFetchCount','batchCap','archiveChunkBytes','logicalWorkers','taskQueueCapacityPerWorker','physicalSessions','taskLifetimeNs','physicalOfferPermitNsFromDispatch','drainAdmissionNs','profileSha256','dispatchOrderPolicy','fineDispatchCapacityPreset')};settings.append(fixed)
    assert fixed['readWindow']==128 and fixed['eventFetchCount']==32 and fixed['batchCap']==4 and fixed['archiveChunkBytes']==6144 and fixed['logicalWorkers']==128 and fixed['taskQueueCapacityPerWorker']==64 and fixed['physicalSessions']==1
    csvpath=B/f'dispatch-capacity-{rate}-root-review-r1/materialized/attempt-{rate}/idle-arm/load/arrivals.csv'
    bodies=read(A/'ORIGINAL_SCOPE_INVENTORIES.json');pin=bodies['root-review']['files'][f'materialized/attempt-{rate}/idle-arm/load/arrivals.csv']
    assert csvpath.stat().st_size==pin['bytes']and sha(csvpath)==pin['sha256'];inputs[str(csvpath)]=dict(bytes=pin['bytes'],sha256=pin['sha256'])
    accepted=[];not_sent=0;within=0
    with csvpath.open()as stream:
        for index,row in enumerate(csv.DictReader(stream)):
            assert int(row['arrival_index'])==index and int(row['worker'])==index%128 and int(row['request_seq'])==1+index//128
            if row['status']=='NOT_SENT':not_sent+=1;assert int(row['admitted_physical_offers'])==0;continue
            assert row['status']=='APPLIED'and row['result_code']=='ACCEPTED'and row['reply_replayed']=='false'
            accepted.append(int(row['reply_completion_offset_ns'])-int(row['scheduled_offset_ns']))
            within+=int(int(row['reply_completion_offset_ns'])<=20*10**9)
    assert index+1==rate*20 and len(accepted)==root['confirmedAcceptedUniqueOrders']and not_sent==root['notSent']and within/20==root['arrivalWindowGoodputPerSecond']
    all_p99=q(accepted,.99)if len(accepted)==rate*20 else None
    assert all_p99==root['allArrivalP99Ns']and q(accepted,.99)==root['acceptedOrderConditionalP99Ns']
    assert root['serverRejected']==root['unknownObserved']==root['unknownFinal']==0
    finite=(root['windowConfirmationFraction']>=.99 and not_sent==0 and all_p99 is not None and all_p99<=10**9 and root['schedulerTimingValid'])
    assert finite==push['finiteProgressionPermitted']
    observations.append(dict(rate=rate,planned=rate*20,accepted=len(accepted),notSent=not_sent,rejected=0,observedUnknown=0,finalUnknown=0,
        goodput=within/20,windowConfirmationFraction=within/(rate*20),allArrivalAcceptedP50Ns=q(accepted,.5)if len(accepted)==rate*20 else None,
        allArrivalAcceptedP99Ns=all_p99,conditionalAcceptedP99Ns=q(accepted,.99),sampledBacklogHighWater=root['sampledBacklogHighWater'],
        perWorkerQueueHighWater=diag['maximumObservedQueueSizePerWorker'],afterPositiveOfferP99Ns=diag['afterFirstPositiveOfferReturnP99Ns'],
        drainNs=summary['lastKnownReplyDrainNs'],maintenanceCycles=diag['maintenanceCycles'],maintenanceWallNs=diag['maintenanceWallNs'],
        fullOfferedCutIntervals=recovery['fullOfferedEquivalentCutIntervals'],intervalsReachingZeroRecordedWaiting=recovery['intervalsReachingZeroRecordedWaiting'],
        finiteProgressionGateMet=finite,privateCommit=push['commit'],scheduledOriginUTC=cfg['scheduledOriginUTC']))
assert all(v==settings[0]for v in settings)
assert all(Path(n).stat().st_size==v['bytes']and sha(Path(n))==v['sha256']for n,v in inputs.items())
O.mkdir();report=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),observations=observations,
    fixedConfiguration=settings[0],sourceCommit='566dd2fa8b185caa54f3c1061fcdf0009bc3cfd0',codeFingerprint='2b8d7594e03f8eeeef7aaf8e07db12c3bb585ba4ba67970d065c7174420fbf68',
    allOriginalCsvBodiesBoundToCommittedCompressedScopeInventories=True,allPriorPrivateNativeReadinessProofsRequired=True,
    allInputBodiesUnchanged=True,inputs=inputs,sourceSha256=sha(Path(__file__)),
    scope='Fresh20s lineages,ROTATING_CONTINUE,fixed leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64. One existing CPU host/three JVMs/loopback UDP and one physical session. Finite progression gate and within-window cut recovery are not sustained capacity,independent-host network performance,statistical significance,hard realtime or100M proof. Global accepted percentiles remain null on loss.')
(O/'CURVE.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,observations=observations)))
