"""Fixed20000@1000 read32/128 common128 cohort; full outcomes and strict timing required."""
from cpu_read_window32_abab import *
def validate_registration(release, cap, registration):
    require(registration['arrivals'] == 20000 and registration['rate'] == 1000
            and registration['batchCap'] == 4 and registration['archiveChunkBytes'] == 6144 and registration['readWindow'] == cap
            and registration['eventFetchCount']==32 and registration.get('commonReadWindow128Envelope') is True and registration.get('commonEventFetchEnvelope',False) is False and registration['commonChunkEnvelope'] is False and registration['commonReadWindowEnvelope'] is True and registration['appointedLeader'] == 0
            and registration['sync'] == 2 and registration['profileSha256'] == release['profileFingerprint']
            and registration['codeSha256'] == release['codeFingerprint'], 'Actual arm configuration/code/profile differs')
    require(registration.get('maintainedCapacityPreset') is False and registration.get('windowSeconds')==20 and registration.get('scope')=='LOCAL_THREE_JVM_READ128_CAPACITY_EXPERIMENT' and registration.get('preloadWarmupMillis')==5000,'Explicit finite capacity preset registration missing')
    require(registration.get('retentionIdleSelection') == selection(), 'Actual arm idle selection differs')
    require(registration.get('ownerPollSelection') == expected_owner_selection(selected_owner_park_ns()), 'Actual explicit owner selection differs')
    require(type(registration['ports']) is int and registration['ports'] == FIXED_PORTS,
            'Observed finite loopback port range differs')
    require(isinstance(registration['lineage'], str) and registration['lineage'].startswith('capacity-pilot-')
            and 1 <= len(registration['lineage']) <= 64, 'Fresh finite arm lineage differs')
def validate_long_summary(summary,cap):
    require(summary['scheduledArrivals']==summary['releasedArrivals']==20000 and summary['ratePerSecond']==1000 and summary['batchCap']==4 and summary['archiveChunkBytes']==6144 and summary['readWindow']==cap and summary.get('commonReadWindow128Envelope')is True and summary.get('maintainedCapacityPreset',False)is False,'Exact maintained1000/s source required')
    require(summary['arrivalClockPausedForMaintenance']is False and summary['schedulerTimingValid']is True and summary['schedulerLatenessOver20ms']==0,'Strict source scheduler gate; keep invalid attempts')
    require(summary['unknownObserved']==summary['unknownFinal']==summary['duplicateOrOutOfRangeAcceptedOrderIds']==0 and 3<=summary['maintenanceCycles']<=7,'Known outcomes and bounded maintenance required')
    require(all(type(summary[k])is int and 0<=summary[k]<=20000 for k in ['completedLogicalReplies','notSent','confirmedAcceptedUniqueOrders','serverRejected']),'Outcome counts must be nonnegative bounded integers')
    require(summary['completedLogicalReplies']+summary['notSent']==20000 and summary['confirmedAcceptedUniqueOrders']+summary['serverRejected']==summary['completedLogicalReplies'],'Complete original outcome partition required')
    if summary['notSent']or summary['serverRejected']:require(summary['allArrivalP99Ns']is None,'All-arrival accepted p99 must remain null on rejection/loss')
    return True

def validate_selected_page_observations(release,registration,configuration,summary,plan,completion,functional):
    for label,value in [('registration',registration),('configuration',configuration),('summary',summary),('plan',plan),('functional',functional)]:
        require(value.get('eventFetchCount')==32 and value.get('commonReadWindow128Envelope') is True and value.get('commonEventFetchEnvelope',False) is False,'Actual fixedpage32/common32 selection differs: '+label)
        require(value.get('readWindow',value.get('requestedReadWindow'))==selected_read_window(),'Actual selected read window differs: '+label)
    for value in [configuration,summary,plan]:require(value.get('batchCap')==4 and value.get('archiveChunkBytes')==6144,'Actual fixed cap4/chunk6144 differs')
    require(plan==selected_plan(release) and summary['maintenanceRpcMetrics'].get('eventFetchCount')==32
        and summary['maintenanceRpcMetrics'].get('readWindow')==selected_read_window()
        and summary['maintenanceRpcMetrics'].get('commonReadWindow128Envelope') is True,'Actual selected Plan/coordinator differs')
    return True
def validate_result(base, registry, release):
    registry.discover()
    require(set(registry.registrations)=={selected_read_window()}, 'One actual long-cut arm registration required')
    require(len(registry.records) == 4 and {r['role'] for r in registry.records.values()} == {'pilot-parent'} |
            {'window-%d-node-%d' % (c, n) for c in WINDOWS for n in range(3)}, 'Three node identities plus parent required')
    result = json_bounded(base, PAIR / 'completion.json')
    require(result['passed'] is True and result['commonReadWindow128Envelope'] is True and result['offeredRate']==1000 and result['preloadWarmupMillis']==5000 and result['readWindow']==selected_read_window() and result['eventFetchCount']==32,'New finite capacity completion differs')
    arms = []
    for cap in WINDOWS:
        root = PAIR
        completion = json_bounded(base, root / 'completion.json')
        stop = json_bounded(base, root / 'owned-stop.json')
        functional = json_bounded(base, root / 'capacity-correctness-result.json')
        artifact_inventory = json_bounded(base, root / 'artifact-inventory.json')
        require(artifact_inventory['codeFingerprint'] == release['codeFingerprint']
                and {row['path'] for row in artifact_inventory['actualFiles']} == set(release['nodeClassPath']),
                'Actual loaded class-source closure/code fingerprint differs')
        for artifact in artifact_inventory['actualFiles']:
            frozen = release['artifacts'][artifact['path']]
            require(artifact['bytes'] == frozen['bytes'] and artifact['sha256'] == frozen['sha256'],
                    'Actual loaded JAR bytes differ from frozen release')
        actual_plan = json_bounded(base, root / 'load/admission-plan.json')
        require(actual_plan == selected_plan(release), 'Actual codec-derived plan differs from pre-registered arm bound')
        require(completion['passed'] is True and completion['allOwnedStopped'] is True
                and completion['fixedLeader'] == 0 and stop['allOwnedStopped'] is True
                and functional['passed'] is True and functional['noCapacityPromotion'] is True,
                'Functional proof or Java owned-clean-stop receipt failed')
        idle_actual = dict(validate_idle_artifacts(base,root,registry,selected_park_ns(),selected_window=selected_read_window()))
        idle_actual['historicalValidatorScope'] = idle_actual.pop('scope')
        idle_actual['scope'] = 'Actual node and owner MediaDriver strategies only; load-owner polling is attested separately'
        require(functional.get('eventFetchCount')==selected_event_page() and functional.get('commonReadWindow128Envelope') is True and functional.get('commonEventFetchEnvelope',False) is False, 'Functional selected event page differs')
        summary = functional['actualSourceSummary']
        require(summary.get('retentionIdleSelection') == selection(), 'Summary idle selection missing/drifted')
        validate_long_summary(summary, cap)
        require(summary.get('eventFetchCount')==selected_event_page() and summary.get('commonReadWindow128Envelope') is True and summary.get('commonEventFetchEnvelope',False) is False
            and summary['maintenanceRpcMetrics'].get('eventFetchCount')==selected_event_page(), 'Summary/coordinator actual selected page differs')
        require(summary['maintenanceRpcMetrics']['readWindow'] == cap
                and summary['physicalOfferTape']['readWindow'] == cap
                and summary['physicalOfferTape']['readBusinessControlPhaseExclusionEnforced'] is True
                and 1 <= summary['physicalOfferTape']['readOnlyRawRegistryHighWater'] <= cap, 'Runtime selected read-window/tape bound differs')
        observations = json_bounded(base, root / 'load/transport-observations.json')
        require(isinstance(observations, list) and observations, 'Actual load transport observations required')
        previous_bounds = None
        previous_associations = -1
        initial_term = observations[0]['leadershipTermId']
        require(type(initial_term) is int and initial_term == 0, 'Actual initial leadership term required')
        for sample in observations:
            require(sample['archiveChunkBytes'] == 6144, 'Actual requested archive chunk differs')
            bounds = sample['actualEgressBounds']
            actual_images = validate_egress(bounds)
            if previous_bounds is not None:
                validate_egress_progress(previous_bounds, bounds)
            previous_bounds = bounds
            require(bounds['replyHeaderImageAssociations'] >= previous_associations, 'Actual Header association counter regressed')
            previous_associations = bounds['replyHeaderImageAssociations']
            require(sample['leadershipTermId'] == initial_term, 'Same leader reelected with a changed leadership term invalidates stationary arm')
            require(sample['leaderMemberId'] == 0 and sample['profileSha256'] == release['profileFingerprint']
                    and sample['lineageId'] == registry.registrations[cap]['lineage']
                    and sample['maintenanceEnabled'] is True and sample['mtuLength'] == 1248,
                    'Actual load leader/profile/maintenance/MTU differs')
            require(all(event['leaderMemberId'] == 0 and event['leadershipTermId'] == initial_term for event in sample['newLeaderEvents']),
                    'Observed leadership member/term change invalidates fixed leader sample')
        require(previous_associations > 0, 'Final actual egress Header associations missing')
        final_egress = functional['actualEgressBounds']
        require(max(image['largestObservedApplicationReplyBytes'] for image in final_egress['images']) <= actual_plan['largestReplyBytes'], 'Actual observed reply exceeds prospective codec-derived upper bound')
        require(validate_egress_progress(previous_bounds, final_egress)
                and final_egress['replyHeaderImageAssociations'] >= previous_associations
                and final_egress['replyHeaderImageAssociations'] == summary['physicalOfferTape']['recordedReplies']
                and final_egress['actualImageObservations'] >= 2, 'Terminal actual Image/raw reply association closure differs')
        original_summary=json_bounded(base,root/'load/load-result.json')
        require(original_summary==summary, 'Functional/source original summary differs')
        parent=next(row['identity']for row in registry.records.values()if row['role']=='pilot-parent')
        nodes={member:next(row['identity']for row in registry.records.values()if row['role']=='window-%d-node-%d'%(selected_read_window(),member))for member in (0,1,2)}
        configuration=json_bounded(base,root/'load/configuration.json')
        warm=json_bounded(base,root/'preload-warmup.json');require(warm['requestedMillis']==5000 and warm['outsideArrivalWindow']is True and warm['noSyntheticOrdersDuringWarmup']is True and warm['endedMonotonicNs']-warm['startedMonotonicNs']>=5000000000 and warm['endedMonotonicNs']<configuration['scheduledOriginMonotonicNs'],'Actual equal5second pre-load warm-up differs')
        validate_selected_page_observations(release,registry.registrations[cap],configuration,original_summary,actual_plan,completion,functional)
        owner_actual=validate_owner_bundle(registration=registry.registrations[cap],
            configuration=configuration,summary=original_summary,
            before=json_bounded(base,root/'load/owner-before-close.json'),after=json_bounded(base,root/'load/owner-after-close.json'),
            parent=parent,nodes=nodes,expected_owner_cap=selected_owner_park_ns(),expected_parent_arguments=parent_argv(release),
            expected_node_arguments={member:node_argv(release,cap,member,registry.registrations[cap])for member in (0,1,2)},
            node_idle_actuals={member:json_bounded(base,root/('node-%d/idle-observations/idle-000.actual.json'%member))for member in (0,1,2)},
            parent_idle_actuals=[sample['retentionIdlePolicy']for sample in observations]+[summary['physicalOfferTape']['lastActualTransportObservation']['retentionIdlePolicy']])
        final_position = json_bounded(base, root / 'final-position.json')
        require(functional['allThreeSnapshotLogsMatched'] is True and final_position['combinedSha256'] == functional['finalCombinedSha256'],
                'Functional final all-three checkpoint hash binding differs')
        log_reports = []
        for member in range(3):
            log = root / ('node-%d.log' % member)
            require(log.stat().st_size <= MAX_LOG, 'Stopped node log cap')
            original_log = log.read_bytes()
            text = original_log.decode('utf8', 'strict')
            role = 'window-%d-node-%d' % (cap, member)
            node_identity = next(row['identity'] for row in registry.records.values() if row['role'] == role)
            require('VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s' % (
                    member, node_identity['pid'], release['profileFingerprint'], registry.registrations[cap]['lineage'],
                    release['codeFingerprint']) in text and 'preparedArchiveCacheEnabled=true' in text,
                    'Actual node startup log identity/profile/code/prepared-cache differs')
            log_reports.append(classify_node_log(original_log, node=member, pid=node_identity['pid'],
                profile=release['profileFingerprint'], lineage=registry.registrations[cap]['lineage'],
                code=release['codeFingerprint'], final_hash=final_position['combinedSha256'],
                idle_actual=json_bounded(base, root / ('node-%d/idle-observations/idle-000.actual.json' % member))))
            if member == 0:
                require('VECTOR_V3_ROLE role=LEADER' in text, 'Actual node0 leader role was not observed')
            # Follower roles during clean shutdown are outside the load window. The owner
            # transport's initial/final observations and all onNewLeader callbacks gate it.
        arms.append({'batchCap': 4, 'archiveChunkBytes': 6144, 'serverDriverMaximumParkNs': selected_park_ns(), 'ownerPollMaximumParkNs': selected_owner_park_ns(), 'eventFetchCount':selected_event_page(),'readWindow':selected_read_window(),'commonReadWindow128Envelope':True,'commonEventFetchEnvelope':False, 'idleAttestation': idle_actual, 'ownerPollAttestation': owner_actual, 'nodeLogClassifications': log_reports, 'retainedPostCheckpointEosWarningPairs': sum(r['warningPairCount'] for r in log_reports), 'completion': completion, 'functional': functional})
    return {'passed': True, 'arms': arms, 'functionalPilotOnly': True, 'capacityOrEnduranceProven': False}

# Exact original idle evidence reconciliation, with only this cohort role selector extended.
from idle_attestation import validate_actual
def validate_idle_artifacts(base,root,registry,maximum,*,selected_window=8):
    """Closed-only read of actual startup files/logs and owner observations."""
    require(type(selected_window)is int and selected_window in (32,128),'Explicit new cohort read32|128 idle registry window required')
    expected_roles={'pilot-parent'}|{'window-%d-node-%d'%(selected_window,node)for node in range(3)}
    records=list(registry.records.values());roles=[row.get('role')for row in records]
    require(len(records)==4 and len(set(roles))==4 and set(roles)==expected_roles,'Exact unique selected-window three-node plus parent role registry required')
    identities=[row.get('identity')for row in records]
    require(all(isinstance(row,dict)and type(row.get('pid'))is int and row['pid']>1 for row in identities)
            and len({row['pid']for row in identities})==4,'Idle registry requires four distinct exact process identities')
    root = Path(root)
    reports = []
    for node in range(3):
        identity = next(row['identity'] for row in registry.records.values()
                        if row['role']=='window-%d-node-%d'%(selected_window,node))
        folder = root / ('node-%d/idle-observations' % node)
        base.no_links(folder)
        # This fresh, non-restarting arm expects one launch, retaining both intent and actual.
        require({p.name for p in folder.iterdir()} == {'idle-000.intent.json', 'idle-000.actual.json'},
                'Fresh single-launch idle evidence closure differs')
        intent_path, actual_path = folder / 'idle-000.intent.json', folder / 'idle-000.actual.json'
        for path in [intent_path, actual_path]:
            base.no_links(path)
            require(path.is_file() and path.stat().st_size <= 1024**2, 'Idle evidence file size/type cap')
        intent, actual = json.loads(intent_path.read_text()), json.loads(actual_path.read_text())
        require(set(intent) == {'schema', 'slot', 'node', 'pid', 'atUTC', 'selection'}
                and intent['schema'] == 'retention-idle-startup-intent-v1' and intent['slot'] == 0
                and intent['node'] == node and intent['pid'] == identity['pid']
                and intent['selection'] == selection(maximum), 'Reserved idle intent binding differs')
        report = validate_actual(actual, maximum, identity['pid'], node)
        lines = (root / ('node-%d.log' % node)).read_text().splitlines()
        logged = [json.loads(line.split('VECTOR_V3_IDLE_ATTESTATION ', 1)[1])
                  for line in lines if line.startswith('VECTOR_V3_IDLE_ATTESTATION ')]
        require(logged == [actual], 'Actual startup file/log idle evidence mismatch')
        reports.append(dict(report, node=node))
    parent = next(row['identity'] for row in registry.records.values() if row['role'] == 'pilot-parent')
    load = root / 'load'
    for name in ['configuration.json', 'load-result.json']:
        require(json.loads((load / name).read_text())['retentionIdleSelection'] == selection(maximum),
                'Load configured/summary idle selection mismatch')
    samples = json.loads((load / 'transport-observations.json').read_text())
    require(isinstance(samples, list) and samples, 'Owner actual transport observations required')
    for sample in samples:
        reports.append(validate_actual(sample['retentionIdlePolicy'], maximum, parent['pid'], -1))
    terminal = json.loads((load / 'load-result.json').read_text())['physicalOfferTape']['lastActualTransportObservation']
    validate_actual(terminal['retentionIdlePolicy'], maximum, parent['pid'], -1)
    return {'passed': True, 'nodeRolesPerProcess': 4, 'ownerDriverRoles': 1,
            'configuredMaximumParkNs': maximum, 'reports': reports,
            'actualSleepDurationMeasured': False,
            'scope': 'Actual installed instances/factory consumption evidence; owner loop remains unchanged at up to1ms'}
