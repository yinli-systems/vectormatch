#!/usr/bin/env python3
"""Offline publication gate for all four registered client-driver trials."""
from pathlib import Path
import importlib.util
import json
import hashlib

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
CONTROLLER_SHA = 'e5fa98bf5ee4978b259120afb1b1da3cdcef87b3225b64814e405914f590fc29'
OUT = REPO / 'evidence/2026-10-24/runpod-cpu/client-driver-experiment/comparison'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    controller = BASE / 'capacity_client_driver_abab.py'
    if sha(controller) != CONTROLLER_SHA: raise ValueError('frozen client experiment controller changed')
    spec = importlib.util.spec_from_file_location('fixed_client_driver_abab', controller)
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    path = REPO / 'evidence/2026-10-24/runpod-cpu/registrations' / (c.MATRIX_ID + '.json')
    plan = c.validate_matrix(c.read(path))
    matrix = REPO / 'evidence/2026-10-24/runpod-cpu/matrices' / c.MATRIX_ID
    points = c.completed_prefix(matrix, plan, 4)
    c.require(len(points) == len(plan['trialPlans']) == 4, 'all four raw/native/archive closures required')
    rows, analyses = [], []
    for point, child in zip(points, plan['trialPlans']):
        local = Path(point['analysisDirectory']); summary = local / 'analysis/summary.json'
        analysis = c.read(summary); x = analysis['trials'][0]; d = x['derived']
        receipt = c.read(matrix / 'point-executions' / child['jobId'] / 'receipt.json')
        c.require(receipt['passed'] is True and receipt['point'] == point, 'registered point receipt differs')
        trial = local / 'raw/evidence/runs' / child['jobId']
        legacy_path = local / 'raw/pinned-tools/scripts/verify-capacity-config.py'
        c.require(sha(legacy_path) == child['tools']['scripts/verify-capacity-config.py']['sha256'], 'original verifier bytes differ')
        legacy = c.import_file('legacy_client_report_' + child['task']['stage'], legacy_path)
        mixed = c.mixed_verifier(child)
        verification = mixed.verify(child, trial, legacy)
        c.require(verification['passed'] is True and verification['configurationOnly'] is False, 'actual measured driver/source verification failed')
        idle = c.actual_idle_check(child, legacy, trial)
        c.require(idle['passed'] and all(n['distinctInstanceCount'] == 11 for n in idle['nodes']), 'actual node100us instances differ')
        telemetry_path = local / 'analysis/cpu-telemetry.json'; telemetry = c.read(telemetry_path)
        for name, digest in telemetry['inputSha256'].items(): c.require(sha(trial / name) == digest, 'CPU observer input changed')
        c.require(d['rows'] == 350000 and d['unknownAtInitialDeadline'] == d['unknownUnresolved'] == 0, 'arrival/UNKNOWN scope differs')
        if d['clientNotSent'] or d['businessRejected'] or d['serverErrors']:
            c.require(d['allOfferedAcceptedP99Millis'] is None, 'conditional tail mislabeled as all-offered')
        rows.append({'stage': child['task']['stage'], 'jobId': child['jobId'],
            'clientDriverMaxParkNs': child['task']['clientDriverMaxParkNs'], 'nodeMaxParkNs': 100000,
            'measurementValid': x['measurementValid'], 'finiteStable': x['observedStableWindow'],
            'windowGoodputPerSecond': d['arrivalWindowGoodputPerSecond'],
            'acceptedIncludingDrain': d['confirmedAccepted'], 'notSent': d['clientNotSent'],
            'businessRejected': d['businessRejected'], 'serverErrors': d['serverErrors'],
            'conditionalAcceptedP99Millis': d['latency']['conditionalAccepted']['p99Millis'],
            'allOfferedAcceptedP99Millis': d['allOfferedAcceptedP99Millis'],
            'initialUnknown': d['unknownAtInitialDeadline'], 'finalUnknown': d['unknownUnresolved'],
            'peakObservedOutstanding': x['backlog']['peakObservedOutstanding'], 'drainSeconds': d['drainSeconds'],
            'averageLogicalCores': {n: v.get('averageLogicalCores') if isinstance(v, dict) else None for n, v in telemetry['processes'].items()},
            'sampledRssMaxBytes': {n: v.get('rssBytes', {}).get('maxObserved') if isinstance(v, dict) else None for n, v in telemetry['processes'].items()},
            'actualMeasuredDriver': verification['actualMeasuredDriverObservation'],
            'analysisSha256': sha(summary), 'cpuTelemetrySha256': sha(telemetry_path),
            'configurationVerificationSha256': sha(trial / 'configuration-verification.json'),
            'completeArchiveSha256': point['completion']['archive']['sha256']})
        analyses.append(analysis)
    result = {'passed': True, 'matrixId': c.MATRIX_ID, 'matrixPlanSha256': plan['matrixPlanSha256'],
        'registrationSha256': sha(path), 'controllerSha256': CONTROLLER_SHA, 'reporterSha256': sha(__file__),
        'nodeRevision': c.REVISION, 'loadRevision': c.LOAD_REVISION, 'rows': rows,
        'scope': 'All four preregistered A1/B1/A2/B2 trials. Same candidate loadJARs in both arms;node433/node100us fixed;clientMediaDriver1ms(A)/100us(B),owner loop1ms fixed;leader0,sync2,2gheaps,W128/Q64,mux1,MTU1248,22k/s×350k fresh arrivals per independent state. One existing CPU host,threeJVMs,loopbackUDP. Window goodput excludes drain. Accepted-only tails are conditional;all-offered accepted p99 stays unavailable with any loss. CPU means use approximate window samples per owned process;host/cgroup is shared and counted once. No sustained ceiling,three-machine isolation,HTTP/PG/WS,100M or hard real-time proof.'}
    OUT.mkdir(parents=True, exist_ok=False)
    (OUT / 'comparison.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    for group in ('A', 'B'):
        selected = [a for a, r in zip(analyses, rows) if r['stage'].startswith(group)]
        summary = {'generatedAt': max(a['generatedAt'] for a in selected), 'scope': result['scope'],
                   'trials': [a['trials'][0] for a in selected]}
        (OUT / ('analysis-' + group + '.json')).write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    lines = ['# Client-only MediaDriver max-park A/B/A/B', '', result['scope'], '',
        '|Stage|Client max park|Window accepted/s|Not sent|Accepted-only p99 ms|All-arrival p99 ms|Drain ms|Finite stable|',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        tail = 'N/A' if r['allOfferedAcceptedP99Millis'] is None else f"{r['allOfferedAcceptedP99Millis']:.3f}"
        lines.append(f"|{r['stage']}|{r['clientDriverMaxParkNs']/1000:.0f}us|{r['windowGoodputPerSecond']:.3f}|{r['notSent']}|{r['conditionalAcceptedP99Millis']:.3f}|{tail}|{r['drainSeconds']*1000:.3f}|{r['finiteStable']}|")
    lines += ['', 'All original raw outcomes,actual measured-owner driver observations,source/classpath receipts,canonical/native archives and CPU samples remain bound in comparison.json. Older source433 capacity timings are context,not controls in this experiment. Both repetitions must be evaluated;two pairs do not establish a production SLA or a unique cause outside the explicitly changed driver policy.', '',
        '![Every registered client trial](client-driver-abab.png)', '', '[Numeric evidence and hashes](comparison.json)']
    (OUT / 'README.md').write_text('\n'.join(lines) + '\n')
    (OUT / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps({'passed': True, 'points': 4, 'output': str(OUT)}))

if __name__ == '__main__': main()
