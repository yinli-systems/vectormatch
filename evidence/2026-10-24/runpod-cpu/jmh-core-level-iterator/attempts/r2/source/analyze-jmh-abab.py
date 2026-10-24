"""Read-only acceptance and descriptive batch means for the registered core A/B/A/B."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics

REPO = Path(__file__).resolve().parents[3]
VERIFIER_SHA = '73cc163d605c9471087ce65a915a943fabe988c18018f984a2e3a8d67d4da99b'
WORKER_SHA = '8323714d0fab440bb426908af1fcbb246a4ef38becf3077d1d6e6976e53517e7'
REVISIONS = {'A': '987f6526b8a0b3c3516ee668a239990cc79fbd8f', 'B': '7a4cf09be5055fa48c4246b21679d9038bbbfd5f'}
CORE = 'lib/core-0.1.0-SNAPSHOT.jar'
ENGINE = 'io/vectormatch/core/MatchingEngine.class'
ENGINE_SHA = {'A': 'ba350e0abfbed6ccf58e6e4274c5186a4fa658bd43fdcf13520137d03aeeb1c0',
              'B': '1fa54482a99dea5082a3eda97122c3e2e44d262f981240d062fe8a73ea9ff381'}
JARS = {'lib/' + n for n in ('commons-math3-3.6.1.jar', 'core-0.1.0-SNAPSHOT.jar', 'jmh-core-1.37.jar',
                           'jopt-simple-5.0.4.jar', 'vectormatch-core-jmh-0.1.0-SNAPSHOT.jar')}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Regular input required: ' + str(path))
    return json.loads(path.read_text())


def argv_sha(arguments):
    import os
    return hashlib.sha256(b''.join(os.fsencode(a) + b'\0' for a in arguments)).hexdigest()


def identity(record):
    require(type(record['pid']) is int and record['pid'] > 1 and type(record['startTicks']) is int
            and record['startTicks'] > 0, 'Invalid positive process identity')
    require(record['commandSha256'] == argv_sha(record['arguments']), 'Captured argv SHA differs')
    return record['pid'], record['startTicks'], record['commandSha256']


def audit_gate(audit, plan):
    require(audit.get('passed') is True, 'Artifact audit did not pass')
    require(audit.get('distributions') == {g: plan['distributions'][g]['files'] for g in ('A', 'B')},
            'Artifact inventories do not match registered plan')
    expected = {name: {} for name in JARS}
    expected[CORE] = {ENGINE: ENGINE_SHA}
    require(audit.get('changedJarEntries') == expected, 'Artifact audit permits non-engine changes or missing evidence')


def ownership_gate(owned, process, events, stage):
    records = owned['records']
    require(len(records) == 46 and owned['forkIdentitiesObserved'] == 45, 'Expected1runner and45 positive fork records')
    keys = [identity(r) for r in records]
    require(len(set(keys)) == 46 and len({r['pid'] for r in records}) == 46, 'Duplicate process/fork identity')
    runners = [r for r in records if r['kind'] == 'runner']
    forks = [r for r in records if r['kind'] == 'fork']
    require(len(runners) == 1 and len(forks) == 45, 'Incorrect runner/fork kinds')
    require(not owned['unverifiedCandidates'] and not owned['errors'], 'Unresolved process observation')
    require(all(r['stopped'] is True and type(r['observedSamples']) is int and r['observedSamples'] > 0 for r in records),
            'Every observed identity must have stopped after positive sampling')
    runner = runners[0]
    require(identity(process) == identity(runner), 'Runner process record differs')
    for key, value in process.items():
        require(runner.get(key) == value, 'Runner process proof differs: ' + key)
    require(process['arguments'] == stage['arguments'] and process['expectedCommandSha256'] == process['commandSha256']
            == process['actualCommandSha256'], 'Runner double argv proof differs')
    require(runner['sessionId'] == runner['processGroupId'] == runner['pid'] and runner['parentPid'] > 1,
            'Runner parent/session differs')
    parents = {r['pid']: r for r in records}
    for fork in forks:
        require(fork['arguments'].count('org.openjdk.jmh.runner.ForkedMain') == 1, 'Not a measured ForkedMain')
        require(fork['sessionId'] == fork['processGroupId'] == runner['pid'], 'Fork session differs')
        require(type(fork['sourceParentTid']) is int and fork['sourceParentTid'] > 1
                and type(fork['sourceParentThreadStartTicks']) is int and fork['sourceParentThreadStartTicks'] > 0,
                'Missing positive source task identity')
        seen, current = set(), fork
        while current['pid'] != runner['pid']:
            require(current['pid'] not in seen and current['parentPid'] in parents, 'Fork parent chain not owned')
            seen.add(current['pid']); current = parents[current['parentPid']]
    discovered, stopped = {}, set()
    for event in events:
        if event['event'] == 'discovered':
            key = identity(event)
            require(key not in discovered, 'Duplicate discovery event')
            discovered[key] = event
        elif event['event'] == 'stopped':
            matches = [k for k in discovered if k[:2] == (event['pid'], event['startTicks'])]
            require(len(matches) == 1 and matches[0] not in stopped, 'Stopped event has no unique prior discovery')
            stopped.add(matches[0])
        else:
            require(event['event'] == 'task-observation-gap', 'Unexpected process event')
    require(set(discovered) == set(keys) == stopped, 'Discovery/stopped event coverage differs')
    for record in records:
        event = discovered[identity(record)]
        for key, value in record.items():
            if key not in ('observedSamples', 'stopped'):
                require(event.get(key) == value, 'Process discovery proof differs: ' + key)
    require(stage['cleanup']['processes'] == owned and stage['cleanup'].get('all45ExpectedMeasuredForksObserved') is True,
            'Cleanup does not bind complete ownership summary')
    return [identity(r) for r in forks]


def analyze_attempt(attempt):
    attempt = Path(attempt); raw = attempt / 'raw'
    plan, registered, receipt = read(raw / 'plan.json'), read(attempt / 'registration.json'), read(raw / 'receipt.json')
    require(plan == registered and plan['workerSha256'] == WORKER_SHA and sha(raw / 'worker.py') == WORKER_SHA,
            'Registered plan/worker differs')
    expected_stages = [{'id': n, 'group': g, 'expectedCases': 15, 'forks': 3, 'warmup': 500, 'measurement': 10}
                       for n, g in zip(('A1', 'B1', 'A2', 'B2'), ('A', 'B', 'A', 'B'))]
    require(plan['stages'] == expected_stages, 'Fixed four-stage15case/3fork/500warmup/10measurement contract differs')
    require(set(plan['distributions']) == {'A', 'B'} and all(plan['distributions'][g]['revision'] == REVISIONS[g]
            and set(plan['distributions'][g]['files']) == JARS for g in ('A', 'B')), 'Registered source/inventory differs')
    require(receipt['passed'] is True and receipt['jobId'] == plan['jobId'] and len(receipt['stages']) == 4
            and receipt.get('interruptedSignal') is None, 'Incomplete/interrupted campaign receipt')
    verifier = REPO / 'scripts/verify-core-jmh.py'
    require(sha(verifier) == VERIFIER_SHA, 'Independent verifier source changed')
    spec = importlib.util.spec_from_file_location('jmh_independent_case_verifier', verifier)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    proof = module.verify(attempt / 'registration.json', raw)
    data, inputs, all_forks = {}, {}, []
    key = lambda row: (row['benchmark'], tuple(sorted(row['params'].items())))
    for position, declaration in enumerate(expected_stages):
        name, group = declaration['id'], declaration['group']
        stage = read(raw / (name + '-verification.json'))
        require(stage['stage'] == name and stage['group'] == group and stage['sourceRevision'] == REVISIONS[group]
                and stage['passed'] is True and stage['exitCode'] == 0 and stage['cleanup']['passed'] is True
                and stage.get('interruptedSignal') is None, 'Stage receipt status/source differs')
        names = {name + suffix for suffix in ('.json', '.log', '-process.json', '-owned-process-summary.json', '-owned-processes.jsonl')}
        require(set(stage['rawFilesSha256']) == names, 'Incomplete stage raw SHA inventory')
        for filename, digest in stage['rawFilesSha256'].items():
            require(sha(raw / filename) == digest, 'Stage raw input SHA differs: ' + filename)
        recorded = dict(receipt['stages'][position])
        post_sha = recorded.pop('postArtifactAuditSha256', None)
        require(recorded == stage, 'Campaign/stage receipt differs beyond documented post-audit hash')
        before, after = raw / (name + '-artifact-audit.json'), raw / (name + '-artifact-audit-after.json')
        require(post_sha == sha(after), 'Post-stage artifact audit SHA differs')
        before_value, after_value = read(before), read(after)
        require(before_value == after_value, 'Artifacts changed during stage')
        audit_gate(before_value, plan)
        owned, process = read(raw / (name + '-owned-process-summary.json')), read(raw / (name + '-process.json'))
        with (raw / (name + '-owned-processes.jsonl')).open() as stream:
            events = [json.loads(line) for line in stream if line.strip()]
        all_forks.extend(ownership_gate(owned, process, events, stage))
        rows = read(raw / (name + '.json'))
        require(all(r.get('warmupBatchSize') == 1 and r.get('measurementBatchSize') == 1 for r in rows), 'Batch size differs')
        data[name] = {key(r): r for r in rows}
        inputs[name] = {'rawFilesSha256': stage['rawFilesSha256'], 'verificationSha256': sha(raw / (name + '-verification.json')),
            'artifactBeforeSha256': sha(before), 'artifactAfterSha256': sha(after), 'forks': 45,
            'observerCpuSeconds': stage['observerCpuSeconds'], 'observerElapsedSeconds': stage['observerElapsedSeconds']}
    require(len(all_forks) == len(set(all_forks)) == 180, 'Expected180 unique measured fork identities')
    require(all(data[n].keys() == data['A1'].keys() for n in data), 'Case coverage differs between stages')
    cases = []
    for case_key, row in data['A1'].items():
        stages = {n: {'mean': data[n][case_key]['primaryMetric']['score'],
            'forkMeans': [statistics.mean(f) for f in data[n][case_key]['primaryMetric']['rawData']],
            'jmhError': data[n][case_key]['primaryMetric']['scoreError']} for n in data}
        a = stages['A1']['forkMeans'] + stages['A2']['forkMeans']; b = stages['B1']['forkMeans'] + stages['B2']['forkMeans']
        target = 'FreshMatchingBenchmark' in row['benchmark'] and row['params']['initialPriceLevels'] in ('1', '100') and row['params']['tradesPerCommand'] in ('10', '100')
        cases.append({'benchmark': row['benchmark'], 'params': row['params'], 'declaredTarget': target,
            'unit': 'us/normalized command in64command batch', 'stages': stages,
            'Amean': statistics.mean(a), 'Bmean': statistics.mean(b), 'BoverA': statistics.mean(b) / statistics.mean(a),
            'pair1BoverA': stages['B1']['mean'] / stages['A1']['mean'], 'pair2BoverA': stages['B2']['mean'] / stages['A2']['mean'],
            'sameImprovementDirectionBothPairs': stages['B1']['mean'] < stages['A1']['mean'] and stages['B2']['mean'] < stages['A2']['mean'],
            'AforkRange': [min(a), max(a)], 'BforkRange': [min(b), max(b)], 'outliersRemoved': 0})
    require(len(cases) == 15 and sum(r['declaredTarget'] for r in cases) == 4, 'Incorrect target/all-case coverage')
    return {'passed': True, 'sourceSha256': sha(__file__), 'independentVerifierSha256': VERIFIER_SHA,
        'independentCaseVerification': proof, 'stageInputs': inputs, 'cases': cases,
        'inputSha256': {p: sha(raw / p) for p in ('plan.json', 'receipt.json', 'worker.py')},
        'counts': {'stages': 4, 'casesPerStage': 15, 'measuredForks': 180, 'rawMeasurements': 1800},
        'ownershipScope': 'Archived matching source plus captured argv/discovery/stop proofs; no fresh OS inspection or fabricated second-read samples.',
        'scope': 'All15cases/all4rounds/all180forks retained. Ten measurements nested within each fork; six fork means per condition. Ratios/ranges are descriptive batch means, not per-order p99, sustained throughput or proof of significance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--attempt', type=Path, required=True)
    args = parser.parse_args(); report = analyze_attempt(args.attempt)
    with (args.attempt / 'comparison.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
    lines = ['# Complete CPU core A/B/A/B', '', 'All15cases,3forks/case,500warmup/10measurement; normalized64-command batch means. No outliers removed.', '',
        '|Case|Params|A mean us|B mean us|Pair1 B/A|Pair2 B/A|Combined B/A|', '|---|---|---:|---:|---:|---:|---:|']
    for r in report['cases']:
        label = 'MATCH' if 'FreshMatching' in r['benchmark'] else r['params']['action']
        lines.append(f"|{label}|{r['params']}|{r['Amean']:.6f}|{r['Bmean']:.6f}|{r['pair1BoverA']:.3f}|{r['pair2BoverA']:.3f}|{r['BoverA']:.3f}|")
    lines += ['', 'B/A<1 means lower measured time. See [all fork means and ranges](comparison.json). These finite descriptive comparisons do not establish individual-order p99, significance, sustained new-command rate or replicated-path improvement. The capacity workload uses one repeatedly partial maker and needs a separate comparison.']
    with (args.attempt / 'README.md').open('x') as stream:
        stream.write('\n'.join(lines) + '\n')
    print(json.dumps({'passed': True, 'counts': report['counts']}))


if __name__ == '__main__':
    main()
