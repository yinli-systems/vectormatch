from pathlib import Path
p=Path(__file__).parent/'audit_raw.py';s=p.read_text()
s=s.replace('from common import WINDOWS,audit_arguments,egress,egress_progress','from common import WINDOWS,audit_arguments,egress,egress_progress\nfrom read_phase_audit import audit_rpc_phases,correlation_map')
s=s.replace("require(out['error'] == '', 'RPC error reply')", "require(re.fullmatch('[A-Z0-9_]{0,128}',out['error']) is not None,'Invalid bounded RPC error')")
s=s.replace('def audit_arm(cap):\n    arm =', 'def audit_arm(selected_window):\n    cap=6144\n    arm =')
s=s.replace("('window-%d' % cap)", "('window-%d' % selected_window)")
s=s.replace("cfg['commonChunkEnvelope'] is True", "cfg['commonChunkEnvelope'] is False and cfg['commonReadWindowEnvelope'] is True and cfg['readWindow']==selected_window")
a=s.index('    request_by_correlation = {f[\'decoded\'][\'correlation\']:f for f in reqs}')
b=s.index('    for f in reqs+reps:',a)
s=s[:a]+'''    request_by_correlation = correlation_map(reqs)
    physical_callbacks_by_correlation = correlation_map(reps,False)
    # Business arrival rows bind their original completion against the earliest callback.
    # Maintenance uses an independent exact logical-wire SHA / owner-completion binding below.
    reply_by_correlation = {c:min(v,key=lambda f:f['at']) for c,v in physical_callbacks_by_correlation.items()}
    require(set(request_by_correlation) == set(reply_by_correlation), 'Physical request/callback correlation closure')
''' +s[b:]
a=s.index('    rpc_kinds=collections.defaultdict(list); previous_end=-1')
b=s.index("    require(set(rpc_kinds)",a)
s=s[:a]+'''    phase_report=audit_rpc_phases(rpc_rows,logical_requests,logical_replies,reqs,reps,offers,origin,selected_window)
    logical_request_by_correlation=correlation_map(logical_requests)
    logical_reply_by_correlation=correlation_map(logical_replies)
    rpc_kinds=collections.defaultdict(list)
    for row in rpc_rows:
        rpc_kinds[row['kind']].append(int(row['elapsed_ns']))
''' +s[b:]
s=s.replace("prefix_checks=audit_prefixes(arm,cap,cycles,rpc_rows,logical_requests,logical_replies)", "prefix_checks=audit_prefixes(arm,cap,cycles,rpc_rows,logical_requests,logical_replies,offers,request_by_correlation,origin,phase_report)")
s=s.replace("    return {'archiveChunkBytes':cap,'batchCap':4", "    return {'archiveChunkBytes':cap,'readWindow':selected_window,'readPhaseBindings':phase_report,'batchCap':4")
s=s.replace("'totalLogicalRpcElapsedNs':sum(sum(v) for v in rpc_kinds.values()),", "'sumOverlappingCoordinatorRpcElapsedNsNotWallTime':sum(sum(v) for v in rpc_kinds.values()),")
s=s.replace("cap=int(role.split('-')[1]); arm=next(a for a in arms if a['archiveChunkBytes']==cap)", "cap=int(role.split('-')[1]); arm=next(a for a in arms if a['readWindow']==cap)")
s=s.replace("def terminal_inventory(chunk):", "def terminal_inventory(selected_window):").replace("('window-'+str(chunk))/'load'", "('window-'+str(selected_window))/'load'")
a=s.index('def audit_prefixes(');b=s.index('\ndef audit_egress(',a)
s=s[:a]+'''def audit_prefixes(arm,chunk,cycles,rpc_rows,requests,replies,offers,physical_q,origin,phase_report):
    from bisect import bisect_left
    maint=arm/'load/maintenance';reply_blob=raw(maint/'logical-rpc-replies.bin')
    qmap=correlation_map(requests);vmap=correlation_map(replies)
    business_times=sorted(int(o['offset_ns'])+origin for o in offers if physical_q[int(o['correlation_id'])]['decoded']['kind']=='BusinessBatch')
    previous_chain=None;previous_command=0;previous_event=0;reports=[];all_phases=set()
    for cycle in cycles:
        row=properties(maint/('cycle-%d.verified.txt'%cycle['cycle']));low,high=int(row['logicalRpcCountAtStart']),int(row['logicalRpcCountAtEnd'])
        require(row['archiveChunkBytes']==str(chunk) and row['eventFetchCount']=='16','Cycle selected policy differs')
        selected_rows=rpc_rows[low:high]
        require(selected_rows and selected_rows[0]['kind']=='PrepareArchive','Cycle starts with prepare barrier')
        require(selected_rows[-2]['kind']=='ArchiveCommit' and selected_rows[-1]['kind']=='EventAck','Cycle ends with exact serialized archive/event ACK barriers')
        require(all(x['kind'] in ('ArchiveChunk','FetchEvents') for x in selected_rows[1:-2]),'Unexpected serialized operation among reads')
        phases=[]
        for x in selected_rows[1:-2]:
            g=int(x['read_phase_generation'])
            if not phases or phases[-1]!=g:phases.append(g)
        require(len(phases)==2 and len(set(phases))==2 and not set(phases)&all_phases,'Exactly two unique read phases per cycle')
        all_phases.update(phases)
        chunks=[x for x in selected_rows if x['kind']=='ArchiveChunk'];events=[x for x in selected_rows if x['kind']=='FetchEvents']
        require(chunks and events and all(int(x['read_phase_generation'])==phases[0] for x in chunks) and all(int(x['read_phase_generation'])==phases[1] for x in events),'Prepare then chunk then event phase order differs')
        start,end=cycle['startOffsetNs']+origin,cycle['endOffsetNs']+origin
        i=bisect_left(business_times,start);require(i==len(business_times) or business_times[i]>=end,'Business offer during complete maintenance cycle')
        descriptor=vmap[int(selected_rows[0]['correlation_id'])]['decoded'];acknowledgement=descriptor['ack'];total=descriptor['total']
        require(qmap[int(selected_rows[0]['correlation_id'])]['decoded']['throughCommand']==acknowledgement[3],'Prepare target differs from descriptor')
        require(acknowledgement[2]==previous_command+1 and acknowledgement[3]==cycle['throughCommandSeq'],'Exact command range')
        if previous_chain is not None:require(acknowledgement[4]==previous_chain,'Archive chain continuity')
        payload=bytearray();event_values=[];event_frames=[]
        chunk_pairs=sorted(((qmap[int(x['correlation_id'])],vmap[int(x['correlation_id'])]) for x in chunks),key=lambda pair:pair[0]['decoded']['offset'])
        event_pairs=sorted(((qmap[int(x['correlation_id'])],vmap[int(x['correlation_id'])]) for x in events),key=lambda pair:pair[0]['decoded']['fromEvent'])
        for req,rep in chunk_pairs:
            q,v=req['decoded'],rep['decoded']
            require(q['ack']==v['ack']==acknowledgement and q['total']==v['total']==total and q['offset']==v['offset']==len(payload),'Exact unique descriptor/offset chunk binding')
            require(q['count']==min(chunk,total-len(payload)) and len(v['chunk'])==q['count'],'Actual selected chunk length');payload.extend(v['chunk'])
        for req,rep in event_pairs:
            q,v=req['decoded'],rep['decoded']
            require(q['fromEvent']==previous_event+len(event_values)+1 and 1<=q['count']<=16 and len(v['events'])==q['count'],'Exact unique complete event page binding')
            for event in v['events']:require(event[0]==previous_event+len(event_values)+1,'Exact event prefix continuity');event_values.append(event)
            event_frames.append(reply_blob[rep['offset']:rep['offset']+4+rep['bytes']])
        commit=qmap[int(selected_rows[-2]['correlation_id'])]['decoded'];event_ack=qmap[int(selected_rows[-1]['correlation_id'])]['decoded']
        require(len(payload)==total and hashlib.sha256(payload).hexdigest()==acknowledgement[6],'Complete canonical payload SHA')
        require(commit['ack']==acknowledgement and event_ack['throughEvent']==int(row['throughEventSeq']),'Exact destructive ACK targets')
        require(previous_event+len(event_values)==int(row['throughEventSeq']),'Full event prefix total')
        for field,expected in [('archiveFile',bytes(payload)),('eventFile',b''.join(event_frames))]:
            name=pathlib.PurePosixPath(row[field]).name;require(re.fullmatch(r'\\d{4}-(archive|events)\\.bin',name) is not None,'Bounded immutable writer path')
            require(raw(arm/'load/writer'/name)==expected,'Logical transfer versus durable writer differs')
        previous_chain=acknowledgement[5];previous_command=acknowledgement[3];previous_event=int(row['throughEventSeq'])
        reports.append({'cycle':cycle['cycle'],'readPhases':phases,'archiveBytes':total,'archiveChunkRpcs':len(chunk_pairs),'eventCount':len(event_values),'eventFetchRpcs':len(event_pairs),'archivePayloadSha256':acknowledgement[6],'durableWriterBytesEqualRawTransfers':True,'businessOffersExcludedAcrossCompleteCycle':True})
    require(len(reports)==3 and len(all_phases)==6 and all_phases=={p['generation'] for p in phase_report['readPhases']},'Exactly three complete cycles / six read phases required')
    require(sum(x['archiveChunkRpcs'] for x in reports)==sum(r['kind']=='ArchiveChunk' for r in rpc_rows) and sum(x['eventFetchRpcs'] for x in reports)==sum(r['kind']=='FetchEvents' for r in rpc_rows),'Actual descriptor/event-derived inventory differs')
    return reports
''' +s[b:]
s=s.replace("{arm['archiveChunkBytes']:arm['rawMetrics'] for arm in arms}","{arm['readWindow']:arm['rawMetrics'] for arm in arms}")
s=s.replace("'RPC elapsed includes caller wait, transport, server, scheduling and evidence writes, not pure fsync.'", "'Read RPC elapsed includes ordered head wait, transport, server, scheduling and evidence writes. Intervals overlap; their sum is not wall time or pure fsync.'")
p.write_text(s)
