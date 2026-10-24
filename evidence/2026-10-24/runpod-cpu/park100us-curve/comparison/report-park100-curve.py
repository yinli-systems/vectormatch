#!/usr/bin/env python3
"""Publish only the complete eight-point registered finite CPU curve, without filtering."""
from pathlib import Path
import hashlib
import importlib.util
import json

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
CONTROLLER_SHA = '400956e2bb9488ecdf06fef8557caa7e8ee98a3a1e6faf9620f4d93708a2b974'
OUT = REPO / 'evidence/2026-10-24/runpod-cpu/park100us-curve/comparison'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def report():
    path = BASE / 'capacity_park100_curve.py'
    if sha(path) != CONTROLLER_SHA:
        raise ValueError('frozen capacity controller changed')
    spec = importlib.util.spec_from_file_location('fixed_park100_curve', path)
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    registration = REPO / 'evidence/2026-10-24/runpod-cpu/registrations' / (c.MATRIX_ID + '.json')
    plan = c.validate_matrix(c.read(registration))
    matrix = REPO / 'evidence/2026-10-24/runpod-cpu/matrices' / c.MATRIX_ID
    points = c.completed_prefix(matrix, plan, 8)
    c.require(len(points) == len(plan['trialPlans']) == 8, 'all eight registered points required')
    rows = []
    for point, child in zip(points, plan['trialPlans']):
        local = Path(point['analysisDirectory'])
        summary = local / 'analysis/summary.json'
        x = c.read(summary)['trials'][0]; d = x['derived']
        receipt = c.read(matrix / 'point-executions' / child['jobId'] / 'receipt.json')
        c.require(receipt['passed'] is True and receipt['point'] == point, 'point receipt changed')
        trial = local / 'raw/evidence/runs' / child['jobId']
        verifier_path = local / 'raw/pinned-tools/scripts/verify-capacity-config.py'
        c.require(sha(verifier_path) == child['tools']['scripts/verify-capacity-config.py']['sha256'], 'pinned verifier changed')
        verifier = c.import_file('park100_actual_' + child['jobId'].replace('-', '_'), verifier_path)
        idle = c.actual_idle_check(child, verifier, trial)
        c.require(idle['passed'] and all(n['distinctInstanceCount'] == 11 for n in idle['nodes']), 'actual node idle proof differs')
        c.require(d['rows'] == 350000 and d['unknownAtInitialDeadline'] == d['unknownUnresolved'] == 0, 'finite arrival/UNKNOWN scope differs')
        if d['clientNotSent'] or d['businessRejected'] or d['serverErrors']:
            c.require(d['allOfferedAcceptedP99Millis'] is None, 'conditional tail misrepresented as all offered')
        rows.append({
            'jobId': child['jobId'], 'repetition': child['task']['repetition'],
            'targetArrivalRatePerSecond': child['task']['rate'], 'arrivals': 350000,
            'arrivalWindowSeconds': x['arrivalWindowSeconds'], 'measurementValid': x['measurementValid'],
            'finiteStable': x['observedStableWindow'], 'classification': x['classification'],
            'windowGoodputPerSecond': d['arrivalWindowGoodputPerSecond'],
            'acceptedIncludingDrain': d['confirmedAccepted'], 'notSent': d['clientNotSent'],
            'businessRejected': d['businessRejected'], 'serverErrors': d['serverErrors'],
            'initialUnknown': d['unknownAtInitialDeadline'], 'finalUnknown': d['unknownUnresolved'],
            'conditionalAcceptedP99Millis': d['latency']['conditionalAccepted']['p99Millis'],
            'allOfferedAcceptedP99Millis': d['allOfferedAcceptedP99Millis'],
            'conditionalQueueP99Millis': d['latency']['queue']['p99Millis'],
            'conditionalInitialExecuteP99Millis': d['latency']['initialExecute']['p99Millis'],
            'drainSeconds': d['drainSeconds'], 'peakObservedOutstanding': x['backlog']['peakObservedOutstanding'],
            'peakQueueDepth': x['backlog']['peakQueueDepth'], 'peakInFlight': x['backlog']['peakInFlight'],
            'schedulerLatenessAboveLimitCount': x['rawSummary']['schedulerLatenessAboveLimitCount'],
            'analysisSha256': sha(summary), 'completeArchiveSha256': point['completion']['archive']['sha256'],
            'actualNodeIdleVerificationSha256': sha(trial / 'node-idle-variant-verification.json'),
            'rawTelemetrySha256': sha(local / 'raw/watch/telemetry.jsonl'),
        })
    return {'passed': True, 'matrixId': c.MATRIX_ID, 'matrixPlanSha256': plan['matrixPlanSha256'],
            'registrationSha256': sha(registration), 'controllerSha256': CONTROLLER_SHA,
            'reporterSha256': sha(__file__), 'rows': rows,
            'scope': 'All eight preregistered points retained in execution order. Single existing CPU host,three JVMs,loopback UDP,source433,node max park100us,client original1ms,leader0,sync2,2g heaps,W128/Q64,mux1,MTU1248. Each350k arrivals starts independent state. Window goodput excludes drain. Accepted-only tails are conditional; missing all-arrival accepted p99 remains null when any request is not accepted. No sustained ceiling,three-machine failure isolation,HTTP/PG/WS capacity,100M total,100M/s,100M connections or hard realtime claim.'}

def main():
    result = report()  # No output directory before all eight raw/archive gates pass.
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    summaries = [json.loads((REPO / 'evidence/2026-10-24/runpod-cpu/capacity' / r['jobId'] / 'analysis/summary.json').read_text())
                 for r in result['rows']]
    combined = {'schemaVersion': 1, 'generatedAt': max(x['generatedAt'] for x in summaries),
                'scope': result['scope'], 'trials': [x['trials'][0] for x in summaries],
                'sourceAnalysisSha256': {r['jobId']: r['analysisSha256'] for r in result['rows']}}
    (OUT / 'combined-analysis.json').write_text(json.dumps(combined, indent=2, allow_nan=False) + '\n')
    lines = ['# Fixed100us node capacity curve', '', result['scope'], '',
             '|Rate/s|Repeat|Window accepted/s|Not sent|Accepted-only p99 ms|All-arrival p99 ms|Peak queue|Finite stable|',
             '|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in result['rows']:
        tail = 'N/A' if r['allOfferedAcceptedP99Millis'] is None else f"{r['allOfferedAcceptedP99Millis']:.3f}"
        lines.append(f"|{r['targetArrivalRatePerSecond']}|{r['repetition']}|{r['windowGoodputPerSecond']:.3f}|{r['notSent']}|{r['conditionalAcceptedP99Millis']:.3f}|{tail}|{r['peakQueueDepth']}|{r['finiteStable']}|")
    lines += ['', 'Each point passed pinned raw-arrival analysis, fixed leader, canonical snapshot, asset conservation, actual node idle instances, owned-process cleanup and full native archive checks. All repeats remain reported. The independent analysis labels an overloaded point as observed overload or undersized client; it does not uniquely attribute a server bottleneck. The previously completed18k A/B/A/B belongs to its own registered experiment and is linked separately; its timings are not folded into these repetitions.', '',
              '[Complete18k node-only A/B/A/B](../../node-idle-abab/comparison/README.md)', '',
              '![Every registered point](park100us-capacity.png)', '',
              '[All numeric values and raw/archive hashes](comparison.json)']
    (OUT / 'README.md').write_text('\n'.join(lines) + '\n')
    (OUT / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'passed': True, 'points': 8, 'output': str(OUT)}))

if __name__ == '__main__':
    main()
