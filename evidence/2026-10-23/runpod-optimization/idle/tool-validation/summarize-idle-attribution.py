#!/usr/bin/env python3
"""Independent frozen-reader attribution for node idle or the separate18k matrix.

ROOT OUTPUT_JSON [--experiment node-idle|pipeline-capacity] [--cohorts formal|pilot]
Default requires all four node-idle attempts and completion/owned cleanup evidence.
--self-test reads source only and uses synthetic metadata; it does not summarize raw.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import re
import sys
import tarfile
import types
import zipfile


NAK_SHA = 'e4eba79229bd21fcb439a45af488298254ae2438f3e91868544f8b37099a931d'
PIPELINE_SHA = '5ebfecadc6271df7f16b8f10834cdb61b91e174ebb19dd4b36246d61afffe2a5'
POSTPROCESSOR_VALIDATOR_SHA = 'ded89b5948bb5b5b036e0fdd97b0447dedab8afdb8cafdad043a726fb44057c3'
NODE_REVISION = '87ad09c11807a78d4f8e3b2ad6088e6940e33261'
LOAD_REVISION = 'e57e341909a49692b9ecbf9693803ed62a240b06'
LOAD_BUNDLE = 'f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937'
ANALYSIS_IDENTITY = '31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f'
ANALYSIS_REVISION = '3fd86fe535fc0858e300e0337d4da154f622ae32'
IDLE_VERIFIER_SHA = '7b4f10c9577595267fdbf04da11ef1ea82b92aa837428a1fd356f5c6ea81336c'
PREPARED_SHA = '2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Regular immutable input required: ' + str(path))
    h, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block); size += len(block)
    return {'path': str(path), 'sha256': h.hexdigest(), 'bytes': size}


def load_module(name, path, expected):
    identity = digest(path)
    require(identity['sha256'] == expected, 'Pinned source changed: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value, identity


def tasks(experiment, pilot=False):
    if experiment == 'pipeline-capacity':
        require(not pilot, '18k matrix has no new pilot cohort')
        return [{'id': f'pc-{mode}-18000-w128-r{rep}', 'cohort': mode, 'rate': 18000,
                 'arrivals': 350000, 'workers': 128, 'transportMode': mode,
                 'phase': 'pipeline-session-ownership-capacity-boundary', 'repetition': rep}
                for rep in (1, 2) for mode in ('direct', 'multiplexed')]
    require(experiment == 'node-idle', 'Unknown experiment')
    if pilot:
        return [{'id': 'i-pilot-park100000-10000-w128', 'cohort': 'pilot', 'rate': 10000,
                 'arrivals': 350000, 'workers': 128, 'transportMode': 'multiplexed', 'maxParkNs': 100000,
                 'phase': 'node-idle-strict350k-canonical-pilot', 'repetition': 1}]
    return [{'id': f'i-park{park}-26000-w128-r{rep}', 'cohort': f'park{park}', 'rate': 26000,
             'arrivals': 350000, 'workers': 128, 'transportMode': 'multiplexed', 'maxParkNs': park,
             'phase': 'node-only-data-path-max-park-control', 'repetition': rep}
            for rep in (1, 2) for park in (1000000, 100000)]


def plan_checks(plan, experiment, pilot):
    expected = tasks(experiment, pilot)
    require(plan.get('trials') == expected, 'Require exact complete registered task order/phase/rate/workers')
    require(plan.get('preparedSnapshotSha256') == PREPARED_SHA, 'Prepared fixture changed')
    node, load = plan.get('node', {}), plan.get('load', {})
    require(load.get('revision') == LOAD_REVISION and load.get('bundleSha256') == LOAD_BUNDLE,
            'Fixed e57 load identity changed')
    expected_node = NODE_REVISION if experiment == 'node-idle' else LOAD_REVISION
    require(node.get('revision') == expected_node, 'Unexpected node source')
    if experiment == 'node-idle':
        require(re.fullmatch('[0-9a-f]{64}', node.get('bundleSha256', ''))
                and node['bundleSha256'] != LOAD_BUNDLE, 'Require separate pinned new node bundle')
        require(plan.get('loadBuild', {}).get('revision') == LOAD_REVISION, 'Separate load build identity changed')
    else:
        require(node == load and plan.get('rate') == 18000, '18k node/load identity or rate differs')
    require(plan.get('build', {}).get('revision') == expected_node, 'Node build revision differs')
    identity = plan.get('postprocessor', {})
    require(plan.get('analysisIdentitySha256') == identity.get('analysisIdentitySha256') == ANALYSIS_IDENTITY
            and identity.get('revision') == ANALYSIS_REVISION, 'Independent31e4 analysis identity changed')
    require(plan.get('noHiddenReissue') is True and plan.get('requireAllOwnedProcessesStoppedBeforeNextTrial') is True,
            'Owned-stop/no-reissue protocol missing')
    return expected


def frozen_reader(root, experiment, pilot):
    path = root.parent / 'nak/tool-validation/summarize-nak-attribution.py'
    identity = digest(path)
    require(identity['sha256'] == NAK_SHA, 'Frozen NAK reader changed')
    source = path.read_text()
    aliases = ('park1000000', 'park100000') if experiment == 'node-idle' else ('direct', 'multiplexed')
    replacements = [("'pilot100us'", "'pilot'"), ("'delay1000'", repr(aliases[0])),
                    ("'delay100000'", repr(aliases[1])), ("tasks[0].get('nakDelayNs')", '1000'),
                    ("            failure = optional_json(directory / 'failure.json', core, inputs)\n",
                     "            failure = optional_json(directory / 'failure.json', core, inputs)\n"
                     "            if load is None and isinstance(failure, dict) and isinstance(failure.get('loadSummary'), dict):\n"
                     "                load = failure['loadSummary']  # Original failed evidence only; never a fake result.\n")]
    if experiment == 'node-idle':
        replacements.extend([
            ("'sameNodeAndLoadSource': node.get('revision') == client.get('revision') and node.get('revision') is not None,",
             "'separateNodeAndLoadSourcesPinned': node.get('revision') == '" + NODE_REVISION + "' and client.get('revision') == '" + LOAD_REVISION + "',"),
            ("'sameNodeAndLoadBundle': node.get('bundleSha256') == client.get('bundleSha256') and node.get('bundleSha256') is not None,",
             "'separateNodeAndLoadBundlesPinned': node.get('bundleSha256') != client.get('bundleSha256') and node.get('bundleSha256') is not None and client.get('bundleSha256') == '" + LOAD_BUNDLE + "',")])
    changes = []
    for before, after in replacements:
        count = source.count(before)
        require(count > 0 and (count == 1 or before in ("'pilot100us'", "'delay1000'", "'delay100000'")),
                'Unexpected frozen reader adaptation boundary: ' + before)
        source = source.replace(before, after)
        changes.append({'before': before, 'after': after, 'occurrences': count})
    value = types.ModuleType('frozen_nak_reader_for_independent_idle_or_18k')
    value.__file__ = str(path)
    exec(compile(source, str(path) + ':explicit-in-memory-cohort-and-source-map', 'exec'), value.__dict__)
    return value, identity, changes, ('pilot',) if pilot else aliases


def all_requested(result, expected):
    actual = [trial['id'] for group in result.get('cohorts', {}).values() for trial in group.get('trials', [])]
    require(len(actual) == len(expected) and set(actual) == {x['id'] for x in expected}
            and not result.get('pendingOrUnavailableTrials') and result.get('allRegisteredRequestedAttemptsIncluded') is True,
            'All requested terminal attempts and three completed observers must be exported; partial curves are refused')


def owned_cleanup(receipt, state):
    require(receipt.get('passed') is True, 'Owned process cleanup did not pass')
    nodes = receipt.get('nodes')
    require(isinstance(nodes, list) and len(nodes) == 3 and {x.get('node') for x in nodes} == {0, 1, 2},
            'Complete three-node owned cleanup required')
    for node in nodes:
        n = node['node']; watch = state + '/watch/'
        expected = {watch + x + '-process.json' for x in ('telemetry', 'counters', 'attribution')}
        expected.add(state + '/node-' + str(n) + '/process.json')
        if n == 2:
            expected.update(watch + x + '-process.json' for x in ('load', 'controller'))
        records = node.get('records', [])
        require(node.get('passed') is True and len(records) == len(expected)
                and {x.get('record') for x in records} == expected, 'Missing/duplicate/differing owned PID records')
        require(all(x.get('recordPresent') is True and x.get('after') == 'stopped' and x.get('passed') is True for x in records),
                'Missing records/identity mismatches are not stopped-process proof')
    return True


def node_class_diff(node, load):
    def jars(release):
        output = {}
        with tarfile.open(release['archive']) as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.startswith('dist/cluster/lib/') and member.name.endswith('.jar'):
                    with zipfile.ZipFile(io.BytesIO(archive.extractfile(member).read())) as jar:
                        output[Path(member.name).name] = {name: hashlib.sha256(jar.read(name)).hexdigest()
                            for name in jar.namelist() if not name.endswith('/')}
        return output
    before, after = jars(load), jars(node)
    require(before and set(before) == set(after), 'Node/load dependency JAR filename sets differ')
    changed = []
    for name in before:
        if not name.startswith('cluster-'):
            require(before[name] == after[name], 'Unrelated dependency/core JAR bytes changed: ' + name)
            continue
        for entry in sorted(set(before[name]) | set(after[name])):
            if before[name].get(entry) == after[name].get(entry): continue
            require(entry == 'io/vectormatch/cluster/ClusterNodeMain.class'
                    or entry.startswith('io/vectormatch/cluster/ClusterNodeMain$'), 'Unrelated cluster class changed: ' + entry)
            changed.append(entry)
    require(changed, 'Require actual new node-only idle class bytes')
    return {'changedClusterEntries': sorted(changed), 'otherJarEntriesUnchanged': True,
            'scope': 'All named JAR entry bytes compared independently. ZIP timestamps/packaging excluded; this is not live JVM inspection.'}


def postprocess_checks(directory, plan, entry, inputs):
    def read(name):
        path = directory / name; inputs.append(digest(path)); return json.loads(path.read_text())
    identity = plan['postprocessor']; checks = read('postprocess.json')
    require(read('postprocessor-identity.json') == identity, 'Trial analysis sidecar differs')
    analysis = checks.get('analysis', {})
    require(checks.get('postprocessor') == identity and checks.get('analysisIdentitySha256') == ANALYSIS_IDENTITY
            and analysis.get('analysisIdentitySha256') == ANALYSIS_IDENTITY, 'Retained analysis identity differs')
    expected_command = [identity['python']['executable'], '-I', '-B',
                        str(Path(identity['root']) / identity['entryPoint']), '--runs-dir', str(directory.parent),
                        '--output-dir', str(directory.parent.parent / 'analysis')]
    require(analysis.get('command') == expected_command, 'Independent analyzer command/runtime differs')
    require(analysis.get('toolSha256') == identity['files'][identity['entryPoint']], 'Analysis entry-point source hash differs')
    require(analysis.get('exitCode') == checks.get('configuration', {}).get('exitCode') == checks.get('archive', {}).get('exitCode') == 0
            and analysis.get('rawInputsUnchanged') is True and analysis.get('arrivalsShaAgrees') is True,
            'Postprocess/configuration/archive checks did not complete')
    verifier = plan['buildTools']['scripts/verify-capacity-config.py']
    require(checks['configuration'].get('toolSha256') == verifier['sha256'], 'Node-source verifier differs')
    snapshots = analysis.get('immutableOutputSha256', {})
    require(set(snapshots) == {'analysis-summary.json', 'analysis-capacity.csv'}, 'Missing immutable analyzer outputs')
    for name, sha in snapshots.items():
        actual = digest(directory / name); inputs.append(actual)
        require(actual['sha256'] == sha, 'Immutable analyzer output changed: ' + name)
    snapshot = json.loads((directory / 'analysis-summary.json').read_text())
    rows = [row for row in snapshot.get('trials', []) if row.get('id') == entry['id']]
    require(len(rows) == 1, 'Immutable analyzer snapshot omitted/duplicated this attempt')
    require(rows[0].get('inputSha256') == analysis.get('inputSha256Before'),
            'Immutable analyzer input SHA key/value closure differs from postprocess before-snapshot')
    archives = entry['csvArchiveEvidence']['archives']
    require(len(archives) == 1 and archives[0]['gzipReadThroughEndAndCrcVerified'] is True, 'Complete gzip evidence required')
    manifest_path = directory / 'arrivals-archive.json'; inputs.append(digest(manifest_path))
    manifest = json.loads(manifest_path.read_text()); archive = archives[0]
    require(manifest['compressedSha256'] == archive['sha256'] and manifest['rawSha256'] == archive['uncompressedSha256']
            and manifest['rawBytes'] == archive['uncompressedBytes'] and manifest['compressedBytes'] == archive['bytes'],
            'Gzip/raw manifest digest or byte counts differ')
    for name, sha in analysis.get('inputSha256Before', {}).items():
        require(Path(name).name == name and name not in ('.', '..'), 'Unsafe analysis raw input path')
        if name == 'arrivals.csv':
            require(sha == archive['uncompressedSha256'], 'Analyzed CSV differs from independently decoded archive')
        else:
            actual = digest(directory / name); inputs.append(actual)
            require(actual['sha256'] == sha, 'Analyzed input changed: ' + name)
    require(rows[0].get('inputSha256', {}).get('arrivals.csv') == archive['uncompressedSha256'], 'Analyzer CSV hash differs')
    return {'passed': True, 'analysisIdentitySha256': ANALYSIS_IDENTITY, 'command': expected_command,
            'immutableOutputSha256': snapshots, 'rawCsvShaCheckedAgainstDecodedArchive': True,
            'scope': 'No analyzer invocation or plaintext CSV restoration; compare retained outputs/inputs with independently decoded gzip bytes.'}, rows[0]


def exact_node_arguments(record, verifier, task, fixed, trial, release, hosts, experiment):
    arguments = record.get('arguments', [])
    extra = [] if experiment == 'pipeline-capacity' else ['-Dvectormatch.node.dataPathMaxParkNs=' + str(task['maxParkNs'])]
    expected = ['/opt/vectormatch/tools/jdk-21.0.13+9/bin/java',
                '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED', '--add-opens=java.base/java.util.zip=ALL-UNNAMED',
                '-Xmx2g', '-Dvm.process.identity=' + trial['state'] + '/node-' + str(record['auditNode']),
                '-Daeron.cluster.appointed.leader.id=0', '-Daeron.cluster.max.sessions=256',
                '-Daeron.nak.unicast.delay=1000', *extra, '-cp', release + '/dist/cluster/lib/*',
                'io.vectormatch.cluster.ClusterNodeMain',
                *verifier.node_arguments(trial, fixed, record['auditNode'], hosts)]
    return {'exactFullArgumentsMatched': arguments == expected,
            'recordedCommandDigestMatched': record.get('commandSha256') == verifier.command_sha256(arguments),
            'expectedArguments': expected, 'recordedArguments': arguments}


def refresh_eligibility_counts(result):
    trials = []
    for group in result['cohorts'].values():
        rows = group['trials']; trials.extend(rows)
        group['validFiniteObservationCount'] = sum(row.get('validFiniteObservation') is True for row in rows)
        group['diagnosticsOnlyAttemptCount'] = sum(row.get('diagnosticsOnly') is True for row in rows)
    result['validFiniteObservationCount'] = sum(row.get('validFiniteObservation') is True for row in trials)
    result['diagnosticsOnlyAttemptCount'] = sum(row.get('diagnosticsOnly') is True for row in trials)


def summarize(root, experiment, pilot):
    root = root.resolve()
    plan_path = root / ('pilot-plan.json' if pilot else 'plan.json')
    plan = json.loads(plan_path.read_text()); expected = plan_checks(plan, experiment, pilot)
    reader, reader_identity, adaptations, cohorts = frozen_reader(root, experiment, pilot)
    result = reader.summarize(root, cohorts)
    all_requested(result, expected)
    inputs = result['inputs']; inputs.append(digest(plan_path))
    optimization = root.parent; workspace = optimization.parents[2]
    pipeline, pipeline_identity = load_module('pinned_pipeline_checks_only',
        optimization / 'pipeline/tool-validation/summarize-pipeline-attribution.py', PIPELINE_SHA)
    validator, validator_identity = load_module('pinned_analysis_identity_validator',
        workspace / 'runtime/cloud/optimization-20261024/pipeline-capacity/postprocessor.py', POSTPROCESSOR_VALIDATOR_SHA)
    validator.validate_identity(plan['postprocessor'], check_python=False)
    analysis_identity = plan['postprocessor']
    for path in [Path(analysis_identity['root']) / name for name in analysis_identity['files']]:
        inputs.append(digest(path))
    for path in (analysis_identity['sourceArchive']['path'], analysis_identity['validationReceipt']['path']):
        inputs.append(digest(path))
    verifier_declared = plan['buildTools']['scripts/verify-capacity-config.py']
    verifier_expected = IDLE_VERIFIER_SHA if experiment == 'node-idle' else 'beb8eaf5f5ba1311aa02e7ff89777505270fa13d5506a4d3850153f802f7f100'
    require(verifier_declared['sha256'] == verifier_expected, 'Unexpected separately pinned node-source verifier')
    verifier, verifier_identity = load_module('pinned_node_source_verifier', Path(verifier_declared['path']), verifier_expected)
    for side in ('node', 'load'):
        actual = digest(plan[side]['archive']); inputs.append(actual)
        require(actual['sha256'] == plan[side]['bundleSha256'], 'Pinned local bundle bytes changed: ' + side)
    if experiment == 'node-idle':
        audit = node_class_diff(plan['node'], plan['load'])
        require(audit['changedClusterEntries'] == plan.get('nodeClassDiffAudit', {}).get('changedClusterEntries')
                and plan.get('nodeClassDiffAudit', {}).get('otherJarEntriesUnchanged') is True, 'Registered node-only class diff differs')
        result['independentlyVerifiedNodeClassDiff'] = audit
    for cohort, group in result['cohorts'].items():
        for entry in group['trials']:
            task = next(t for t in expected if t['id'] == entry['id'])
            directory = root / cohort / 'runs' / task['id']
            trial = entry['manifest']; config = json.loads((directory / 'configuration.json').read_text())
            load_path = directory / 'load-result.json'
            load = json.loads(load_path.read_text()) if load_path.is_file() else (entry.get('failure') or {}).get('loadSummary', {})
            entry['loadSummaryProvenance'] = 'load-result.json' if load_path.is_file() else 'failure.json/loadSummary; original diagnostic evidence'
            fixed = group['campaign']['fixed']; actual_prepared = digest(directory / 'prepared-snapshot.bin'); inputs.append(actual_prepared)
            checks = pipeline.pipeline_checks(group['campaign'], plan, task, trial, config, load, actual_prepared['sha256'])
            checks['preparedFixtureDigestPinnedIndependently'] = actual_prepared['sha256'] == PREPARED_SHA
            cleanup = json.loads((directory / 'all-owned-processes-stopped.json').read_text())
            owned_cleanup(cleanup, trial['state'])
            entry['completeExplicitOwnedCleanupVerified'] = True
            entry['ownedCleanupTimestampUtc'] = cleanup.get('timestamp')
            nodes = []
            for node in range(3):
                record = json.loads((directory / f'node{node}/process.json').read_text())
                record['auditNode'] = node
                argument_check = exact_node_arguments(record, verifier, task, fixed, trial, plan['node']['root'], ','.join(config['memberHosts']), experiment)
                startup = (directory / f'node{node}/process.log').read_text()
                role_lines = [line for line in startup.splitlines() if line.startswith('VECTOR_NODE_DATA_PATH_IDLE ')]
                idle_matched, error = None, None
                try:
                    if experiment == 'node-idle':
                        verifier.verify_node_data_path_jvm_arguments(record['arguments'], fixed)
                        verifier.verify_node_data_path_startup(fixed, startup, node)
                        idle_matched = fixed.get('nodeDataPathMaxParkNs') == task['maxParkNs']
                    else:
                        require(not role_lines and not any('vectormatch.node.dataPath' in x for x in record['arguments']), '18k historical node contains undeclared idle opt-in')
                        idle_matched = True
                except (AssertionError, ValueError, KeyError, TypeError) as exc:
                    idle_matched, error = False, str(exc)
                nodes.append({'node': node, **argument_check, 'idlePolicyMatched': idle_matched,
                              'idleEvidenceError': error, 'actualCreatedInstanceLines': role_lines})
            checks['allNodeArgumentsAndDigestsMatched'] = all(n['exactFullArgumentsMatched'] and n['recordedCommandDigestMatched'] for n in nodes)
            checks['allNodeIdleRoleEvidenceMatched'] = all(n['idlePolicyMatched'] is True for n in nodes)
            postprocessing, analyzer = postprocess_checks(directory, plan, entry, inputs)
            entry['independentPostprocessorVerification'] = postprocessing
            entry['analyzerClassification'] = {k: analyzer.get(k) for k in ('classification', 'measurementValid', 'observedStableWindow', 'stabilityChecks', 'inputSha256')}
            entry['nodeAndLoadConfigurationEvidence'] = {'checks': checks, 'allMatched': all(x is True for x in checks.values()),
                'nodes': nodes, 'preparedSnapshot': actual_prepared, 'nodeSource': plan['node'], 'loadSource': plan['load'],
                'nodeAndLoadSameArtifact': experiment == 'pipeline-capacity',
                'scope': 'Separate node/load sources are checked independently. runnerSelected concerns an idle instance selected by the pinned library implementation, not agent liveness or CPU. Unselected driver instances remain explicitly configured evidence.'}
            extras = verifier.load_generator_jvm_arguments(trial, config, fixed)
            expected_load = verifier.load_generator_arguments(trial, trial['release'], extras)
            load_record_path = directory / 'load-process.json'; inputs.append(digest(load_record_path))
            load_record = json.loads(load_record_path.read_text())
            checks['fixedLoadFullCommandDigestMatched'] = load_record.get('commandSha256') == verifier.command_sha256(expected_load)
            if pilot:
                entry['strictPilotPassed'] = (load.get('scheduledArrivals') == load.get('confirmedAcceptedCommands') == 350000
                    and all(type(load.get(k)) is int and load[k] == 0 for k in ('clientNotSentCommands', 'businessRejectedCommands',
                        'serverErrors', 'unknownAtInitialDeadline', 'unresolvedFinal', 'schedulerLatenessAboveLimitCount'))
                    and entry['canonicalBusinessCorrectnessVerified'] is True and analyzer.get('measurementValid') is True)
                checks['strictPilotPrerequisitesSatisfied'] = entry['strictPilotPassed']
            pipeline.diagnostics_only(entry, checks)
            entry['nodeAndLoadConfigurationEvidence']['allMatched'] = all(x is True for x in checks.values())
            entry['reportedLatencyDistributions'] = {'microsecondDistributions': {k: load.get(k) for k in
                ('acceptedScheduledToConfirmedMicroseconds', 'executeInitialAttemptMicroseconds', 'queueDelayMicroseconds', 'schedulerLatenessMicroseconds')},
                'allOfferedAcceptedP99Microseconds': load.get('allOfferedAcceptedP99Microseconds'),
                'scope': 'Conditional returned/accepted responses include drain; dropped/unknown arrivals receive no invented latency. Invalid points remain diagnostic only.'}
    action = 'pipeline-capacity-matrix-completed' if experiment == 'pipeline-capacity' else 'node-idle-' + ('pilot' if pilot else 'matrix') + '-completed'
    timeline_path = root / 'timeline.jsonl'; inputs.append(digest(timeline_path))
    events = [json.loads(line) for line in timeline_path.read_text().splitlines() if line.strip()]
    completion = [row for row in events if row.get('action') == action]
    require(len(completion) == 1 and [x['id'] for x in completion[0].get('trials', [])] == [x['id'] for x in expected], 'Complete requested matrix/pilot timeline required')
    def utc(value):
        require(isinstance(value, str), 'UTC completion/cleanup timestamp missing')
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    completed_at = utc(completion[0].get('timestamp'))
    require(all(utc(entry['manifest'].get('completedAt')) <= completed_at
                and utc(entry.get('ownedCleanupTimestampUtc')) <= completed_at
                for group in result['cohorts'].values() for entry in group['trials']), 'Completion event precedes a trial/owned cleanup')
    result['completionEvent'] = completion[0]
    unique = {}
    for identity in inputs:
        old = unique.setdefault(identity['path'], identity)
        require(old == identity, 'Input changed while reading: ' + identity['path'])
    result['inputs'] = list(unique.values())
    result['reusedNakWrapperSha256'] = result.pop('scriptSha256')
    result['scriptSha256'] = digest(Path(__file__))['sha256']
    result['tools'].update(frozenNakReader=reader_identity, pipelineMetadataChecks=pipeline_identity,
                           independentAnalysisValidator=validator_identity, nodeSourceVerifier=verifier_identity,
                           independentWrapper=digest(Path(__file__)))
    result['test'] = experiment + '-independent-owned-attribution'
    result['inMemoryFrozenSourceAdaptations'] = adaptations
    result['postprocessorIdentity'] = analysis_identity
    refresh_eligibility_counts(result)
    result['generatedAt'] = datetime.now(timezone.utc).isoformat()
    result['scope'] = ('Requested complete registered finite observations only. Node-only idle changes maximum park for selected node data-path roles; fixed e57 multiplexed load is a separate artifact. '
        'The alternative18k mode retains its original direct/multiplexed factor and same e57 artifact, never merged with idle. Strict pilot and formal are separate. '
        'Process/TID/startTicks/inode/FD-overlap/whole-collection interior and monotonic gap rules are frozen; missing is not zero. '
        'CnC first/last cumulative deltas have different coverage from adjacent CPU/socket pairs. Positions are non-atomic differences, not exact lag; archive write-path wall time includes force/descheduling. '
        'Invalid/failed attempts remain diagnostic and cannot establish capacity. Finite paths do not prove sustained capacity, universal ceilings, unique causation or a full replicated checkpoint/restart.')
    return result


def self_test():
    expected = tasks('node-idle'); assert len(expected) == 4 and len(tasks('node-idle', True)) == 1
    cap = tasks('pipeline-capacity'); assert len(cap) == 4 and all(t['rate'] == 18000 for t in cap)
    fake = {'cohorts': {'x': {'trials': [{'id': t['id']} for t in expected]}},
            'pendingOrUnavailableTrials': [], 'allRegisteredRequestedAttemptsIncluded': True}
    all_requested(fake, expected)
    fake['cohorts']['x']['trials'].pop()
    try: all_requested(fake, expected)
    except ValueError: pass
    else: raise AssertionError('Partial formal must fail')
    plan = {'trials': expected, 'preparedSnapshotSha256': PREPARED_SHA,
            'node': {'revision': NODE_REVISION, 'bundleSha256': 'a' * 64},
            'load': {'revision': LOAD_REVISION, 'bundleSha256': LOAD_BUNDLE},
            'build': {'revision': NODE_REVISION}, 'loadBuild': {'revision': LOAD_REVISION},
            'postprocessor': {'revision': ANALYSIS_REVISION, 'analysisIdentitySha256': ANALYSIS_IDENTITY},
            'analysisIdentitySha256': ANALYSIS_IDENTITY, 'noHiddenReissue': True,
            'requireAllOwnedProcessesStoppedBeforeNextTrial': True}
    assert plan_checks(plan, 'node-idle', False) == expected
    for field, value in [('preparedSnapshotSha256', 'b' * 64), ('analysisIdentitySha256', 'b' * 64), ('noHiddenReissue', False)]:
        try: plan_checks({**plan, field: value}, 'node-idle', False)
        except ValueError: pass
        else: raise AssertionError('Changed fixed identity accepted: ' + field)
    broken = {**plan, 'node': plan['load']}
    try: plan_checks(broken, 'node-idle', False)
    except ValueError: pass
    else: raise AssertionError('Old node cannot be relabeled as idle')
    state = '/owned/test'; receipt = {'passed': True, 'nodes': []}
    for n in range(3):
        names = [state + '/watch/' + x + '-process.json' for x in ('telemetry', 'counters', 'attribution')]
        names.append(state + '/node-' + str(n) + '/process.json')
        if n == 2: names += [state + '/watch/' + x + '-process.json' for x in ('load', 'controller')]
        receipt['nodes'].append({'node': n, 'passed': True, 'records': [{'record': name, 'recordPresent': True, 'after': 'stopped', 'passed': True} for name in names]})
    assert owned_cleanup(receipt, state)
    receipt['nodes'][2]['records'][0]['recordPresent'] = False
    try: owned_cleanup(receipt, state)
    except ValueError: pass
    else: raise AssertionError('Missing owned record is not stopped')
    root = Path(__file__).resolve().parents[1]
    for experiment, pilot in [('node-idle', False), ('node-idle', True), ('pipeline-capacity', False)]:
        _, identity, changes, _ = frozen_reader(root, experiment, pilot)
        assert identity['sha256'] == NAK_SHA and len(changes) == (7 if experiment == 'node-idle' else 5)
    workspace = root.parent.parents[2]
    verifier, _ = load_module('synthetic_idle_verifier_only', workspace / 'scripts/verify-capacity-config.py', IDLE_VERIFIER_SHA)
    fixed = {'nodeDataPathMaxParkNs': 100000, 'driverThreadingArgument': 'SHARED'}
    lines = ['VECTOR_CLUSTER_STARTED node=0 driverThreading=SHARED driverIdleMaxSpins=10 driverIdleMaxYields=5 '
             'driverIdleMinParkNs=1000 driverIdleMaxParkNs=100000 nodeDataPathIdlePolicyVersion=1 '
             'nodeDataPathMaxParkNs=100000 nodeDataPathIdleInstancesDistinct=true']
    for i, role in enumerate(verifier.NODE_DATA_PATH_ROLES, 1):
        yields = 5 if role.startswith('driver-') else 20
        selected = not role.startswith('driver-') or role == 'driver-shared'
        lines.append(f'VECTOR_NODE_DATA_PATH_IDLE node=0 role={role} instanceId={i} runnerSelected={str(selected).lower()} '
            'strategyClass=org.agrona.concurrent.BackoffIdleStrategy '
            f'configuration=BackoffIdleStrategy{{alias=backoff,maxSpins=10,maxYields={yields},minParkPeriodNs=1000,maxParkPeriodNs=100000}}')
    verifier.verify_node_data_path_startup(fixed, '\n'.join(lines), 0)
    try: verifier.verify_node_data_path_startup(fixed, '\n'.join(lines).replace('maxYields=20', 'maxYields=5'), 0)
    except AssertionError: pass
    else: raise AssertionError('Agent20yields must not become driver5')
    pipeline, _ = load_module('synthetic_diagnostics_only', root.parent / 'pipeline/tool-validation/summarize-pipeline-attribution.py', PIPELINE_SHA)
    failed = {'validFiniteObservation': False, 'capacityEligibility': 'CANONICAL_INCOMPLETE_UNKNOWN_GUARD'}
    pipeline.diagnostics_only(failed, {'sourceMatched': True})
    assert failed['diagnosticsOnly'] is True and failed['validFiniteObservation'] is False
    invalid_configuration = {'validFiniteObservation': True, 'capacityEligibility': 'VALID_FINITE_OBSERVATION_CLASSIFICATION_SEPARATE',
                             'analyzerClassification': {'measurementValid': True}}
    pipeline.diagnostics_only(invalid_configuration, {'nodeMatched': False})
    totals = {'cohorts': {'x': {'trials': [invalid_configuration]}}, 'validFiniteObservationCount': 1}
    refresh_eligibility_counts(totals)
    assert totals['validFiniteObservationCount'] == 0 and totals['diagnosticsOnlyAttemptCount'] == 1
    assert totals['cohorts']['x']['validFiniteObservationCount'] == 0
    print(json.dumps({'status': 'PASS', 'checks': ['formal-four-required', 'partial-refused', 'strict-pilot-separate', '18k-separate-phase',
        'separate-node-load-identities', 'old-node-not-relabelled', 'prepared-pinned', 'analysis31e4-pinned', 'no-hidden-reissue',
        'exact-owned-observer-load-controller-records', 'missing-record-not-zero', 'frozen-reader-hash', 'explicit-in-memory-source-adaptations',
        'eight-role-runner-selection-metadata', 'agent20-driver5-preserved', 'failed-never-promoted', 'post-check-validity-counts-recomputed'],
        'actualRawSummarizationExecuted': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?'); parser.add_argument('output_json', type=Path, nargs='?')
    parser.add_argument('--experiment', choices=('node-idle', 'pipeline-capacity'), default='node-idle')
    parser.add_argument('--cohorts', choices=('formal', 'pilot'), default='formal')
    parser.add_argument('--self-test', action='store_true'); args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.root is None or args.output_json is None: parser.error('ROOT OUTPUT_JSON required')
    require(not args.output_json.exists(), 'Output already exists; frozen reports are never overwritten')
    result = summarize(args.root, args.experiment, args.cohorts == 'pilot')
    result['reproduction'] = {'argv': [sys.executable, '-B', str(Path(__file__).resolve()), str(args.root), str(args.output_json),
                                     '--experiment', args.experiment, '--cohorts', args.cohorts]}
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n'
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open('x') as stream: stream.write(text)
    print(json.dumps({'output': str(args.output_json), 'included': result['includedTerminalAttemptCount'],
                      'registered': result['registeredAttemptCount'], 'allRequestedIncluded': result['allRegisteredRequestedAttemptsIncluded'],
                      'sha256': digest(args.output_json)['sha256'], 'scriptSha256': result['scriptSha256']}))


if __name__ == '__main__':
    main()
