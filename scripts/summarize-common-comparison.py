#!/usr/bin/env python3
"""Verify closed thin receipts before summarizing a finite common-subset campaign.

This verifies the published receipts against their frozen member inventories. Full
raw business replay and authenticated asset downloads are separate recorded steps;
this tool never substitutes thin metadata for replaying the private raw assets.
"""
from pathlib import Path
import argparse, hashlib, json

RATES = (10000, 50000, 100000, 250000)
ARMS = ('a1', 'b1', 'a2', 'b2')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path):
    return json.loads(path.read_text())


def bound_file(directory, manifest, original, local=None):
    path = directory / (local or original.replace('/', '__'))
    body = path.read_bytes()
    expected = manifest['files'][original]
    require(len(body) == expected['bytes'] and hashlib.sha256(body).hexdigest() == expected['sha256'],
            f'{directory.name}: changed thin member {original}')
    return json.loads(body)


def summarize(root):
    root = Path(root)
    preparation = root / 'preparation'
    for name, expected in load(preparation / 'MANIFEST.json').items():
        data = (preparation / name).read_bytes()
        require(len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'],
                'changed frozen preparation: ' + name)
    candidate_bytes = (preparation / 'CANDIDATE.json').read_bytes()
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()
    candidate = json.loads(candidate_bytes)
    admission = load(preparation / 'CPU_ADMISSION.json')
    names = ['qualification-r1', 'native-vector-q1', 'native-exchange-q1'] + [f'{r}-{a}' for r in RATES for a in ARMS]
    rows = []
    assets = []
    previous_exit = 0
    functional = []
    for name in names:
        d = root / name
        manifest = load(d / 'MEMBER_MANIFEST.json')
        proof = load(d / 'PRIVATE_ASSET_VERIFIED.json')
        plan = load(d / 'EXACT_COMPRESSED_PLAN.json')
        require(manifest['scope'] == name and manifest['allJavaAndOriginalWorkerStopped'], 'unclosed original ' + name)
        require(proof['authenticatedFullDownloadVerified'] and proof['allOriginalMembersVerified'], 'unverified original ' + name)
        require(proof['bytes'] == plan['bytes'] and proof['sha256'] == plan['sha256'], 'archive plan changed ' + name)
        require(proof['memberCount'] == len(manifest['files']) and proof['privateDraftRelease'] == 423510304, 'asset inventory differs ' + name)
        require(proof['name'] == f'vectormatch-common-comparison-20261027-r1-{name}.tar.gz', 'wrong asset ' + name)
        require(manifest['files']['inputs/CANDIDATE.json']['sha256'] == candidate_sha, 'artifact cohort changed ' + name)
        state = bound_file(d, manifest, 'complete.json')
        env = bound_file(d, manifest, 'environment.json')
        launch = bound_file(d, manifest, 'java.launch.json')
        exited = bound_file(d, manifest, 'java.exit.json')
        require(state['passed'] and exited['exitCode'] == 0 and exited['groupClosed'], 'failed native ' + name)
        require(env['bootId'] == admission['boot'] and env['hostname'] == admission['host'] and
                env['affinity'] == admission['chosen'] and env['cpuMax'] == admission['cpuMax'] and
                env['sourceCommit'] == candidate['sourceCommit'], 'environment changed ' + name)
        require(launch['epoch'] > previous_exit, 'overlapping Java measurement ' + name)
        previous_exit = exited['epoch']
        argv = launch['argv']
        require(argv[:3] == ['taskset', '-c', ','.join(map(str, admission['chosen']))], 'affinity argv changed ' + name)
        for flag in ['-Xms1g', '-Xmx3g', '-XX:ActiveProcessorCount=8', '-XX:+UseG1GC']:
            require(flag in argv, 'JVM flag changed ' + name)
        assets.append({'point': name, 'assetId': proof['assetId'], 'bytes': proof['bytes'], 'sha256': proof['sha256']})
        if name == 'qualification-r1':
            junit = bound_file(d, manifest, 'junit/RESULT.json')
            require(junit['found'] == junit['passed'] == 6 and junit['platform'] == 'Linux' and
                    all(junit[k] == 0 for k in ['failed', 'skipped', 'aborted', 'containerFailures']), 'qualification differs')
            continue
        config = bound_file(d, manifest, 'native/configuration.json')
        result = bound_file(d, manifest, 'native/result.json')
        audit = bound_file(d, manifest, 'PYTHON_AUDIT.json')
        resources = bound_file(d, manifest, 'native/resources.json')
        backlog = bound_file(d, manifest, 'native/backlog.json')
        require(audit['passed'] and audit['independentPythonBusinessReplay'] and state['rawAuditPassed'] and result['correctnessPassed'], 'replay failed ' + name)
        for key, value in audit['verified'].items():
            require(result[key] == value, 'raw audit/result mismatch ' + name + '/' + key)
        for original, key in [('native/commands.csv', 'sourceSha256'), ('native/outcomes.csv', 'fullOutcomeSha256'), ('native/trades.csv', 'fullTradeSha256')]:
            require(manifest['files'][original]['sha256'] == audit[key], 'raw digest differs ' + name)
        require(result['sourceSha256'] == audit['sourceSha256'], 'source hash differs ' + name)
        require(not any(result[k] for k in ['sustainedCapacityProven', 'replicated', 'comparativeWinner']), 'unsupported claim ' + name)
        require(result['accepted'] + result['businessRejected'] + result['notSent'] + result['unknown'] == result['planned'], 'incomplete arrival coverage ' + name)
        require(config['seed'] == 73439 and config['totalOutstandingCreditBound'] == 8192 and config['java'] == '21.0.13+9-LTS', 'common config changed ' + name)
        if name.startswith('native-'):
            require(config['rate'] == 1000 and config['seconds'] == 1 and result['accepted'] == 1000 and result['unknown'] == 0, 'functional qualification failed ' + name)
            functional.append((audit['sourceSha256'], audit['fullTradeSha256']))
            continue
        rate, arm = name.split('-')
        mode = 'VECTOR' if arm.startswith('a') else 'EXCHANGE'
        require(config['mode'] == mode and config['rate'] == int(rate) and config['seconds'] == 5 and result['planned'] == int(rate) * 5, 'point config differs ' + name)
        before = {x['collector']: x for x in resources['gcBefore']}
        gc_count = sum(x['count'] - before[x['collector']]['count'] for x in resources['gcAfter'])
        gc_ms = sum(x['elapsedMs'] - before[x['collector']]['elapsedMs'] for x in resources['gcAfter'])
        cpu_ns = resources['cpuAfterNs'] - resources['cpuBeforeNs']
        require(cpu_ns >= 0 and gc_count >= 0 and gc_ms >= 0, 'resource clock regressed ' + name)
        row = {'point': name, 'mode': mode, 'rate': int(rate), 'seconds': 5,
               'sourceSha256': audit['sourceSha256'], 'tradeSha256': audit['fullTradeSha256'],
               'characteristics': config['characteristics'], **result,
               'cpuSecondsMeasurementAndDrain': cpu_ns / 1e9,
               'averageProcessCoresMeasurementAndDrain': cpu_ns / result['measurementAndDrainNs'],
               'gcCollectionsMeasurementAndDrain': gc_count, 'gcElapsedMsMeasurementAndDrain': gc_ms,
               'sampledMaxQueue': max((x['queue'] for x in backlog), default=0),
               'sampledMaxOutstanding': max((x['outstanding'] for x in backlog), default=0)}
        rows.append(row)
    require(len(set(functional)) == 1, 'functional commands/trades differ')
    require(len({x['assetId'] for x in assets}) == 19, 'reused raw asset')
    for rate in RATES:
        cohort = [r for r in rows if r['rate'] == rate]
        require(len(cohort) == 4 and len({r['sourceSha256'] for r in cohort}) == 1, 'different frozen workload at ' + str(rate))
        accepted = [r for r in cohort if r['accepted'] == r['planned']]
        require(len({r['tradeSha256'] for r in accepted}) <= 1, 'full-acceptance trade histories differ at ' + str(rate))
    return {'schema': 'verified-common-comparison-summary-1', 'sourceCommit': candidate['sourceCommit'],
            'bootId': admission['boot'], 'affinity': admission['chosen'], 'finiteArms': len(rows),
            'planned': sum(r['planned'] for r in rows), 'accepted': sum(r['accepted'] for r in rows),
            'notSent': sum(r['notSent'] for r in rows), 'businessRejected': sum(r['businessRejected'] for r in rows),
            'unknown': sum(r['unknown'] for r in rows), 'finiteGatePasses': sum(r['finiteGatePassed'] for r in rows),
            'schedulingValidArms': sum(r['schedulerValid'] for r in rows),
            'sustainedCapacityProven': False, 'replicated': False, 'comparativeWinner': False,
            'scope': '16 five-second in-process common-subset API points; receipts checked, full raw replay recorded separately',
            'points': rows, 'privateAssets': assets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.evidence)
    with args.output.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('points', 'privateAssets')}))


if __name__ == '__main__':
    main()
