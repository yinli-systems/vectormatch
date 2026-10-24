"""Strict configured-policy evidence, never a claim about observed OS sleep duration.

Schema remains a draft until the fresh-per-consumption Java fix and native proof
are frozen. Multiple actual instances of one logical role are permitted/bounded.
"""
import json
from pathlib import Path

PROPERTY = 'vectormatch.retention.idleMaxParkNs'
ASSOCIATION = ('Direct shared-driver object and bounded factory creations associated with exact launched contexts. '
               'Intended uses follow pinned per-role constructor order, not a global call order or a count of active threads.')
USES = {
    'driver-shared': ['directly installed shared-driver context object'],
    'owner-driver-shared': ['directly installed shared-driver context object'],
    'archive-shared': ['control-subscription registration retry helper; may never idle', 'Archive shared AgentRunner'],
    'consensus': ['ConsensusModuleAgent internal waits', 'ConsensusModule AgentRunner'],
    'service': ['ClusteredServiceAgent internal waits', 'ClusteredServiceContainer AgentRunner']}

NODE_ROLES = {'driver-shared': 5, 'archive-shared': 20, 'consensus': 20, 'service': 20}
OWNER_ROLES = {'owner-driver-shared': 5}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def selection(maximum):
    require(type(maximum) is int and maximum in [100000, 1000000], 'Explicit canonical idle arm required')
    return {'schema': 'retention-idle-selection-v1', 'property': PROPERTY,
            'maximumParkNs': maximum, 'factor': 'maximum requested park only'}


def validate_actual(value, maximum, pid, node):
    require(set(value) == {'schema', 'node', 'pid', 'selection', 'instancesDistinct', 'instances',
                           'selectedLogicalRoles', 'expectedConsumptionCounts', 'observedConsumptionCounts',
                           'sleepDurationMeasured', 'hardRealtimeGuaranteed',
                           'runningAgentThreadCountIndependentlyObserved', 'associationScope'},
            'Unknown/missing actual idle attestation field')
    require(value['schema'] == 'retention-idle-actual-v2' and type(value['node']) is int
            and value['node'] == node and type(value['pid']) is int and value['pid'] == pid and pid > 1,
            'Actual idle process/node identity mismatch')
    require(value['selection'] == selection(maximum) and value['instancesDistinct'] is True
            and value['sleepDurationMeasured'] is False and value['hardRealtimeGuaranteed'] is False
            and value['runningAgentThreadCountIndependentlyObserved'] is False
            and value['associationScope'] == ASSOCIATION, 'Actual idle source/selection/measurement scope mismatch')
    roles = OWNER_ROLES if node == -1 else NODE_ROLES
    require(type(node) is int and node in [-1, 0, 1, 2], 'Unsupported actual idle role scope')
    counts = {role: len(USES[role]) for role in roles}
    require(value['selectedLogicalRoles'] == sorted(roles)
            and value['expectedConsumptionCounts'] == counts and value['observedConsumptionCounts'] == counts
            and all(type(n) is int for field in ['expectedConsumptionCounts','observedConsumptionCounts']
                    for n in value[field].values()),
            'Pinned source bounded factory consumption inventory differs')
    rows = value['instances']
    require(isinstance(rows, list) and len(rows) == sum(counts.values()), 'Exact consumed factory instance inventory required')
    seen, per_role = set(), {role: set() for role in roles}
    for row in rows:
        require(set(row) == {'role', 'instanceOrdinal', 'roleConsumptionOrdinal', 'roleConsumptionBound',
                             'strategyClass', 'strategyDescription', 'maximumSpins', 'maximumYields',
                             'minimumParkNs', 'maximumParkNs', 'sourceDerivedIntendedUse', 'factoryCallerStack',
                             'factoryCallerFrameLimit', 'factoryCallerTextByteLimit', 'factoryCallerTailMayBeOmitted',
                             'association'}, 'Unknown/missing consumed idle instance field')
        role, ordinal, consumption = row['role'], row['instanceOrdinal'], row['roleConsumptionOrdinal']
        require(role in roles and type(ordinal) is int and ordinal > 0 and ordinal not in seen,
                'Unknown role or reused actual idle instance ordinal')
        require(type(consumption) is int and consumption in range(1, counts[role]+1)
                and consumption not in per_role[role] and type(row['roleConsumptionBound']) is int
                and row['roleConsumptionBound'] == counts[role], 'Per-role consumed ordinal/bound differs')
        seen.add(ordinal); per_role[role].add(consumption)
        text = ('BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=%d, '
                'minParkPeriodNs=1000, maxParkPeriodNs=%d}') % (roles[role], maximum)
        require(row['strategyClass'] == 'org.agrona.concurrent.BackoffIdleStrategy'
                and row['strategyDescription'] == text and row['maximumSpins'] == 10
                and row['maximumYields'] == roles[role] and row['minimumParkNs'] == 1000
                and row['maximumParkNs'] == maximum, 'Actual consumed idle strategy tuple differs')
        association = ('actual installed shared-driver getter object' if 'driver' in role else
                       'source-ordered factory consumption; private agent field not read back')
        require(row['sourceDerivedIntendedUse'] == USES[role][consumption-1]
                and row['association'] == association, 'Source-derived factory use/getter association differs')
        stack = row['factoryCallerStack']
        require(row['factoryCallerFrameLimit'] == 5 and row['factoryCallerTextByteLimit'] == 256
                and isinstance(stack, list) and 1 <= len(stack) <= 5
                and type(row['factoryCallerTailMayBeOmitted']) is bool
                and row['factoryCallerTailMayBeOmitted'] == (len(stack) == 5), 'Bounded caller diagnostic metadata differs')
        for frame in stack:
            require(set(frame) == {'class', 'method', 'classTruncated', 'methodTruncated', 'line'}
                    and type(frame['line']) is int, 'Bounded caller frame fields differ')
            for name in ['class', 'method']:
                require(isinstance(frame[name], str) and 0 < len(frame[name].encode('utf8')) <= 256
                        and type(frame[name+'Truncated']) is bool, 'Caller frame text/byte/truncation bounds differ')
    require(seen == set(range(1, len(rows)+1))
            and all(per_role[role] == set(range(1, n+1)) for role, n in counts.items()),
            'Per-process actual creation ordinal or per-role consumption closure differs')
    return {'passed': True, 'logicalRoles': len(roles), 'actualFactoryCreations': len(rows),
            'perRoleActualFactoryCreations': counts, 'configuredMaximumParkNs': maximum,
            'actualSleepDurationMeasured': False, 'runningAgentThreadCountIndependentlyObserved': False,
            'hardRealtimeGuaranteed': False}


def validate_idle_artifacts(base, root, registry, maximum):
    """Closed-only read of actual startup files/logs and owner observations."""
    root = Path(root)
    reports = []
    for node in range(3):
        identity = next(row['identity'] for row in registry.records.values()
                        if row['role'] == 'window-8-node-' + str(node))
        folder = root / ('node-%d/idle-observations' % node)
        base.no_links(folder)
        # This fresh, non-restarting arm expects one launch, retaining both intent and actual.
        require({p.name for p in folder.iterdir()} == {'idle-000.intent.json', 'idle-000.actual.json'},
                'Fresh single-launch idle evidence closure differs')
        intent_path, actual_path = folder / 'idle-000.intent.json', folder / 'idle-000.actual.json'
        for path in [intent_path, actual_path]:
            base.no_links(path)
            require(path.is_file() and path.stat().st_size <= 1024**2, 'Idle evidence file size/type cap')
        intent, actual = json.loads(intent_path.read_text()), json.loads(actual_path.read_text())
        require(set(intent) == {'schema', 'slot', 'node', 'pid', 'atUTC', 'selection'}
                and intent['schema'] == 'retention-idle-startup-intent-v1' and intent['slot'] == 0
                and intent['node'] == node and intent['pid'] == identity['pid']
                and intent['selection'] == selection(maximum), 'Reserved idle intent binding differs')
        report = validate_actual(actual, maximum, identity['pid'], node)
        lines = (root / ('node-%d.log' % node)).read_text().splitlines()
        logged = [json.loads(line.split('VECTOR_V3_IDLE_ATTESTATION ', 1)[1])
                  for line in lines if line.startswith('VECTOR_V3_IDLE_ATTESTATION ')]
        require(logged == [actual], 'Actual startup file/log idle evidence mismatch')
        reports.append(dict(report, node=node))
    parent = next(row['identity'] for row in registry.records.values() if row['role'] == 'pilot-parent')
    load = root / 'load'
    for name in ['configuration.json', 'load-result.json']:
        require(json.loads((load / name).read_text())['retentionIdleSelection'] == selection(maximum),
                'Load configured/summary idle selection mismatch')
    samples = json.loads((load / 'transport-observations.json').read_text())
    require(isinstance(samples, list) and samples, 'Owner actual transport observations required')
    for sample in samples:
        reports.append(validate_actual(sample['retentionIdlePolicy'], maximum, parent['pid'], -1))
    terminal = json.loads((load / 'load-result.json').read_text())['physicalOfferTape']['lastActualTransportObservation']
    validate_actual(terminal['retentionIdlePolicy'], maximum, parent['pid'], -1)
    return {'passed': True, 'nodeRolesPerProcess': 4, 'ownerDriverRoles': 1,
            'configuredMaximumParkNs': maximum, 'reports': reports,
            'actualSleepDurationMeasured': False,
            'scope': 'Actual installed instances/factory consumption evidence; owner loop remains unchanged at up to1ms'}
