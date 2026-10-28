"""Exploratory sweep: run and audit every case in PLAN order; a failing case is recorded, never skipped silently.

Exploration only (no ABAB selection): it ranks configurations so the best one can be confirmed by ABAB."""
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


def main():
    with (P / 'CONTROLLER.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = []
        for name, spec in c.PLAN['cases'].items():
            row = dict(case=name, rate=spec['rate'], seconds=spec['seconds'], sync=spec.get('sync', 2),
                       cores=len(spec.get('cpuSets', c.PLAN['cpuSets'])[0]) // 2, maxParkNs=spec['maxParkNs'])
            try:
                c.run(name, spec['seconds'])
                audit = c.close(name)
                row.update(latency=audit['fullLatency'], offerToReply=audit['offerToReply'], gates=audit['gates'],
                           registeredGatePass=audit['registeredGatePass'], counts=audit['counts'],
                           telemetry=[{k: t[k] for k in ('role', 'meanCpuCores', 'gcPauseCount', 'gcPause')} for t in audit['telemetry']])
            except BaseException as e:
                row.update(registeredGatePass=False, error=repr(e)[-400:], traceback=traceback.format_exc()[-2000:])
                try:
                    row.update(from_samples(name))
                except Exception as missing:
                    row['samplesError'] = repr(missing)
            rows.append(row)
            # Evidence files are write-once, so each case gets its own row file and the summary is written once.
            c.save(P / (name + '-SWEEP_ROW.json'), row)
            c.progress(dict(stage='rung', **{k: v for k, v in row.items() if k not in ('traceback', 'telemetry')}))
        c.save(P / 'SWEEP.json', dict(rows=rows, exploratory=True))
        c.progress(dict(stage='complete', cases=len(rows)))


if __name__ == '__main__':
    main()
