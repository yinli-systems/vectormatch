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
import traceback
from common import CHUNKS,audit_arguments,egress,egress_progress

HERE = pathlib.Path(__file__).resolve().parent
COLLECTION = None
JOB = None
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
    arm = JOB / 'chunk-pair' / ('chunk-%d' % cap); load = arm/'load'; maint = load/'maintenance'
    cfg = js(load/'configuration.json'); summary = js(load/'load-result.json')
    require(cfg['arrivals'] == 6400 and cfg['ratePerSecond'] == 500 and cfg['windowSeconds'] == 12.8 and cfg['batchCap'] == 4 and cfg['archiveChunkBytes']==cap and cfg['eventFetchCount']==16 and cfg['commonChunkEnvelope'] is True, 'Fixed source configuration')
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
        require(frame['decoded']['kind'] == 'BusinessBatch' and len(frame['decoded']['members']) <= 4, 'Business batch cap mismatch')
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
    require(len(rpc_rows) == len(logical_requests) == len(logical_replies) == (1785 if cap==3072 else 1298), 'Logical RPC count closure')
    rpc_kinds=collections.defaultdict(list); previous_end=-1
    for number,(row,req,rep) in enumerate(zip(rpc_rows,logical_requests,logical_replies),1):
        request_value,reply_value=req['decoded'],rep['decoded']; correlation=int(row['correlation_id'])
        start,end,elapsed=map(int,(row['start_monotonic_ns'],row['end_monotonic_ns'],row['elapsed_ns']))
        require(int(row['rpc']) == number and row['completed'] == 'true' and end-start == elapsed and elapsed >= 0 and start >= previous_end, 'RPC timing invalid')
        previous_end=end
        require(correlation == request_value['correlation'] == reply_value['correlation'] and row['kind'] == request_value['kind'], 'RPC correlation/kind mismatch')
        require(request_by_correlation[correlation]['sha'] == req['sha'] and reply_by_correlation[correlation]['sha'] == rep['sha'], 'Logical-to-physical RPC wire mismatch')
        require(reply_value['tag'] == {'PrepareArchive':3,'ArchiveChunk':4,'FetchEvents':2,'ArchiveCommit':1,'EventAck':1}[row['kind']], 'RPC reply tag mismatch')
        if request_value['kind']=='ArchiveChunk':
            require(row['archive_chunk_requested_bytes']==str(request_value['count']) and row['event_fetch_requested_count']=='', 'Archive requested-count CSV differs from actual wire')
            require(1<=request_value['count']<=cap,'Selected chunk bound exceeded')
        elif request_value['kind']=='FetchEvents':
            require(row['event_fetch_requested_count']==str(request_value['count']) and row['archive_chunk_requested_bytes']=='', 'Event requested-count CSV differs from actual wire')
            require(1<=request_value['count']<=16,'Fixed event page bound exceeded')
        else:
            require(row['archive_chunk_requested_bytes']==row['event_fetch_requested_count']=='','Spurious selected-count CSV fields')
        rpc_kinds[row['kind']].append(elapsed)
    require({k:len(v) for k,v in rpc_kinds.items()} == {'PrepareArchive':3,'ArchiveChunk':(975 if cap==3072 else 488),'FetchEvents':801,'ArchiveCommit':3,'EventAck':3}, 'RPC kind inventory differs')
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
    prefix_checks=audit_prefixes(arm,cap,cycles,rpc_rows,logical_requests,logical_replies)
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
    egress_report=audit_egress(arm,cap,cfg,summary,reps,transport)
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
    return {'archiveChunkBytes':cap,'batchCap':4,'config':cfg,'prefixReadback':prefix_checks,'egressAssociationAttestation':egress_report,'rawMetrics':raw_metrics,'arrivalLatencyP50Ns':nearest(latencies,.5),
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
        'classification':('VALID_FINITE_OVERLOAD' if within<6400 else 'VALID_FINITE_WINDOW_OBSERVATION'),'classificationReason':'One finite exposure; eventual acceptance and window replies do not prove sustained capacity. Overload classification requires replies outstanding at window end; no performance promotion from one pair.'}

def utc(value):
    # Coarse labels only: Python may reject Java Instant's 7..9 fractional digits.
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|\+00:00)', value)
    require(match is not None, 'Unexpected UTC format')
    whole = datetime.datetime.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return whole.replace(microsecond=int((match.group(2) or '').ljust(6,'0')[:6]))

def audit_telemetry(arms):
    path=JOB/'owned-cpu-rss-io-1hz.jsonl'; data=raw(path); samples=[json.loads(line) for line in data.splitlines()]
    receipt=js(JOB/'telemetry-receipt.json')
    require(receipt['samples'] == len(samples) and 2<=len(samples)<=512 and receipt['bytes'] == len(data) and receipt['sha256'] == hashlib.sha256(data).hexdigest(), 'Telemetry receipt closure')
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
    require(sum(unavailable.values())==receipt['metricUnavailableOrExitedSamples'],'Unavailable sample count mismatch')
    unavailable_reasons=collections.Counter(r.get('reason') for s in samples for r in s['owned'] if not r['available'])
    require(set(unavailable_reasons)<={'Registered exact process no longer alive'},'Unexpected unavailable telemetry reason')
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
        if role.startswith('chunk-'):
            cap=int(role.split('-')[1]); arm=next(a for a in arms if a['archiveChunkBytes']==cap); start=utc(arm['config']['scheduledOriginUTC']); finish=start+datetime.timedelta(seconds=12.8)
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
    require(set(result)=={'pilot-parent'}|{'chunk-%d-node-%d'%(c,n) for c in CHUNKS for n in range(3)}, 'Telemetry process set')
    return {'samples':len(samples),'bytes':len(data),'unavailableOrExitedRecords':sum(unavailable.values()),'unavailableByRole':dict(unavailable),
        'unavailableReasons':dict(unavailable_reasons),
        'firstUtc':samples[0]['atUtc'],'lastUtc':samples[-1]['atUtc'],'lastPhase':samples[-1]['phase'],'processes':result,
        'fineJavaPythonMonotonicAlignmentValidated':False,'phaseMethod':'Coarse UTC labels only, Java origin Instant is approximate and Python UTC sampling is not atomic. CPU deltas use only Python monotonic times on identical PID/startTicks/argv SHA.',
        'scope':'1 Hz sampled owned process CPU/RSS/kernel IO; observed spans include startup/load/maintenance/shutdown. Missing/exited counters are explicit; no zeros invented. No pure force/fsync latency or independent storage saturation inference.'}

def terminal_inventory(chunk):
    load=JOB/'chunk-pair'/('chunk-'+str(chunk))/'load'
    table=rows(load/'arrivals.csv');require(len(table)==6400,'All planned arrival rows required, including failures')
    counts=collections.Counter();accepted=[];reply_times=[];order_ids=set();duplicates=0;within=0
    for index,row in enumerate(table):
        require(int(row['arrival_index'])==index and int(row['worker'])==index%128 and row['producer']=='load-w%d'%(index%128) and int(row['request_seq'])==1+index//128 and int(row['scheduled_offset_ns'])==index*2000000,'Every planned identity/schedule must close')
        counts[row['status']]+=1
        if row['arrival_offset_ns']!='':counts['released']+=1
        if row['unknown_observed_offset_ns']!='':counts['initialUNKNOWN']+=1
        if row['status'] in ('UNKNOWN_FINAL','PENDING'):counts['finalUNKNOWN']+=1
        if row['status']=='NOT_SENT':counts['notSent']+=1
        if row['initial_server_admission_status']=='ADMISSION_REJECTED':counts['initialAdmissionRejected']+=1
        if row['status']=='APPLIED':
            if row['result_code']!='ACCEPTED':counts['businessRejected']+=1
            if row['reply_completion_offset_ns']!='':reply_times.append(int(row['reply_completion_offset_ns'])-int(row['scheduled_offset_ns']))
            if row['result_code']=='ACCEPTED':
                oid=int(row['order_id']);duplicates+=oid in order_ids or not 2<=oid<=6401;order_ids.add(oid)
                if row['reply_completion_offset_ns']!='':
                    end=int(row['reply_completion_offset_ns']);accepted.append(end-int(row['scheduled_offset_ns']));within+=end<=12800000000
    all_accepted=len(accepted)==6400 and len(order_ids)==6400 and duplicates==0
    return {'rows':len(table),'allIdentitiesAndSchedulesVerified':True,'counts':dict(counts),'acceptedUniqueOrders':len(order_ids),'duplicateOrOutOfRangeAcceptedOrderIds':duplicates,'acceptedRepliesInsideWindow':within,'arrivalWindowGoodputPerSecond':within/12.8,'allArrivalAcceptedP99Ns':nearest(accepted) if all_accepted else None,'acceptedConditionalP99Ns':nearest(accepted),'completedReplyConditionalP99Ns':nearest(reply_times),'policy':'All-arrival accepted p99 is null unless every planned arrival has one distinct accepted result; unknown/notSent/rejected rows remain counted.'}

def audit_prefixes(arm,chunk,cycles,rpc_rows,requests,replies):
    maint=arm/'load/maintenance';reply_blob=raw(maint/'logical-rpc-replies.bin');previous_chain=None;previous_command=0;previous_event=0;reports=[]
    for cycle in cycles:
        row=properties(maint/('cycle-%d.verified.txt'%cycle['cycle']));low,high=int(row['logicalRpcCountAtStart']),int(row['logicalRpcCountAtEnd'])
        require(row['archiveChunkBytes']==str(chunk) and row['eventFetchCount']=='16','Cycle selected policy differs')
        pairs=list(zip(requests[low:high],replies[low:high]));require(pairs[0][0]['decoded']['kind']=='PrepareArchive','Cycle starts with prepare barrier')
        descriptor=pairs[0][1]['decoded'];acknowledgement=descriptor['ack'];total=descriptor['total'];require(acknowledgement[2]==previous_command+1 and acknowledgement[3]==cycle['throughCommandSeq'],'Exact command range')
        if previous_chain is not None:require(acknowledgement[4]==previous_chain,'Archive chain continuity')
        payload=bytearray();event_values=[];event_frames=[];commits=[];event_acks=[]
        for req,rep in pairs[1:]:
            q,v=req['decoded'],rep['decoded']
            if q['kind']=='ArchiveChunk':
                require(q['ack']==v['ack']==acknowledgement and q['total']==v['total']==total and q['offset']==v['offset']==len(payload),'Exact descriptor/offset chunk binding')
                require(q['count']==min(chunk,total-len(payload)) and len(v['chunk'])==q['count'],'Actual selected chunk length');payload.extend(v['chunk'])
            elif q['kind']=='FetchEvents':
                require(q['fromEvent']==previous_event+len(event_values)+1 and 1<=q['count']<=16 and len(v['events'])==q['count'],'Complete event page binding')
                for event in v['events']:require(event[0]==previous_event+len(event_values)+1,'Exact event prefix continuity');event_values.append(event)
                event_frames.append(reply_blob[rep['offset']:rep['offset']+4+rep['bytes']])
            elif q['kind']=='ArchiveCommit':commits.append(q)
            elif q['kind']=='EventAck':event_acks.append(q)
            else:raise AssertionError('Unexpected cycle operation')
        require(len(payload)==total and hashlib.sha256(payload).hexdigest()==acknowledgement[6],'Complete canonical payload SHA')
        require(len(commits)==len(event_acks)==1 and commits[0]['ack']==acknowledgement and event_acks[0]['throughEvent']==int(row['throughEventSeq']),'Exact destructive ACK targets')
        require(previous_event+len(event_values)==int(row['throughEventSeq']),'Full event prefix total')
        for field,expected in [('archiveFile',bytes(payload)),('eventFile',b''.join(event_frames))]:
            name=pathlib.PurePosixPath(row[field]).name;require(re.fullmatch(r'\d{4}-(archive|events)\.bin',name) is not None,'Bounded immutable writer path')
            require(raw(arm/'load/writer'/name)==expected,'Logical raw transfer versus durable writer file differs')
        previous_chain=acknowledgement[5];previous_command=acknowledgement[3];previous_event=int(row['throughEventSeq'])
        reports.append({'cycle':cycle['cycle'],'archiveBytes':total,'archiveChunkRpcs':math.ceil(total/chunk),'eventCount':len(event_values),'eventFetchRpcs':math.ceil(len(event_values)/16),'archivePayloadSha256':acknowledgement[6],'durableWriterBytesEqualRawTransfers':True})
    require(sum(x['archiveChunkRpcs'] for x in reports)==(975 if chunk==3072 else 488) and sum(x['eventFetchRpcs'] for x in reports)==801,'Prospective inventory independently checked against actual prefix sizes')
    return reports

def audit_egress(arm,chunk,cfg,summary,replies,observations):
    geometry=None;previous=-1;per_image={};previous_bounds=None
    for sample in observations:
        require(sample['archiveChunkBytes']==chunk,'Observed chunk policy differs');bounds=sample['actualEgressBounds'];current=egress(bounds)
        if previous_bounds is not None:egress_progress(previous_bounds,bounds)
        geometry=current;previous_bounds=bounds
        require(bounds['replyHeaderImageAssociations']>=previous,'Association counters regressed');previous=bounds['replyHeaderImageAssociations']
        for image in bounds['images']:
            key=image['imageCorrelationId'];require(image['associatedApplicationReplies']>=per_image.get(key,-1),'Per-Image counter regressed');per_image[key]=image['associatedApplicationReplies']
    functional=js(arm/'functional-result.json');terminal=functional['actualEgressBounds'];egress_progress(previous_bounds,terminal);geometry=egress(terminal)
    source_terminal=summary['physicalOfferTape']['lastActualTransportObservation']['actualEgressBounds'];require(source_terminal==terminal,'Functional/source terminal egress attestation differs');egress(source_terminal)
    require(terminal['replyHeaderImageAssociations']==source_terminal['replyHeaderImageAssociations']==summary['physicalOfferTape']['recordedReplies']==len(replies) and terminal['replyHeaderImageAssociations']>=previous,'Raw total versus runtime Header associations differs')
    require(max(x['largestObservedApplicationReplyBytes'] for x in terminal['images'])==max(x['bytes'] for x in replies),'Actual observed maximum reply versus raw tape differs')
    return {'geometry':geometry,'rawReplyCount':len(replies),'runtimeAssociatedReplies':terminal['replyHeaderImageAssociations'],'largestRawReplyBytes':max(x['bytes'] for x in replies),'scope':'Source-enforced per-callback actual Header/Image validation with independently reconciled aggregate counts/geometry. Raw reply tape has no Image ID; no independent per-reply Image mapping claimed.'}

def main():
    global COLLECTION,JOB,HERE
    a,c,release=audit_arguments(__doc__);COLLECTION=a.collection;JOB=COLLECTION/'raw-files/job';HERE=a.out
    try:
        actual=js(JOB/'release.json')
        require(INPUTS['raw-files/job/release.json']['sha256']==c['releaseSha256'] and actual==release,'Frozen source/release binding')
        inventories={str(chunk):terminal_inventory(chunk) for chunk in CHUNKS}
        (HERE/'all-arrival-terminal-inventory.json').write_text(json.dumps(inventories,indent=2)+'\n')
        arms=[audit_arm(chunk) for chunk in CHUNKS]
        require(all(arm['config']['actualCodeSha256']==release['codeFingerprint'] and arm['config']['profileSha256']==release['profileFingerprint'] for arm in arms),'Release runtime fingerprints differ')
        telemetry=audit_telemetry(arms)
        result={'passed':True,'round':c['round'],'scope':'Independent LOCAL strict successful-round raw audit. No SSH, Git, process launch or mutation of raw inputs. Nonzero/partial outcomes retain an all-arrival inventory and fail strict closure rather than being hidden.','sourceCommit':release['sourceCommit'],'releaseSha256':c['releaseSha256'],'arms':arms,'telemetry':telemetry,'inputs':INPUTS,
            'limitations':['One round is one ordered A/B pair; full ABAB requires independently closed and root-attested round 1 before round 2. No automatic promotion.','Finite same-host three-JVM source, no sustained maximum, independent-host network/storage durability, zero-latency or 100M claim.','Last reply and final maintenance boundary drains are recomputed; totalSourceDrainNs is reported and ordered, without separately logged terminal event.','RPC elapsed includes caller wait, transport, server, scheduling and evidence writes, not pure fsync.','Actual per-callback Header/Image association is source enforced and aggregate counters close against raw reply totals; raw reply tape contains NO Image ID, so independent per-reply Image mapping is not claimed.','Telemetry is bounded/sampled; Java/Python monotonic alignment is not validated and UTC phase labels are coarse.']}
        (HERE/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'passed':True,'round':c['round'],'rawMetrics':{arm['archiveChunkBytes']:arm['rawMetrics'] for arm in arms},'telemetrySamples':telemetry['samples'],'inputs':len(INPUTS)},indent=2))
    except BaseException as error:
        (HERE/'failure.json').write_text(json.dumps({'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'inputs':INPUTS,'rawInputsUnchanged':True,'partialReportsRetained':True},indent=2)+'\n');raise

if __name__=='__main__':main()
