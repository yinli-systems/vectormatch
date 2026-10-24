#!/usr/bin/env python3
"""Bundle five unchanged independently analyzed CPU rows; no analyzer/cloud run.

All output files are CREATE_NEW. Export the resulting summary with the existing
scripts/export-capacity-ui.py; this builder does not edit evidence/index.json.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

JOBS = ('cpu-capacity-13000-w128-r1', 'cpu-capacity-18000-w128-r1',
        'cpu-capacity-26000-w128-r1', 'cpu-capacity-13000-w128-r2', 'cpu-capacity-18000-w128-r2')
MISSING = 'cpu-capacity-26000-w128-r2'
MATRIX = 'cpu-capacity-staircase-433-r1'
ANALYSIS_ID = '31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f'
SOURCE = '433f02bebe2f3109ec363291fa562d5c509c0723'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def artifact(path, repository):
    return {'path': str(path.relative_to(repository)), 'bytes': path.stat().st_size, 'sha256': sha(path)}


def save_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def build(repository, output):
    cpu = repository / 'evidence/2026-10-24/runpod-cpu'
    matrix_root = cpu / 'matrices' / MATRIX
    matrix = json.loads((matrix_root / 'matrix-summary.json').read_text())
    registration_path = cpu / 'registrations' / (MATRIX + '.json')
    registration = json.loads(registration_path.read_text())
    require([point['id'] for point in matrix['points']] == list(JOBS), 'Original five-point execution order differs')
    require(matrix['completed'] is False and matrix['unlaunchedIds'] == [MISSING], 'Original stopped/missing point scope differs')
    require(registration['sourceRevision'] == SOURCE and registration['matrixPlanSha256'] == matrix['matrixPlanSha256'], 'Original matrix source/registration differs')
    rows, provenance, fingerprints, criteria = [], [], set(), None
    for job in JOBS:
        local = cpu / 'capacity' / job
        summary_path = local / 'analysis/summary.json'
        summary = json.loads(summary_path.read_text())
        post = json.loads((local / 'postprocess.json').read_text())
        require(post['exitCode'] == 0 and post['analysisIdentitySha256'] == ANALYSIS_ID, 'Unverified independent analyzer provenance: ' + job)
        require(len(summary['trials']) == 1 and summary['trials'][0]['id'] == job, 'Unexpected independently analyzed rows')
        row = summary['trials'][0]
        require(row['workers'] == 128 and row['scheduledArrivals'] == 350000, 'Different CPU workload')
        require(row['trial']['sourceRevision'] == SOURCE and row['phase'] == 'cpu-single-host-fixed-config-capacity-staircase', 'Different source/phase')
        require(row['comparisonFingerprintSha256'], 'Missing comparison fingerprint')
        fingerprints.add(row['comparisonFingerprintSha256'])
        if criteria is None:
            criteria = summary['criteria']
        require(criteria == summary['criteria'], 'Mixed independent analysis criteria')
        raw = local / 'raw/evidence/runs' / job
        require(isinstance(row['inputSha256'], dict) and row['inputSha256'], 'Raw input provenance missing')
        for name, expected in row['inputSha256'].items():
            require(sha(raw / name) == expected, 'Independently analyzed raw input changed: ' + job + '/' + name)
        if row['derived']['clientNotSent'] or row['derived']['businessRejected'] or row['derived']['serverErrors'] or row['derived']['unknownUnresolved']:
            require(row['derived']['allOfferedAcceptedP99Millis'] is None and row['observedStableWindow'] is False,
                    'Overload cannot acquire a finite all-offered accepted p99/stable flag')
        rows.append(row)  # Deliberately preserve the original row object, including invalid status and nulls.
        files = [summary_path, local / 'postprocess.json', local / 'completion.json',
                 matrix_root / 'trial-plans' / (job + '.json'), raw / 'arrivals.csv.gz', raw / 'arrivals-archive.json']
        provenance.append({'id': job, 'sourceSummaryRowCanonicalJsonSha256': canonical_sha(row),
                           'artifacts': [artifact(path, repository) for path in files],
                           'independentAnalyzerInputSha256': row['inputSha256']})
    require(len(fingerprints) == 1, 'CPU rows are not one fixed-configuration group')
    require([row['measurementValid'] for row in rows] == [True, True, True, True, False], 'Original invalid18kr2 observation changed')
    require([row['id'] for row in rows if row['observedStableWindow']] == [JOBS[0], JOBS[3]], 'Original finite stability flags changed')
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    bundle = {'schemaVersion': 1, 'generatedAt': generated, 'trials': rows, 'criteria': criteria,
              'scope': 'Five unchanged independently analyzed rows from one CPU loopback fixed-config matrix. No pilot/GPU/idle-variant aggregation.',
              'sourceMatrixId': MATRIX, 'sourceMatrixPlanSha256': matrix['matrixPlanSha256'],
              'missingRegisteredPointIds': [MISSING]}
    proof = {'schemaVersion': 1, 'generatedAt': generated, 'builderSha256': sha(Path(__file__)),
             'sourceRevision': SOURCE, 'analysisIdentitySha256': ANALYSIS_ID,
             'comparisonFingerprintSha256': next(iter(fingerprints)),
             'matrixArtifacts': [artifact(registration_path, repository), artifact(matrix_root / 'matrix-summary.json', repository)],
             'trialSources': provenance, 'missingRegisteredPointIds': [MISSING],
             'scope': 'Raw input hashes rechecked locally; rows copied without re-analysis/reclassification. CSV archives and their manifests remain original. Whole native state archives remain local/FUSE; not duplicated for UI.',
             'limitations': ['One CPU host / three JVMs / loopback UDP; not independent hosts.',
                             'Finite350k windows:13k repeated stable,18k/26k overload observed; no sustained maximum claim.',
                             '18kr2 generator invalid retained;26kr2 was never launched after the registered halt.',
                             'Accepted-only p99 is conditional; all-offered accepted p99 remains null for dropped/rejected/unknown outcomes.']}
    output.mkdir(parents=True, exist_ok=True)
    require(not (output / 'summary.json').exists() and not (output / 'provenance.json').exists(), 'CREATE_NEW outputs already exist')
    save_new(output / 'summary.json', bundle)
    proof['bundleArtifact'] = artifact(output / 'summary.json', repository)
    save_new(output / 'provenance.json', proof)
    print(json.dumps({'points': len(rows), 'fingerprint': next(iter(fingerprints)),
                      'summary': str(output / 'summary.json'), 'provenance': str(output / 'provenance.json')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[5])
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    build(args.repository, args.output)


if __name__ == '__main__':
    main()
