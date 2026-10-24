"""Local, source-pinned preparation for a separate pilot checkpoint job; no cloud action at import."""
import hashlib
import importlib.util
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parents[4]
EVIDENCE = WORKSPACE / 'evidence/2026-10-23/runpod-optimization'
WINDOW = EVIDENCE / 'window350k'
OUT = WINDOW / 'checkpoint'
PILOT = WINDOW / 'pilot/runs/w-pilot-10000-w128'
JOB_ID = 'p-checkpoint-pilot350k-v1'
REVISION = '52fbf7fa46ed274891a2bbf0d9fba9d87456d1f5'
CORE_SHA = '2295cdc63e603aa5a225e6e39fbb9f7316c47daf1faf7b064b8345045dc28c06'
SOURCE = OUT / 'tool-validation/source/CapacityCheckpointProbe.java'
CLASS = BASE / 'classes/io/vectormatch/cluster/CapacityCheckpointProbe.class'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    assert path.is_file() and not path.is_symlink(), str(path)
    value = hashlib.sha256()
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
    plan = read(WINDOW / 'pilot-plan.json')
    path = BASE.parent / 'campaign.py'
    assert digest(path) == plan['controllerSha256']['campaign.py']
    spec = importlib.util.spec_from_file_location('frozen_checkpoint_window350k_campaign', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    identity = module.validate_identity(plan)
    assert identity['node']['revision'] == identity['load']['revision'] == REVISION
    return module, identity


def prerequisites():
    """Completion is an ordering/cleanup gate, never a claim that every NAK trial was valid."""
    trial = read(PILOT / 'trial.json'); result = read(PILOT / 'result.json')
    assert result['passed'] and result['canonicalSnapshotBytesVerified'] and result['outboxPendingVerified']
    assert result['confirmedAcceptedCommands'] == result['scheduledArrivals'] == 350000
    assert result['finalCommandSeq'] == 350167 and result['finalEventSeq'] == 700267 and result['finalMarketSeq'] == 700201
    assert result['finalOutboxPending'] == 700267 and result['stateHash'] == CORE_SHA
    assert trial['release'].endswith('/' + REVISION) and trial.get('completedAt')
    assert trial['state'] == '/opt/vectormatch/runtime/capacity-20261023/w-pilot-10000-w128'
    assert (PILOT / 'final-snapshot.bin').stat().st_size == 57682277 and digest(PILOT / 'final-snapshot.bin') == CORE_SHA
    proofs = {}
    for name in ('trial.json', 'configuration.json', 'result.json', 'receipt.json', 'final-snapshot.bin',
                 'fixed-leader-check.json', 'configuration-verification.json', 'arrivals-archive.json',
                 'node0/process.json', 'node1/process.json', 'node2/process.json'):
        path = PILOT / name; proofs[str(path.relative_to(WORKSPACE))] = digest(path)
    assert read(PILOT / 'fixed-leader-check.json')['passed']
    assert read(PILOT / 'configuration-verification.json')['passed']
    states = {trial['state']}
    for cohort in ('pilot', 'w128', 'w256'):
        folder = WINDOW / cohort / 'runs'
        if folder.exists():
            for path in folder.glob('*/trial.json'):
                value = read(path); assert value['state'].startswith('/opt/vectormatch/runtime/capacity-20261023/')
                states.add(value['state'])
    nak = EVIDENCE / 'nak'
    matrix = nak / 'plan.json'
    assert matrix.exists(), 'New NAK plan must finish before this checkpoint registration'
    completed = []
    for path in (nak / 'pilot-plan.json', matrix):
        if not path.exists():
            continue
        proofs[str(path.relative_to(WORKSPACE))] = digest(path)
        plan = read(path)
        for task in plan['trials']:
            directory = nak / task['cohort'] / 'runs' / task['id']
            raw = read(directory / 'trial.json')
            assert raw.get('completedAt'), 'NAK attempt still pending'
            assert raw['state'].startswith('/opt/vectormatch/runtime/capacity-20261023/')
            assert read(directory / 'all-owned-processes-stopped.json')['passed'], 'NAK cleanup incomplete'
            states.add(raw['state']); completed.append(raw['completedAt'])
            for name in ('trial.json', 'receipt.json', 'all-owned-processes-stopped.json'):
                target = directory / name; proofs[str(target.relative_to(WORKSPACE))] = digest(target)
    timeline = nak / 'timeline.jsonl'
    events = [json.loads(line) for line in timeline.read_text().splitlines()]
    done = [event for event in events if event.get('action') == 'nak-delay-matrix-completed']
    assert done and max(completed) <= done[-1]['timestamp'], 'NAK matrix completion timeline missing/too early'
    proofs[str(timeline.relative_to(WORKSPACE))] = digest(timeline)
    # Same failed state may have been repaired under its own job; do not treat it as this checkpoint target.
    recovery = WINDOW / 'unknown-recovery/runs/u-recover-w256-r1-v1/verification.json'
    assert read(recovery)['passed']
    proofs[str(recovery.relative_to(WORKSPACE))] = digest(recovery)
    return {'proofs': proofs, 'knownTestStates': sorted(states), 'state': trial['state']}


def validate_plan(plan):
    assert plan['jobId'] == JOB_ID and plan['wholeJobBudgetSeconds'] == 900
    assert plan['snapshotCommandTimeoutSeconds'] == plan['snapshotRecoveryWaitSeconds'] == 180
    assert plan['fullPostProbeTimeoutSeconds'] == 600
    for name, expected in plan['controllerSha256'].items():
        assert name in ('common.py', 'register.py', 'run.py') and digest(BASE / name) == expected
    assert set(plan['controllerSha256']) == {'common.py', 'register.py', 'run.py'}
    assert digest(SOURCE) == plan['sourceSha256'] and digest(CLASS) == plan['classSha256']
    assert prerequisites() == plan['prerequisites']
    c, identity = campaign(); assert identity == plan['identity']
    return c, identity
