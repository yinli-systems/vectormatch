"""Pure correlation/phase seam for the read-window experiment; no I/O or process operations.

All physical callbacks are retained. CSV coordinator elapsed intervals overlap and
include ordered head wait and evidence work; they must never be summed as walltime.
Retained slot/consume occupancy is source-enforced and reconciled from runtime high
water, not independently reconstructed from these CSV completion observations.
"""
from collections import defaultdict
from bisect import bisect_left

READ_KINDS = {'ArchiveChunk', 'FetchEvents'}
CONTROL_KINDS = {'PrepareArchive', 'ArchiveCommit', 'EventAck'}
CSV_FIELDS = ('rpc','kind','correlation_id','start_monotonic_ns','end_monotonic_ns',
              'elapsed_ns','completed','archive_chunk_requested_bytes','event_fetch_requested_count',
              'read_phase_generation','read_window','armed_monotonic_ns','owner_reply_completed_ns')


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def correlation_map(frames, unique=True):
    grouped = defaultdict(list)
    for frame in frames:
        grouped[frame['decoded']['correlation']].append(frame)
    if unique:
        require(all(len(v) == 1 for v in grouped.values()), 'Duplicate logical/request correlation')
        return {k:v[0] for k,v in grouped.items()}
    return dict(grouped)


def maximum_overlap(intervals):
    """Half-open [first positive offer, first raw reply callback) wire-observed intervals."""
    points = []
    for start,end in intervals:
        require(end >= start, 'Callback precedes first positive offer')
        if start == end:
            continue
        points += [(start,1),(end,-1)]
    active = high = 0
    for _,delta in sorted(points, key=lambda p:(p[0],p[1])):
        active += delta
        require(active >= 0, 'Invalid interval closure')
        high = max(high,active)
    require(active == 0,'Incomplete interval closure')
    return high


def audit_rpc_phases(rows, logical_requests, logical_replies, physical_requests,
                     physical_replies, offers, origin, selected_window, *, maximum_read_phases=8, expected_phase_count=None):
    require(type(selected_window) is int and selected_window in (1,8), 'Selected read window must be1 or8')
    require(type(maximum_read_phases)is int and 1<=maximum_read_phases<=24,'Prospectively bounded phase cap required')
    require(rows and len(rows) == len(logical_requests) == len(logical_replies), 'Logical RPC count closure')
    requests=correlation_map(logical_requests);replies=correlation_map(logical_replies)
    physical_q=correlation_map(physical_requests);physical_r=correlation_map(physical_replies,False)
    require(set(requests)==set(replies),'Logical request/reply correlation closure')
    row_by_corr={int(r['correlation_id']):r for r in rows}
    require(len(row_by_corr)==len(rows) and set(row_by_corr)==set(requests),'Logical CSV correlation closure')
    require(set(physical_q)==set(physical_r),'All physical request/callback correlation closure')
    first_positive={};positive_counts=defaultdict(int)
    for offer in offers:
        corr=int(offer['correlation_id']);require(corr in physical_q,'Unknown offer correlation')
        if int(offer['return_code'])>=0:
            positive_counts[corr]+=1
            first_positive.setdefault(corr,int(offer['offset_ns']))
    business_offer_times=sorted([int(o['offset_ns'])+origin for o in offers if physical_q[int(o['correlation_id'])]['decoded']['kind']=='BusinessBatch'])
    phases=defaultdict(list);serial=[];report_rows=[];used_physical=set();extra_callbacks=0
    for number,row in enumerate(rows,1):
        require(tuple(row)==CSV_FIELDS, 'Exactly13 RPC timing columns required')
        corr=int(row['correlation_id']);q=requests[corr];v=replies[corr];kind=q['decoded']['kind']
        require(int(row['rpc'])==number and row['completed']=='true' and row['kind']==kind,'RPC sequence/completion/kind differs')
        start,end,elapsed=(int(row[k]) for k in ('start_monotonic_ns','end_monotonic_ns','elapsed_ns'))
        require(end-start==elapsed and elapsed>=0,'Coordinator RPC elapsed invalid')
        require(corr in physical_q and corr in first_positive and positive_counts[corr]<=4,'Logical RPC lacks bounded possible admission')
        require(physical_q[corr]['sha']==q['sha'],'Original logical-to-physical request wire differs')
        require(start<=physical_q[corr]['at']+origin<=end,'Original physical request outside coordinator interval')
        callbacks=physical_r[corr]
        require(any(f['sha']==v['sha'] for f in callbacks),'Logical reply not present in complete physical callback tape')
        require(any(f['sha']==v['sha'] and f['at']+origin<=end for f in callbacks),'Logical reply only appears after coordinator end')
        require(all(f['at']>=first_positive[corr] for f in callbacks),'Physical callback precedes offer')
        require(v['decoded']['correlation']==corr and v['decoded']['profile']==q['decoded']['profile'] and v['decoded']['lineage']==q['decoded']['lineage'],'Logical reply scope/correlation differs')
        require(all(f['decoded']['profile']==q['decoded']['profile'] and f['decoded']['lineage']==q['decoded']['lineage'] for f in callbacks),'Physical duplicate/late scope differs')
        used_physical.add(corr);extra_callbacks+=len(callbacks)-1
        expected_tag={'PrepareArchive':3,'ArchiveChunk':4,'FetchEvents':2,'ArchiveCommit':1,'EventAck':1}
        require(kind in expected_tag and v['decoded']['tag']==expected_tag[kind] and v['decoded'].get('error','')=='','Accepted logical RPC must have successful operation payload')
        if kind=='ArchiveChunk':
            require(row['archive_chunk_requested_bytes']==str(q['decoded']['count']) and row['event_fetch_requested_count']=='','Archive requested count CSV differs')
            require(1<=q['decoded']['count']<=6144,'Archive6144 cap exceeded')
        elif kind=='FetchEvents':
            require(row['event_fetch_requested_count']==str(q['decoded']['count']) and row['archive_chunk_requested_bytes']=='','Event count CSV differs')
            require(1<=q['decoded']['count']<=16,'Fetch16 cap exceeded')
        else:
            require(row['archive_chunk_requested_bytes']==row['event_fetch_requested_count']=='','Spurious read count on serialized control')
        if kind in READ_KINDS:
            generation=int(row['read_phase_generation']);window=int(row['read_window'])
            armed=int(row['armed_monotonic_ns']);owner=int(row['owner_reply_completed_ns'])
            require(generation>0 and window==selected_window and start<=armed<=owner<=end,'Read phase/window/owner timing invalid')
            first_callback=min(callbacks,key=lambda f:f['at'])
            require(first_callback['sha']==v['sha'],'First read callback does not bind accepted logical reply wire')
            require(any(f['sha']==v['sha'] and f['at']<=owner-origin for f in callbacks),'Accepted logical reply only appears after owner completion')
            require(armed-origin<=first_positive[corr]<=first_callback['at']<=owner-origin,'Read raw offer/callback outside arm-to-owner-completion observations')
            phases[generation].append({'correlation':corr,'kind':kind,'start':start,'end':end,'armed':armed,'owner':owner,'firstPositive':first_positive[corr],'firstCallback':min(f['at'] for f in callbacks),'request':q,'reply':v})
        else:
            # Serialized controls are outside read-bank phases. Exact sentinel is part of the source schema.
            require(row['read_phase_generation']=='0' and row['read_window']=='0' and row['armed_monotonic_ns']=='' and row['owner_reply_completed_ns']=='','Serialized control has read-phase fields')
            serial.append((start,end,corr,kind))
        report_rows.append({'correlation':corr,'kind':kind,'coordinatorElapsedNs':elapsed,'physicalCallbacks':len(callbacks),'physicalErrorCallbacksRetained':sum(bool(f['decoded'].get('error','')) for f in callbacks),'positiveOffers':positive_counts[corr]})
    require(set(physical_q)-used_physical=={c for c,f in physical_q.items() if f['decoded']['kind']=='BusinessBatch'},'Nonbusiness physical RPC omitted from logical inventory')
    require(phases and len(phases)<=maximum_read_phases,'Bounded read phase inventory required')
    if expected_phase_count is not None:
        require(type(expected_phase_count)is int and expected_phase_count==maximum_read_phases
                and len(phases)==expected_phase_count,'Exact workload read phase inventory required')
    phase_reports=[];previous_end=None;previous_generation=0
    for generation,items in sorted(phases.items()):
        require(generation>previous_generation and len({r['kind'] for r in items})==1,'Read phase generation/kind closure')
        begin=min(r['start'] for r in items);end=max(r['end'] for r in items)
        require(previous_end is None or begin>=previous_end,'Separate read phases overlap coordinator closure')
        previous_end,previous_generation=end,generation
        for low,high,_,_ in serial:
            require(high<=begin or low>=end,'Serialized prepare/ACK overlaps open read phase')
        i=bisect_left(business_offer_times,begin)
        require(i==len(business_offer_times) or business_offer_times[i]>=end,'Business offer during maintenance read phase')
        high=maximum_overlap([(r['firstPositive'],r['firstCallback']) for r in items])
        require(1<=high<=selected_window,'Actual possible-admission in-flight interval exceeds selected window')
        phase_reports.append({'generation':generation,'kind':items[0]['kind'],'logicalReads':len(items),'reservationStartNs':begin,'observedLowerBoundNotExactBankLifetime':True,'coordinatorLastEndNs':end,'wallSpanNs':end-begin,'wireObservedOfferedAwaitingFirstCallbackHighWater':high})
    # Controls themselves remain serial; overlapping read rows are deliberately legal.
    for a,b in zip(sorted(serial),sorted(serial)[1:]):require(a[1]<=b[0],'Serialized controls overlap')
    return {'passed':True,'logicalRpcs':len(rows),'readPhases':phase_reports,'extraPhysicalCallbacksRetained':extra_callbacks,'actualOfferedHighWater':max(p['wireObservedOfferedAwaitingFirstCallbackHighWater'] for p in phase_reports),'selectedReadWindow':selected_window,'pipelineActuallyOverlapped':any(p['wireObservedOfferedAwaitingFirstCallbackHighWater']>1 for p in phase_reports),'coordinatorElapsedSumIsWallTime':False,'retainedSlotOccupancyIndependentlyReconstructed':False,'timingScope':'Phase min reservation start through max coordinator end is an observed lower bound, not exact bank lifetime. Per RPC coordinator end is after logical reply flush, before timing flush/consume. Elapsed includes ordered head wait and overlapping read intervals; retained capacity is source-enforced/runtime-attested, without independent consume timestamps.','rpcBindings':report_rows}
