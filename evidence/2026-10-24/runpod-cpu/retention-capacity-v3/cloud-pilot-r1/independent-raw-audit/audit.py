#!/usr/bin/env python3
"""Independent local raw capacity audit. No SSH, subprocess, git or business mutation."""
import collections
import csv
import datetime
import hashlib
import json
import math
import pathlib
import re
import struct

HERE = pathlib.Path(__file__).resolve().parent
COLLECTION = HERE.parent / 'collection-r1'
JOB = COLLECTION / 'raw-files/job'
INPUTS = {}

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def raw(path):
    value = path.read_bytes()
    INPUTS[str(path.relative_to(COLLECTION))] = {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    return value

def js(path):
    return json.loads(raw(path))

def rows(path):
    return list(csv.DictReader(raw(path).decode('ascii').splitlines()))

class Reader:
    def __init__(self, value):
        self.value, self.position = value, 0
    def take(self, count):
        require(0 <= count <= len(self.value) - self.position, 'Truncated or invalid binary field')
        result = self.value[self.position:self.position+count]
        self.position += count
        return result
    def number(self, form):
        return struct.unpack('>' + form, self.take(struct.calcsize('>' + form)))[0]
    def i(self): return self.number('i')
    def q(self): return self.number('q')
    def b(self): return self.number('B')
    def flag(self):
        value = self.b(); require(value in (0, 1), 'Noncanonical bool'); return bool(value)
    def text(self, limit=1024):
        size = self.i(); require(0 <= size <= limit, 'Oversize string'); return self.take(size).decode('utf8', 'strict')
    def end(self):
        require(self.position == len(self.value), 'Trailing binary bytes')

def ack(r):
    return [r.text(64), r.text(64), r.q(), r.q(), r.text(64), r.text(64), r.text(64)]

def nested(value):
    r = Reader(value)
    require((r.i(), r.number('H'), r.q(), r.b()) == (0x564d5731, 2, 0, 2), 'Expected canonical place')
    out = {'account': r.q(), 'producer': r.text(512), 'seq': r.q(), 'client': r.text(512),
           'side': r.b(), 'price': r.q(), 'quantity': r.q(), 'tif': r.b(), 'sha': hashlib.sha256(value).hexdigest()}
    r.end()
    require(out['account'] == 2 and out['side'] == 0 and out['price'] == 10 and out['quantity'] == 1,
            'Unexpected load command')
    return out

KINDS = {2:'ArchiveCommit', 3:'EventAck', 4:'Position', 5:'FetchEvents', 6:'PrepareArchive', 7:'ArchiveChunk', 8:'BusinessBatch'}
def request(value):
    r = Reader(value)
    require(len(value) <= 4096 and (r.i(), r.number('H')) == (0x564d5733, 3), 'Invalid request header')
    out = {'profile': r.text(64), 'lineage': r.text(64), 'correlation': r.q()}
    tag = r.b(); require(tag in KINDS, 'Unexpected operation'); out['kind'] = KINDS[tag]
    if tag == 8:
        count = r.i(); require(1 <= count <= 4, 'Invalid batch count')
        out['members'] = [nested(r.take(r.i())) for _ in range(count)]
    elif tag == 2:
        out['maintenanceIdentity'] = [r.text(48), r.q()]; out['ack'] = ack(r)
    elif tag == 3:
        out['maintenanceIdentity'] = [r.text(48), r.q()]; out['throughEvent'] = r.q()
    elif tag == 5:
        out['fromEvent'], out['count'] = r.q(), r.i()
    elif tag == 6:
        out['throughCommand'] = r.q()
    elif tag == 7:
        out['ack'] = ack(r); out['total'], out['offset'], out['count'] = r.i(), r.i(), r.i()
    r.end()
    return out

def result(r):
    return {'code': r.b(), 'reason': r.text(1024), 'commandSeq': r.q(), 'orderId': r.q(), 'remaining': r.q(), 'trades': r.i()}

def reply(value):
    r = Reader(value)
    require(len(value) <= 8192 and (r.i(), r.number('H')) == (0x564d5233, 3), 'Invalid reply header')
    out = {'profile': r.text(64), 'lineage': r.text(64), 'correlation': r.q(), 'counters': [r.q() for _ in range(7)],
           'stateHash': r.text(64), 'error': r.text(128), 'tag': r.b()}
    require(out['error'] == '', 'RPC error reply')
    tag = out['tag']
    if tag == 1:
        out['result'] = result(r) if r.flag() else None
        out['replayed'] = r.flag()
        if r.flag():
            out['maintenance'] = {'code': r.b(), 'replayed': r.flag(), 'exported': r.q(), 'error': r.text(128)}
            if r.flag(): out['maintenance']['compaction'] = [r.q(), r.q(), r.i(), r.i(), r.flag()]
    elif tag == 2:
        out['exported'], out['lastEvent'], count = r.q(), r.q(), r.i()
        require(0 <= count <= 16, 'Bad event reply count')
        out['events'] = []
        for _ in range(count):
            event = [r.q(), r.q(), r.b()] + [r.q() for _ in range(4)] + [r.b(), r.q(), r.q(), r.text(128)]
            out['events'].append(event)
    elif tag == 3:
        out['ack'] = ack(r); out['total'] = r.i()
    elif tag == 4:
        out['ack'] = ack(r); out['total'], out['offset'], count = r.i(), r.i(), r.i()
        out['chunk'] = r.take(count)
    elif tag == 5:
        count = r.i(); require(1 <= count <= 4, 'Invalid batch reply count'); out['members'] = []
        for _ in range(count):
            entry = {'index':r.i(), 'account':r.q(), 'producer':r.text(48), 'seq':r.q(), 'sha':r.text(64), 'status':r.b()}
            entry['result'] = result(r) if r.flag() else None
            entry['replayed'] = r.flag(); entry['frontier'] = [r.q() for _ in range(4)]
            out['members'].append(entry)
    else:
        raise AssertionError('Invalid reply tag')
    r.end()
    return out

def frames(path, physical, decoder):
    value = raw(path); r = Reader(value); out = []
    while r.position < len(value):
        offset = r.position; at = r.q() if physical else None
        size = r.i(); payload = r.take(size)
        out.append({'offset':offset, 'at':at, 'bytes':size, 'sha':hashlib.sha256(payload).hexdigest(), 'decoded':decoder(payload)})
    return out

def nearest(values, p=.99):
    return sorted(values)[max(0, math.ceil(len(values)*p)-1)] if values else None

def properties(path):
    return dict(line.split('=',1) for line in raw(path).decode().splitlines() if '=' in line)

def audit_arm(cap):
    arm = JOB / 'pilot-pair' / ('cap-%d' % cap); load = arm/'load'; maint = load/'maintenance'
    cfg = js(load/'configuration.json'); summary = js(load/'load-result.json')
    require(cfg['arrivals'] == 6400 and cfg['ratePerSecond'] == 500 and cfg['windowSeconds'] == 12.8 and cfg['batchCap'] == cap, 'Fixed source configuration')
    require(cfg['logicalWorkers'] == 128 and cfg['taskQueueCapacityPerWorker'] == 64 and cfg['physicalSessions'] == 1
            and cfg['sharedMediaDrivers'] == 1 and cfg['batchFlushNs'] == 50000 and cfg['arrivalClockPausesForMaintenance'] is False, 'Fixed owner configuration')
    arrivals = rows(load/'arrivals.csv'); require(len(arrivals) == 6400, 'Arrival row closure')
    origin = cfg['scheduledOriginMonotonicNs']; window = 12_800_000_000
    reqs = frames(load/'physical-requests.bin', True, request); reps = frames(load/'physical-replies.bin', True, reply)
    request_by_correlation = {f['decoded']['correlation']:f for f in reqs}
    reply_by_correlation = {f['decoded']['correlation']:f for f in reps}
    require(len(request_by_correlation) == len(reqs) and len(reply_by_correlation) == len(reps), 'Duplicate transport correlation')
    require(set(request_by_correlation) == set(reply_by_correlation), 'Physical request/reply closure')
    for f in reqs+reps:
        require(f['decoded']['profile'] == cfg['profileSha256'] and f['decoded']['lineage'] == cfg['lineage'], 'Scope mismatch')
    indexes = rows(load/'physical-request-index.csv'); offers = rows(load/'physical-offer-codes.csv')
    require(len(indexes) == len(reqs), 'Index frame closure')
    for number, (f, row) in enumerate(zip(reqs,indexes),1):
        require(int(row['frame']) == number and int(row['wire_offset']) == f['offset'] and int(row['wire_length']) == f['bytes']
                and int(row['correlation_id']) == f['decoded']['correlation'] and row['wire_sha256'] == f['sha'], 'Raw request index mismatch')
        require(int(row['first_offer_offset_ns']) >= f['at'], 'Offer index precedes raw frame')
        require(int(row['members']) == len(f['decoded'].get('members',[None])), 'Index member count mismatch')
    admissions = collections.Counter()
    for number,row in enumerate(offers,1):
        require(int(row['attempt']) == number, 'Offer attempt gap')
        f = request_by_correlation[int(row['correlation_id'])]
        require(int(row['wire_offset']) == f['offset'] and int(row['offset_ns']) >= f['at'], 'Offer raw offset mismatch')
        if int(row['return_code']) >= 0: admissions[int(row['correlation_id'])] += 1
    lateness=[]; latencies=[]; within=0; identities=set(); accepted_ids=set(); command_seqs=set(); batch_distribution=collections.Counter()
    for index,row in enumerate(arrivals):
        require(int(row['arrival_index']) == index and int(row['worker']) == index%128 and row['producer'] == 'load-w%d'%(index%128)
                and int(row['request_seq']) == 1+index//128 and int(row['scheduled_offset_ns']) == index*2_000_000, 'Open-loop identity/schedule mismatch')
        require(row['status'] == 'APPLIED' and row['result_code'] == 'ACCEPTED' and row['unknown_observed_offset_ns'] == ''
                and row['not_sent_reason'] == '0' and row['reply_replayed'] == 'false' and row['initial_server_admission_status'] == '', 'Unexpected terminal/UNKNOWN/rejection')
        timing = [int(row[k]) for k in ('scheduled_offset_ns','arrival_offset_ns','dispatch_offset_ns','submit_offset_ns',
                    'first_wire_offer_call_offset_ns','first_successful_offer_return_offset_ns','reply_completion_offset_ns')]
        require(timing == sorted(timing), 'Arrival timing order invalid')
        late = timing[1]-timing[0]; lateness.append(late); latencies.append(timing[-1]-timing[0]); within += timing[-1] <= window
        correlation = int(row['correlation_id']); batch = int(row['batch_index']); frame = request_by_correlation[correlation]
        require(timing[4] <= frame['at'] <= timing[5] and timing[-1] >= reply_by_correlation[correlation]['at'], 'CSV timing does not contain raw transport observation')
        require(frame['decoded']['kind'] == 'BusinessBatch' and len(frame['decoded']['members']) <= cap, 'Business batch cap mismatch')
        member = frame['decoded']['members'][batch]; answer = reply_by_correlation[correlation]['decoded']['members'][batch]
        require(member['producer'] == answer['producer'] == row['producer'] and member['seq'] == answer['seq'] == int(row['request_seq'])
                and member['account'] == answer['account'] == 2 and member['sha'] == answer['sha'] == row['command_sha256'], 'Arrival-to-wire identity mismatch')
        require(answer['index'] == batch and answer['status'] == 0 and answer['result']['code'] == 0 and not answer['replayed'], 'Batch reply status mismatch')
        for column,key in [('command_seq','commandSeq'),('order_id','orderId'),('remaining_quantity','remaining'),('trade_count','trades')]:
            require(int(row[column]) == answer['result'][key], 'CSV versus wire result differs')
        require(int(row['admitted_physical_offers']) == admissions[correlation], 'Admission count mismatch')
        identity=(row['producer'],int(row['request_seq'])); require(identity not in identities,'Duplicate logical identity'); identities.add(identity)
        require(int(row['order_id']) not in accepted_ids and int(row['command_seq']) not in command_seqs, 'Duplicate accepted result')
        accepted_ids.add(int(row['order_id'])); command_seqs.add(int(row['command_seq']))
    require(accepted_ids == set(range(2,6402)) and command_seqs == set(range(4,6404)), 'Exact order/command frontier range')
    for f in reqs:
        if f['decoded']['kind'] == 'BusinessBatch': batch_distribution[len(f['decoded']['members'])] += 1
    rpc_rows=rows(maint/'logical-rpc-timings.csv'); logical_requests=frames(maint/'logical-rpc-requests.bin',False,request)
    logical_replies=frames(maint/'logical-rpc-replies.bin',False,reply)
    require(len(rpc_rows) == len(logical_requests) == len(logical_replies) == 1785, 'Logical RPC count closure')
    rpc_kinds=collections.defaultdict(list); previous_end=-1
    for number,(row,req,rep) in enumerate(zip(rpc_rows,logical_requests,logical_replies),1):
        request_value,reply_value=req['decoded'],rep['decoded']; correlation=int(row['correlation_id'])
        start,end,elapsed=map(int,(row['start_monotonic_ns'],row['end_monotonic_ns'],row['elapsed_ns']))
        require(int(row['rpc']) == number and row['completed'] == 'true' and end-start == elapsed and elapsed >= 0 and start >= previous_end, 'RPC timing invalid')
        previous_end=end
        require(correlation == request_value['correlation'] == reply_value['correlation'] and row['kind'] == request_value['kind'], 'RPC correlation/kind mismatch')
        require(request_by_correlation[correlation]['sha'] == req['sha'] and reply_by_correlation[correlation]['sha'] == rep['sha'], 'Logical-to-physical RPC wire mismatch')
        require(reply_value['tag'] == {'PrepareArchive':3,'ArchiveChunk':4,'FetchEvents':2,'ArchiveCommit':1,'EventAck':1}[row['kind']], 'RPC reply tag mismatch')
        rpc_kinds[row['kind']].append(elapsed)
    require({k:len(v) for k,v in rpc_kinds.items()} == {'PrepareArchive':3,'ArchiveChunk':975,'FetchEvents':801,'ArchiveCommit':3,'EventAck':3}, 'RPC kind inventory differs')
    cycles=[]
    for number in range(1,4):
        row=properties(maint/('cycle-%d.verified.txt'%number)); start,end=int(row['cycleStartedMonotonicNs']),int(row['cycleEndedMonotonicNs'])
        low,high=int(row['logicalRpcCountAtStart']),int(row['logicalRpcCountAtEnd'])
        subset=rpc_rows[low:high]
        require(int(row['cycle']) == number and subset and start <= int(subset[0]['start_monotonic_ns'])
                and end >= int(subset[-1]['end_monotonic_ns']) and row['forceAndReadbackBeforeBothAcks'] == 'true', 'Cycle timing closure')
        released=sum(start-origin <= int(x['arrival_offset_ns']) < end-origin for x in arrivals)
        cycles.append({'cycle':number,'durationNs':end-start,'rpcCount':high-low,'startOffsetNs':start-origin,'endOffsetNs':end-origin,
                       'arrivalsReleasedDuringCycle':released,'throughCommandSeq':int(row['throughCommandSeq'])})
    raw_metrics={'scheduledArrivals':6400,'releasedArrivals':len(arrivals),'notSent':0,'unknownObserved':0,'unknownFinal':0,
        'serverRejected':0,'confirmedAcceptedUniqueOrders':len(accepted_ids),'acceptedOrdersInArrivalWindow':within,
        'arrivalWindowGoodputPerSecond':within/12.8,'allArrivalP99Ns':nearest(latencies),
        'lastKnownReplyDrainNs':max(0,max(int(x['reply_completion_offset_ns']) for x in arrivals)-window),
        'schedulerLatenessOver20ms':sum(v>20_000_000 for v in lateness),'schedulerMaxLatenessNs':max(lateness)}
    for key,value in raw_metrics.items(): require(summary[key] == value, 'Raw versus reported metric differs: '+key)
    require(raw_metrics['schedulerLatenessOver20ms'] == 0, 'Invalid scheduler timing')
    require(summary['totalSourceDrainNs'] >= raw_metrics['lastKnownReplyDrainNs'], 'Source drain before final reply')
    require(window+summary['totalSourceDrainNs'] >= cycles[-1]['endOffsetNs'], 'Source drain before final maintenance end')
    per_kind={k:{'count':len(v),'totalElapsedNs':sum(v),'maxElapsedNs':max(v),'p99Ns':nearest(v),'failed':0} for k,v in rpc_kinds.items()}
    for k,m in per_kind.items():
        for field in ('count','totalElapsedNs','maxElapsedNs','failed'):
            require(summary['maintenanceRpcMetrics']['rpcKinds'][k][field] == m[field], 'Reported RPC metric mismatch')
    backlog=rows(load/'backlog.csv'); previous=-10**30
    for row in backlog:
        require(int(row['offset_ns'])>previous and 0<=int(row['queued'])<=8192 and 0<=int(row['pending'])<=128
                and int(row['maintenance_phase']) in (0,1) and 0<=int(row['released'])<=6400,'Invalid backlog sample')
        previous=int(row['offset_ns'])
    owners=[js(load/name) for name in ('owner-before-close.json','owner-after-close.json')]
    for owner in owners:
        require(owner['pendingLogicalCommands'] == owner['readyLogicalCommands'] == owner['activeFrames']
                == owner['unresolvedPossiblyExecutedLogicalCommands'] == owner['logicalNotSent'] == 0
                and owner['firstAcceptedLogicalCommands'] == owner['logicalAppliedResults'] == 6400
                and owner['failureType'] is None, 'Final owner closure mismatch')
    require(owners[-1]['closed'] is True and owners[-1]['ownerThreadAlive'] is False,'Owner thread close incomplete')
    transport=js(load/'transport-observations.json')
    require(transport and all(v['leaderMemberId'] == 0 and v['leadershipTermId'] == 0 and v['lineageId'] == cfg['lineage']
                and v['profileSha256'] == cfg['profileSha256'] and v['maintenanceEnabled'] is True
                and v['mtuLength'] == 1248 and not v['newLeaderEvents'] for v in transport),'Fixed load leader/term observation mismatch')
    final=js(arm/'final-position.json'); node_logs=[]
    for member in range(3):
        identity=js(arm/('node-%d-identity.json'%member)); log=raw(arm/('node-%d.log'%member))
        require(len(log)<=4*1024**2,'Node log cap exceeded'); text=log.decode('utf8','strict')
        expected='VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s'%(member,identity['pid'],cfg['profileSha256'],cfg['lineage'],cfg['actualCodeSha256'])
        require(text.count(expected)==1 and 'sync=2 mtu=1248 preparedArchiveCacheEnabled=true' in text
                and ('VECTOR_V3_SNAPSHOT_WRITTEN profile=%s lineage=%s hash=%s'%(cfg['profileSha256'],cfg['lineage'],final['combinedSha256'])) in text,
                'Node complete identity/checkpoint log mismatch')
        require('Exception' not in text and 'ERROR' not in text,'Node error log marker')
        node_logs.append({'member':member,'bytes':len(log),'lines':len(text.splitlines()),'pid':identity['pid'],
            'startTicks':identity['linuxStartTicks'],'commandSha256':identity['linuxCommandSha256'],
            'finalCheckpointSha256':final['combinedSha256']})
    return {'cap':cap,'config':cfg,'rawMetrics':raw_metrics,'arrivalLatencyP50Ns':nearest(latencies,.5),
        'replyDrainNsIndependentlyRecomputed':raw_metrics['lastKnownReplyDrainNs'],
        'totalSourceDrainNsReportedNotDirectlyRawTimestamped':summary['totalSourceDrainNs'],
        'finalMaintenanceEndDrainNsFromRawCycleReceipt':max(0,cycles[-1]['endOffsetNs']-window),
        'batchSizePhysicalFrameCounts':dict(batch_distribution),'physicalRequests':len(reqs),'physicalReplies':len(reps),
        'physicalOfferAttempts':len(offers),'negativeOffers':sum(int(x['return_code'])<0 for x in offers),
        'logicalMaintenanceRpcs':len(rpc_rows),'rpcKinds':per_kind,'cycles':cycles,
        'totalMaintenanceCycleNs':sum(x['durationNs'] for x in cycles),'totalLogicalRpcElapsedNs':sum(sum(v) for v in rpc_kinds.values()),
        'backlogSamples':len(backlog),'observedBacklogHighWater':max(int(x['queued']) for x in backlog),
        'sampledMaintenanceRows':sum(int(x['maintenance_phase']) == 1 for x in backlog),
        'nodeLogs':node_logs,'loadTransportObservations':len(transport),'finalOwnerUnknownUnresolvedCount':0,
        'classification':'VALID_FINITE_OVERLOAD','classificationReason':'500/s arrival window ends with replies still outstanding; long backlog/drain. Eventual acceptance is not 500/s stable service capacity.'}

def utc(value):
    # Coarse labels only: Python may reject Java Instant's 7..9 fractional digits.
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|\+00:00)', value)
    require(match is not None, 'Unexpected UTC format')
    whole = datetime.datetime.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return whole.replace(microsecond=int((match.group(2) or '').ljust(6,'0')[:6]))

def audit_telemetry(arms):
    path=JOB/'owned-cpu-rss-io-1hz.jsonl'; data=raw(path); samples=[json.loads(line) for line in data.splitlines()]
    receipt=js(JOB/'telemetry-receipt.json')
    require(receipt['samples'] == len(samples) == 47 and receipt['bytes'] == len(data) and receipt['sha256'] == hashlib.sha256(data).hexdigest(), 'Telemetry receipt closure')
    require(len(data)<=8*1024**2 and len(samples)<=512 and receipt['fsyncDuringLoad'] is False and receipt['afterClosureFsyncOnly'] is True, 'Telemetry bounded/closure mode')
    process=collections.defaultdict(list); unavailable=collections.Counter(); last_mono=-1; elapsed=-1; previous_utc=None
    for number,sample in enumerate(samples):
        require(sample['sample']==number and sample['monotonicNs']>last_mono and sample['elapsedSeconds']>elapsed,'Telemetry monotonic sample order')
        require(sample['clockTicksPerSecond']==100 and sample['pageSizeBytes']==4096,'Telemetry units differ')
        instant=utc(sample['atUtc']); require(previous_utc is None or instant>=previous_utc,'UTC sample regressed')
        last_mono,elapsed,previous_utc=sample['monotonicNs'],sample['elapsedSeconds'],instant
        for row in sample['owned']:
            if not row['available']:
                unavailable[row['role']]+=1; continue
            require(row['rssBytesFromStat']==row['rssPages']*4096,'RSS unit conversion')
            require(set(row['io'])=={'read_bytes','write_bytes','syscr','syscw'} and all(isinstance(v,int) and v>=0 for v in row['io'].values()),'IO closure')
            process[row['role']].append((sample,row))
    require(sum(unavailable.values())==receipt['metricUnavailableOrExitedSamples']==80,'Unavailable sample count mismatch')
    unavailable_reasons=collections.Counter(r.get('reason') for s in samples for r in s['owned'] if not r['available'])
    require(set(unavailable_reasons)=={'Registered exact process no longer alive'},'Unexpected unavailable telemetry reason')
    result={}
    for role, observed in sorted(process.items()):
        identities={(v['pid'],v['startTicks'],v['commandSha256']) for s,v in observed}; require(len(identities)==1,'Process identity changed')
        for (a,x),(b,y) in zip(observed,observed[1:]):
            require(y['userTicks']>=x['userTicks'] and y['systemTicks']>=x['systemTicks'] and all(y['io'][k]>=x['io'][k] for k in x['io']),'Process counter regressed')
        first,a=observed[0]; last,b=observed[-1]; duration=(last['monotonicNs']-first['monotonicNs'])/1e9
        record={'availableSamples':len(observed),'unavailableOrExitedSamples':unavailable[role],
            'firstUtc':first['atUtc'],'lastUtc':last['atUtc'],'observedDurationSeconds':duration,
            'sampledMaxVmRSSBytes':max(v['status']['VmRSSBytes'] for s,v in observed),
            'sampledMaxStatRSSBytes':max(v['rssBytesFromStat'] for s,v in observed),
            'cpuSecondsDelta':((b['userTicks']+b['systemTicks'])-(a['userTicks']+a['systemTicks']))/100,
            'kernelIODeltas':{k:b['io'][k]-a['io'][k] for k in a['io']},'identity':{'pid':a['pid'],'startTicks':a['startTicks'],'commandSha256':a['commandSha256']}}
        record['observedSpanAverageCores']=record['cpuSecondsDelta']/duration if duration else None
        if role.startswith('cap-'):
            cap=int(role.split('-')[1]); arm=next(a for a in arms if a['cap']==cap); start=utc(arm['config']['scheduledOriginUTC']); finish=start+datetime.timedelta(seconds=12.8)
            record['coarseUTCExposureAvailableSamples']=sum(start<=utc(s['atUtc'])<finish for s,v in observed)
            record['coarseUTCPostWindowAvailableSamples']=sum(utc(s['atUtc'])>=finish for s,v in observed)
            record['coarseUTCExposureIncompleteSampleFailures']=sum(not r['available'] and r['role']==role for s in samples if start<=utc(s['atUtc'])<finish for r in s['owned'])
            expected=next(v for v in arm['nodeLogs'] if v['member']==int(role.split('-')[-1]))
            require((a['pid'],a['startTicks'],a['commandSha256']) == (expected['pid'],expected['startTicks'],expected['commandSha256']), 'Telemetry versus Java identity receipt mismatch')
            selected=[(s,v) for s,v in observed if start<=utc(s['atUtc'])<finish]
            if len(selected)>=2:
                sa,x=selected[0]; sb,y=selected[-1]; span=(sb['monotonicNs']-sa['monotonicNs'])/1e9
                cpu=((y['userTicks']+y['systemTicks'])-(x['userTicks']+x['systemTicks']))/100
                record['coarseUTCExposureInteriorObservedSeconds']=span
                record['coarseUTCExposureInteriorAverageCores']=cpu/span
                record['coarseUTCExposureInteriorKernelIODeltas']={k:y['io'][k]-x['io'][k] for k in x['io']}
        result[role]=record
    require(set(result)=={'pilot-parent'}|{'cap-%d-node-%d'%(c,n) for c in (1,4) for n in range(3)}, 'Telemetry process set')
    return {'samples':len(samples),'bytes':len(data),'unavailableOrExitedRecords':sum(unavailable.values()),'unavailableByRole':dict(unavailable),
        'unavailableReasons':dict(unavailable_reasons),
        'firstUtc':samples[0]['atUtc'],'lastUtc':samples[-1]['atUtc'],'lastPhase':samples[-1]['phase'],'processes':result,
        'fineJavaPythonMonotonicAlignmentValidated':False,'phaseMethod':'Coarse UTC labels only, Java origin Instant is approximate and Python UTC sampling is not atomic. CPU deltas use only Python monotonic times on identical PID/startTicks/argv SHA.',
        'scope':'1 Hz sampled owned process CPU/RSS/kernel IO; observed spans include startup/load/maintenance/shutdown. Missing/exited counters are explicit; no zeros invented. No pure force/fsync latency or independent storage saturation inference.'}

def main():
    release=js(JOB/'release.json')
    require(INPUTS['raw-files/job/release.json']['sha256'] == 'f56126dab203c80b42f950fa7037fb0b58e52103bf4f6fb86e7f578b0bd4dfa4'
        and release['sourceCommit'] == '4102446b333573efde2b33a0eb53a8177575bad5','Frozen source/release binding')
    arms=[audit_arm(c) for c in (1,4)]
    require(all(a['config']['actualCodeSha256']==release['codeFingerprint'] and a['config']['profileSha256']==release['profileFingerprint'] for a in arms),'Release runtime fingerprints differ')
    telemetry=audit_telemetry(arms)
    result={'passed':True,'scope':'Independent LOCAL raw audit only; no cloud access, source mutation, git stage/commit or benchmark launch.',
        'sourceCommit':'4102446b333573efde2b33a0eb53a8177575bad5','arms':arms,'telemetry':telemetry,
        'limitations':['One cap1 then one cap4, distinct fresh lineages, no ABAB or performance promotion.',
            'Both arms are finite overload, not stable throughput maximum or sustained p99 SLA.',
            'Raw reply drain independently computed; full source drain is reported and checked only for ordering, since its exact terminal timestamp has no separate raw event.',
            'Arrival p99 includes queuing and maintenance from scheduled arrival through observed reply completion; it is not matching-core or network-only latency.',
            'Logical RPC elapsed includes caller wait, transport, server, scheduling and raw trace writes; cannot isolate fsync or unique bottleneck.',
            'Same host, three JVM nodes, shared overlay/storage/CPU; no independent-host network or storage durability proof.',
            'Telemetry 1 Hz is sampled and introduces overhead; Java/Python monotonic alignment is not validated.',
            'No 100M cumulative/s/connection target or production safety proven.'], 'inputs':INPUTS}
    (HERE/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'passed':True,'rawMetrics':{a['cap']:a['rawMetrics'] for a in arms},'telemetrySamples':telemetry['samples'],'inputs':len(INPUTS)},indent=2))

if __name__=='__main__': main()
