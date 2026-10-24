#!/usr/bin/env python3
"""Read-only resource context for two frozen trials; output is CREATE_NEW.

Each JSONL is read once: hash all original bytes, parse only through the first
sample after arrival end. No CSV, subprocess, network or source-state mutation.
"""
import argparse
import calendar
import datetime as dt
from decimal import Decimal
import hashlib
import json
from pathlib import Path

JOBS = ('cpu-capacity-18000-w128-r1', 'cpu-capacity-18000-w128-r2')
PROCESSES = ('load', 'node-0', 'node-1', 'node-2')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc_ns(value):
    require(value.endswith('Z') or value.endswith('+00:00'), 'Only explicit UTC accepted')
    text = value[:-1] if value.endswith('Z') else value[:-6]
    whole, _, fraction = text.partition('.')
    require(len(fraction) <= 9 and (not fraction or fraction.isdigit()), 'Invalid UTC fraction')
    seconds = calendar.timegm(dt.datetime.fromisoformat(whole).timetuple())
    return seconds * 1_000_000_000 + int((fraction + '000000000')[:9])


def iso_ns(value):
    seconds, nanos = divmod(value, 1_000_000_000)
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + '.%09dZ' % nanos


def read_json(path, inputs, root):
    raw = path.read_bytes()
    inputs[str(path.relative_to(root))] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return json.loads(raw)


def bracket(path, origin, end, timestamp_key, type_key, inputs, root):
    digest = hashlib.sha256()
    metadata, selected, previous, closed = None, [], None, False
    size = 0
    with path.open('rb') as stream:
        for line in stream:
            digest.update(line); size += len(line)
            if closed:
                continue
            row = json.loads(line)
            if row.get(type_key) == 'metadata':
                require(metadata is None, 'Duplicate metadata')
                metadata = row
                continue
            if row.get(type_key) != 'sample':
                continue
            stamp = utc_ns(row[timestamp_key])
            if stamp <= origin:
                previous = row
                continue
            if not selected:
                require(previous is not None, 'Missing pre-origin sample: ' + str(path))
                selected.append(previous)
            selected.append(row)
            closed = stamp >= end
    inputs[str(path.relative_to(root))] = {'bytes': size, 'sha256': digest.hexdigest()}
    require(metadata is not None and selected and closed, 'Incomplete arrival bracket: ' + str(path))
    stamps = [utc_ns(row[timestamp_key]) for row in selected]
    require(all(a < b for a, b in zip(stamps, stamps[1:])), 'Nonincreasing sample UTC')
    return metadata, selected


def nested(mapping, *keys):
    try:
        for key in keys:
            mapping = mapping[key]
        return mapping
    except (KeyError, TypeError):
        return None


def cumulative(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict):
        return {'available': False, 'delta': None, 'reason': 'Missing cumulative object; unavailable is not zero'}
    values = {}
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        valid = type(a) in (int, float) and type(b) in (int, float) and b >= a
        values[key] = {'before': a, 'after': b, 'delta': b - a if valid else None,
                       'available': valid}
    return values


def coverage(rows, key, origin, end):
    first, last = utc_ns(rows[0][key]), utc_ns(rows[-1][key])
    return {'sampleCount': len(rows), 'firstSampleUtc': rows[0][key], 'lastSampleUtc': rows[-1][key],
            'originLeadNs': origin - first, 'arrivalEndOvershootNs': last - end,
            'wallBracketDurationNs': last - first,
            'selectedSampleUtc': [r[key] for r in rows],
            'scope': 'Enclosing observed sample bracket; includes the declared lead/overshoot. Not an interpolated exact arrival-window measurement.'}


def process_context(rows, name, ticks_per_second):
    samples = [nested(row, 'processes', name) for row in rows]
    valid = all(isinstance(s, dict) and s.get('status') == 'verified' for s in samples)
    identities = {(s.get('pid'), s.get('startTicks'), s.get('commandSha256'))
                  for s in samples if isinstance(s, dict)}
    if not valid or len(identities) != 1:
        return {'available': False, 'averageCpuCores': None, 'reason': 'Incomplete/changed verified process identity'}
    stats = [nested(s, 'metrics', 'stat', 'value') for s in samples]
    required = ('userCpuTicks', 'systemCpuTicks', 'majorFaults')
    if not all(isinstance(s, dict) and all(type(s.get(k)) is int for k in required) for s in stats):
        return {'available': False, 'averageCpuCores': None, 'reason': 'Missing raw process CPU/fault counters'}
    delta = cumulative(stats[0], stats[-1])
    require(delta['userCpuTicks']['available'] and delta['systemCpuTicks']['available'], 'Process CPU reset')
    duration = (rows[-1]['monotonicNs'] - rows[0]['monotonicNs']) / 1e9
    user = delta['userCpuTicks']['delta'] / ticks_per_second
    system = delta['systemCpuTicks']['delta'] / ticks_per_second
    intervals = []
    for a, b, x, y in zip(rows, rows[1:], stats, stats[1:]):
        elapsed = (b['monotonicNs'] - a['monotonicNs']) / 1e9
        ticks = y['userCpuTicks'] + y['systemCpuTicks'] - x['userCpuTicks'] - x['systemCpuTicks']
        require(elapsed > 0 and ticks >= 0, 'Invalid CPU interval')
        intervals.append({'fromUtc': a['wallTimeUtc'], 'throughUtc': b['wallTimeUtc'],
                          'elapsedMonotonicSeconds': elapsed, 'averageCpuCores': ticks / ticks_per_second / elapsed})
    rss = [nested(s, 'metrics', 'status', 'value', 'VmRSSBytes') for s in samples]
    return {'available': True, 'pid': samples[0]['pid'], 'startTicks': samples[0]['startTicks'],
            'commandSha256': samples[0]['commandSha256'], 'userCpuSeconds': user, 'systemCpuSeconds': system,
            'averageCpuCores': (user + system) / duration,
            'peakSampleInterval': max(intervals, key=lambda x: x['averageCpuCores']),
            'sampleIntervals': intervals, 'majorFaultDelta': delta['majorFaults']['delta'],
            'rssMinBytes': min(rss) if all(type(x) is int for x in rss) else None,
            'rssMaxBytes': max(rss) if all(type(x) is int for x in rss) else None,
            'scope': 'Aggregate process CPU ticks / CLOCK_MONOTONIC elapsed; cores consumed, not a percent of an assumed host allocation.'}


def telemetry_context(metadata, rows, origin, end):
    first, last = rows[0], rows[-1]
    mono = [r['monotonicNs'] for r in rows]
    require(all(a < b for a, b in zip(mono, mono[1:])), 'Nonincreasing telemetry monotonic clock')
    duration = (mono[-1] - mono[0]) / 1e9
    cpu = cumulative(nested(first, 'cgroup', 'metrics', 'cpu.stat', 'value'),
                     nested(last, 'cgroup', 'metrics', 'cpu.stat', 'value'))
    usage = nested(cpu, 'usage_usec', 'delta')
    memory = [nested(r, 'cgroup', 'metrics', 'memory.current', 'value') for r in rows]
    result = {'coverage': coverage(rows, 'wallTimeUtc', origin, end),
              'monotonicDurationNs': mono[-1] - mono[0],
              'endToEndWallMinusMonotonicDifferenceNs': utc_ns(last['wallTimeUtc']) - utc_ns(first['wallTimeUtc']) - (mono[-1] - mono[0]),
              'sampleMetadata': metadata,
              'selectedSamples': [{'sequence': r['sequence'], 'wallTimeUtc': r['wallTimeUtc'],
                                  'monotonicNs': r['monotonicNs'], 'collectionFinishedMonotonicNs': r['collectionFinishedMonotonicNs']}
                                 for r in rows],
              'processes': {name: process_context(rows, name, metadata['hardware']['clockTicksPerSecond']) for name in PROCESSES},
              'cgroup': {'status': nested(first, 'cgroup', 'status'), 'directory': nested(first, 'cgroup', 'directory'),
                         'cpuMaxAtStart': nested(first, 'cgroup', 'metrics', 'cpu.max'),
                         'cpuMaxAtEnd': nested(last, 'cgroup', 'metrics', 'cpu.max'),
                         'cpuStat': cpu, 'averageCpuCores': usage / 1e6 / duration if usage is not None else None,
                         'memoryMinBytes': min(memory) if all(type(x) is int for x in memory) else None,
                         'memoryMaxBytes': max(memory) if all(type(x) is int for x in memory) else None,
                         'memoryEvents': cumulative(nested(first, 'cgroup', 'metrics', 'memory.events', 'value'),
                                                    nested(last, 'cgroup', 'metrics', 'memory.events', 'value')),
                         'scope': 'Sampler-visible cgroup leaf; hidden ancestors/host scheduling are not measured. Leaf cpu.max=max and zero throttle do not exclude other restrictions.'},
              'network': {'interface': nested(first, 'network', 'interface'),
                          'udp': cumulative(nested(first, 'network', 'udp', 'value'), nested(last, 'network', 'udp', 'value')),
                          'device': {direction: cumulative(nested(first, 'network', 'device', 'value', direction),
                                                          nested(last, 'network', 'device', 'value', direction))
                                     for direction in ('receive', 'transmit')},
                          'scope': 'UDP counters cover the sampler network namespace; device counters cover lo. Neither attributes packets to one process.'}}
    return result


def counter_key(counter):
    return tuple(counter[name] for name in ('counterId', 'typeId', 'registrationId', 'ownerId', 'referenceId', 'label'))


def counter_identity(key):
    return dict(zip(('counterId', 'typeId', 'registrationId', 'ownerId', 'referenceId', 'label'), key))


def selected_counter(label):
    patterns = ('Bytes sent', 'Bytes received', 'NAKs', 'Retransmit', 'Flow control', 'back-pressure',
                'Errors', 'Short sends', 'Invalid packets', 'Failed offers', 'Unblocked', 'Loss gap fills',
                'Client liveness', 'Revoked', 'rejected', 'timed out', 'work cycle', 'cycle exceeded',
                'total write bytes', 'total write time', 'Cluster election count')
    return any(p in label for p in patterns)


def cnc_context(metadata, rows, origin, end, expected_pid):
    require(metadata['driverPidFromCnc'] == expected_pid, 'CnC process PID differs from verified node identity')
    keyed = []
    for row in rows:
        pairs = [(counter_key(c), c['value']) for c in row['counters']]
        require(len(pairs) == len(dict(pairs)), 'Duplicate CnC identity in one sample')
        keyed.append(dict(pairs))
    stable = set(keyed[0]).intersection(*(set(r) for r in keyed[1:]))
    totals, gauges, state = [], [], []
    for key in sorted(set().union(*(set(r) for r in keyed))):
        label = key[-1]
        present = [(index, row[key]) for index, row in enumerate(keyed) if key in row]
        values = [v for _, v in present]
        if 'max cycle time' in label or 'max write time' in label:
            changes = []
            previous_index, previous = present[0]
            for index, value in present[1:]:
                if value != previous:
                    changes.append({'observedAtUtc': rows[index]['timestamp'], 'elapsedNanos': rows[index]['elapsedNanos'],
                                    'observationIntervalAfterUtc': rows[previous_index]['timestamp'],
                                    'valueNs': value, 'newHighWater': value > previous})
                previous_index, previous = index, value
            gauges.append({'identity': counter_identity(key), 'presentThroughoutBracket': key in stable,
                           'beforeOrFirstObservedNs': values[0], 'afterOrLastObservedNs': values[-1],
                           'updates': changes,
                           'scope': 'Cumulative maximum since registration; a preexisting high value does not locate a stall in this arrival window. Refresh is only localized to its sampling interval.'})
        elif label.startswith(('Cluster node role', 'Cluster leadership term id', 'Cluster election state')):
            state.append({'identity': counter_identity(key), 'presentThroughoutBracket': key in stable,
                          'observedValues': sorted(set(values)), 'stable': key in stable and len(set(values)) == 1})
        elif selected_counter(label) or key[1] in (13, 19, 20):
            valid = key in stable and all(type(v) is int for v in values) and all(a <= b for a, b in zip(values, values[1:]))
            totals.append({'identity': counter_identity(key), 'presentThroughoutBracket': key in stable,
                           'firstObservedUtc': rows[present[0][0]]['timestamp'], 'lastObservedUtc': rows[present[-1][0]]['timestamp'],
                           'beforeOrFirstObserved': values[0], 'afterOrLastObserved': values[-1],
                           'delta': values[-1] - values[0] if valid else None,
                           'deltaAvailable': valid,
                           'reasonIfUnavailable': None if valid else 'Partial counter lifetime or nonmonotonic counter; no full-bracket delta inferred',
                           'observedMin': min(values), 'observedMax': max(values)})
    return {'coverage': coverage(rows, 'timestamp', origin, end), 'metadata': metadata,
            'maxDriverHeartbeatAgeMs': max(row['driverHeartbeatAgeMs'] for row in rows),
            'stableIdentityCount': len(stable), 'identitiesAddedByEnd': len(set(keyed[-1]) - set(keyed[0])),
            'identitiesRemovedByEnd': len(set(keyed[0]) - set(keyed[-1])),
            'cumulativeCounters': totals, 'maximumGauges': gauges, 'clusterStateGauges': state,
            'scope': 'Only node driver CnC; no load driver CnC was collected. Asynchronous 1Hz samples are not atomic. Identity includes id/type/registration/owner/reference/label; partial lifetimes yield null delta.'}


def analyze(capacity_root, job):
    directory = capacity_root / job / 'raw/evidence/runs' / job
    inputs = {}
    load = read_json(directory / 'load-result.json', inputs, capacity_root)
    identities = read_json(directory / 'cpu-counter-identity.json', inputs, capacity_root)
    origin = utc_ns(load['scheduledOriginUtcApproximate'])
    duration = int(Decimal(str(load['arrivalWindowSeconds'])) * 1_000_000_000)
    expected_duration = load['scheduledArrivals'] * 1_000_000_000 // load['targetArrivalRatePerSecond']
    require(duration == expected_duration, 'Arrival duration does not match registered arrivals/rate')
    end = origin + duration
    metadata, rows = bracket(directory / 'telemetry.jsonl', origin, end, 'wallTimeUtc', 'type', inputs, capacity_root)
    telemetry = telemetry_context(metadata, rows, origin, end)
    cnc = {}
    for node in range(3):
        meta, samples = bracket(directory / ('node%d-counters.jsonl' % node), origin, end, 'timestamp', 'kind', inputs, capacity_root)
        process = telemetry['processes']['node-%d' % node]
        require(process['available'], 'Verified node process samples required')
        cnc[str(node)] = cnc_context(meta, samples, origin, end, process['pid'])
    require(identities['passed'] is True, 'Original counter identity check failed')
    summary_keys = ('scheduledArrivals', 'targetArrivalRatePerSecond', 'arrivalWindowSeconds', 'completionWindowSeconds',
                    'confirmedAcceptedCommands', 'clientNotSentCommands', 'businessRejectedCommands', 'serverErrors',
                    'unknownAtInitialDeadline', 'unresolvedFinal', 'schedulerLatenessAboveLimitCount', 'generatorTimingInvalid',
                    'executeStartAfterPlannedDeadlineCount', 'executeStartDeadlineLimitMs',
                    'schedulerLatenessMicroseconds', 'queueDelayMicroseconds', 'executeInitialAttemptMicroseconds',
                    'allOfferedAcceptedP99Microseconds')
    return {'jobId': job, 'inputsRelativeToCapacityRoot': inputs,
            'arrivalWindow': {'originUtcApproximate': load['scheduledOriginUtcApproximate'], 'originEpochNs': origin,
                              'endUtcApproximate': iso_ns(end), 'endEpochNs': end, 'durationNs': duration,
                              'scope': 'Per-trial Java approximate UTC origin; no assumption that different trials share an origin. Whole load-process lifetime includes validation and is not this window.'},
            'loadResultSelectedFields': {k: load[k] for k in summary_keys},
            'clientTransportCountersSum': {k: sum(worker[k] for worker in load['transportCountersByWorker'])
                                          for k in ('acceptedOffers', 'acceptedResends', 'unacceptedOffers', 'unknownRequestTimeouts')},
            'clientTransportScope': 'Unaccepted offer attempts may be retried locally; not a count of lost business commands. No client-driver CnC attribution.',
            'telemetry': telemetry, 'nodeCnc': cnc}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capacity-root', type=Path, default=Path(__file__).resolve().parents[2] / 'capacity')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('resource-context.json'))
    args = parser.parse_args()
    require(not args.output.exists(), 'CREATE_NEW output already exists')
    result = {'schemaVersion': 1, 'generatedAtUtc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Read-only derived context for two independent 18k trials. This does not reclassify frozen results or establish a unique cause of scheduler lateness. No CSV/analyzer/network/JVM run.',
              'limitations': ['1Hz resource samples cannot identify millisecond-scale thread stalls.',
                              'UTC arrival origins are approximate; explicit enclosing sample overshoot is retained.',
                              'Process CPU utilization does not measure host scheduling pressure or invisible cgroup ancestors.',
                              'No GC/JFR/thread scheduling traces or load-driver CnC are present.',
                              'Counter absence is unavailable/null, never inferred zero.'],
              'trials': [analyze(args.capacity_root, job) for job in JOBS]}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'created': str(args.output), 'trials': len(result['trials']),
                      'scriptSha256': result['scriptSha256'], 'bytes': args.output.stat().st_size}))


if __name__ == '__main__':
    main()
