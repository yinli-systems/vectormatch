"""Pure explicit read32 contracts; local metadata is not Linux/native qualification."""
SOURCE_COMMIT='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'
CODE_FINGERPRINT='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
PROFILE_FINGERPRINT='732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68'

def require(value,message):
    if not value:raise AssertionError(message)

def selected_page(value):
    require(type(value)is int and value==32,'Explicit fixed selected event page32 required')
    return value

def selected_read_window(value):
    require(type(value)is int and value in(8,32),'Explicit selected read window8 or32 required')
    return value

def validate_fetch_pair(request,reply,*,event_fetch_count):
    selected_page(event_fetch_count)
    require(request['kind']=='FetchEvents' and type(request['fromEvent'])is int and request['fromEvent']>=1
        and type(request['count'])is int and 1<=request['count']<=event_fetch_count,'Fetch request exceeds selected page or range')
    require(reply['tag']==2 and reply.get('error','')=='' and len(reply['events'])==request['count'],
        'Exact complete requested event reply count required')
    start=request['fromEvent'];events=reply['events']
    require(type(reply['exported'])is int and type(reply['lastEvent'])is int
        and 0<=reply['exported']<start and start+request['count']-1<=reply['lastEvent'],
        'Event response exported/last range does not contain requested prefix')
    require([event[0]for event in events]==list(range(start,start+request['count'])),
        'Exact complete contiguous requested event prefix required')
    return True

def validate_selected_configuration(configuration,summary,plan,*,selected_window,event_fetch_count):
    selected_page(event_fetch_count);selected_read_window(selected_window)
    for label,value in [('configuration',configuration),('summary',summary),('plan',plan)]:
        require(value.get('eventFetchCount')==event_fetch_count
            and value.get('commonReadWindow32Envelope')is True
            and value.get('commonEventFetchEnvelope',False)is False,
            label+' fixed event page/common32 envelope differs')
        require(value.get('readWindow',value.get('requestedReadWindow'))==selected_window
            and value.get('batchCap')==4 and value.get('archiveChunkBytes')==6144
            and value.get('commonReadWindowEnvelope')is True and value.get('commonChunkEnvelope',False)is False,
            label+' fixed selected read/cap4/chunk6144 differs')
    require(configuration['actualCodeSha256']==CODE_FINGERPRINT
        and configuration['profileSha256']==PROFILE_FINGERPRINT,'New read32 actual code/profile required; old87a cannot qualify')
    require(configuration['retentionIdleSelection']['maximumParkNs']==100000
        and configuration['ownerPollSelection']['maximumParkNs']==1000000
        and configuration['ownerPollActual']['available']is True
        and configuration['ownerPollActual']['ownerPollMaxParkNs']==1000000,
        'Explicit driver100us and actual constructed owner1ms selection required')
    coordinator=summary['maintenanceRpcMetrics']
    require(coordinator['eventFetchCount']==event_fetch_count and coordinator['readWindow']==selected_window
        and coordinator.get('commonReadWindow32Envelope')is True,'Actual coordinator selected page/read32 envelope differs')
    require(plan['maxReadOnlyInFlight']==32 and plan['maximumPhysicalOffersPerRpc']==4
        and plan['maximumRawTraceBytes']==182433396 and plan['maximumAllocatedGrowthBytes']==754102673
        and plan['maximumRawTraceBytes']<=2*1024**3 and plan['maximumAllocatedGrowthBytes']<=5*1024**3//2
        and plan['minimumFreeRuntimeBytes']==1024**3,'Exact actual-JAR page32/common32 finite budgets required')
    require(plan['largestReplyBytes']==6791 and 6763<=plan['largestReplyBytes']<=6919
        and 6763+32<=6951,'Page32 must fit unchanged supported complete reply envelope')
    require(plan['maximumLogicalMaintenanceRpcs']==plan['selectedMaximumLogicalMaintenanceRpcs']==5131
        and plan['maximumEventFetchRpcs']==2113 and plan['maximumArchiveChunkRpcs']==2982
        and plan['maximumJournalRecords']==96 and plan['maximumJournalBytes']==117792
        and plan['readOnlyStagingBytes']==1984256 and plan['readOnlyFailureTraceReserveBytes']==1073760,
        'Fixed page32/common32 actual codec/RPC/staging/failure inventory differs')
    return True

def validate_cycle_selection(row,phase_report,chunk,*,selected_window,event_fetch_count):
    selected_page(event_fetch_count);selected_read_window(selected_window)
    require(phase_report['selectedEventFetchCount']==event_fetch_count
        and phase_report['selectedReadWindow']==selected_window,'Cycle/phase selected page or window differs')
    require(row['archiveChunkBytes']==str(chunk) and row['eventFetchCount']==str(event_fetch_count)
        and row['readWindow']==str(selected_window),'Cycle selected policy differs')
    return True

def validate_cycle_page_request(request,*,previous_event,consumed,through_event,event_fetch_count):
    selected_page(event_fetch_count)
    remaining=through_event-previous_event-consumed
    require(remaining>0 and request['fromEvent']==previous_event+consumed+1
        and request['count']==min(event_fetch_count,remaining),'Exact selected page or final partial cycle prefix differs')
    return True

def validate_read_failure_bundle(metadata,original_requests,*,selected_window,event_fetch_count):
    """Reconcile supplied retained originals only; never treats missing disk bodies as durable.

    A zero-sized outstanding bundle is legal after all reads were consumed. The
    caller separately retains complete logical tapes and all failed output bytes.
    """
    selected_page(event_fetch_count);selected_read_window(selected_window)
    require(metadata['schema']=='retention-v3-read-phase-failure-v1'
        and metadata['readWindow']==selected_window
        and metadata['retainedOriginalCount']==len(original_requests)==len(metadata['retainedReads'])
        and 0<=len(original_requests)<=selected_window,'Failure bundle exceeds selected retained-credit limit')
    require(type(metadata['originalsWrittenAndFlushed'])is bool
        and metadata['independentDurabilityProven']is False and metadata['logicalTapesMayBePartial']is True
        and metadata['ackAfterFailureAllowed']is False,'Failure cannot authorize ACK or claim independent durability')
    correlations=set();kinds=set();scopes=set()
    for frame,observed in zip(original_requests,metadata['retainedReads']):
        q=frame['decoded'];correlation=q['correlation']
        require(correlation not in correlations and q['kind']in('ArchiveChunk','FetchEvents')
            and observed['correlationId']==correlation and observed['wireSha256']==frame['sha']
            and observed['operationKind']==q['kind'] and observed['consumed']is False,
            'Failure original correlation/SHA/operation/outstanding identity differs')
        require(0<=observed['acceptedPhysicalOffers']<=observed['possibleOffers']<=4
            and observed['absoluteOfferDeadlineNs']>observed['reservedMonotonicNs'],
            'Failure original offer or absolute permit bounds differ')
        if q['kind']=='FetchEvents':require(1<=q['count']<=event_fetch_count and q['fromEvent']>=1,'Failure event range differs')
        else:require(1<=q['count']<=6144,'Failure chunk range differs')
        correlations.add(correlation);kinds.add(q['kind']);scopes.add((q['profile'],q['lineage']))
    require(len(kinds)<=1 and len(scopes)<=1,'Failure retained phase kinds/scopes must remain exclusive')
    return {'passed':True,'retainedOriginals':len(original_requests),'selectedReadWindow':selected_window,
        'persistedOriginalBodiesClaimed':metadata['originalsWrittenAndFlushed'],
        'independentDurabilityProven':False,'ackAuthorized':False,'completeRawFailureArchiveStillRequired':True}
