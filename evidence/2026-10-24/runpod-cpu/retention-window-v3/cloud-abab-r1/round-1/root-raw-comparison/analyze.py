#!/usr/bin/env python3
"""Local-only additional performance analysis, using the frozen wire decoder."""
import collections
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
PREP = BASE / 'window-cloud-preparation-r1'
COLLECTION = BASE / 'window-cloud-collection-round-1-r1' / 'collection'
JOB = COLLECTION / 'raw-files/job'
INPUTS = {}


def need(value, reason):
    if not value:
        raise AssertionError(reason)


def raw(path):
    value = path.read_bytes()
    key = str(path.relative_to(BASE))
    binding = {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    need(key not in INPUTS or INPUTS[key] == binding, 'Input changed during analysis')
    INPUTS[key] = binding
    return value


def js(path):
    return json.loads(raw(path))


def table(path):
    return list(csv.DictReader(raw(path).decode('ascii').splitlines()))


def quantiles(values):
    ordered = sorted(values)
    return {name: ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]
            for name, fraction in [('p50', .5), ('p90', .9), ('p95', .95),
                                   ('p99', .99), ('p999', .999), ('max', 1)]}


frozen = js(PREP / 'LOCAL_PREPARATION_FROZEN.json')
for name in ('audit_raw.py', 'common.py', 'read_phase_audit.py'):
    value = raw(PREP / name)
    need(len(value) == frozen['files'][name]['bytes'] and
         hashlib.sha256(value).hexdigest() == frozen['files'][name]['sha256'],
         'Decoder or its dependency differs from frozen preparation')
sys.path.insert(0, str(PREP))
spec = importlib.util.spec_from_file_location('frozen_wire_decoder', PREP / 'audit_raw.py')
decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decoder)
decoder.COLLECTION = COLLECTION
# All decoder input reads participate in this analysis' before/after binding.
decoder.raw = raw


def analyze_arm(window):
    arm = JOB / 'read-window-pair' / ('window-%d' % window)
    load = arm / 'load'
    maint = load / 'maintenance'
    cfg = js(load / 'configuration.json')
    summary = js(load / 'load-result.json')
    need(cfg['arrivals'] == 6400 and cfg['readWindow'] == window and
         cfg['batchCap'] == 4 and cfg['archiveChunkBytes'] == 6144 and
         cfg['eventFetchCount'] == 16 and cfg['ratePerSecond'] == 500 and
         cfg['windowSeconds'] == 12.8, 'Unexpected workload factor')
    arrivals = table(load / 'arrivals.csv')
    need(len(arrivals) == 6400, 'Missing arrival rows')
    reqs = decoder.frames(load / 'physical-requests.bin', True, decoder.request)
    reps = decoder.frames(load / 'physical-replies.bin', True, decoder.reply)
    q = decoder.correlation_map(reqs)
    callbacks = decoder.correlation_map(reps, False)
    need(set(q) == set(callbacks), 'Request/callback identity closure')
    first_reply = {k: min(v, key=lambda f: f['at']) for k, v in callbacks.items()}
    offers = table(load / 'physical-offer-codes.csv')
    positive = collections.Counter()
    negative = 0
    for index, row in enumerate(offers, 1):
        corr = int(row['correlation_id'])
        need(int(row['attempt']) == index and corr in q and
             int(row['wire_offset']) == q[corr]['offset'] and
             int(row['offset_ns']) >= q[corr]['at'], 'Offer-to-wire binding')
        if int(row['return_code']) >= 0:
            positive[corr] += 1
        else:
            negative += 1
    need(set(positive) == set(q) and all(v == 1 for v in positive.values()),
         'Actual run must have exactly one positive admission per physical frame')
    for frame in reqs + reps:
        need(frame['decoded']['profile'] == cfg['profileSha256'] and
             frame['decoded']['lineage'] == cfg['lineage'], 'Wire scope differs')

    components = collections.defaultdict(list)
    bound_members = set()
    order_ids, command_seqs, identities = set(), set(), set()
    inside = 0
    completion_offsets = []
    timestamp_columns = ('scheduled_offset_ns', 'arrival_offset_ns',
                         'dispatch_offset_ns', 'submit_offset_ns',
                         'first_wire_offer_call_offset_ns',
                         'first_successful_offer_return_offset_ns',
                         'reply_completion_offset_ns')
    for index, row in enumerate(arrivals):
        need(int(row['arrival_index']) == index and int(row['worker']) == index % 128 and
             row['producer'] == 'load-w%d' % (index % 128) and
             int(row['request_seq']) == 1 + index // 128 and
             int(row['scheduled_offset_ns']) == index * 2_000_000,
             'Arrival identity or open-loop schedule differs')
        need(row['status'] == 'APPLIED' and row['result_code'] == 'ACCEPTED' and
             row['unknown_observed_offset_ns'] == '' and row['not_sent_reason'] == '0' and
             row['reply_replayed'] == 'false' and row['initial_server_admission_status'] == '',
             'Nonaccepted/unknown/notSent/replayed arrival invalidates all-arrival metric')
        times = [int(row[k]) for k in timestamp_columns]
        need(times == sorted(times), 'Timestamp order invalid')
        corr, member_index = int(row['correlation_id']), int(row['batch_index'])
        frame, answer = q[corr], first_reply[corr]
        need(frame['decoded']['kind'] == 'BusinessBatch' and
             answer['decoded']['tag'] == 5 and answer['decoded']['error'] == '',
             'Arrival lacks accepted business wire')
        need(times[4] <= frame['at'] <= times[5] and times[-1] >= answer['at'],
             'Arrival timestamps do not contain raw wire observations')
        member = frame['decoded']['members'][member_index]
        result = answer['decoded']['members'][member_index]
        need(member['producer'] == result['producer'] == row['producer'] and
             member['seq'] == result['seq'] == int(row['request_seq']) and
             member['account'] == result['account'] == 2 and
             member['sha'] == result['sha'] == row['command_sha256'], 'CSV-to-wire member identity')
        need(result['index'] == member_index and result['status'] == 0 and
             result['result']['code'] == 0 and result['replayed'] is False and
             int(row['admitted_physical_offers']) == positive[corr], 'Business result/admission differs')
        for column, key in [('command_seq', 'commandSeq'), ('order_id', 'orderId'),
                            ('remaining_quantity', 'remaining'), ('trade_count', 'trades')]:
            need(int(row[column]) == result['result'][key], 'CSV-to-wire result differs')
        identity = (row['producer'], int(row['request_seq']))
        binding = (corr, member_index)
        need(identity not in identities and binding not in bound_members and
             int(row['order_id']) not in order_ids and int(row['command_seq']) not in command_seqs,
             'Duplicate business execution or CSV identity')
        identities.add(identity)
        bound_members.add(binding)
        order_ids.add(int(row['order_id']))
        command_seqs.add(int(row['command_seq']))
        components['allArrivalScheduleToReply'].append(times[-1] - times[0])
        components['schedulerLateness'].append(times[1] - times[0])
        components['arrivalToDispatch'].append(times[2] - times[1])
        components['dispatchToFirstSuccessfulOfferReturn'].append(times[5] - times[2])
        components['firstSuccessfulOfferReturnToReplyCompletion'].append(times[-1] - times[5])
        completion_offsets.append(times[-1])
        inside += times[-1] <= 12_800_000_000
    need(order_ids == set(range(2, 6402)) and command_seqs == set(range(4, 6404)),
         'Order/command frontiers differ')
    business = [f for f in reqs if f['decoded']['kind'] == 'BusinessBatch']
    expected_members = {(f['decoded']['correlation'], i)
                        for f in business for i in range(len(f['decoded']['members']))}
    need(bound_members == expected_members, 'Unbound or duplicate business wire members')
    distribution = collections.Counter(len(f['decoded']['members']) for f in business)
    kind_counts = collections.Counter(f['decoded']['kind'] for f in reqs)
    latencies = {k: quantiles(v) for k, v in components.items()}
    metrics = {'acceptedDistinctArrivals': len(arrivals), 'acceptedInsideArrivalWindow': inside,
               'arrivalWindowGoodputPerSecond': inside / 12.8,
               'allArrivalP99Ns': latencies['allArrivalScheduleToReply']['p99'],
               'lastKnownReplyDrainNs': max(0, max(completion_offsets) - 12_800_000_000)}
    for key, value in metrics.items():
        if key in summary:
            need(summary[key] == value, 'Raw recomputation differs from runtime summary')

    rpc_rows = table(maint / 'logical-rpc-timings.csv')
    logical_q = decoder.frames(maint / 'logical-rpc-requests.bin', False, decoder.request)
    logical_r = decoder.frames(maint / 'logical-rpc-replies.bin', False, decoder.reply)
    phase = decoder.audit_rpc_phases(rpc_rows, logical_q, logical_r, reqs, reps, offers,
                                     cfg['scheduledOriginMonotonicNs'], window)
    origin = cfg['scheduledOriginMonotonicNs']
    business_offer_times = [int(r['offset_ns']) + origin for r in offers
                            if q[int(r['correlation_id'])]['decoded']['kind'] == 'BusinessBatch']
    cycles = []
    previous_end = previous_rpc_end = 0
    for number in range(1, 4):
        values = dict(line.split('=', 1) for line in
                      raw(maint / ('cycle-%d.verified.txt' % number)).decode('ascii').splitlines() if '=' in line)
        start, end = int(values['cycleStartedMonotonicNs']), int(values['cycleEndedMonotonicNs'])
        low, high = int(values['logicalRpcCountAtStart']), int(values['logicalRpcCountAtEnd'])
        subset = rpc_rows[low:high]
        need(int(values['cycle']) == number and start >= previous_end and low == previous_rpc_end and
             subset[0]['kind'] == 'PrepareArchive' and subset[-1]['kind'] == 'EventAck' and
             start <= int(subset[0]['start_monotonic_ns']) <=
             int(subset[-1]['end_monotonic_ns']) <= end, 'Cycle endpoint/order closure')
        need(not any(start <= t < end for t in business_offer_times),
             'Business physical offer overlaps full maintenance cycle')
        need(int(values['readWindow']) == window and values['forceAndReadbackBeforeBothAcks'] == 'true',
             'Cycle receipt factor/durability-order field differs')
        cycle = {'cycle': number, 'recordedStartMonotonicNs': start, 'recordedEndMonotonicNs': end,
                 'recordedWallDurationNs': end - start, 'logicalRpcs': high - low,
                 'startOffsetNs': start - origin, 'endOffsetNs': end - origin,
                 'arrivalsReleasedDuringCycle': sum(start - origin <= int(r['arrival_offset_ns']) < end - origin
                                                    for r in arrivals),
                 'businessOffersDuringCycle': 0,
                 'sumRpcElapsedNsNotWallTime': sum(int(r['elapsed_ns']) for r in subset)}
        cycles.append(cycle)
        previous_end, previous_rpc_end = end, high
    need(previous_rpc_end == len(rpc_rows) == 1298, 'Cycle/RPC inventory closure')
    backlog = table(load / 'backlog.csv')
    return {'readWindow': window, 'rawMetrics': metrics, 'latencyComponentQuantilesNs': latencies,
            'componentPercentilesAreNotAdditive': True,
            'businessBatchSizeDistributionFrames': dict(sorted(distribution.items())),
            'businessOrdersFromDecodedFrames': sum(k * v for k, v in distribution.items()),
            'businessFrames': len(business), 'meanOrdersPerBusinessFrame': 6400 / len(business),
            'framesSavedByBatchingVersusOnePerOrder': 6400 - len(business),
            'physicalRequestsByKind': dict(kind_counts), 'allPhysicalRequests': len(reqs),
            'allPositiveAdmissions': sum(positive.values()), 'extraPositiveAdmissions': 0,
            'negativeOffers': negative, 'allPhysicalCallbacks': len(reps),
            'extraCallbacks': len(reps) - len(callbacks),
            'all6400ArrivalsBoundExactlyOnceToPhysicalRequestAndAcceptedReply': True,
            'cycles': cycles, 'totalRecordedMaintenanceCycleWallNs': sum(c['recordedWallDurationNs'] for c in cycles),
            'cycleWallScope': 'Recorded coordinator cycle start/end endpoints, independently subtracted and cross-checked against complete RPC ranges and absence of business offers; not kernel/fsync attribution.',
            'readPhaseObservedLowerBounds': phase['readPhases'],
            'wireObservedPositiveOfferAwaitingFirstCallbackHighWater': phase['actualOfferedHighWater'],
            'retainedConsumeIntervalsIndependentlyReconstructed': False,
            'backlogSamples': {'rows': len(backlog), 'maxSampledAggregateQueued': max(int(r['queued']) for r in backlog),
                               'maxSampledPending': max(int(r['pending']) for r in backlog),
                               'scope': 'Sampled observations, not continuous queue maxima or per-worker source high-water.'}}


arms = [analyze_arm(1), analyze_arm(8)]
need(arms[1]['allPositiveAdmissions'] - arms[0]['allPositiveAdmissions'] ==
     arms[1]['businessFrames'] - arms[0]['businessFrames'] == 1628,
     'Admission difference is not exactly the business frame-count difference')
need(arms[0]['physicalRequestsByKind'].keys() == arms[1]['physicalRequestsByKind'].keys() and
     all(arms[0]['physicalRequestsByKind'][k] == arms[1]['physicalRequestsByKind'][k]
         for k in arms[0]['physicalRequestsByKind'] if k != 'BusinessBatch'),
     'Maintenance physical request counts changed')
report = {'schema': 'window-round1-independent-performance-analysis-v1', 'passed': True,
          'scope': 'One finite fixed-order pair, 6400 orders per arm at planned500/s; no stable-capacity, absolute-realtime, endurance or independent-host claim.',
          'armOrder': [1, 8], 'preregisteredTotalOrder': [1, 8, 1, 8],
          'counterbalancedOrder': False, 'fixedOrderDriftLimitation': True,
          'rawWireDecoderReusedFromFrozenPreparation': True,
          'performanceAndBatchCalculationsIndependentOfRuntimeSummary': True,
          'nativeAndOriginalPostgresProtectionIndependentlyAuditedHere': False,
          'arms': arms,
          'comparisons': {'allArrivalP99ReductionFraction': 1 - arms[1]['rawMetrics']['allArrivalP99Ns'] / arms[0]['rawMetrics']['allArrivalP99Ns'],
                          'recordedMaintenanceCycleWallReductionFraction': 1 - arms[1]['totalRecordedMaintenanceCycleWallNs'] / arms[0]['totalRecordedMaintenanceCycleWallNs'],
                          'extraPhysicalAdmissionsExplainedExactlyByAdditionalBusinessFrames': 1628,
                          'goodputImprovementObserved': False},
          'limitations': ['No change to preregistered same-order ABAB; it is not a counterbalanced experiment.',
                          'Finite tail orders and a trailing maintenance cycle do not establish persistent500/s queue growth or sustained capacity.',
                          'Per-RPC coordinator elapsed intervals overlap under pipelining; their sum is not maintenance wall time.',
                          'Component percentiles are over the same6400 arrivals but cannot be added to reconstruct total p99.',
                          'Batch distributions explain the complete admission-count difference; shorter pauses are a plausible reason for less batch filling, not a separately isolated causal factor.',
                          'Wire positive-admission intervals establish observed read overlap; retained-slot/consume timestamps are not independently recorded.']}
for key, binding in INPUTS.items():
    value = (BASE / key).read_bytes()
    need(len(value) == binding['bytes'] and hashlib.sha256(value).hexdigest() == binding['sha256'],
         'Input changed before final output')
report['inputFiles'] = INPUTS
report['allInputsUnchangedAfterAnalysis'] = True
target = OUT / 'comparison.json'
with target.open('x') as out:
    json.dump(report, out, indent=2, sort_keys=True)
    out.write('\n')
print(json.dumps({'passed': True, 'report': str(target),
                  'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'inputs': len(INPUTS),
                  'metrics': [a['rawMetrics'] for a in arms],
                  'maintenanceCycleWallNs': [a['totalRecordedMaintenanceCycleWallNs'] for a in arms]}, indent=2))
