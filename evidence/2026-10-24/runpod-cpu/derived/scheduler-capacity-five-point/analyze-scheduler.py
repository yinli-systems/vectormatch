#!/usr/bin/env python3
"""Read-only, single-pass CSV diagnostic; never reclassifies a frozen capacity point."""
import argparse
import calendar
from collections import Counter, deque
import csv
import datetime as dt
import hashlib
import heapq
import json
from pathlib import Path

THRESHOLDS = (1_000_000, 5_000_000, 10_000_000, 20_000_000)


def utc_ns(text):
    text = text.replace('+00:00', 'Z').rstrip('Z')
    whole, _, fraction = text.partition('.')
    seconds = calendar.timegm(dt.datetime.fromisoformat(whole).timetuple())
    return seconds * 1_000_000_000 + int((fraction + '000000000')[:9])


def iso_ns(value):
    seconds, nanos = divmod(value, 1_000_000_000)
    return dt.datetime.fromtimestamp(seconds, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + '.%09dZ' % nanos


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_rows(path, digest):
    def lines():
        with path.open('rb') as stream:
            for line in stream:
                digest.update(line)
                yield line.decode('utf-8')
    return csv.DictReader(lines())


def analyze(job):
    directory = job / 'raw/evidence/runs' / job.name
    summary_path = job / 'analysis/summary.json'
    frozen = json.loads(summary_path.read_text())['trials'][0]
    load_path = directory / 'load-result.json'
    load = json.loads(load_path.read_text())
    origin = utc_ns(load['scheduledOriginUtcApproximate'])
    rate = load['targetArrivalRatePerSecond']
    scheduled = load['scheduledArrivals']
    window = scheduled * 1_000_000_000 // rate
    limit = frozen['configuration']['schedulerLatenessLimitMs'] * 1_000_000
    counts, totals, outcomes = Counter(), Counter(), Counter()
    bins, bursts, late_rows, largest_gaps = {}, [], [], []
    previous = None
    recent = deque(maxlen=4)
    first_context = None
    active_burst = None
    input_digest = hashlib.sha256()
    for row in csv_rows(directory / 'arrivals.csv', input_digest):
        if None in row or any(v is None for v in row.values()):
            raise ValueError('CSV width error')
        index = int(row['index'])
        planned, enqueued, late = (int(row[k]) for k in ('planned_offset_ns', 'enqueued_offset_ns', 'scheduler_lateness_ns'))
        if index != counts['rows'] or planned != index * 1_000_000_000 // rate or enqueued - planned != late:
            raise ValueError('Index/planned/lateness mismatch')
        counts['rows'] += 1
        outcomes[row['outcome']] += 1
        bucket = bins.setdefault(planned // 1_000_000_000, Counter())
        bucket['rows'] += 1
        bucket['schedulerSumNs'] += late
        bucket['schedulerMaxNs'] = max(bucket['schedulerMaxNs'], late)
        totals['schedulerSumNs'] += late
        totals['schedulerMaxNs'] = max(totals['schedulerMaxNs'], late)
        for threshold in THRESHOLDS:
            if late > threshold:
                counts['schedulerAbove%dNs' % threshold] += 1
                bucket['schedulerAbove%dNs' % threshold] += 1
        selected = {k: row[k] for k in ('index', 'worker', 'request_seq', 'outcome', 'unknown_at_initial_deadline')}
        selected.update({k: int(row[k]) if row[k] else None for k in ('planned_offset_ns', 'enqueued_offset_ns',
            'execute_started_offset_ns', 'initial_attempt_end_offset_ns', 'confirmed_offset_ns', 'scheduler_lateness_ns',
            'queue_delay_ns', 'initial_execute_rtt_ns', 'scheduled_to_confirmed_ns')})
        selected.update(plannedUtcApproximate=iso_ns(origin + planned), enqueuedUtcApproximate=iso_ns(origin + enqueued))
        if previous is not None:
            gap = enqueued - previous['enqueued_offset_ns']
            item = (gap, index, {'gapNs': gap, 'previous': previous, 'next': selected})
            if len(largest_gaps) < 10:
                heapq.heappush(largest_gaps, item)
            elif gap > largest_gaps[0][0]:
                heapq.heapreplace(largest_gaps, item)
        if late > limit:
            counts['schedulerAboveDeclaredLimit'] += 1
            late_rows.append(selected)
            if first_context is None:
                first_context = list(recent)
        if late > THRESHOLDS[0]:
            if active_burst is None:
                active_burst = {'firstIndex': index, 'firstPlannedNs': planned, 'firstEnqueuedNs': enqueued,
                                'rows': 0, 'maxLatenessNs': 0, 'aboveDeclaredLimit': 0}
            active_burst.update(lastIndex=index, lastPlannedNs=planned, lastEnqueuedNs=enqueued)
            active_burst['rows'] += 1
            active_burst['maxLatenessNs'] = max(active_burst['maxLatenessNs'], late)
            active_burst['aboveDeclaredLimit'] += late > limit
        elif active_burst is not None:
            bursts.append(active_burst)
            active_burst = None
        if row['initial_execute_rtt_ns']:
            started = int(row['execute_started_offset_ns'])
            ended = int(row['initial_attempt_end_offset_ns'])
            rtt = int(row['initial_execute_rtt_ns'])
            if ended - started != rtt:
                raise ValueError('RTT mismatch')
            counts['executed'] += 1
            totals['initialExecuteSumNs'] += rtt
            totals['queueSumNs'] += int(row['queue_delay_ns'])
            bucket['executed'] += 1
            bucket['initialExecuteSumNs'] += rtt
            bucket['queueSumNs'] += int(row['queue_delay_ns'])
            # Exact integral of CSV execute-call intervals clipped to the arrival window.
            # This measures occupied logical worker calls, not simultaneous server execution.
            start, end = max(0, started), min(window, ended)
            if end > start:
                totals['arrivalExecuteIntervalAreaNs'] += end - start
                for second in range(start // 1_000_000_000, (end - 1) // 1_000_000_000 + 1):
                    overlap = min(end, (second + 1) * 1_000_000_000) - max(start, second * 1_000_000_000)
                    bins.setdefault(second, Counter())['executeIntervalAreaNs'] += overlap
        previous = selected
        recent.append(selected)
    if active_burst is not None:
        bursts.append(active_burst)
    if input_digest.hexdigest() != frozen['inputSha256']['arrivals.csv']:
        raise ValueError('Frozen input SHA differs')
    if counts['rows'] != scheduled or counts['schedulerAboveDeclaredLimit'] != load['schedulerLatenessAboveLimitCount']:
        raise ValueError('Raw/load counts differ')
    for burst in bursts:
        burst['firstPlannedUtcApproximate'] = iso_ns(origin + burst['firstPlannedNs'])
        burst['lastPlannedUtcApproximate'] = iso_ns(origin + burst['lastPlannedNs'])
        burst['firstEnqueuedUtcApproximate'] = iso_ns(origin + burst['firstEnqueuedNs'])
        burst['lastEnqueuedUtcApproximate'] = iso_ns(origin + burst['lastEnqueuedNs'])
    bin_rows = []
    for second, values in sorted(bins.items()):
        duration = min(window, (second + 1) * 1_000_000_000) - second * 1_000_000_000
        bin_rows.append({'plannedOffsetSecond': second, 'plannedUtcApproximate': iso_ns(origin + second * 1_000_000_000),
            **dict(values), 'meanExecuteCallConcurrencyInArrivalWindow': values['executeIntervalAreaNs'] / duration if duration > 0 else None})
    backlog_path = directory / 'backlog.csv'
    with backlog_path.open(newline='') as stream:
        backlog = [{k: int(r[k]) for k in ('offset_ns', 'scheduled_due', 'enqueued', 'started', 'reply_confirmed',
            'client_not_sent', 'in_flight', 'queue_depth')} for r in csv.DictReader(stream)]
    return {'id': job.name, 'classificationUnchanged': frozen['classification'],
        'measurementValidUnchanged': frozen['measurementValid'], 'stabilityChecksUnchanged': frozen.get('stabilityChecks'),
        'validityChecksUnchanged': frozen.get('validityChecks'),
        'derivedFrozen': {k: frozen['derived'][k] for k in ('arrivalWindowGoodputPerSecond', 'confirmedAccepted',
            'clientNotSent', 'unknownAtInitialDeadline', 'unknownUnresolved', 'drainSeconds')},
        'latencyFrozen': frozen['derived']['latency'], 'backlogFrozen': frozen['backlog'],
        'originUtcApproximate': iso_ns(origin), 'arrivalWindowEndUtcApproximate': iso_ns(origin + window),
        'windowNs': window, 'rate': rate, 'schedulerLimitNs': limit, 'counts': dict(counts), 'outcomes': dict(outcomes),
        'schedulerAboveDeclaredLimitRows': late_rows, 'precedingFirstLateRows': first_context,
        'schedulerAbove1msBursts': bursts, 'largestEnqueueGaps': [x[2] for x in sorted(largest_gaps, reverse=True)],
        'initialExecuteMeanNs': totals['initialExecuteSumNs'] / counts['executed'] if counts['executed'] else None,
        'queueMeanNs': totals['queueSumNs'] / counts['executed'] if counts['executed'] else None,
        'meanExecuteCallConcurrencyInArrivalWindow': totals['arrivalExecuteIntervalAreaNs'] / window,
        'logicalCallSlotOccupancyFraction': totals['arrivalExecuteIntervalAreaNs'] / window / load['workers'],
        'binsByPlannedSecond': bin_rows, 'backlogSamples': backlog,
        'inputSha256': {'arrivals.csv': input_digest.hexdigest(), 'load-result.json': sha(load_path),
            'analysis/summary.json': sha(summary_path), 'backlog.csv': sha(backlog_path)},
        'scope': 'CSV times use the load JVM monotonic origin. UTC is approximate. API occupancy integrates execute-call intervals, not server parallelism; bins by planned arrival may contain calls executing later. No invalid point is promoted and no p99 values are subtracted.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capacity_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    jobs = sorted(p for p in args.capacity_root.glob('cpu-capacity-*') if (p / 'analysis/summary.json').is_file())
    result = {'schemaVersion': 1, 'generatedAtUtc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'scriptSha256': sha(__file__), 'scope': 'Read-only one-pass finite CPU capacity diagnostics; original classifications/results unchanged.',
        'trials': [analyze(job) for job in jobs]}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'sha256': sha(args.output), 'trials': len(result['trials']),
        'lateCounts': {r['id']: r['counts'].get('schedulerAboveDeclaredLimit', 0) for r in result['trials']}}, indent=2))


if __name__ == '__main__':
    main()
