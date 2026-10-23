"""Pinned local preparation helpers. No network operation runs at import time."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parents[4]
EVIDENCE = WORKSPACE / 'evidence/2026-10-23/runpod-optimization'
WINDOW = EVIDENCE / 'window350k'
OUT = WINDOW / 'unknown-recovery'
JOB_ID = 'u-recover-w256-r1-v1'
FAILED_ID = 'w-window-26000-w256-r1'
FAILED = WINDOW / 'w256/runs' / FAILED_ID
REVISION = '52fbf7fa46ed274891a2bbf0d9fba9d87456d1f5'
SOURCE = OUT / 'tool-validation/source/UnknownRecoveryProbe.java'
CLASS = BASE / 'classes/io/vectormatch/cluster/UnknownRecoveryProbe.class'
HEADER = 'index\tworker\taccount_id\tproducer_id\trequest_seq\tclient_order_id\tobservation\n'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    value = hashlib.sha256()
    assert path.is_file() and not path.is_symlink(), str(path)
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def campaign():
    # Validate the frozen helper before importing any application/cloud helper code.
    formal = read(WINDOW / 'plan.json')
    path = BASE.parent / 'campaign.py'
    assert digest(path) == formal['controllerSha256']['campaign.py']
    spec = importlib.util.spec_from_file_location('frozen_window350k_campaign', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    identity = module.validate_identity(formal)
    assert identity['node']['revision'] == identity['load']['revision'] == REVISION
    assert identity['node'] == identity['load']
    return module, identity


def inputs():
    audit_path = WINDOW / 'tool-validation/unknown-audit.json'
    audit = read(audit_path)
    assert audit['passed'] and audit['cacheCompleteForThisFrozenSnapshot']
    assert digest(WINDOW / 'tool-validation/unknown-audit.py') == audit['auditToolSha256']
    assert audit['allExecutedMeasuredCommandsMatchOriginalPayloads'] and audit['allKnownRepliesMatchCanonicalCachedResults']
    assert audit['sourceLoadRevision'] == REVISION and len(audit['unresolved']) == 256
    assert audit['finalSnapshot']['sha256'] == digest(FAILED / 'final-snapshot.bin')
    assert audit['finalSnapshot']['commandSeq'] == 3726 and audit['finalSnapshot']['eventSeq'] == 7385
    assert audit['finalSnapshot']['marketSeq'] == 7319 and audit['finalSnapshot']['cachedResults'] == 3726
    config = read(FAILED / 'configuration.json')
    trial = read(FAILED / 'trial.json')
    load = read(FAILED / 'load-result.json')
    assert trial['id'] == FAILED_ID and trial.get('completedAt') and read(FAILED / 'receipt.json')['exitCode'] == 1
    assert load['unresolvedFinal'] == 256 and load['confirmedAcceptedCommands'] == 3307
    assert config['profile'] == 'extended-350k-256' and config['workers'] == 256
    assert config['producerPrefix'] == 'capacity-fixed-v1' and config['priceTicks'] == 10000
    assert config['quantityLotsPerMeasuredCommand'] == 1 and config['expectedStateProfile'] == 'capacity-350k-v1'
    assert trial['release'].endswith('/' + REVISION)
    assert trial['state'] == '/opt/vectormatch/runtime/capacity-20261023/' + FAILED_ID
    manifest = read(FAILED / 'arrivals-archive.json')
    assert digest(FAILED / 'arrivals.csv.gz') == manifest['compressedSha256']
    assert digest(FAILED / 'arrivals.csv') == manifest['rawSha256'] == audit['archive']['decoded']['sha256']
    wanted = {row['arrivalIndex']: row for row in audit['unresolved']}
    assert len(wanted) == 256 and len({row['worker'] for row in wanted.values()}) == 256
    with (FAILED / 'arrivals.csv').open(newline='') as stream:
        actual = {int(row['index']): row for row in csv.DictReader(stream) if row['outcome'] == 'UNKNOWN_UNRESOLVED'}
    assert set(actual) == set(wanted)
    lines = [HEADER]
    observations = []
    for index, value in sorted(wanted.items()):
        row = actual[index]
        command = value['command']
        assert command == {'type': 'Place', 'accountId': int(row['account_id']), 'producerId': row['producer_id'],
                           'requestSeq': int(row['request_seq']), 'clientOrderId': row['client_order_id'],
                           'side': 'BUY', 'priceTicks': 10000, 'quantityLots': 1, 'timeInForce': 'IOC'}
        assert int(row['worker']) == value['worker'] == index % 256
        assert command['accountId'] == 1000100 + value['worker'] % 64
        assert command['requestSeq'] == index // 256 + 1
        assert command['producerId'] == 'capacity-fixed-v1-w' + str(value['worker'])
        assert command['clientOrderId'] == 'ioc-capacity-fixed-v1-' + str(index)
        observation = value['snapshotObservation']; observations.append(observation)
        lines.append('\t'.join([str(index), row['worker'], row['account_id'], row['producer_id'],
                                row['request_seq'], row['client_order_id'], observation]) + '\n')
    assert observations.count('CACHED_ACCEPTED') == 252
    assert observations.count('ABSENT_FROM_THIS_FROZEN_SNAPSHOT') == 4
    names = ['configuration.json', 'trial.json', 'load-process.json', 'load-result.json', 'failure.json',
             'receipt.json', 'final-snapshot.bin', 'arrivals.csv', 'arrivals.csv.gz', 'arrivals-archive.json']
    proofs = {str((FAILED / name).relative_to(WORKSPACE)): digest(FAILED / name) for name in names}
    proofs[str(audit_path.relative_to(WORKSPACE))] = digest(audit_path)
    proofs[str((WINDOW / 'tool-validation/unknown-audit.py').relative_to(WORKSPACE))] = audit['auditToolSha256']
    return {'proofs': proofs, 'commands': ''.join(lines), 'state': trial['state'],
            'preCoreSha256': audit['finalSnapshot']['sha256'], 'expectedExportedSeq': 0,
            'expectedPending': 7385, 'failedTrialState': trial['state']}


def validate_plan(plan):
    assert plan['jobId'] == JOB_ID and plan['originalCapacityRoundRemainsInvalid'] is True
    assert plan['wholeRecoveryBudgetSeconds'] == 900 and plan['probeDeadlineSeconds'] == 600
    for name, expected in plan['controllerSha256'].items():
        assert name in ('common.py', 'register.py', 'run.py') and digest(BASE / name) == expected
    assert set(plan['controllerSha256']) == {'common.py', 'register.py', 'run.py'}
    assert digest(SOURCE) == plan['sourceSha256'] and digest(CLASS) == plan['classSha256']
    for name, expected in plan['classFiles'].items():
        assert name in ('UnknownRecoveryProbe.class', 'UnknownRecoveryProbe$Saved.class')
        assert digest(CLASS.parent / name) == expected
    assert set(plan['classFiles']) == {'UnknownRecoveryProbe.class', 'UnknownRecoveryProbe$Saved.class'}
    assert hashlib.sha256(json.dumps(plan['classFiles'], sort_keys=True).encode()).hexdigest() == plan['classBundleSha256']
    observed = inputs()
    assert observed['proofs'] == plan['inputSha256'] and observed['state'] == plan['state']
    assert hashlib.sha256(observed['commands'].encode()).hexdigest() == plan['commandsSha256']
    assert digest(OUT / 'commands.tsv') == plan['commandsSha256']
    c, identity = campaign()
    assert identity == plan['identity']
    return c, identity
