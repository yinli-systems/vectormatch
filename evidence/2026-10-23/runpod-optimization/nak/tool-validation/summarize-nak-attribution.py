#!/usr/bin/env python3
"""Read-only NAK pilot/formal attribution using frozen identity/window functions.

NAK_ROOT OUTPUT_JSON [--cohorts pilot100us|delay1000,delay100000]
Failed terminal attempts are retained without creating or assuming result.json.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


FROZEN = {
    'core': ('tool-validation/summarize-attribution.py', 'b868baa93ded4f343379d4b4a77e84f55594e39059522c871947ff7dd12e755f'),
    'network': ('network/tool-validation/summarize-network-attribution.py', 'df9cefa9332488fe683484afa8f5fd8a660c84c46213ddfa4831e69f4e91645d'),
    'threading': ('threading/tool-validation/summarize-threading-attribution.py', 'c97b74a777c2a5423ec33ad03a3bd6d1171702b380ceb9d0023c624e3649c964'),
    'window': ('window350k/tool-validation/summarize-window-attribution.py', '1bc8929607b2b58debb8961ce9324057d4cc87af982d1342e52acbf0053f6f6a'),
}
UNKNOWN = ('Confirmed-only replay skipped: {count} UNKNOWN_UNRESOLVED identities may already have executed; canonical validation is incomplete. '
           'Preserve the original identities for same-key recovery; no core business mismatch is established.')
LOAD_FIELDS = ('workers', 'scheduledArrivals', 'queueCapacityPerWorker', 'targetArrivalRatePerSecond',
               'confirmedAcceptedCommands', 'confirmedWithinArrivalWindow', 'confirmedWithinArrivalWindowPerSecond',
               'unknownAtInitialDeadline', 'unresolvedFinal', 'clientNotSentCommands', 'clientQueueFullNotSent',
               'businessRejectedCommands', 'serverErrors', 'completionWindowSeconds', 'drainSeconds', 'generatorTimingInvalid')


def digest(path):
    h, size = hashlib.sha256(), 0
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
            size += len(block)
    return {'path': str(path), 'sha256': h.hexdigest(), 'bytes': size}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def optional_json(path, core, inputs):
    return core.read_json(path, inputs) if path.is_file() else None


def expected_unknown(failure, load):
    count = load.get('unresolvedFinal') if isinstance(load, dict) else None
    return (isinstance(failure, dict) and type(count) is int and count > 0 and failure.get('passed') is False
            and failure.get('errorType') == 'java.lang.IllegalStateException'
            and failure.get('error') == UNKNOWN.format(count=count) and failure.get('loadSummary') == load)


def eligibility(result, failure, load, receipt, leader, verification, stopped):
    canonical = (failure is None and isinstance(result, dict) and result.get('passed') is True
                 and result.get('canonicalSnapshotBytesVerified') is True and receipt.get('exitCode') == 0)
    if not canonical:
        status = ('CANONICAL_INCOMPLETE_UNKNOWN_GUARD' if expected_unknown(failure, load)
                  else 'FAILED_OR_CANONICAL_UNVERIFIED')
    elif result.get('measurementValid') is not True or load.get('generatorTimingInvalid') is not False:
        status = 'CANONICAL_VALID_MEASUREMENT_INVALID'
    elif not all(isinstance(x, dict) and x.get('passed') is True for x in (leader, verification, stopped)):
        status = 'CANONICAL_VALID_MISSING_OR_FAILED_EXTERNAL_CHECK'
    else:
        status = 'VALID_FINITE_OBSERVATION_CLASSIFICATION_SEPARATE'
    return {'canonicalBusinessCorrectnessVerified': canonical,
            'expectedCanonicalIncompleteUnknownGuard': expected_unknown(failure, load),
            'capacityEligibility': status,
            'validFiniteObservation': status == 'VALID_FINITE_OBSERVATION_CLASSIFICATION_SEPARATE',
            'scope': 'A valid finite observation is not a stable-capacity conclusion. Failed client-reported confirmations are not correctness-validated business success.'}


def nak_evidence(directory, campaign, config, trial, core, inputs):
    fixed = campaign.get('fixed', {}) if isinstance(campaign, dict) else {}
    fields = ('nakUnicastDelayNs', 'clientNakUnicastDelayNs', 'nakUnicastRetryDelayRatio')
    declared = {name: fixed.get(name) for name in fields}
    if not (type(declared['nakUnicastDelayNs']) is int and declared['nakUnicastDelayNs'] in (1000, 100000)
            and declared['clientNakUnicastDelayNs'] == declared['nakUnicastDelayNs']
            and type(declared['nakUnicastRetryDelayRatio']) is int and declared['nakUnicastRetryDelayRatio'] == 100):
        raise ValueError('Missing or differing explicit registered node/client NAK treatment')
    nodes = []
    for n in range(3):
        record = optional_json(directory / f'node{n}/process.json', core, inputs)
        args = record.get('arguments') if isinstance(record, dict) else None
        log = directory / f'node{n}/process.log'
        lines = []
        if log.is_file():
            inputs.append(digest(log))
            lines = [line for line in log.read_text().splitlines() if line.startswith('VECTOR_CLUSTER_STARTED ')]
        observations = []
        for line in lines:
            item = {}
            for field in ('nakUnicastDelayNs', 'nakUnicastRetryDelayRatio'):
                values = re.findall(r'(?:^|\s)' + field + r'=(\d+)(?=\s|$)', line)
                item[field] = int(values[0]) if len(values) == 1 else None
                item[field + 'Occurrences'] = len(values)
            observations.append(item)
        expected = '-Daeron.nak.unicast.delay=' + str(declared['nakUnicastDelayNs'])
        nak_args = [value for value in args if isinstance(value, str) and 'aeron.nak' in value] if isinstance(args, list) else None
        nodes.append({'node': n, 'processCommandSha256': record.get('commandSha256') if record else None,
                      'recordedClasspath': args[args.index('-cp') + 1] if isinstance(args, list) and '-cp' in args and args.index('-cp') + 1 < len(args) else None,
                      'recordedNakJvmArguments': nak_args, 'singleExactDeclaredJvmFlag': nak_args == [expected] if nak_args is not None else None,
                      'startupObservations': observations,
                      'startupMatchesDeclared': all(x['nakUnicastDelayNs'] == declared['nakUnicastDelayNs']
                                                    and x['nakUnicastRetryDelayRatio'] == declared['nakUnicastRetryDelayRatio']
                                                    for x in observations) if observations else None})
    extras = trial.get('loadGeneratorJvmArguments')
    load_args = [x for x in extras if isinstance(x, str) and 'aeron.nak' in x] if isinstance(extras, list) else None
    expected_load = '-Daeron.nak.unicast.delay=' + str(declared['clientNakUnicastDelayNs'])
    load = {'actualSharedDriverContext': {name: config.get(name) for name in ('clientNakUnicastDelayNs', 'clientNakUnicastRetryDelayRatio')},
            'recordedNakJvmArguments': load_args, 'singleExactDeclaredJvmFlag': load_args == [expected_load] if load_args is not None else None,
            'actualContextMatchesDeclared': config.get('clientNakUnicastDelayNs') == declared['clientNakUnicastDelayNs']
                                           and config.get('clientNakUnicastRetryDelayRatio') == declared['nakUnicastRetryDelayRatio']}
    return {'declaredFixedConfiguration': declared, 'nodes': nodes, 'load': load,
            'allDeclaredSettingsObserved': all(x['singleExactDeclaredJvmFlag'] is True and x['startupMatchesDeclared'] is True for x in nodes)
                                          and load['singleExactDeclaredJvmFlag'] is True and load['actualContextMatchesDeclared'] is True,
            'scope': 'Node JVM arguments plus effective NodeMain startup values; client values are recorded from the actual shared driver context after workers connected. '
                     'These are recorded runtime/configuration attestations, not a fresh live JVM inspection. Command hashes and configuration receipt input hashes remain separately available.'}


def logs(directory, inputs):
    output = []
    paths = [directory / 'load.log', directory / 'controller.log'] + [directory / f'node{n}/process.log' for n in range(3)]
    for path in paths:
        if not path.is_file():
            output.append({'path': str(path), 'status': 'missing', 'matchingLines': None})
            continue
        inputs.append(digest(path))
        hits = []
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r'(?:Exception in thread|^ERROR\b|^WARN\b|OutOfMemoryError|^Caused by:)', line):
                hits.append({'line': i, 'text': line[:1200]})
        output.append({'path': str(path), 'status': 'read', 'matchingLineCount': len(hits), 'matchingLines': hits[:10],
                       'scope': 'Project-owned log pattern audit only; no matching line does not establish absence of all possible JVM/Aeron errors.'})
    return output


def summarize(root, cohorts):
    if cohorts not in (('pilot100us',), ('delay1000', 'delay100000')):
        raise ValueError('Request pilot100us or delay1000,delay100000 explicitly')
    optimization = root.parent
    workspace = optimization.parents[2]
    tools, loaded = {}, {}
    for name, (relative, expected) in FROZEN.items():
        path = optimization / relative
        identity = digest(path)
        if identity['sha256'] != expected:
            raise ValueError('Frozen source changed: ' + str(path))
        tools[name] = identity
        loaded[name] = module('frozen_nak_' + name, path)
    helper_path = workspace / 'scripts/summarize-capacity-telemetry.py'
    tools['cncSummaryHelper'] = digest(helper_path)
    if tools['cncSummaryHelper']['sha256'] != '21f77b02b872051906f284d9d0709d768ba681d0dce648fb27d7bc28b1d0b0b0':
        raise ValueError('Frozen CnC helper changed')
    helper = module('frozen_nak_cnc_helper', helper_path)
    core, window, network, threading = (loaded[n] for n in ('core', 'window', 'network', 'threading'))
    inputs, pending, data = [], [], {}
    plan_path = root / ('pilot-plan.json' if cohorts == ('pilot100us',) else 'plan.json')
    plan = optional_json(plan_path, core, inputs)
    if not isinstance(plan, dict):
        raise ValueError('No registered plan for requested cohort(s)')
    source_archive = optional_json(root / 'tool-validation/controller-sources.json', core, inputs)
    controller_hashes = plan.get('controllerSha256', {})
    archived = source_archive.get('files', {}) if isinstance(source_archive, dict) else {}
    controller_checks = {}
    for name, expected in controller_hashes.items():
        entry = archived.get(name, {})
        source = entry.get('source')
        actual = hashlib.sha256(source.encode()).hexdigest() if isinstance(source, str) else None
        controller_checks[name] = {'planSha256': expected, 'archivedSha256': entry.get('sha256'), 'computedArchivedSourceSha256': actual,
                                  'matched': actual == entry.get('sha256') == expected}
    if not controller_checks or not all(x['matched'] for x in controller_checks.values()):
        raise ValueError('Registered controller hashes do not match exact archived source')
    deployments = {name: optional_json(root / filename, core, inputs) for name, filename in (
        ('release', 'node-release.json'), ('manifest', 'node-deployment-manifest.json'), ('upload', 'node-upload-receipt.json'))}
    for cohort in cohorts:
        campaign = optional_json(root / cohort / 'campaign.json', core, inputs)
        trials = []
        runs = root / cohort / 'runs'
        for directory in sorted(runs.iterdir()) if runs.is_dir() else []:
            if not directory.is_dir():
                continue
            trial = optional_json(directory / 'trial.json', core, inputs)
            receipt = optional_json(directory / 'receipt.json', core, inputs)
            load = optional_json(directory / 'load-result.json', core, inputs)
            result = optional_json(directory / 'result.json', core, inputs)
            failure = optional_json(directory / 'failure.json', core, inputs)
            paths = [directory / f'node{n}-attribution.jsonl' for n in range(3)]
            documents = [core.read_jsonl(path, inputs) for path in paths]
            complete = all(any(row.get('type') == 'complete' for row in d['rows']) and not d['parseErrors'] for d in documents)
            if not (isinstance(trial, dict) and trial.get('completedAt') and isinstance(receipt, dict)
                    and isinstance(load, dict) and (result is not None or failure is not None) and complete):
                pending.append({'cohort': cohort, 'id': directory.name, 'reason': 'terminal-trial/receipt/load/outcome/three-complete-attributions-not-all-exported'})
                continue
            start = core.utc(load.get('scheduledOriginUtcApproximate'))
            seconds = core.number(load.get('arrivalWindowSeconds'))
            if start is None or seconds is None or seconds <= 0:
                pending.append({'cohort': cohort, 'id': directory.name, 'reason': 'terminal-outcome-has-no-valid-arrival-window', 'failure': failure})
                continue
            end = start + seconds
            config = optional_json(directory / 'configuration.json', core, inputs) or {}
            verification = optional_json(directory / 'configuration-verification.json', core, inputs)
            leader = optional_json(directory / 'fixed-leader-check.json', core, inputs)
            stopped = optional_json(directory / 'all-owned-processes-stopped.json', core, inputs)
            classification = None
            summary = optional_json(root / cohort / 'analysis/summary.json', core, inputs)
            if isinstance(summary, dict):
                matches = [x for x in summary.get('trials', []) if x.get('id') == directory.name]
                if len(matches) == 1:
                    classification = {name: matches[0].get(name) for name in ('classification', 'measurementValid', 'stability', 'inputSha256')}
            context = {'workers': load.get('workers'), 'queueCapacityPerWorker': load.get('queueCapacityPerWorker'),
                       'totalConfiguredFifoSlots': load['workers'] * load['queueCapacityPerWorker'] if type(load.get('workers')) is int and type(load.get('queueCapacityPerWorker')) is int else None,
                       'maxSynchronousRequestsInFlight': config.get('maxServiceRequestsInFlight'), 'profile': config.get('profile'),
                       'stateProfile': config.get('expectedStateProfile'), 'declaredCoreLimits': config.get('expectedCoreLimits'),
                       'declaredResultCachePerProducer': config.get('expectedResultCachePerProducer'),
                       'initialResultCachePerProducer': config.get('initialResultCachePerProducer')}
            identity_fields = ('loadGeneratorRevision', 'loadGeneratorBundleSha256', 'deploymentRevision', 'deploymentBundleSha256', 'release')
            entry = {'id': directory.name, 'manifest': trial, 'retainedFailedTrial': failure is not None,
                     **eligibility(result, failure, load, receipt, leader, verification, stopped),
                     'receipt': receipt, 'failure': failure, 'resultPassed': result.get('passed') if isinstance(result, dict) else None,
                     'configurationVerification': verification, 'fixedLeaderCheckPassed': leader.get('passed') if isinstance(leader, dict) else None,
                     'allOwnedProcessesStopped': stopped.get('passed') if isinstance(stopped, dict) else None,
                     'analyzerClassification': classification,
                     'arrivalWindow': {'scheduledOriginUtcApproximate': load['scheduledOriginUtcApproximate'], 'arrivalWindowSeconds': seconds,
                                       'endUtcApproximate': datetime.fromtimestamp(end, timezone.utc).isoformat(),
                                       'scope': 'Approximate UTC arrival window; whole collection interval interior; rates use same-host monotonic deltas. No synchronized one-way clock claim.'},
                     'clientReportedLoadOutcomes': {name: load.get(name) for name in LOAD_FIELDS},
                     'recordedArtifactIdentity': {name: trial.get(name) for name in identity_fields},
                     'nakSettingsEvidence': nak_evidence(directory, campaign, config, trial, core, inputs),
                     'workerAndRetentionContext': context,
                     'observerFileCount': 3,
                     'observers': [core.observer_summary(path, directory / path.name.replace('-attribution.jsonl', '-telemetry.jsonl'), start, end, inputs, 1.5) for path in paths],
                     'cgroupQuotaAndThrottling': [threading.cgroup_summary(directory / f'node{n}-telemetry.jsonl', start, end, core, helper, inputs) for n in range(3)],
                     'recorderCounters': [network.recorder_summary(directory / f'node{n}-counters.jsonl', start, end, core, helper, inputs) for n in range(3)],
                     'outsideWindowSocketBufferAttestation': {stage: network.buffer_attestation(directory / f'socket-buffer-{stage}.json', core, inputs) for stage in ('before', 'after')},
                     'observerCapCoverage': [window.observer_limits(path, start, end, core, inputs) for path in paths],
                     'csvArchiveEvidence': window.csv_archives(directory, inputs), 'projectLogPatternAudit': logs(directory, inputs)}
            node, client = plan.get('node', {}), plan.get('load', {})
            source_checks = {
                'nodeRevision': trial.get('deploymentRevision') == node.get('revision') and node.get('revision') is not None,
                'nodeBundle': trial.get('deploymentBundleSha256') == node.get('bundleSha256') and node.get('bundleSha256') is not None,
                'nodeRelease': trial.get('release') == node.get('root') and node.get('root') is not None,
                'loadRevision': trial.get('loadGeneratorRevision') == client.get('revision') and client.get('revision') is not None,
                'loadBundle': trial.get('loadGeneratorBundleSha256') == client.get('bundleSha256') and client.get('bundleSha256') is not None,
                'sameNodeAndLoadSource': node.get('revision') == client.get('revision') and node.get('revision') is not None,
                'sameNodeAndLoadBundle': node.get('bundleSha256') == client.get('bundleSha256') and node.get('bundleSha256') is not None,
                'nodeRecordedClasspaths': all(x['recordedClasspath'] == trial.get('release', '') + '/dist/cluster/lib/*' for x in entry['nakSettingsEvidence']['nodes'])}
            tasks = [x for x in plan.get('trials', []) if x.get('id') == directory.name and x.get('cohort') == cohort]
            task_checks = len(tasks) == 1 and all(trial.get(key) == tasks[0].get(key) for key in ('id', 'rate', 'arrivals', 'workers', 'phase', 'repetition'))
            task_checks = task_checks and entry['nakSettingsEvidence']['declaredFixedConfiguration']['nakUnicastDelayNs'] == tasks[0].get('nakDelayNs')
            receipt_hashes = []
            if isinstance(verification, dict):
                for name, expected in verification.get('rawSha256', {}).items():
                    relative = Path(name)
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('Unsafe configuration receipt relative input path')
                    path = directory / relative
                    actual = digest(path) if path.is_file() else None
                    if actual is not None:
                        inputs.append(actual)
                    receipt_hashes.append({'relativePath': name, 'expectedSha256': expected,
                                           'actualSha256': actual['sha256'] if actual else None,
                                           'matched': actual is not None and actual['sha256'] == expected})
            entry['registeredSourceAndTaskChecks'] = {'artifactIdentity': source_checks, 'registeredTaskMatched': task_checks,
                                                      'configurationReceiptRawInputs': receipt_hashes,
                                                      'allConfigurationReceiptInputsMatched': all(x['matched'] for x in receipt_hashes) if receipt_hashes else None}
            if not (all(source_checks.values()) and task_checks and entry['nakSettingsEvidence']['allDeclaredSettingsObserved']
                    and receipt_hashes and all(x['matched'] for x in receipt_hashes)):
                if entry['validFiniteObservation']:
                    entry['capacityEligibility'] = 'CANONICAL_VALID_MISSING_OR_DIFFERING_SOURCE_TREATMENT_OR_RECEIPT'
                entry['validFiniteObservation'] = False
            trials.append(entry)
        if trials:
            data[cohort] = {'campaign': campaign, 'completedAttempts': len(trials),
                            'canonicalPassedAttempts': sum(x['canonicalBusinessCorrectnessVerified'] for x in trials),
                            'failedOrCanonicalUnverifiedAttempts': sum(not x['canonicalBusinessCorrectnessVerified'] for x in trials), 'trials': trials}
    distinct = {}
    for row in inputs:
        previous = distinct.setdefault(row['path'], row)
        if previous != row:
            raise ValueError('Input changed while reading: ' + row['path'])
    actual_ids = {t['id'] for group in data.values() for t in group['trials']}
    expected_tasks = [task for task in plan.get('trials', []) if task.get('cohort') in cohorts]
    return {'schemaVersion': 1, 'test': 'explicit-node-client-nak-delay-owned-attribution',
            'generatedAt': datetime.now(timezone.utc).isoformat(), 'rootDirectory': str(root),
            'scriptSha256': digest(Path(__file__))['sha256'], 'tools': tools,
            'requestedCohorts': list(cohorts), 'cohorts': data, 'pendingOrUnavailableTrials': pending,
            'registeredAttemptCount': len(expected_tasks), 'includedTerminalAttemptCount': len(actual_ids),
            'allRegisteredRequestedAttemptsIncluded': actual_ids == {t['id'] for t in expected_tasks},
            'unavailableCohorts': [x for x in cohorts if x not in data],
            'registeredPlanIdentity': {name: plan.get(name) for name in ('node', 'load', 'observer', 'build', 'buildTools', 'pilotPolicy')},
            'registeredControllerHashes': controller_checks, 'recordedDeploymentAttestations': deployments,
            'inputs': list(distinct.values()), 'maximumAcceptedGapMultiplier': 1.5,
            'scope': 'Only requested actually terminal attempts, separate cohorts and all failures retained without result spoofing. '
                     'NAK delay changes both node and shared client driver; retry ratio100 and other registered inputs are separate fixed evidence. '
                     'Frozen whole-collection/TID/process/inode/FD-overlap identity and gap rules apply; no missing metric is zero. '
                     'CnC first/last monotonic counter coverage can span missed samples, unlike adjacent CPU/socket intervals. Positions are non-atomic observations, not exact instantaneous lag. '
                     'Archive write-path time includes force/descheduling and is not pure fsync latency. Observer costs are sampling estimates, not an observer-off experiment. '
                     'Pilot is not a controlled same-load comparison; finite path observations do not prove sustained capacity, engine ceiling, monotonic behavior, unique causation or replicated full checkpoint/restart.'}


def self_test():
    load = {'unresolvedFinal': 2, 'workers': 256, 'generatorTimingInvalid': False}
    failure = {'passed': False, 'errorType': 'java.lang.IllegalStateException', 'error': UNKNOWN.format(count=2), 'loadSummary': dict(load)}
    assert expected_unknown(failure, load)
    assert not eligibility(None, failure, load, {'exitCode': 1}, {}, {}, {})['validFiniteObservation']
    assert eligibility(None, failure, load, {'exitCode': 1}, {}, {}, {})['capacityEligibility'] == 'CANONICAL_INCOMPLETE_UNKNOWN_GUARD'
    assert not expected_unknown({**failure, 'error': UNKNOWN.format(count=1)}, load)
    assert not expected_unknown(failure, {**load, 'workers': 128})
    assert eligibility({'passed': True, 'canonicalSnapshotBytesVerified': True, 'measurementValid': True}, None, load, {'exitCode': 0}, {'passed': True}, {'passed': True}, {'passed': True})['validFiniteObservation']
    assert not eligibility({'passed': True, 'canonicalSnapshotBytesVerified': True, 'measurementValid': False}, None, load, {'exitCode': 0}, {'passed': True}, {'passed': True}, {'passed': True})['validFiniteObservation']
    print(json.dumps({'status': 'PASS', 'checks': ['exact-unknown-guard', 'failure-never-valid-point', 'wrong-count-rejected', 'different-summary-rejected', 'finite-validity-separate-from-stability', 'invalid-measurement-not-valid-point']}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nak_root', type=Path, nargs='?')
    parser.add_argument('output_json', type=Path, nargs='?')
    parser.add_argument('--cohorts', choices=('pilot100us', 'delay1000,delay100000'), default='pilot100us')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return
    if args.nak_root is None or args.output_json is None:
        parser.error('NAK_ROOT OUTPUT_JSON are required')
    result = summarize(args.nak_root, tuple(args.cohorts.split(',')))
    result['reproduction'] = {'argv': [sys.executable, '-B', str(Path(__file__).resolve()), str(args.nak_root), str(args.output_json), '--cohorts', args.cohorts]}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output_json.with_suffix(args.output_json.suffix + '.tmp')
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(args.output_json)
    print(json.dumps({'output': str(args.output_json), 'included': result['includedTerminalAttemptCount'],
                      'registered': result['registeredAttemptCount'], 'allRequestedRegisteredAttemptsIncluded': result['allRegisteredRequestedAttemptsIncluded'],
                      'cohorts': {key: value['completedAttempts'] for key, value in result['cohorts'].items()}, 'pending': len(result['pendingOrUnavailableTrials']), 'scriptSha256': result['scriptSha256']}))


if __name__ == '__main__':
    main()
