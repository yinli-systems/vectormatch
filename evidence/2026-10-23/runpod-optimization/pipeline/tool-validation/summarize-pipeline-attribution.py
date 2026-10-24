#!/usr/bin/env python3
"""Prepare/reproduce direct128-session versus multiplexed1-session attribution.

PIPELINE_ROOT OUTPUT_JSON [--cohorts direct,multiplexed|pilot]
The default requires all four registered formal attempts exported completely.
--self-test uses only synthetic values and loads frozen source, never cloud data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import types


NAK_WRAPPER_SHA = 'e4eba79229bd21fcb439a45af488298254ae2438f3e91868544f8b37099a931d'
COHORTS = (('direct', 'multiplexed'), ('pilot',))
ADAPTATIONS = (
    ("'pilot100us'", "'pilot'"),
    ("'delay1000'", "'direct'"),
    ("'delay100000'", "'multiplexed'"),
    ("tasks[0].get('nakDelayNs')", "plan.get('fixedNakNodeAndLoadNs')"),
    ("            failure = optional_json(directory / 'failure.json', core, inputs)\n",
     "            failure = optional_json(directory / 'failure.json', core, inputs)\n"
     "            if load is None and isinstance(failure, dict) and isinstance(failure.get('loadSummary'), dict):\n"
     "                load = failure['loadSummary']  # Actual failed-run evidence, in memory only; never a fake result.\n"),
)


def digest(path):
    h, size = hashlib.sha256(), 0
    with path.open('rb') as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(data)
            size += len(data)
    return {'path': str(path), 'sha256': h.hexdigest(), 'bytes': size}


def adapted_wrapper(path):
    identity = digest(path)
    if identity['sha256'] != NAK_WRAPPER_SHA:
        raise ValueError('Frozen NAK wrapper source changed')
    source = path.read_text()
    changes = []
    for before, after in ADAPTATIONS:
        count = source.count(before)
        if count == 0 or ((before.startswith('tasks[') or before.lstrip().startswith('failure =')) and count != 1):
            raise ValueError('Unexpected frozen source adaptation boundary: ' + before)
        source = source.replace(before, after)
        changes.append({'before': before, 'after': after, 'occurrences': count})
    result = types.ModuleType('frozen_nak_in_memory_for_pipeline')
    result.__file__ = str(path)
    exec(compile(source, str(path) + ':in-memory-pipeline-directory-map', 'exec'), result.__dict__)
    return result, identity, changes


def expected_tasks(cohorts):
    if cohorts == ('pilot',):
        return [{'id': 'p-pilot-multiplexed-10000-w128', 'cohort': 'pilot', 'rate': 10000,
                 'arrivals': 350000, 'workers': 128, 'transportMode': 'multiplexed',
                 'phase': 'pipeline-multiplexed-full350k-canonical-pilot', 'repetition': 1}]
    if cohorts == ('direct', 'multiplexed'):
        return [{'id': f'p-{mode}-26000-w128-r{rep}', 'cohort': mode, 'rate': 26000,
                 'arrivals': 350000, 'workers': 128, 'transportMode': mode,
                 'phase': 'pipeline-session-ownership-arrangement-control', 'repetition': rep}
                for rep in (1, 2) for mode in ('direct', 'multiplexed')]
    raise ValueError('Request formal direct,multiplexed or explicit single pilot')


def require_plan(plan, cohorts):
    if not isinstance(plan, dict) or plan.get('trials') != expected_tasks(cohorts):
        raise ValueError('Require exact registered task order and logicalW128 workload')
    if not (plan.get('fixedLogicalInFlight') == 128 and plan.get('fixedFifoSlots') == 8192
            and plan.get('fixedNakNodeAndLoadNs') == 1000):
        raise ValueError('Missing/differing fixed logical window/FIFO/NAK plan declaration')
    return plan['trials']


def require_complete(result, plan, cohorts):
    tasks = require_plan(plan, cohorts)
    actual = [trial['id'] for group in result.get('cohorts', {}).values() for trial in group.get('trials', [])]
    expected = [trial['id'] for trial in tasks]
    if (len(actual) != len(expected) or set(actual) != set(expected)
            or result.get('pendingOrUnavailableTrials') or not result.get('allRegisteredRequestedAttemptsIncluded')):
        raise ValueError('All requested registered attempts must be terminal and fully exported; no partial measured curve is emitted')
    return tasks


def pipeline_checks(campaign, plan, task, manifest, config, load, actual_prepared_sha):
    fixed = campaign.get('fixed', {})
    mode = task['transportMode']
    sessions = 128 if mode == 'direct' else 1
    aeron = 'one-independent-Aeron-per-client' if mode == 'direct' else 'one-session-one-network-owner'
    expected_flags = ['-Dvectormatch.capacity.client.driver=shared', '-Daeron.nak.unicast.delay=1000',
                      '-Dvectormatch.capacity.client.transport=' + mode]
    prepared = [campaign.get('preparedSnapshotSha256'), plan.get('preparedSnapshotSha256'),
                config.get('preparedSnapshotSha256'), actual_prepared_sha]
    return {
        'fixedTransportModeAndPhysicalSessionCount': fixed.get('clientTransportMode') == mode
             and type(fixed.get('clientSessionCount')) is int and fixed['clientSessionCount'] == sessions,
        'configurationActualTransportAndSessionCount': config.get('clientTransportMode') == mode
             and type(config.get('clientSessionCount')) is int and config['clientSessionCount'] == sessions,
        'loadResultActualTransportAndSessionCount': load.get('clientTransportMode') == mode
             and type(load.get('clientSessionCount')) is int and load['clientSessionCount'] == sessions,
        'actualAeronOwnershipMode': config.get('clientAeronMode') == load.get('clientAeronMode') == aeron,
        'oneSharedMediaDriverBothArms': config.get('clientDriverMode') == load.get('clientDriverMode') == 'shared'
             and type(config.get('clientDriverCount')) is int and type(load.get('clientDriverCount')) is int
             and config['clientDriverCount'] == load['clientDriverCount'] == 1,
        'exactExplicitLoadJvmFlags': manifest.get('loadGeneratorJvmArguments') == expected_flags,
        'logicalWorkersAndInFlight128': config.get('workers') == load.get('workers') == manifest.get('workers') == 128
             and config.get('maxServiceRequestsInFlight') == 128,
        'samePerWorkerQueue64AndTotalFifo8192': config.get('queueCapacityPerWorker') == load.get('queueCapacityPerWorker') == 64
             and fixed.get('queuePerWorker') == 64 and manifest.get('queuePerWorker') == 64,
        'same350kProfileAndWorkload': config.get('profile') == 'extended-350k-256'
             and config.get('expectedStateProfile') == 'capacity-350k-v1'
             and config.get('scheduledArrivals') == load.get('scheduledArrivals') == task['arrivals'] == 350000
             and config.get('ratePerSecond') == load.get('targetArrivalRatePerSecond') == task['rate'],
        'sameFixtureAndRetentionLimits': config.get('seededMakerQuantity') == 380000
             and config.get('seededQuotePerBuyer') == 1900000000 and config.get('seededBuyerAccounts') == 64
             and config.get('initialResultCachePerProducer') == config.get('expectedResultCachePerProducer') == 1024
             and config.get('expectedCoreLimits') == {'maxAccounts': 10000, 'maxProducers': 10000,
                                                    'maxRetainedOrders': 360000, 'maxCachedResults': 100000},
        'sameNodeHeapDriverBufferSync': fixed.get('nodeHeap') == fixed.get('loadHeap') == '2g'
             and fixed.get('maxClusterSessions') == 256 and fixed.get('syncLevel') == 2
             and fixed.get('driverThreadingArgument') == 'SHARED' and fixed.get('socketReceiveBufferArgumentBytes') == 131072,
        'sameExplicitNak1000nsRatio100': fixed.get('nakUnicastDelayNs') == fixed.get('clientNakUnicastDelayNs') == 1000
             and fixed.get('nakUnicastRetryDelayRatio') == 100
             and config.get('clientNakUnicastDelayNs') == load.get('clientNakUnicastDelayNs') == 1000
             and config.get('clientNakUnicastRetryDelayRatio') == load.get('clientNakUnicastRetryDelayRatio') == 100,
        'preparedSnapshotActualDigestMatchesPlanAndBothDeclarations': all(isinstance(value, str) and len(value) == 64 for value in prepared)
             and len(set(prepared)) == 1,
    }


def diagnostics_only(trial, checks):
    analyzer = trial.get('analyzerClassification')
    valid = (trial.get('validFiniteObservation') is True and all(value is True for value in checks.values())
             and isinstance(analyzer, dict) and analyzer.get('measurementValid') is True)
    trial['validFiniteObservation'] = valid
    trial['diagnosticsOnly'] = not valid
    if not valid and trial.get('capacityEligibility') == 'VALID_FINITE_OBSERVATION_CLASSIFICATION_SEPARATE':
        trial['capacityEligibility'] = 'PIPELINE_CONFIGURATION_OR_MEASUREMENT_INVALID_DIAGNOSTICS_ONLY'
    trial['statisticalUse'] = ('Valid finite observation; stability/classification remains separate.' if valid else
                              'Diagnostics only: client-reported counts/latencies and resources retained, excluded from valid capacity comparisons.')


def summarize(root, cohorts):
    if cohorts not in COHORTS:
        raise ValueError('Use direct,multiplexed or explicit pilot')
    source = root.parent / 'nak/tool-validation/summarize-nak-attribution.py'
    frozen, frozen_identity, changes = adapted_wrapper(source)
    plan_path = root / ('pilot-plan.json' if cohorts == ('pilot',) else 'plan.json')
    plan = json.loads(plan_path.read_text())
    tasks = require_plan(plan, cohorts)
    # The frozen reader performs the whole-collection/process/TID/socket/CnC/cgroup rules.
    # Only cohort literals and its NAK-varying task lookup are adapted in memory.
    result = frozen.summarize(root, cohorts)
    require_complete(result, plan, cohorts)
    result['reusedNakWrapperSha256'] = result.pop('scriptSha256')
    result['scriptSha256'] = digest(Path(__file__))['sha256']
    result['tools'].update(frozenNakWrapper=frozen_identity, pipelineWrapper=digest(Path(__file__)))
    result['test'] = 'logical128-direct-vs-single-session-network-owner-attribution'
    result['inMemoryFrozenSourceAdaptations'] = changes
    for cohort, group in result['cohorts'].items():
        campaign = group.get('campaign') or {}
        for trial in group['trials']:
            directory = root / cohort / 'runs' / trial['id']
            config_path, load_path = directory / 'configuration.json', directory / 'load-result.json'
            config = json.loads(config_path.read_text()) if config_path.is_file() else {}
            if load_path.is_file():
                load = json.loads(load_path.read_text())
                load_provenance = 'load-result.json'
            else:
                load = (trial.get('failure') or {}).get('loadSummary') or {}
                load_provenance = 'failure.json/loadSummary (diagnostic fallback; no result created)'
            trial['loadSummaryProvenance'] = load_provenance
            task = next(value for value in tasks if value['id'] == trial['id'])
            prepared = directory / 'prepared-snapshot.bin'
            prepared_identity = digest(prepared) if prepared.is_file() else None
            if prepared_identity:
                result['inputs'].append(prepared_identity)
            checks = pipeline_checks(campaign, plan, task, trial['manifest'], config, load,
                                     prepared_identity['sha256'] if prepared_identity else None)
            trial['pipelineTransportAndWindowEvidence'] = {
                'checks': checks, 'allMatched': all(value is True for value in checks.values()),
                'preparedSnapshot': prepared_identity,
                'expected': {'transportMode': task['transportMode'], 'physicalSessions': 128 if task['transportMode'] == 'direct' else 1,
                             'logicalWorkers': 128, 'logicalMaxInFlight': 128, 'queuePerWorker': 64, 'aggregateFifo': 8192,
                             'nodeAndLoadNakDelayNs': 1000, 'retryRatio': 100},
                'actualConfiguration': {key: config.get(key) for key in ('clientTransportMode', 'clientSessionCount', 'clientAeronMode',
                                       'clientDriverMode', 'clientDriverCount', 'workers', 'maxServiceRequestsInFlight', 'queueCapacityPerWorker')},
                'actualLoadResult': {key: load.get(key) for key in ('clientTransportMode', 'clientSessionCount', 'clientAeronMode', 'clientDriverMode', 'clientDriverCount')},
                'scope': 'Physical session/network-owner arrangement changes while logicalW128/FIFO8192 and independent producer identities remain configured. '
                         'Runtime connection/session metadata plus source/controller/argument attestations are not live session-liveness telemetry. '
                         'Prepared binary is independently SHA256 checked. Missing/mismatched fields invalidate comparison rather than implying zero.'}
            trial['reportedLatencyDistributions'] = {
                'microsecondDistributions': {key: load.get(key) for key in ('acceptedScheduledToConfirmedMicroseconds',
                    'scheduledToConfirmedMicroseconds', 'executeInitialAttemptMicroseconds', 'executeThroughResolutionMicroseconds',
                    'queueDelayMicroseconds', 'schedulerLatenessMicroseconds')},
                'allOfferedAcceptedP99Microseconds': load.get('allOfferedAcceptedP99Microseconds'),
                'scope': 'Raw client-reported conditional response distributions include replies during drain. Dropped/unresolved arrivals receive no invented latency; '
                         'all-offered finite p99 remains null when the raw result says unavailable. Invalid points use these numbers for diagnostics only.'}
            diagnostics_only(trial, checks)
    distinct = {}
    for item in result['inputs']:
        previous = distinct.setdefault(item['path'], item)
        if previous != item:
            raise ValueError('Input changed while reading: ' + item['path'])
    result['inputs'] = list(distinct.values())
    all_trials = [trial for group in result['cohorts'].values() for trial in group['trials']]
    result['validFiniteObservationCount'] = sum(trial['validFiniteObservation'] for trial in all_trials)
    result['diagnosticsOnlyAttemptCount'] = sum(trial['diagnosticsOnly'] for trial in all_trials)
    result['generatedAt'] = datetime.now(timezone.utc).isoformat()
    result['scope'] = (
        'Default formal output requires the exact four complete registered direct/multiplexed attempts; pilot is explicitly separate. '
        'Both arms have128 logical synchronous in-flight slots,128 producers,Q64/FIFO8192,one sharedMediaDriver,NAK1000ns node+load/retry100 '
        'and one common source-pinned node/load artifact. Direct128 physical sessions versus multiplexed1 session changes ownership/dispatch/retry arrangement, '
        'not the pure in-flight window or matching core. Invalid/failed/mismatched points retain diagnostics but are excluded from valid capacity comparisons. '
        'Frozen whole-collection interior/monotonic adjacent identity/TID/inode/FD-overlap rules and explicit missing/gap/truncation accounting apply. '
        'CnC cumulative first/last counters may span missed samples; position differences are non-atomic, not exact lag. Archive write wall time includes '
        'write/force/descheduling, not pure fsync latency; observer cost is not an observer-off experiment. '
        'A finite path result does not prove sustained capacity, a unique bottleneck, a universal engine ceiling or a replicated full checkpoint/restart.')
    return result


def self_test():
    # Pure metadata fixtures: no raw benchmark data or actual summarization is read.
    cohorts = ('direct', 'multiplexed')
    plan = {'trials': expected_tasks(cohorts), 'fixedLogicalInFlight': 128, 'fixedFifoSlots': 8192,
            'fixedNakNodeAndLoadNs': 1000, 'preparedSnapshotSha256': 'a' * 64}
    fake_result = {'cohorts': {mode: {'trials': [{'id': x['id']} for x in plan['trials'] if x['cohort'] == mode]} for mode in cohorts},
                   'pendingOrUnavailableTrials': [], 'allRegisteredRequestedAttemptsIncluded': True}
    assert len(require_complete(fake_result, plan, cohorts)) == 4
    fake_result['cohorts']['multiplexed']['trials'].pop()
    try:
        require_complete(fake_result, plan, cohorts)
    except ValueError:
        pass
    else:
        raise AssertionError('Partial formal curve must not be emitted')
    assert len(expected_tasks(('pilot',))) == 1 and expected_tasks(('pilot',))[0]['rate'] == 10000
    task = plan['trials'][1]
    fixed = {'clientTransportMode': 'multiplexed', 'clientSessionCount': 1, 'queuePerWorker': 64,
             'nodeHeap': '2g', 'loadHeap': '2g', 'maxClusterSessions': 256, 'syncLevel': 2,
             'driverThreadingArgument': 'SHARED', 'socketReceiveBufferArgumentBytes': 131072,
             'nakUnicastDelayNs': 1000, 'clientNakUnicastDelayNs': 1000, 'nakUnicastRetryDelayRatio': 100}
    campaign = {'fixed': fixed, 'preparedSnapshotSha256': 'a' * 64}
    runtime = {'clientTransportMode': 'multiplexed', 'clientSessionCount': 1, 'clientAeronMode': 'one-session-one-network-owner',
               'clientDriverMode': 'shared', 'clientDriverCount': 1, 'workers': 128, 'maxServiceRequestsInFlight': 128,
               'queueCapacityPerWorker': 64, 'profile': 'extended-350k-256', 'expectedStateProfile': 'capacity-350k-v1',
               'scheduledArrivals': 350000, 'targetArrivalRatePerSecond': 26000, 'ratePerSecond': 26000,
               'seededMakerQuantity': 380000, 'seededQuotePerBuyer': 1900000000, 'seededBuyerAccounts': 64,
               'initialResultCachePerProducer': 1024, 'expectedResultCachePerProducer': 1024,
               'expectedCoreLimits': {'maxAccounts': 10000, 'maxProducers': 10000, 'maxRetainedOrders': 360000, 'maxCachedResults': 100000},
               'clientNakUnicastDelayNs': 1000, 'clientNakUnicastRetryDelayRatio': 100, 'preparedSnapshotSha256': 'a' * 64}
    manifest = {'workers': 128, 'queuePerWorker': 64, 'loadGeneratorJvmArguments': [
                '-Dvectormatch.capacity.client.driver=shared', '-Daeron.nak.unicast.delay=1000', '-Dvectormatch.capacity.client.transport=multiplexed']}
    checks = pipeline_checks(campaign, plan, task, manifest, runtime, runtime, 'a' * 64)
    assert all(checks.values())
    for key, value in (('clientSessionCount', True), ('workers', 256), ('queueCapacityPerWorker', 128),
                       ('clientNakUnicastDelayNs', 100000), ('clientTransportMode', 'direct')):
        assert not all(pipeline_checks(campaign, plan, task, manifest, {**runtime, key: value}, runtime, 'a' * 64).values())
    assert not all(pipeline_checks(campaign, plan, task, manifest, runtime, runtime, 'b' * 64).values())
    invalid = {'validFiniteObservation': False, 'capacityEligibility': 'CANONICAL_INCOMPLETE_UNKNOWN_GUARD'}
    diagnostics_only(invalid, checks)
    assert invalid['diagnosticsOnly'] and not invalid['validFiniteObservation']
    valid = {'validFiniteObservation': True, 'capacityEligibility': 'VALID_FINITE_OBSERVATION_CLASSIFICATION_SEPARATE', 'analyzerClassification': {'measurementValid': True}}
    diagnostics_only(valid, checks)
    assert not valid['diagnosticsOnly'] and valid['validFiniteObservation']
    analyzer_invalid = {**valid, 'analyzerClassification': {'measurementValid': False}}
    diagnostics_only(analyzer_invalid, checks)
    assert analyzer_invalid['diagnosticsOnly'] and not analyzer_invalid['validFiniteObservation']
    source = Path(__file__).resolve().parents[2] / 'nak/tool-validation/summarize-nak-attribution.py'
    before = digest(source)
    loaded, identity, changes = adapted_wrapper(source)
    assert identity == before == digest(source) and len(changes) == 5
    assert loaded.expected_unknown({'passed': False, 'errorType': 'java.lang.IllegalStateException',
                                    'error': loaded.UNKNOWN.format(count=1), 'loadSummary': {'unresolvedFinal': 1}}, {'unresolvedFinal': 1})
    print(json.dumps({'status': 'PASS', 'checks': ['formal-four-required', 'partial-refused', 'pilot-separate', 'actual-mode-session-count',
                      'typed-session-count-not-bool', 'logical-window-and-FIFO-pinned', 'NAK1000-pinned', 'prepared-digest-pinned',
                      'failed-not-promoted', 'valid-finite-separate-from-stable', 'analyzer-invalid-diagnostics-only', 'frozen-source-hash', 'in-memory-only-adaptation', 'terminal-failure-fallback-source-compiled', 'exact-unknown-retained'],
                      'actualRawSummarizationExecuted': False}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pipeline_root', type=Path, nargs='?')
    parser.add_argument('output_json', type=Path, nargs='?')
    parser.add_argument('--cohorts', choices=('direct,multiplexed', 'pilot'), default='direct,multiplexed')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.pipeline_root is None or args.output_json is None:
        parser.error('PIPELINE_ROOT OUTPUT_JSON are required')
    result = summarize(args.pipeline_root, tuple(args.cohorts.split(',')))
    result['reproduction'] = {'argv': [sys.executable, '-B', str(Path(__file__).resolve()), str(args.pipeline_root), str(args.output_json), '--cohorts', args.cohorts]}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + '.tmp')
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(args.output_json)
    print(json.dumps({'output': str(args.output_json), 'included': result['includedTerminalAttemptCount'],
                      'registered': result['registeredAttemptCount'], 'allRequestedIncluded': result['allRegisteredRequestedAttemptsIncluded'],
                      'cohorts': {key: value['completedAttempts'] for key, value in result['cohorts'].items()}, 'scriptSha256': result['scriptSha256']}))


if __name__ == '__main__':
    main()
