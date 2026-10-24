#!/usr/bin/env python3
"""Independent mixed-source CPU client-driver experiment verifier; no legacy source mutation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote

NODE_REVISION = '433f02bebe2f3109ec363291fa562d5c509c0723'
LOAD_REVISION = 'ebede54c0cf46deabdd7d03a8a155a3a9e13b38a'
NODE_VERIFIER_SHA256 = 'e41416942f3baf6a1a6836a1f76289a599d50887973b905ae7a008fe55fbe0c0'
MANIFEST_SHA256 = '177819fe91de0952b8aeadee365b179d2f60f31b4f1b53056175b6bb4668ed69'
NODE_ROOT = '/opt/vectormatch-cpu/releases/' + NODE_REVISION
LOAD_ROOT = '/opt/vectormatch-cpu/client-releases/' + LOAD_REVISION
JAVA = '/opt/vectormatch-cpu/tools/jdk/bin/java'
NODE_JAVA = '/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java'
PREPARED_SHA256 = '2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4'
OPEN_FLAGS = ['--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED', '--add-opens=java.base/java.util.zip=ALL-UNNAMED']
JARS = {'dist/cluster/lib/' + n for n in ('agrona-2.6.1.jar', 'aeron-all-1.53.3.jar', 'core-0.1.0-SNAPSHOT.jar', 'cluster-0.1.0-SNAPSHOT.jar')}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def command_sha(arguments):
    return hashlib.sha256(b''.join(a.encode() + b'\0' for a in arguments)).hexdigest()


def load_flags(plan):
    maximum = plan['task']['clientDriverMaxParkNs']
    require(type(maximum) is int and maximum in (1000000, 100000), 'Only explicit1ms/100us arms supported')
    return ['-Dvectormatch.capacity.client.driver=shared', '-Daeron.nak.unicast.delay=1000',
            '-Dvectormatch.capacity.client.transport=multiplexed', '-Dvectormatch.client.driverMaxParkNs=' + str(maximum)]


def load_arguments(plan):
    return [JAVA, *OPEN_FLAGS, *load_flags(plan), '-Xmx2g', '-cp', LOAD_ROOT + '/dist/cluster/lib/*',
            'io.vectormatch.cluster.RemoteCapacityExperiment', plan['paths']['trial'], '23000',
            '22000', '350000', '128', '64', '2000', '30000', '0', '20', 'extended-350k-256']


def node_arguments(plan, node, legacy):
    return [NODE_JAVA, *OPEN_FLAGS, '-Xmx2g', '-Dvm.process.identity=' + plan['paths']['state'] + '/node-' + str(node),
            '-Daeron.cluster.appointed.leader.id=0', '-Daeron.cluster.max.sessions=256',
            '-Daeron.nak.unicast.delay=1000', '-Dvectormatch.node.dataPathMaxParkNs=100000',
            '-cp', NODE_ROOT + '/dist/cluster/lib/*', 'io.vectormatch.cluster.ClusterNodeMain',
            *legacy.node_arguments({'state': plan['paths']['state']}, plan['fixed'], node, '127.0.0.1,127.0.0.1,127.0.0.1')]


def verify_manifest(plan):
    m = plan['loadArtifactManifest']
    source = plan.get('loadArtifactManifestSource', '')
    require(hashlib.sha256(source.encode()).hexdigest() == MANIFEST_SHA256 and json.loads(source) == m, 'Candidate manifest source/payload SHA differs')
    require(plan.get('loadArtifactManifestSha256') == MANIFEST_SHA256, 'Pinned candidate preparation manifest SHA differs')
    require(m.get('schemaVersion') == 1 and m.get('passed') is True and m.get('candidateRevision') == LOAD_REVISION
            and m.get('nodeRevision') == NODE_REVISION and m.get('remoteRoot') == LOAD_ROOT
            and m.get('deploymentScope') == 'LOCAL_PREPARATION_ONLY_NOT_DEPLOYED', 'Mixed-source manifest identity differs')
    rows = m.get('files', [])
    require(len(rows) == 4 and {r['path'] for r in rows} == JARS, 'Exact four-JAR candidate classpath required')
    baseline = plan['deployment']['filesVerified']
    for row in rows:
        require(row['baselineSha256'] == baseline[row['path']] and type(row['bytes']) is int and row['bytes'] > 0
                and re.fullmatch(r'[a-f0-9]{64}', row['sha256']), 'Candidate/baseline JAR binding differs')
        if row['path'].endswith(('agrona-2.6.1.jar', 'aeron-all-1.53.3.jar')):
            require(row['sha256'] == row['baselineSha256'] and row['jarBytesEqual'] is True, 'Dependency bytes changed')
    changed = m.get('changedEntries', [])
    require(len(changed) == 18 and len({r['entry'] for r in changed}) == 18, 'Exact prepared class change audit required')
    require(all(r['jar'] == 'cluster-0.1.0-SNAPSHOT.jar'
                and re.fullmatch(r'io/vectormatch/cluster/(ClusterClient|MultiplexedLoadTransports|RemoteCapacityExperiment)(\$[^/]*)?\.class', r['entry'])
                for r in changed), 'Unexpected production entry change')
    return m


def verify_classpath_receipt(plan, receipt):
    m = verify_manifest(plan)
    expected_node = {name: {'sha256': plan['deployment']['filesVerified'][name]} for name in JARS}
    expected_load = {row['path']: {'sha256': row['sha256'], 'bytes': row['bytes']} for row in m['files']}
    require(receipt.get('schemaVersion') == 1 and receipt.get('passed') is True
            and receipt.get('nodeRevision') == NODE_REVISION and receipt.get('loadRevision') == LOAD_REVISION
            and receipt.get('nodeRoot') == NODE_ROOT and receipt.get('loadRoot') == LOAD_ROOT
            and receipt.get('manifestSha256') == MANIFEST_SHA256, 'Actual classpath receipt identity differs')
    for phase in ('before', 'after'):
        block = receipt.get(phase, {})
        require(block.get('node') == expected_node and block.get('load') == expected_load,
                'Exact actual node/load classpath inventory differs: ' + phase)
    return receipt


def verify_observation(plan, observation, startup):
    maximum = plan['task']['clientDriverMaxParkNs']
    directory = plan['paths']['trial'] + '/load-multiplexed-driver'
    description = ('BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=5, minParkPeriodNs=1000, maxParkPeriodNs='
                   + str(maximum) + '}')
    require(type(observation) is dict and set(observation) == {'available', 'source', 'directory', 'threadingMode', 'strategyClass', 'strategyDescription'},
            'Actual measured-driver observation schema differs')
    require(observation['available'] is True and observation['source'] == 'measured-multiplexed-owner'
            and observation['directory'] in (directory, directory + '/') and observation['threadingMode'] == 'SHARED'
            and observation['strategyClass'] == 'org.agrona.concurrent.BackoffIdleStrategy'
            and observation['strategyDescription'] == description, 'Measured-owner actual strategy differs/unavailable')
    matched = []
    for line in startup.splitlines():
        if not line.startswith('VECTOR_CLIENT_DRIVER_IDLE '):
            continue
        uris = re.findall(r'(?:^|\s)driverDirectoryUri=([^\s]+)', line)
        if len(uris) != 1:
            continue
        uri = urlsplit(uris[0])
        if uri.scheme == 'file' and not uri.netloc and not uri.query and not uri.fragment and unquote(uri.path) in (directory, directory + '/'):
            matched.append(line)
    require(len(matched) == 1, 'Exactly one startup attestation for measured driver URI required; setup/control cannot substitute')
    line = matched[0]
    require(line.count(' actualStrategy=') == 1, 'Missing/duplicate actual strategy field')
    header = line.split(' actualStrategy=', 1)[0]
    for key, value in {'policyVersion': 1, 'maxSpins': 10, 'maxYields': 5, 'minParkNs': 1000,
                       'maxParkNs': maximum, 'threadingMode': 'SHARED'}.items():
        require(re.findall(r'(?:^|\s)' + key + r'=([^\s]+)(?=\s|$)', header) == [str(value)], 'Actual measured driver startup differs: ' + key)
    require(' actualStrategy=' + description + ' scope=client-driver-only' in line, 'Actual startup strategy description differs')
    return observation


def verify(plan, directory, legacy):
    """Read-only acceptance. Caller writes a new receipt; original records are never relabeled."""
    require(__debug__, 'Original node verifier assertions must be enabled')
    directory = Path(directory)
    verify_manifest(plan)
    require(plan.get('sourceSchemaVersion') == 2 and plan.get('sourceRevision') == NODE_REVISION
            and plan.get('loadSourceRevision') == LOAD_REVISION, 'Mixed-source plan schema/revisions differ')
    require(sha(legacy.__file__) == NODE_VERIFIER_SHA256, 'Frozen original node verifier changed')
    trial, config, load = (read(directory / n) for n in ('trial.json', 'configuration.json', 'load-result.json'))
    expected_trial = {'id': plan['jobId'], 'release': NODE_ROOT, 'sourceRevision': NODE_REVISION,
        'deploymentRevision': NODE_REVISION, 'loadGeneratorRevision': LOAD_REVISION, 'loadGeneratorRelease': LOAD_ROOT,
        'loadGeneratorBundleSha256': plan['loadArtifactManifest']['bundleSha256'], 'fixedNodeConfiguration': plan['fixed'],
        'loadGeneratorJvmArguments': load_flags(plan), 'sourceSchemaVersion': 2,
        'nodeSourceRevision': NODE_REVISION, 'loadSourceRevision': LOAD_REVISION}
    for key, expected in expected_trial.items():
        require(trial.get(key) == expected, 'Recorded mixed-source trial differs: ' + key)
    fixed = plan['fixed']
    require(fixed.get('nodeDataPathMaxParkNs') == fixed.get('driverIdleMaxParkNs') == 100000
            and fixed.get('clientDriverMaxParkNs') == plan['task']['clientDriverMaxParkNs'], 'Fixed node/client maximum differs')
    expected_config = {'aeronMtuLength': 1248, 'expectedLeader': 0, 'queueCapacityPerWorker': 64,
        'requestTimeoutMs': 2000, 'drainTimeoutMs': 30000, 'schedulerLatenessLimitMs': 20, 'portBase': 23000,
        'profile': 'extended-350k-256', 'declaredOutboxCapacity': 800000, 'expectedStateProfile': 'capacity-350k-v1',
        'fullCheckpointMaximumBytes': 536870912, 'expectedResultCachePerProducer': 1024,
        'expectedCoreLimits': {'maxAccounts': 10000, 'maxProducers': 10000, 'maxRetainedOrders': 360000, 'maxCachedResults': 100000},
        'memberHosts': ['127.0.0.1'] * 3, 'ratePerSecond': 22000, 'scheduledArrivals': 350000,
        'workers': 128, 'maxServiceRequestsInFlight': 128, 'clientPendingCapacity': 128,
        'clientDriverCount': 1, 'clientSessionCount': 1, 'clientDriverMode': 'shared', 'clientTransportMode': 'multiplexed',
        'clientAeronMode': 'one-session-one-network-owner', 'clientNakUnicastDelayNs': 1000, 'clientNakUnicastRetryDelayRatio': 100,
        'preparedSnapshotSha256': PREPARED_SHA256}
    for key, expected in expected_config.items():
        require(config.get(key) == expected and type(config.get(key)) == type(expected), 'Effective runtime configuration differs: ' + key)
    hashes = {}
    for node in range(3):
        prefix = 'node' + str(node)
        record, startup = read(directory / prefix / 'process.json'), (directory / prefix / 'process.log').read_text()
        expected = node_arguments(plan, node, legacy)
        require(type(record.get('pid')) is int and record['pid'] > 1 and type(record.get('startTicks')) is int and record['startTicks'] > 0, 'Node process identity absent/invalid')
        require(record.get('arguments') == expected and record.get('commandSha256') == command_sha(expected), 'Exact node argv/hash differs')
        proof = read(directory / ('node' + str(node) + '-actual-process.json'))
        require(all(proof.get(key) == record.get(key) for key in ('pid', 'startTicks', 'commandSha256', 'arguments'))
                and proof.get('actualArguments') == expected and proof.get('actualCommandSha256') == command_sha(expected), 'Actual node process observation differs')
        legacy.verify_maximum_cluster_sessions(expected, fixed)
        legacy.verify_nak_jvm_arguments(expected, fixed)
        legacy.verify_node_data_path_jvm_arguments(expected, fixed)
        legacy.verify_requested_receive_buffer_startup(fixed, startup)
        legacy.verify_driver_threading_startup(fixed, startup)
        legacy.verify_nak_startup(fixed, startup)
        legacy.verify_node_data_path_startup(fixed, startup, node)
        instance_lines = [line for line in startup.splitlines() if line.startswith('VECTOR_NODE_DATA_PATH_IDLE ')]
        require(len(instance_lines) == 11, 'Expected all11 actual node idle instances')
        for key, value in {'profile': 'capacity-350k-v1', 'outbox': 800000, 'checkpointMaxBytes': 536870912,
                           'maxRetainedOrders': 360000, 'resultCachePerProducer': 1024}.items():
            require(str(key) + '=' + str(value) in startup, 'Actual node state profile differs: ' + key)
        for name in (prefix + '/process.json', prefix + '/process.log', 'node' + str(node) + '-actual-process.json'):
            hashes[name] = sha(directory / name)
    require(sha(directory / 'prepared-snapshot.bin') == PREPARED_SHA256, 'Prepared canonical bytes differ')
    expected = load_arguments(plan); record = read(directory / 'load-process.json')
    require(type(record.get('pid')) is int and record['pid'] > 1 and type(record.get('startTicks')) is int and record['startTicks'] > 0, 'Load process identity absent/invalid')
    require(record.get('arguments') == record.get('actualArguments') == expected
            and record.get('commandSha256') == record.get('actualCommandSha256') == command_sha(expected), 'Exact actual candidate load argv/hash differs')
    observation = config.get('clientSharedDriverIdleObservation')
    verify_observation(plan, observation, (directory / 'load.log').read_text())
    require(load.get('clientSharedDriverIdleObservation') == observation, 'Load result actual driver observation differs')
    runtime_fields = ('clientDriverCount', 'clientSessionCount', 'clientDriverMode', 'clientTransportMode',
                      'clientAeronMode', 'clientPendingCapacity', 'clientNakUnicastDelayNs', 'clientNakUnicastRetryDelayRatio',
                      'workers', 'queueCapacityPerWorker', 'scheduledArrivals')
    for key in runtime_fields:
        require(load.get(key) == config.get(key) and type(load.get(key)) == type(config.get(key)), 'Load runtime metadata differs: ' + key)
    require(load.get('targetArrivalRatePerSecond') == 22000, 'Load runtime arrival rate differs')
    configuration_only = not (directory / 'result.json').is_file()
    if configuration_only:
        require(legacy.failed_unknown_configuration_only(directory, True) is True, 'Only exact terminal UNKNOWN guard may be configuration-only')
    else:
        result = read(directory / 'result.json')
        require(result.get('clientSharedDriverIdleObservation') == observation, 'Final result actual driver observation differs')
        for key in runtime_fields:
            require(result.get(key) == load.get(key) and type(result.get(key)) == type(load.get(key)), 'Final runtime metadata differs: ' + key)
    classpath = verify_classpath_receipt(plan, read(directory / 'mixed-source-classpath-verification.json'))
    names = ['trial.json', 'configuration.json', 'load-result.json', 'load-process.json', 'load.log',
             'prepared-snapshot.bin', 'mixed-source-classpath-verification.json']
    names += ['failure.json', 'receipt.json'] if configuration_only else ['result.json']
    for name in names: hashes[name] = sha(directory / name)
    return {'schemaVersion': 2, 'passed': True, 'verifier': 'cpu-mixed-source-client-driver-v1',
        'nodeRevision': NODE_REVISION, 'loadRevision': LOAD_REVISION, 'nodeVerifierSha256': NODE_VERIFIER_SHA256,
        'nodeVerifierSourceUnchanged': True, 'legacyMainInvoked': False, 'legacyFunctionsReplaced': False,
        'recordedArgumentsVerified': True, 'loadGeneratorArgumentsVerified': True, 'preparedSnapshotDigestVerified': True,
        'configurationOnly': configuration_only, 'businessCorrectnessVerified': False,
        'actualMeasuredDriverObservation': observation, 'classpathVerified': classpath, 'rawSha256': hashes,
        'scope': 'Independent mixed-source launch/runtime/startup/actual measured-owner and four-JAR before/after receipts. Original source433 node verifier functions called unchanged. Business/leader/canonical/scheduler acceptance remains separate. No hardware, wakeup, sustained-capacity or independent provider attestation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--trial', type=Path, required=True)
    parser.add_argument('--node-verifier', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(sha(args.node_verifier) == NODE_VERIFIER_SHA256, 'Original node verifier source SHA differs before import')
    spec = importlib.util.spec_from_file_location('frozen_unmodified_node_verifier', args.node_verifier)
    legacy = importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
    result = verify(read(args.plan), args.trial, legacy)
    with args.output.open('x') as output: json.dump(result, output, indent=2, allow_nan=False); output.write('\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
