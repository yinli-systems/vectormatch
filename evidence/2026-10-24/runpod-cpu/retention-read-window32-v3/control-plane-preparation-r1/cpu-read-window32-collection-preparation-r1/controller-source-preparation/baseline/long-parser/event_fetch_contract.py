"""Explicit selected-page contracts; pure schema/wire checks, never runtime evidence."""

def require(value,message):
    if not value:raise AssertionError(message)

def selected_page(value):
    require(type(value)is int and value in(16,32),'Explicit selected event page16 or32 required')
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

def validate_selected_configuration(configuration,summary,plan,*,event_fetch_count):
    selected_page(event_fetch_count)
    for label,value in [('configuration',configuration),('summary',summary),('plan',plan)]:
        require(value.get('eventFetchCount')==event_fetch_count and value.get('commonEventFetchEnvelope')is True,
            label+' selected event page/common envelope differs')
        require(value.get('readWindow',value.get('requestedReadWindow'))==8
            and value.get('batchCap')==4 and value.get('archiveChunkBytes')==6144,
            label+' fixed read8/cap4/chunk6144 differs')
    require(summary['maintenanceRpcMetrics']['eventFetchCount']==event_fetch_count,'Actual coordinator selected event page differs')
    require(plan['maxReadOnlyInFlight']==8 and plan['maximumPhysicalOffersPerRpc']==4
        and 0<plan['maximumRawTraceBytes']<=2*1024**3 and 0<plan['maximumAllocatedGrowthBytes']<=5*1024**3//2
        and plan['minimumFreeRuntimeBytes']==1024**3,'Unchanged read/offer/raw/growth/floor bounds required')
    require(6763<=plan['largestReplyBytes']<=6919 and 6763+32<=6951,'Page32 must fit unchanged supported complete reply envelope')
    require(0<plan['selectedMaximumEventFetchRpcs']<=plan['maximumEventFetchRpcs']
        and plan['selectedMaximumLogicalMaintenanceRpcs']<=plan['maximumLogicalMaintenanceRpcs'],
        'Selected RPC counts must remain upper bounds within common operational envelope')
    return True

def validate_cycle_selection(row,phase_report,chunk,*,event_fetch_count):
    selected_page(event_fetch_count)
    require(phase_report['selectedEventFetchCount']==event_fetch_count and phase_report['selectedReadWindow']==8,
        'Cycle/phase selected event page or read8 differs')
    require(row['archiveChunkBytes']==str(chunk) and row['eventFetchCount']==str(event_fetch_count)
        and row['readWindow']=='8','Cycle selected policy differs')
    return True

def validate_cycle_page_request(request,*,previous_event,consumed,through_event,event_fetch_count):
    selected_page(event_fetch_count)
    remaining=through_event-previous_event-consumed
    require(remaining>0 and request['fromEvent']==previous_event+consumed+1
        and request['count']==min(event_fetch_count,remaining),'Exact selected page or final partial cycle prefix differs')
    return True
