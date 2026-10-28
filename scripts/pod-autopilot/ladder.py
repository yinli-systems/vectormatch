"""Rate ladder that records every rung, including ones whose audit refuses the stream.

Rungs run in PLAN order (names ending in '-repeat' are skipped unless needed). Escalation stops at the first
rung that fails its registered gates; that rung's '-repeat' case then runs once. A rung is never retried in
place and every audited or partially audited result is kept as a write-once row file."""
from pathlib import Path
import collections, csv, fcntl, json, os, sys, traceback

sys.path.insert(0, os.environ['VM_ROOT'])
import campaign as c

P = Path(c.ROOT)


def from_samples(name):
    rows = list(csv.DictReader((P / 'experiments' / name / 'evidence' / 'samples.csv').open()))
    lat = sorted(int(r['confirmed_offset_ns']) - int(r['planned_offset_ns']) for r in rows if r['outcome'] == 'ACCEPTED')
    q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))] / 1e3
    return dict(counts=dict(collections.Counter(r['outcome'] for r in rows)),
                latencyFromSamples=dict(p50Us=q(.5), p99Us=q(.99), p999Us=q(.999), maxUs=lat[-1] / 1e3) if lat else None)


def rung(name):
    spec = c.PLAN['cases'][name]
    row = dict(case=name, rate=spec['rate'], seconds=spec['seconds'], sync=spec.get('sync', 2))
    try:
        c.run(name, spec['seconds'])
        audit = c.close(name)
        row.update(latency=audit['fullLatency'], offerToReply=audit['offerToReply'], gates=audit['gates'],
                   registeredGatePass=audit['registeredGatePass'], counts=audit['counts'],
                   inWindowGoodput=audit.get('inWindowGoodput'))
    except BaseException as e:
        row.update(registeredGatePass=False, error=repr(e)[-400:], traceback=traceback.format_exc()[-2000:])
        try:
            row.update(from_samples(name))
        except Exception as missing:
            row['samplesError'] = repr(missing)
    c.save(P / (name + '-LADDER_ROW.json'), row)
    c.progress(dict(stage='rung', **{k: v for k, v in row.items() if k != 'traceback'}))
    return row


def main():
    with (P / 'CONTROLLER.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows, knee = [], None
        for name in [n for n in c.PLAN['cases'] if not n.endswith('-repeat')]:
            row = rung(name)
            rows.append(row)
            if row['registeredGatePass']:
                knee = row['rate']
                continue
            if name + '-repeat' in c.PLAN['cases']:
                rows.append(rung(name + '-repeat'))
            break
        c.save(P / 'LADDER.json', dict(rungs=rows, highestPassingRate=knee,
                                       rule='first failing rung stops escalation and is repeated once; knee = highest rate whose rung passed all registered gates'))
        c.progress(dict(stage='complete', highestPassingRate=knee))


if __name__ == '__main__':
    main()
