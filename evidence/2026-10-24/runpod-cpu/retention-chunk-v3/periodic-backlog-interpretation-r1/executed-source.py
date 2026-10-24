#!/usr/bin/env python3
"""Read-only diagnostic of already frozen finite cohorts; never executes business work."""
import bisect
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-chunk-v3/cloud-abab-r3'
OUT = ROOT / 'runtime/cloud/cpu-20261024/chunk-periodic-backlog-diagnostic-r1'
INPUTS = {}

def raw(path):
    value = path.read_bytes()
    INPUTS[str(path.relative_to(ROOT))] = {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
    return value

def main():
    OUT.mkdir(exist_ok=False)
    comparison = json.loads(raw(SOURCE / 'comparison.json'))
    reports = []
    for cohort in comparison['cohorts']:
        arrival_path = SOURCE / cohort['arrivalCsv']
        arrival_bytes = raw(arrival_path)
        assert hashlib.sha256(arrival_bytes).hexdigest() == cohort['arrivalCsvBinding']['sha256']
        rows = list(csv.DictReader(io.StringIO(arrival_bytes.decode('ascii'))))
        assert len(rows) == 6400 and all(r['status'] == 'APPLIED' and r['result_code'] == 'ACCEPTED' for r in rows)
        config = json.loads(raw(arrival_path.parent / 'configuration.json'))
        origin = config['scheduledOriginMonotonicNs']
        arrivals = sorted(int(r['arrival_offset_ns']) for r in rows)
        completions = sorted(int(r['reply_completion_offset_ns']) for r in rows)
        assert len({int(r['order_id']) for r in rows}) == 6400
        def outstanding(at):
            return bisect.bisect_right(arrivals, at) - bisect.bisect_right(completions, at)
        cycles = []
        for number in range(1, 4):
            path = arrival_path.parent / 'maintenance' / ('cycle-%d.verified.txt' % number)
            properties = dict(line.split('=', 1) for line in raw(path).decode('ascii').splitlines() if '=' in line)
            start = int(properties['cycleStartedMonotonicNs']) - origin
            end = int(properties['cycleEndedMonotonicNs']) - origin
            assert 0 <= start <= end
            cycles.append({'cycle': number, 'startOffsetNs': start, 'endOffsetNs': end,
                           'durationNs': end - start, 'throughCommandSeq': int(properties['throughCommandSeq']),
                           'releasedMinusConfirmedAtStart': outstanding(start),
                           'releasedMinusConfirmedAtEnd': outstanding(end)})
        gaps = []
        for first, second in zip(cycles, cycles[1:]):
            low, high = first['endOffsetNs'], second['startOffsetNs']
            assert high >= low
            instants = sorted({low, high} | {x for x in arrivals + completions if low <= x <= high})
            values = [(outstanding(t), t) for t in instants]
            minimum, at = min(values)
            gaps.append({'afterCycle': first['cycle'], 'beforeCycle': second['cycle'],
                         'minimumReleasedMinusConfirmed': minimum, 'firstMinimumOffsetNs': at})
        reports.append({'label': cohort['label'], 'archiveChunkBytes': cohort['archiveChunkBytes'],
                        'historicalClassificationPreserved': cohort['classification'],
                        'cycles': cycles, 'betweenCycleRecovery': gaps,
                        'noUnboundedGrowthInferenceFromThisExposure': True})
    for name, expected in INPUTS.items():
        value = (ROOT / name).read_bytes()
        assert len(value) == expected['bytes'] and hashlib.sha256(value).hexdigest() == expected['sha256']
    result = {'recordedAtUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'passed': True,
              'scope': 'Local arithmetic on frozen synthetic arrivals and maintenance timestamps. No new benchmark, SSH, Java, SQL or business work.',
              'definition': 'At t: count(actual arrival offset <= t) minus count(full accepted reply completion offset <= t). This is unconfirmed released work, not an independently sampled owner queue component.',
              'cohorts': reports, 'inputs': INPUTS, 'allInputsUnchanged': True,
              'interpretation': 'B1/B2 recover between the first two full cuts. The historical finite-window label describes low window goodput and seconds of latency/drain; it is not proof of unbounded steady-state queue growth at500/s. A1/A2 have only two full cuts too. No sustained500/s capacity or unique instability point is established by any6400-order exposure.',
              'nextMeasurement': 'Keep the window1/8 factor comparison unchanged. Separately preregister a longer exposure with at least10full maintenance cycles, successive equivalent-cut outstanding levels, slope uncertainty and a stated latency SLO.'}
    (OUT / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': True, 'inputsRehashed': len(INPUTS), 'cohorts': reports}, indent=2))

if __name__ == '__main__':
    main()
