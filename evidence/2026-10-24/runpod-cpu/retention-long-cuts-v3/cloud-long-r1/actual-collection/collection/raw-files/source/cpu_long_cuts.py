#!/usr/bin/env python3
"""One fixed long-cut CPU arm. Default read-only preflight; no retries, prior-arm gates or new resources."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from idle_attestation import validate_idle_artifacts
from shutdown_warning import classify as classify_node_log
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
BASE_SHA = '8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87'
HOST = 'ed6c0673f5cb'
ROOT = Path('/opt/vectormatch-cpu')
PREP = ROOT / 'preparation/cpu-long-cuts-cloud-r1'
ARM = 1
JOB = PREP / 'arm-1'
PAIR = JOB / 'idle-arm'
FROZEN_RELEASE_SHA = None
WINDOWS = [8]
MAXIMUM_PARK_NS = 100000
PROPERTY = 'vectormatch.retention.idleMaxParkNs'
SOURCE_COMMIT = 'bcf49c10b77a14708b53d3fc6c115a6a3b834408'
LOG_CLASSIFIER_SHA = 'bb8725c5bc560cc9a72c80a5c5d445373edbd0da91f2cccf41eb3550569319a9'
PREREQUISITE_PINS = {
    'longRawAudit': {'bytes': 3138, 'sha256': 'd62912c9eccad0f6b070658d39626b587c5c017543f456ed9043ac710c5da21b'},
    'longRawParserFreeze': {'bytes': 4465, 'sha256': '1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3'},
    'linuxMetadataObservation': {'bytes': 5151, 'sha256': '78bb2a6a46acfadde6888184caf507da934c2d22b1a532116c7d94a488795c27'},
    'linuxMetadataReceipt': {'bytes': 4901, 'sha256': 'f136046368c57d2998b50854e2b46e5dba3ebfbc639b66ef7cd87476d5824b5f'},
}
FIXED_PORTS = 42000

def configure_arm(number):
    global ARM, JOB, PAIR
    require(type(number) is int and number == 1, 'Only the one pre-registered long-cut arm1 is supported')
    ARM = number
    JOB = PREP / ('arm-' + str(number))
    PAIR = JOB / 'idle-arm'
MAIN = 'io.vectormatch.cluster.RetentionCapacityAeronPilotV3'
NODE = 'io.vectormatch.cluster.RetentionNodeMainV3'
GIB = 1024**3
MAX_LOG = 4 * 1024**2
MAX_ARCHIVE = 256 * 1024**2
MAX_PATHS = 8192
MAX_LOGICAL = 12 * GIB
EXECUTE_SECONDS = 240
TOTAL_SECONDS = 360
METRIC_SAMPLE_CAP = 512
METRIC_BYTES_CAP = 8 * 1024**2


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def load_base():
    path = HERE / 'owned_linux_base_8eeb.py'
    require(digest(path) == BASE_SHA, 'Exact reviewed Linux ownership source differs')
    spec = importlib.util.spec_from_file_location('capacity_owned_linux_8eeb', str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hex_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


RELEASE_KEYS = {'profileFingerprint', 'javaExecutableSha256', 'java', 'configuration', 'releaseReady', 'jdkReleaseSha256', 'schemaVersion', 'status', 'nodeClassPath', 'arms', 'controllerSha256', 'evidenceReferences', 'classPath', 'artifacts', 'codeFingerprint', 'host', 'requiredEvidenceBeforeRootFreezes', 'parentJvmArguments', 'sourceCommit', 'protectedOriginalState', 'derivedPlan', 'profileId', 'logClassification'}
PLAN_KEYS = {'requestedReadWindow', 'maxReadOnlyInFlight', 'commonReadWindowEnvelope', 'readOnlyStagingBytes', 'readOnlyFailureTraceReserveBytes', 'eventFetchCount', 'witness', 'archiveChunkBytes', 'maximumEncodedChunkReplyBytes', 'maximumWriterPayloadBytes', 'maximumEventFetchRpcs', 'maximumArchiveChunkRpcs', 'selectedMaximumArchiveChunkRpcs', 'noRetryRawTraceBytes', 'maximumBusinessFrames', 'batchCap', 'largestReplyBytes', 'commonChunkEnvelope', 'maximumArchivePayloadBytes', 'maximumSupportedArchiveChunkBytes', 'maximumLogicalMaintenanceRpcs', 'maximumPhysicalOffersPerRpc', 'maximumAllocatedGrowthBytes', 'maximumWriterPayloadFiles', 'nativeAllocatedReserveBytes', 'scope', 'maximumJournalRecords', 'arrivals', 'admitted', 'maximumEventPayloadBytes', 'maximumWriterFilesIncludingReceipts', 'archiveHeaderBytes', 'admissionRejections', 'maximumEvents', 'egressAttestationTraceReserveBytes', 'maximumArchiveEntryBytes', 'maximumNegativeOfferAttempts', 'maximumRawTraceBytes', 'worstFourOfferRawTraceBytes', 'selectedMaximumLogicalMaintenanceRpcs', 'minimumFreeRuntimeBytes', 'maximumExtraPositiveOffers', 'maximumJournalBytes', 'maximumMaintenanceCycles'}

def selected_park_ns():
    return MAXIMUM_PARK_NS


def selection(maximum=None):
    return {'schema': 'retention-idle-selection-v1', 'property': PROPERTY,
            'maximumParkNs': selected_park_ns() if maximum is None else maximum,
            'factor': 'maximum requested park only'}


def fixed_configuration():
    return {'arrivals': 33792, 'ratePerSecond': 500, 'batchCap': 4,
            'archiveChunkBytes': 6144, 'readWindow': 8, 'maximumRequestedParkNs': MAXIMUM_PARK_NS,
            'workloadPreset': 'long-cuts-33792-v1', 'exposureNs': 67584000000,
            'fullCommandCuts': 11, 'trailingCommands': 3, 'equivalentFullLoadCutNumbers': list(range(2,12)),
            'eventFetchCount': 16, 'appointedLeader': 0, 'sync': 2,
            'workers': 128, 'queuePerWorker': 64, 'preparedArchiveCache': True,
            'fixedPortsNoFallback': True, 'fixedBasePorts': FIXED_PORTS,
            'commonChunkEnvelope': False, 'commonReadWindowEnvelope': True, 'mtu': 1248,
            'ownerLoopMaximumParkNsUnchanged': 1000000}


def log_policy():
    return {'schema': 'terminal-follower-eos-after-final-checkpoint-v1',
            'classifierSha256': LOG_CLASSIFIER_SHA, 'maximumPairsPerFollower': 1,
            'allowedFollowerMembers': [1, 2], 'maximumPairsPerArm': 2,
            'phaseProof': 'node-log-order-only', 'afterSigtermWallTimeProven': False,
            'eventCanInitiateElection': True, 'originalFailedGatesRetained': True}


def validate_release(release):
    require(isinstance(release, dict) and set(release) in [RELEASE_KEYS, RELEASE_KEYS | {'rootReview'}], 'Unknown or missing frozen release key')
    require(release.get('schemaVersion') == 2 and release.get('releaseReady') is True,
            'Release is an unfrozen draft; code/profile/artifact manifest required')
    require(release['host'] == HOST and release['arms'] == {str(n): {
        'job': str(PREP / ('arm-' + str(n))),
        'armRoot': str(PREP / ('arm-' + str(n)) / 'idle-arm'),
        'maximumParkNs': MAXIMUM_PARK_NS} for n in [1]},
        'Fixed host/one long-cut arm root differs')
    require(release['sourceCommit'] == SOURCE_COMMIT, 'Exact reviewed long-cut feature commit required')
    for field in ['codeFingerprint', 'profileFingerprint', 'javaExecutableSha256', 'jdkReleaseSha256', 'controllerSha256']:
        require(hex_digest(release[field]), 'Actual frozen SHA required: ' + field)
    require(release['logClassification'] == log_policy(), 'Exact reviewed warning predicate/scope required')
    require(release['configuration'] == fixed_configuration(), 'Fixed idle pilot configuration differs')
    require(release['java'] == '/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java', 'Actual canonical Java path differs')
    require(release['profileId'] == 'finite-batch-load-v3-v1' and release['profileFingerprint'] == '732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68', 'Exact unchanged finite profile required')
    require(isinstance(release['classPath'], list) and len(release['classPath']) == 4
            and len(set(release['classPath'])) == len(release['classPath']), 'Exact class-path closure required')
    require(isinstance(release['nodeClassPath'], list) and len(release['nodeClassPath']) in [3, 4]
            and len(set(release['nodeClassPath'])) == len(release['nodeClassPath'])
            and set(release['nodeClassPath']) <= set(release['classPath']), 'Actual class-source-derived node classpath required')
    artifact_root = PREP / 'release/lib'
    require(set(release['artifacts']) == set(release['classPath']), 'All and only loaded runtime JARs must be frozen')
    for path, row in release['artifacts'].items():
        require(set(row) == {'bytes', 'sha256'}, 'Unknown or missing artifact row key')
        require(Path(path).parent == artifact_root and Path(path).suffix == '.jar'
                and type(row['bytes']) is int and 0 < row['bytes'] <= 32 * 1024**2
                and hex_digest(row['sha256']), 'Unsafe/unfrozen artifact row')
    plan = release['derivedPlan']
    for arm in ['8']:
        require(isinstance(plan, dict) and set(plan) == PLAN_KEYS, 'Unknown or missing codec-derived plan key')
        require(plan['arrivals'] == 33792 and plan['batchCap'] == 4 and plan['archiveChunkBytes'] == 6144
                and plan['requestedReadWindow'] == int(arm) and plan['maxReadOnlyInFlight'] == 8
                and plan['commonReadWindowEnvelope'] is True and plan['commonChunkEnvelope'] is False
                and plan['eventFetchCount'] == 16 and plan['admitted'] is True
                and plan['admissionRejections'] == [] and plan['minimumFreeRuntimeBytes'] == GIB,
                'Actual admitted common read-window plan differs')
        require(plan['maximumPhysicalOffersPerRpc'] == 4 and plan['maximumBusinessFrames'] == 33792
                and plan['maximumEvents'] == 67587 and plan['maximumMaintenanceCycles'] == 12
                and plan['maximumWriterPayloadFiles'] == 24 and plan['maximumWriterFilesIncludingReceipts'] == 48
                and plan['maximumJournalRecords'] == 96 and plan['maximumJournalBytes'] == 117792
                and type(plan['selectedMaximumArchiveChunkRpcs']) is int and plan['selectedMaximumArchiveChunkRpcs'] > 0
                and plan['selectedMaximumLogicalMaintenanceRpcs'] == plan['selectedMaximumArchiveChunkRpcs'] + plan['maximumEventFetchRpcs'] + 3 * plan['maximumMaintenanceCycles']
                and plan['maximumArchiveChunkRpcs'] == plan['selectedMaximumArchiveChunkRpcs']
                and plan['maximumLogicalMaintenanceRpcs'] == plan['selectedMaximumLogicalMaintenanceRpcs'],
                'Common read-window RPC/control finite plan differs')
        require(type(plan['maximumAllocatedGrowthBytes']) is int and 0 < plan['maximumAllocatedGrowthBytes'] <= 5 * GIB // 2
                and type(plan['maximumRawTraceBytes']) is int and 0 < plan['maximumRawTraceBytes'] <= 2 * GIB,
                'Hard 2GiB raw / 2.5GiB growth cap required')
        require(type(plan['readOnlyStagingBytes']) is int and plan['readOnlyStagingBytes'] > 0
                and type(plan['readOnlyFailureTraceReserveBytes']) is int and plan['readOnlyFailureTraceReserveBytes'] > 0,
                'Shared eight-slot staging/failure-original trace reserves required')
        require(plan['maximumSupportedArchiveChunkBytes'] == 6144 and plan['maximumEncodedChunkReplyBytes'] == 6919
                and type(plan['largestReplyBytes']) is int and 6727 <= plan['largestReplyBytes'] <= 8192,
                'Actual codec-derived supported upper reply bound required')
        # Prospective codec bound may include a full 64-byte counter hash while the workload uses an empty hash.
        # It is an upper bound: no runtime reply is required to reach it.
    require(release['codeFingerprint'] == '6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8', 'Exact actual long distribution fingerprint required')
    require(plan['maximumLogicalMaintenanceRpcs'] == 7243 and plan['maximumArchiveChunkRpcs'] == 2982
            and plan['maximumEventFetchRpcs'] == 4225 and plan['maximumRawTraceBytes'] == 185514924
            and plan['maximumAllocatedGrowthBytes'] == 757122377, 'Exact actual long Plan differs')
    references = release['evidenceReferences']
    require(isinstance(references, dict) and set(references) == {'longRawAudit','longRawParserFreeze','linuxMetadataObservation','linuxMetadataReceipt','rootEvidenceReview'}, 'Long proof references are incomplete')
    for key, row in references.items():
        require(set(row) == {'path','bytes','sha256'} and row['path'] == str(PREP / ('release/proofs/' + key + '.json'))
                and type(row['bytes']) is int and 0 < row['bytes'] <= 1024**2 and hex_digest(row['sha256']), 'Actual pending prerequisite not frozen: ' + key)
        if key in PREREQUISITE_PINS:
            require({k: row[k] for k in ('bytes','sha256')} == PREREQUISITE_PINS[key], 'Exact actual qualified prerequisite differs: ' + key)
    protection = release['protectedOriginalState']
    require(set(protection) == {'manifest', 'manifestSha256'}, 'Unknown or missing protected-state key')
    require(protection['manifestSha256'] == '6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753' and Path(protection['manifest']).parent == PREP / 'release',
            'Current stopped original-state manifest required; initial clone is not an updated tail baseline')
    require(release['parentJvmArguments'] == ['--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
            '--add-opens=java.base/java.util.zip=ALL-UNNAMED', '-Xmx256m'], 'Fixed parent JVM flags differ')
    return release


def parent_argv(release):
    return [release['java'], '-D' + PROPERTY + '=' + str(selected_park_ns())] + release['parentJvmArguments'] + ['-cp', ':'.join(release['classPath']),
        MAIN, str(PAIR), 'idle-window8-long-cuts', str(FIXED_PORTS)]


def node_argv(release, cap, member, registration):
    return [release['java'], '-D' + PROPERTY + '=' + str(selected_park_ns()), '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
            '--add-opens=java.base/java.util.zip=ALL-UNNAMED', '-Xmx256m',
            '-Daeron.cluster.appointed.leader.id=0', '-cp', ':'.join(release['nodeClassPath']), NODE,
            str(member), str(PAIR), str(registration['ports']), '2',
            release['profileId'], registration['lineage'], release['profileFingerprint'],
            release['codeFingerprint'], 'bounded-maintenance-v1']


def validate_registration(release, cap, registration):
    require(registration['arrivals'] == 33792 and registration['rate'] == 500
            and registration['batchCap'] == 4 and registration['archiveChunkBytes'] == 6144 and registration['readWindow'] == cap
            and registration['eventFetchCount'] == 16 and registration['commonChunkEnvelope'] is False and registration['commonReadWindowEnvelope'] is True and registration['appointedLeader'] == 0
            and registration['sync'] == 2 and registration['profileSha256'] == release['profileFingerprint']
            and registration['codeSha256'] == release['codeFingerprint'], 'Actual arm configuration/code/profile differs')
    require(registration.get('workloadPreset') == 'long-cuts-33792-v1' and registration.get('expectedFullCommandCuts') == 11
            and registration.get('expectedTrailingCommands') == 3 and registration.get('equivalentFullLoadCutNumbers') == list(range(2,12)), 'Long workload/cut declaration differs')
    require(registration.get('retentionIdleSelection') == selection(), 'Actual arm idle selection differs')
    require(type(registration['ports']) is int and registration['ports'] == FIXED_PORTS,
            'Observed finite loopback port range differs')
    require(isinstance(registration['lineage'], str) and registration['lineage'].startswith('capacity-pilot-')
            and 1 <= len(registration['lineage']) <= 64, 'Fresh finite arm lineage differs')


def json_bounded(base, path, maximum=1024**2):
    base.no_links(path)
    require(path.is_file() and path.stat().st_size <= maximum, 'Missing/oversized registered JSON')
    return json.loads(path.read_text())


def kernel_record_from_json(base, row, expected_args):
    arguments = [row['command']] + row['arguments']
    require(arguments == expected_args and row['linuxCommandSha256'] == base.argv_digest(arguments),
            'Java node JSON full argv/SHA differs')
    require(type(row['pid']) is int and row['pid'] > 1
            and type(row['linuxStartTicks']) is int and row['linuxStartTicks'] > 0, 'Linux process identity missing')
    return {'pid': row['pid'], 'startTicks': row['linuxStartTicks'],
            'commandSha256': row['linuxCommandSha256'], 'arguments': arguments}


class Registry:
    """Persist every ownership observation before validation or any signal; retain exited identities too."""
    def __init__(self, base, release, job):
        self.base, self.release, self.job = base, release, Path(job)
        self.records, self.registrations, self.events = {}, {}, 0

    def observe(self, identity, role, origin):
        known = self.records.get((identity['pid'], identity['startTicks']))
        if known is not None and known['identity'] == identity:
            return
        self.base.save(self.job / ('identity-observation-%03d.json' % self.events),
                       {'role': role, 'origin': origin, 'kernelIdentity': identity, 'atUtc': self.base.now()})
        self.events += 1

    def record(self, identity, role, origin):
        key = (identity['pid'], identity['startTicks'])
        if key not in self.records:
            self.observe(identity, role, origin)
            self.records[key] = {'role': role, 'identity': identity}
        require(self.records[key]['identity'] == identity and self.records[key]['role'] == role,
                'Previously registered kernel identity or role differs')

    def discover(self):
        for cap in WINDOWS:
            arm = PAIR
            path = arm / 'registration.json'
            if not path.exists():
                continue
            registration = json_bounded(self.base, path)
            validate_registration(self.release, cap, registration)
            if cap in self.registrations:
                require(registration == self.registrations[cap], 'Arm registration mutated')
            else:
                self.base.save(self.job / ('window-%d-configuration-observed.json' % cap), {
                    'registration': registration, 'atUtc': self.base.now(),
                    'candidateLoopbackUdpPortsFromFrozenNodeArguments': [registration['ports'] + member * 100 + offset
                        for member in range(3) for offset in range(1, 6)],
                    'candidateAddress': '127.0.0.1', 'freshBindAfterNodeLaunchAttempted': False,
                    'independentPreLaunchPortAvailabilityProven': False,
                    'scope': 'Frozen Java ports() binds all 15 before registration, then releases; this observer verifies configured arguments without rebinding active sockets'})
            self.registrations[cap] = registration
            for member in range(3):
                identity_path = arm / ('node-%d-identity.json' % member)
                expected = node_argv(self.release, cap, member, registration)
                if identity_path.exists():
                    row = json_bounded(self.base, identity_path)
                    claimed = kernel_record_from_json(self.base, row, expected)
                    actual = self.base.process_identity(claimed['pid'])
                    # Persist the independent actual identity, including mismatches, before refusing it.
                    if actual is not None:
                        self.observe(actual, 'window-%d-node-%d' % (cap, member), 'independent-proc-observation-unvalidated')
                        require(actual == claimed, 'Live node JSON/kernel PID/startTicks/argv differs; no signal')
                        self.record(actual, 'window-%d-node-%d' % (cap, member), 'independent-proc-observation-validated')
                    else:
                        self.record(claimed, 'window-%d-node-%d' % (cap, member), 'json-kernel-record-process-already-exited')
        # Independently recover nodes launched before Java writes node identity JSON.
        for folder in self.base.PROC.iterdir():
            if not folder.name.isdigit():
                continue
            actual = self.base.process_identity(int(folder.name))
            if actual is None or NODE not in actual['arguments']:
                continue
            args = actual['arguments']
            if not any(str(PAIR) in args for c in WINDOWS):
                continue
            # An unmatched observation is evidence only and must never enter the signal registry.
            self.observe(actual, 'candidate-node', 'fresh-root-proc-observation-unvalidated')
            matched = []
            for cap, registration in self.registrations.items():
                for member in range(3):
                    if args == node_argv(self.release, cap, member, registration):
                        matched.append('window-%d-node-%d' % (cap, member))
            require(len(matched) == 1, 'Fresh-root node argv does not match one registered exact template; no signal')
            self.record(actual, matched[0], 'proc-scan-missing-json-window')
        return list(self.records.values())


def owned_metrics(base, row):
    identity = row['identity']
    result = {'role': row['role'], 'pid': identity['pid'], 'startTicks': identity['startTicks'],
              'commandSha256': identity['commandSha256'], 'available': False}
    try:
        if base.matching_identity(identity) is None:
            return dict(result, processExited=True, reason='Registered exact process no longer alive')
        folder = base.PROC / str(identity['pid'])
        raw = (folder / 'stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        require(len(fields) > 21 and int(fields[19]) == identity['startTicks'], 'Metrics Linux startTicks differs')
        result.update(userTicks=int(fields[11]), systemTicks=int(fields[12]), rssPages=int(fields[21]))
        result['rssBytesFromStat'] = result['rssPages'] * os.sysconf('SC_PAGE_SIZE')
        status = {}
        for line in (folder / 'status').read_text().splitlines():
            name, _, value = line.partition(':')
            if name in ['VmRSS', 'RssAnon', 'RssFile', 'VmSwap']:
                parts = value.split(); require(len(parts) == 2 and parts[1] == 'kB', 'Metric status unit differs')
                status[name + 'Bytes'] = int(parts[0]) * 1024
            elif name == 'Threads':
                status[name] = int(value.strip())
        result['status'] = status
        io = {}
        for line in (folder / 'io').read_text().splitlines():
            name, _, value = line.partition(':')
            if name in ['read_bytes', 'write_bytes', 'syscr', 'syscw']:
                io[name] = int(value.strip())
        require(set(io) == {'read_bytes', 'write_bytes', 'syscr', 'syscw'}, 'Owned IO metric closure unavailable')
        result['io'] = io
        require(base.matching_identity(identity) is not None, 'Exact process exited during metric capture')
        result['available'] = True
    except Exception as error:
        if isinstance(error, InterruptedError):
            raise
        # Partial raw counters remain visible but never masquerade as a complete/reliable sample.
        result['reason'] = repr(error)[:512]
        result['partialCountersMayBePresent'] = True
    return result


def global_metrics(base):
    out = {'available': False}
    try:
        values = {}
        for line in (base.PROC / 'stat').read_text().splitlines():
            fields = line.split()
            if fields and fields[0] == 'cpu':
                values['aggregateCpuTicks'] = [int(v) for v in fields[1:]]
            elif fields and fields[0] in ['ctxt', 'processes', 'procs_running', 'procs_blocked']:
                values[fields[0]] = int(fields[1])
        require('aggregateCpuTicks' in values, 'Global aggregate CPU counters unavailable')
        out.update(values); out['available'] = True
    except Exception as error:
        if isinstance(error, InterruptedError):
            raise
        out['reason'] = repr(error)[:512]
    return out


class Telemetry:
    """1 Hz sampled counters, bounded raw JSONL. Flush only during load; fsync once after closure."""
    def __init__(self, base, job, started):
        self.base, self.started = base, started
        self.path = Path(job) / 'owned-cpu-rss-io-1hz.jsonl'
        self.stream = self.path.open('xb')
        self.samples, self.bytes, self.failures, self.next = 0, 0, 0, 0.0

    def sample(self, registry, phase='execution', force=False):
        instant = time.monotonic()
        if not force and instant < self.next:
            return
        require(self.samples < METRIC_SAMPLE_CAP, 'Finite 512 telemetry sample cap reached')
        owned = [owned_metrics(self.base, row) for row in registry.records.values()]
        self.failures += sum(not row['available'] for row in owned)
        active = sorted({int(row['role'].split('-')[1]) for row in owned
                         if row['role'].startswith('window-') and row['available']})
        value = {'sample': self.samples, 'atUtc': self.base.now(), 'monotonicNs': time.monotonic_ns(),
            'elapsedSeconds': instant - self.started, 'phase': phase, 'samplePeriodSeconds': 1,
            'clock': 'Linux system monotonic clock; compare with Java nanoTime only after host clock validation',
            'clockTicksPerSecond': os.sysconf('SC_CLK_TCK'), 'pageSizeBytes': os.sysconf('SC_PAGE_SIZE'),
            'registeredArms': sorted(registry.registrations), 'activeArmsFromSuccessfulMetricSamples': active,
            'armLineages': {str(c): row['lineage'] for c, row in registry.registrations.items()},
            'global': global_metrics(self.base), 'owned': owned,
            'scope': 'Sampled CPU/RSS/kernel IO counters, not pure fsync or independent-storage latency'}
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
        require(self.bytes + len(raw) <= METRIC_BYTES_CAP, 'Finite 8MiB telemetry byte cap reached')
        self.stream.write(raw); self.stream.flush()
        self.samples += 1; self.bytes += len(raw); self.next = instant + 1.0

    def close(self, all_owned_stopped):
        self.stream.flush()
        if all_owned_stopped:
            os.fsync(self.stream.fileno())
        self.stream.close()
        return {'path': str(self.path), 'samples': self.samples, 'bytes': self.bytes, 'sha256': digest(self.path),
            'metricUnavailableOrExitedSamples': self.failures, 'maximumSamples': METRIC_SAMPLE_CAP,
            'maximumBytes': METRIC_BYTES_CAP, 'fsyncDuringLoad': False,
            'afterClosureFsyncOnly': bool(all_owned_stopped), 'fsyncSkippedBecauseOwnedStopUnconfirmed': not all_owned_stopped,
            'sampleFailureValuesInvented': False}


def protected_state(base, release):
    row = release['protectedOriginalState']
    path = Path(row['manifest'])
    base.no_links(path)
    require(digest(path) == row['manifestSha256'], 'Current original-state manifest differs')
    manifest = json_bounded(base, path, 4 * 1024**2)
    require(manifest['scope'] == 'CURRENT_STOPPED_ORIGINAL_RESTORATION' and len(manifest['nativeTrees']) == 3,
            'Explicit current three-native-tree plus PG baseline required')
    expected_roots = {str(ROOT / ('restorations/original-native-r1/node%d/runtime/cloud-20261023-01/node-%d' % (n, n)))
                      for n in range(3)}
    require({tree['root'] for tree in manifest['nativeTrees']} == expected_roots,
            'Exactly the three original native roots must be protected')
    require(manifest['postgres']['pgData'] == str(ROOT / 'restorations/original-native-r1/node2/runtime/postgres18'),
            'Exactly original stopped PGDATA must be protected')
    output = []
    for tree in manifest['nativeTrees']:
        root = Path(tree['root'])
        require(str(root).startswith(str(ROOT / 'restorations/original-native-r1') + '/'), 'Protected tree outside original restoration')
        actual = base.scan(root, True)
        # Ignore atime/mtime/allocation; bytes, closure, owners and modes are exact.
        require(set(actual['files']) == set(tree['files']) and actual['directories'] == tree['directories'],
                'Protected original native file/directory closure/owner/mode differs')
        for name, expected in tree['files'].items():
            require(all(actual['files'][name][k] == expected[k] for k in ['bytes', 'sha256', 'mode', 'uid', 'gid']),
                    'Protected original native bytes/owner/mode differs')
        output.append({'root': str(root), 'files': len(actual['files']), 'logicalBytes': actual['logicalBytes']})
    require(sum(len(tree['files']) for tree in manifest['nativeTrees']) == 57, 'Current original native57-file baseline required')
    pg = base.verify_pg(manifest['postgres'])
    require(pg['files'] == 989, 'Current stopped PG989-file baseline required')
    return {'passed': True, 'nativeTrees': output, 'postgres': pg, 'manifestSha256': row['manifestSha256']}


def allocated_scan(base, path):
    """Active inventory records metadata only; full hashes/archive are forbidden while any child lives."""
    files, allocated, logical = 0, Path(path).lstat().st_blocks * 512, 0
    for root, directories, names in os.walk(str(path), followlinks=False):
        for name in directories + names:
            child = Path(root) / name
            base.no_links(child)
            st = child.lstat()
            require(st.st_nlink == 1 or child.is_dir(), 'Owned hardlink refused')
            require(child.is_dir() or child.is_file(), 'Owned special file refused')
            require(child.is_dir() or st.st_size <= 512 * 1024**2, 'Owned individual file cap')
            files += 1
            allocated += st.st_blocks * 512
            require(files <= MAX_PATHS, 'Owned path-count cap')
            if child.is_file():
                logical += st.st_size
                require(logical <= MAX_LOGICAL, 'Owned 12GiB logical-byte cap')
                if child.suffix == '.log':
                    require(st.st_size <= MAX_LOG, 'Owned log cap')
    return {'paths': files, 'allocatedBytes': allocated, 'logicalBytes': logical}


def allocation_limit(release):
    return release['derivedPlan']['maximumAllocatedGrowthBytes'] + 16 * 1024**2


def strict_idle(base, allowed=()):
    """A different Java VM also invalidates this controlled existing-host pilot."""
    permitted = {row['pid']: row for row in allowed}
    foreign = []
    for folder in base.PROC.iterdir():
        if not folder.name.isdigit() or int(folder.name) == os.getpid():
            continue
        observed = base.process_identity(int(folder.name))
        if observed is None or not observed['arguments']:
            continue
        executable = Path(observed['arguments'][0]).name
        if executable not in ['java', 'javaw', 'postgres', 'postmaster']:
            continue
        if observed['pid'] in permitted:
            base.matching_identity(permitted[observed['pid']])
        else:
            foreign.append({k: observed[k] for k in ['pid', 'startTicks', 'commandSha256']})
    require(not foreign, 'Unowned Java VM or Postgres active: ' + json.dumps(foreign))
    return {'noUnownedJavaVmOrPostgres': True, 'freshProcObservation': True, 'globalLockClaimed': False}


def verify_archive_members(archive, inventory, prefix='idle-arm'):
    """Full SHA/bytes/mode/owners/empty-dir readback; streaming, no multi-GiB extraction."""
    archive = Path(archive)
    require(not any(p.is_symlink() for p in [archive] + list(archive.parents)), 'Closed archive symlink path refused')
    require(archive.is_file() and archive.stat().st_nlink == 1 and archive.stat().st_size <= MAX_ARCHIVE, 'Closed archive compressed byte/type/link cap')
    require(len(inventory['files']) + len(inventory['directories']) <= MAX_PATHS
            and sum(r['bytes'] for r in inventory['files'].values()) == inventory['logicalBytes']
            and inventory['logicalBytes'] <= MAX_LOGICAL, 'Closed archive finite inventory bounds differ')
    files, directories = set(), set()
    with tarfile.open(str(archive), mode='r|gz') as stream:
        for member in stream:
            name = member.name
            require(name == prefix or name.startswith(prefix + '/'), 'Archive member outside exact owned prefix')
            relative = '.' if name == prefix else name[len(prefix) + 1:]
            require(relative == '.' or (not Path(relative).is_absolute() and '..' not in Path(relative).parts), 'Archive path traversal')
            require(member.isdir() or member.isfile(), 'Archive link/special member refused')
            expected = inventory['directories' if member.isdir() else 'files'].get(relative)
            require(expected is not None, 'Unexpected archive member')
            seen = directories if member.isdir() else files
            require(relative not in seen, 'Duplicate archive member')
            seen.add(relative)
            require(all(getattr(member, key) == expected[key] for key in ['mode', 'uid', 'gid']), 'Archive mode/owner differs')
            if member.isfile():
                require(member.size == expected['bytes'] and member.size <= 512 * 1024**2, 'Archive logical size differs')
                payload = stream.extractfile(member)
                require(payload is not None, 'Missing archive regular payload')
                h, size = hashlib.sha256(), 0
                for chunk in iter(lambda: payload.read(1024**2), b''):
                    size += len(chunk)
                    require(size <= expected['bytes'], 'Archive payload overflow')
                    h.update(chunk)
                require(size == expected['bytes'] and h.hexdigest() == expected['sha256'], 'Archive payload SHA/size differs')
    require(files == set(inventory['files']) and directories == set(inventory['directories']), 'Archive file/directory/empty-dir closure differs')
    return {'passed': True, 'files': len(files), 'directories': len(directories),
            'logicalBytes': inventory['logicalBytes'], 'noExtraction': True,
            'scope': 'Same-host full logical readback; independent local collection is a separate gate'}






def validate_linux_metadata(observation, receipt, release):
    """Actual metadata process/class/Plan binding; no observation gap or assumed canonical executable."""
    root = '/opt/vectormatch-cpu/preparation/cpu-long-cuts-release-metadata-r1'
    require(observation['noDriverOrClusterStarted'] is True
            and observation['actualCodeFingerprint'] == release['codeFingerprint']
            and observation['profileSha256'] == release['profileFingerprint'], 'Actual Linux metadata code/profile/scope differs')
    workload = observation['workloads']['LONG_CUTS']
    require(workload['arrivals'] == 33792 and workload['rate'] == 500 and workload['windowNs'] == 67584000000
            and workload['fullCommandCuts'] == 11 and workload['trailingCommands'] == 3 and workload['cycles'] == 12
            and workload['plan'] == release['derivedPlan'], 'Actual Linux long workload/Plan differs')
    registration, execution = receipt['registration'], receipt['execution']
    expected_command = [release['java'], '-Xmx128m', '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
        '-cp', root + '/classes:' + ':'.join(root + '/lib/' + Path(p).name for p in release['classPath']),
        'io.vectormatch.cluster.LongCutsDistributionObservation', root + '/results/actual-distribution-observation.json']
    identity = execution.get('actualProcessIdentity')
    require(receipt['passed'] is True and receipt['root'] == root
            and receipt['observationSha256'] == release['evidenceReferences']['linuxMetadataObservation']['sha256']
            and registration['hostname'] == HOST and registration['command'] == expected_command
            and registration['javaExecutable'] == registration['actualJavaExecutable'] == release['java']
            and registration['javaExecutableSha256'] == execution['javaExecutableSha256After'] == release['javaExecutableSha256']
            and registration['jdkReleaseSha256'] == execution['jdkReleaseSha256After'] == release['jdkReleaseSha256'],
            'Actual Linux metadata canonical host/argv/executable/JDK differs')
    require(execution.get('processIdentityObservationGap') is False and isinstance(identity, dict)
            and type(identity.get('pid')) is int and identity['pid'] > 1
            and type(identity.get('startTicks')) is int and identity['startTicks'] > 0
            and execution['ownedParentPid'] == identity['pid']
            and identity.get('actualExecutable') == release['java']
            and identity.get('commandSha256') == hashlib.sha256(b'\0'.join(os.fsencode(a) for a in expected_command) + b'\0').hexdigest()
            and execution['exitCode'] == 0 and execution['timedOut'] is False
            and execution['metadataJvmExited'] is True and execution['allInputsUnchanged'] is True,
            'Actual Linux metadata PID/start/argv observation gap, input drift or non-exit')
    rows = receipt['stagedFiles']
    require(rows == registration['inputInventory'] and len(rows) == 6, 'Exact six metadata inputs required')
    require(set(rows) == {'lib/' + Path(p).name for p in release['classPath']} | {
        'LongCutsDistributionObservation.java', 'classes/io/vectormatch/cluster/LongCutsDistributionObservation.class'},
        'Actual metadata input closure differs')
    for path, frozen in release['artifacts'].items():
        actual = rows['lib/' + Path(path).name]
        require(actual['bytes'] == frozen['bytes'] and actual['sha256'] == frozen['sha256'] and actual['mode'] == 0o644,
                'Actual Linux metadata JAR differs')
    require(rows['LongCutsDistributionObservation.java']['sha256'] == 'ed07ec998dabcdd8d22b51ea8745766ae2c788cc84a407d1118276a83b090d78'
            and rows['classes/io/vectormatch/cluster/LongCutsDistributionObservation.class']['sha256'] == '308eb3eb86dd79977fcd92da3a6fb11ec2c2771829a226a93705199f1c603433',
            'Actual Linux Java metadata helper source/class differs')
    bindings = {'io.vectormatch.cluster.RetentionCapacityAeronPilotV3': 'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.cluster.RetentionNodeMainV3': 'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.core.MatchingEngine': 'core-0.1.0-SNAPSHOT.jar',
        'io.aeron.driver.MediaDriver': 'aeron-all-1.53.3.jar', 'org.agrona.DirectBuffer': 'aeron-all-1.53.3.jar'}
    actual = observation['actualCodeSources']
    require(len(actual) == len(bindings) and {r['class'] for r in actual} == set(bindings), 'Actual Linux class-source set differs')
    for row in actual:
        name = bindings[row['class']];frozen = release['artifacts'][str(PREP / 'release/lib' / name)]
        require(row['path'] == root + '/lib/' + name and row['bytes'] == frozen['bytes'] and row['sha256'] == frozen['sha256'],
                'Actual Linux loaded class/JAR binding differs')
    return True


def validate_prerequisite_proofs(values, release):
    """Pure semantic gate shared with stage; caller first verifies each original file's SHA/bytes."""
    require(set(values) == set(release['evidenceReferences']), 'Prerequisite proof value closure differs')
    validate_linux_metadata(values['linuxMetadataObservation'], values['linuxMetadataReceipt'], release)
    audit, parser, review = values['longRawAudit'], values['longRawParserFreeze'], values['rootEvidenceReview']
    require(audit['schemaVersion'] == 1 and audit['scope'] == 'QUALIFIED_LOCAL_LONG_NATIVE_AUDIT_FUNCTIONAL_ONLY'
            and audit['readOnlyAuditPassed'] is True and audit['sourceCommit'] == release['sourceCommit']
            and audit['actualCodeFingerprint'] == release['codeFingerprint'] and audit['profileFingerprint'] == release['profileFingerprint'],
            'Qualified local long audit scope/source/code/profile differs')
    require(audit['workload'] == {'arrivals':33792,'ratePerSecond':500,'windowSeconds':67.584,'batchCap':4,
            'archiveChunkBytes':6144,'eventFetchCount':16,'readWindow':8,'logicalWorkers':128,'taskQueueCapacityPerWorker':64}
            and audit['cycles'] == 12 and audit['readPhases'] == 24 and audit['equivalentFullLoadCuts'] == 10
            and audit['confirmedAcceptedUniqueOrders'] == 33792 and audit['notSent'] == audit['unknownObserved'] == audit['unknownFinal'] == audit['serverRejected'] == 0,
            'Qualified local long audit workload/outcome/phase counts differ')
    require(audit['schedulerTimingValid'] is False and audit['schedulerLatenessOver20ms'] == 26
            and audit['localFunctionalOnly'] is True and audit['noCapacityClaim'] is True
            and audit['futureCpuSchedulerGateDefaultStrict'] is True
            and audit['actualIdleFactoryCreations'] == 22 and audit['warnings'] == 0
            and audit['allConsumedInputsManifestBoundAndRehashed'] is True and audit['consumedInputFiles'] == 80
            and audit['originalOwnedStopReceiptsVerified'] is True and audit['liveProcessProbePerformed'] is False
            and audit['setupPositionHashIndependentlyReconstructed'] is False
            and audit['setupBusinessReplyHashesIntentionallyEmpty'] is True and audit['sameCandidateReferenceIsNotIndependentAlgorithm'] is True,
            'Local diagnostic qualification must remain timing-invalid/functional-only; no CPU timing bypass')
    require(audit['fullArchiveReadback'] == {'passed':True,'entries':191,'files':159,'directories':32,'logicalBytes':1334578086,
            'sha256':'b73ad6c3333007f6938eb6989ab528461d83b17b6d3ab0170d6d805e5c56cc3b',
            'modeOwnerEmptyDirectoryClosureVerified':True,'sparseExtractionPerformed':False}
            and audit['manifestSha256'] == 'b6239c05b7949f844971f2b1dd6e416ba2ce80769eff245623ad4405bacacea7'
            and audit['fullResult']['bytes'] == 1701830 and audit['fullResult']['sha256'] == '68d3cda87612b9c7369c20558f474b75b6c77b890fc32d1a2cdbdb223824161a',
            'Actual full local archive/result closure differs; full result stays outside bounded release JSON')
    require({k:audit['parserFreeze'][k] for k in ('bytes','sha256')} == PREREQUISITE_PINS['longRawParserFreeze']
            == {k:release['evidenceReferences']['longRawParserFreeze'][k] for k in ('bytes','sha256')}, 'Audit/parser freeze cross-binding differs')
    require(parser['schemaVersion'] == 1 and parser['sourceCommitUnderAudit'] == release['sourceCommit']
            and parser['actualCodeFingerprintUnderAudit'] == release['codeFingerprint'] and parser['guardTests'] == 33
            and parser['baselineOriginalsAndCopiesUnchanged'] is True and parser['legacy6400DefaultAndOriginalPhaseCap8Unchanged'] is True
            and parser['defaultImportedSchedulerAdmissionStrict'] is True and parser['localFunctionalDiagnosticOptInIsExplicitRunnerOnly'] is True
            and parser['legacyCollectorCliNotReused'] is True and parser['firstFailedAuditPreserved'] is True
            and parser['rawParserEntry'] == 'source/audit_raw.py:audit_arm(selected_window,arm_override,workload=LONG,local_functional_only=False)',
            'Authoritative long parser source/strict default/failed audit preservation differs')
    require(set(parser['sourceFiles']) == {'run_audit.py','source/archive_closure.py','source/audit_raw.py','source/common.py',
            'source/idle_inventory.py','source/read_phase_audit.py','source/setup_audit.py','source/workload_contract.py',
            'tests/test_long_contract.py','tests/test_phase_baseline.py'}
            and all(type(r['bytes']) is int and r['bytes'] > 0 and hex_digest(r['sha256']) for r in parser['sourceFiles'].values()),
            'Authoritative parser source manifest closure differs')
    expected_bindings = {key:{k:row[k] for k in ('bytes','sha256')} for key,row in release['evidenceReferences'].items() if key != 'rootEvidenceReview'}
    require(review['scope'] == 'ROOT_REVIEWED_LONG_NATIVE_CLOUD_PREREQUISITES' and review['passed'] is True
            and review['sourceCommit'] == release['sourceCommit'] and review['codeFingerprint'] == release['codeFingerprint']
            and review['profileFingerprint'] == release['profileFingerprint'] and review['controllerSha256'] == release['controllerSha256']
            and review['sourceReviewSha256'] == 'a9561e676b19892a58590b16fc51b6e63962261aede70858fa0d48b0d8bd23db'
            and review['nativeReviewSha256'] == '55b3bf21ea23dca8a34bb7a1c2baaf7235cce2ddbf6ec38100fe5a0edc0dd49d'
            and review['proofBindings'] == expected_bindings and review['guardsPassed'] is True
            and review['strictCpuSchedulerRequired'] is True and review['noNewResources'] is True,
            'Root prerelease evidence review failed/scope/source/code/controller/proof binding differs')
    return True


def preflight(base, release):
    validate_release(release)
    require(digest(HERE / 'shutdown_warning.py') == LOG_CLASSIFIER_SHA, 'Actual reviewed warning classifier differs')
    require(digest(__file__) == release['controllerSha256'], 'Actual controller source differs from root-frozen release')
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64'
            and socket.gethostname() == HOST and os.geteuid() == 0, 'Exact existing CPU host/Linux/root required')
    base.no_links(PREP)
    require(PREP.is_dir() and not JOB.exists() and not PAIR.exists(), 'Atomic fresh fixed attempt required; never rerun')
    require(Path(release['java']).resolve() == Path(release['java']), 'Canonical JDK path required')
    jdk_release = Path(release['java']).parents[1] / 'release'
    require(digest(release['java']) == release['javaExecutableSha256'] and digest(jdk_release) == release['jdkReleaseSha256']
            and 'JAVA_VERSION="21.0.13"' in jdk_release.read_text(), 'Actual JDK21 executable/release differs')
    artifact_root = PREP / 'release/lib'
    require(set(str(p) for p in artifact_root.iterdir()) == set(release['artifacts']), 'Exact frozen JAR directory closure required')
    for path, row in release['artifacts'].items():
        base.no_links(path)
        require(Path(path).stat().st_size == row['bytes'] and digest(path) == row['sha256'], 'Frozen loaded artifact differs')
    prerequisite_values = {}
    for key, row in release['evidenceReferences'].items():
        path = Path(row['path']); base.no_links(path)
        require(path.is_file() and path.stat().st_size == row['bytes'] and digest(path) == row['sha256'], 'Actual root-frozen prerequisite proof differs')
        prerequisite_values[key] = json_bounded(base, path)
    validate_prerequisite_proofs(prerequisite_values, release)
    idle = strict_idle(base)
    minimum = allocation_limit(release) + GIB + MAX_ARCHIVE
    require(shutil.disk_usage(ROOT).free >= minimum, 'Initial free space below exact finite single-arm+archive+1GiB floor bound')
    require(base.memory_headroom() >= 8 * GIB, 'Initial memory headroom below 8GiB')
    return {'passed': True, 'atUtc': base.now(), 'idle': idle, 'protectedOriginal': protected_state(base, release),
            'arm': ARM, 'singleManualArmOnly': True, 'minimumInitialFreeBytes': minimum, 'maximumAllocatedGrowthBytes': allocation_limit(release),
            'controllerSha256': digest(__file__), 'baseSha256': BASE_SHA, 'noJavaStarted': True}


def monitor(base, registry, release, initial):
    records = registry.discover()
    strict_idle(base, [r['identity'] for r in records])
    require(shutil.disk_usage(ROOT).free >= GIB, 'Runtime free space below 1GiB')
    observed = allocated_scan(base, JOB)
    require(observed['allocatedBytes'] - initial <= allocation_limit(release), 'Derived single-arm owned allocation cap')
    return observed


def runtime_manifest(base, path, expected_sha):
    require(hex_digest(expected_sha), 'Explicit root-frozen release SHA required; a draft cannot select itself')
    require(Path(path).resolve() == PREP / 'release/release.json', 'One fixed frozen release path required')
    base.no_links(path)
    require(digest(path) == expected_sha, 'Root-frozen release SHA differs')
    return validate_release(json_bounded(base, path))


def clean_all(base, registry, parent, parent_args, deadline):
    errors, reports = [], []
    def stop(record, role):
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'Overall 360s stop-observation deadline expired; no forced kill')
        result = base.stop_owned(record, min(30.0, remaining))
        reports.append(dict(result, role=role))
    # Stopping and reaping the exact direct parent removes its ability to launch another child.
    try:
        if parent.poll() is None:
            identity = base.process_identity(parent.pid)
            if identity is not None:
                registry.record(identity, 'pilot-parent', 'cleanup-direct-child')
                require(identity['arguments'] == parent_args, 'Direct parent argv differs; no signal')
                stop(identity, 'pilot-parent')
        parent.wait(timeout=max(0.01, min(1.0, deadline - time.monotonic())))
    except BaseException as error:
        errors.append({'role': 'pilot-parent', 'error': repr(error)})
    # Discover once more after parent exit; never assume Java SIGTERM executes finally blocks.
    try:
        registry.discover()
    except BaseException as error:
        errors.append({'role': 'post-parent-discovery', 'error': repr(error)})
    for row in list(registry.records.values()):
        if row['role'] == 'pilot-parent':
            continue
        try:
            stop(row['identity'], row['role'])
        except BaseException as error:
            errors.append({'role': row['role'], 'error': repr(error)})
    absent = True
    for row in registry.records.values():
        try:
            require(base.matching_identity(row['identity']) is None, 'Registered process remains alive')
        except BaseException as error:
            absent = False
            errors.append({'role': row['role'], 'error': repr(error)})
    try:
        strict_idle(base)
    except BaseException as error:
        absent = False
        errors.append({'role': 'final-global-idle-observation', 'error': repr(error)})
    return {'allOwnedStopped': absent and parent.poll() is not None and not errors,
            'reports': reports, 'errors': errors, 'forcedKill': False, 'numericPidSignalFallback': False}


def validate_egress(bounds):
    require(bounds['requiredApplicationReplyBytes'] == 6919 and bounds['aeronSessionHeaderBytes'] == 32
            and bounds['requiredCompleteMessageBytes'] == 6951
            and bounds['defaultMetadataSubstituted'] is False
            and bounds['sameOwnerThreadRequired'] is True
            and type(bounds['actualImageObservations']) is int and bounds['actualImageObservations'] >= 1
            and type(bounds['replyHeaderImageAssociations']) is int and bounds['replyHeaderImageAssociations'] >= 0,
            'Actual egress envelope/source association metadata missing or changed')
    require(bounds['maximumEverObservedImages'] == 16 and bounds['maximumLifecycleEvents'] == 256, 'Bounded actual Image lifecycle policy differs')
    images = bounds['images']
    require(isinstance(images, list) and 1 <= len(images) <= 16, 'Actual bounded receiver Image list required')
    identities, associations, limits = {}, 0, []
    for row in images:
        term = row['actualTermBufferLength']
        require(type(term) is int and term >= 65536 and term & (term - 1) == 0
                and row['actualMtuLength'] == 1248, 'Actual Image term/MTU differs')
        maximum = min(term // 8, 16 * 1024**2)
        require(row['derivedMaxMessageLength'] == maximum and maximum >= 6951,
                'Complete reply plus session header exceeds actual Image-derived maximum')
        key = row['imageCorrelationId']
        require(type(key) is int and key >= 0 and key not in identities, 'Actual Image duplicate/invalid correlation')
        identities[key] = {k: row[k] for k in ['imageCorrelationId', 'publicationSessionId', 'streamId',
            'actualTermBufferLength', 'actualMtuLength', 'derivedMaxMessageLength']}
        count, largest = row['associatedApplicationReplies'], row['largestObservedApplicationReplyBytes']
        require(type(count) is int and count >= 0 and type(largest) is int
                and 0 <= largest <= 8192 and largest + 32 <= maximum,
                'Actual Header associations/reply size differs')
        associations += count
        limits.append(maximum)
    active = bounds['activeImageCorrelations']
    require(isinstance(active, list) and active and active == sorted(set(active))
            and set(active) == {r['imageCorrelationId'] for r in images if r['activeAtLastObservation'] is True}
            and all(type(r['activeAtLastObservation']) is bool for r in images), 'Actual active Image flags/set differs or empty')
    events = bounds['lifecycleEvents']
    require(isinstance(events, list) and len(events) <= 256, 'Actual bounded lifecycle events required')
    seen, event_active, previous_at = set(), set(), None
    for index, event in enumerate(events, 1):
        require(set(event) == {'sequence', 'event', 'imageCorrelationId', 'observedAtMonotonicNs', 'source'}
                and event['sequence'] == index and event['source'] == 'actual owner-thread egress subscription Image observation'
                and type(event['observedAtMonotonicNs']) is int
                and (previous_at is None or event['observedAtMonotonicNs'] >= previous_at), 'Actual Image lifecycle event identity/order/source differs')
        previous_at = event['observedAtMonotonicNs']
        correlation = event['imageCorrelationId']
        require(type(correlation) is int and correlation in identities, 'Lifecycle references an unknown actual Image')
        if event['event'] == 'ADDED':
            require(correlation not in seen, 'Retired/seen actual Image identity returned')
            seen.add(correlation); event_active.add(correlation)
        else:
            require(event['event'] == 'REMOVED' and correlation in event_active, 'Inactive/unknown Image retirement')
            event_active = event_active - {correlation}
    require(seen == set(identities) and event_active == set(active), 'Actual ever-seen/active lifecycle closure differs')
    require(associations == bounds['replyHeaderImageAssociations']
            and min(limits) == bounds['minimumActualDerivedMaxMessageLength'], 'Actual Image aggregate counters differ')
    return identities


def validate_egress_progress(previous, current):
    """Active sets may change; immutable ever-seen geometry/events/counters cannot be rewritten."""
    old, new = validate_egress(previous), validate_egress(current)
    require(all(key in new and new[key] == row for key, row in old.items()),
            'Actual ever-seen Image geometry changed or historical identity disappeared')
    require(current['lifecycleEvents'][:len(previous['lifecycleEvents'])] == previous['lifecycleEvents']
            and current['actualImageObservations'] >= previous['actualImageObservations']
            and current['replyHeaderImageAssociations'] >= previous['replyHeaderImageAssociations'],
            'Actual Image lifecycle prefix/observation/reply counters regressed')
    old_rows = {row['imageCorrelationId']: row for row in previous['images']}
    for row in current['images']:
        prior = old_rows.get(row['imageCorrelationId'])
        require(prior is None or (row['associatedApplicationReplies'] >= prior['associatedApplicationReplies']
                and row['largestObservedApplicationReplyBytes'] >= prior['largestObservedApplicationReplyBytes']),
                'Historical actual Image reply association counters regressed')
    return new


def validate_long_summary(summary, cap):
    require(summary['scheduledArrivals'] == 33792 and summary['releasedArrivals'] == 33792
            and summary['ratePerSecond'] == 500 and summary['batchCap'] == 4 and summary['archiveChunkBytes'] == 6144 and summary['readWindow'] == cap
            and summary['arrivalClockPausedForMaintenance'] is False
            and summary['unknownFinal'] == 0 and summary['unknownObserved'] == 0 and summary['maintenanceCycles'] == 12
            and summary['schedulerTimingValid'] is True and summary['schedulerLatenessOver20ms'] == 0
            and summary['confirmedAcceptedUniqueOrders'] == 33792 and summary['notSent'] == 0
            and summary['serverRejected'] == 0 and summary['duplicateOrOutOfRangeAcceptedOrderIds'] == 0
            and summary['completedLogicalReplies'] == 33792,
            'Long source must close all original orders/12cycles with strict actual scheduler; diagnostic timing bypass forbidden')
    return True


def validate_result(base, registry, release):
    registry.discover()
    require(set(registry.registrations) == {8}, 'One actual long-cut arm registration required')
    require(len(registry.records) == 4 and {r['role'] for r in registry.records.values()} == {'pilot-parent'} |
            {'window-%d-node-%d' % (c, n) for c in WINDOWS for n in range(3)}, 'Three node identities plus parent required')
    result = json_bounded(base, PAIR / 'completion.json')
    require(result['passed'] is True and result['archiveChunkBytes'] == 6144 and result['readWindow'] == 8 and result['retentionIdleSelection'] == selection(), 'Single idle arm did not complete')
    arms = []
    for cap in WINDOWS:
        root = PAIR
        completion = json_bounded(base, root / 'completion.json')
        stop = json_bounded(base, root / 'owned-stop.json')
        functional = json_bounded(base, root / 'functional-result.json')
        artifact_inventory = json_bounded(base, root / 'artifact-inventory.json')
        require(artifact_inventory['codeFingerprint'] == release['codeFingerprint']
                and {row['path'] for row in artifact_inventory['actualFiles']} == set(release['nodeClassPath']),
                'Actual loaded class-source closure/code fingerprint differs')
        for artifact in artifact_inventory['actualFiles']:
            frozen = release['artifacts'][artifact['path']]
            require(artifact['bytes'] == frozen['bytes'] and artifact['sha256'] == frozen['sha256'],
                    'Actual loaded JAR bytes differ from frozen release')
        actual_plan = json_bounded(base, root / 'load/admission-plan.json')
        require(actual_plan == release['derivedPlan'], 'Actual codec-derived plan differs from pre-registered arm bound')
        require(completion['passed'] is True and completion['allOwnedStopped'] is True
                and completion['fixedLeader'] == 0 and stop['allOwnedStopped'] is True
                and functional['passed'] is True and functional['noCapacityPromotion'] is True,
                'Functional proof or Java owned-clean-stop receipt failed')
        idle_actual = validate_idle_artifacts(base, root, registry, selected_park_ns())
        summary = functional['actualSourceSummary']
        require(summary.get('retentionIdleSelection') == selection(), 'Summary idle selection missing/drifted')
        validate_long_summary(summary, cap)
        require(summary['maintenanceRpcMetrics']['readWindow'] == cap
                and summary['physicalOfferTape']['readWindow'] == cap
                and summary['physicalOfferTape']['readBusinessControlPhaseExclusionEnforced'] is True
                and 1 <= summary['physicalOfferTape']['readOnlyRawRegistryHighWater'] <= cap, 'Runtime selected read-window/tape bound differs')
        observations = json_bounded(base, root / 'load/transport-observations.json')
        require(isinstance(observations, list) and observations, 'Actual load transport observations required')
        previous_bounds = None
        previous_associations = -1
        initial_term = observations[0]['leadershipTermId']
        require(type(initial_term) is int and initial_term == 0, 'Actual initial leadership term required')
        for sample in observations:
            require(sample['archiveChunkBytes'] == 6144, 'Actual requested archive chunk differs')
            bounds = sample['actualEgressBounds']
            actual_images = validate_egress(bounds)
            if previous_bounds is not None:
                validate_egress_progress(previous_bounds, bounds)
            previous_bounds = bounds
            require(bounds['replyHeaderImageAssociations'] >= previous_associations, 'Actual Header association counter regressed')
            previous_associations = bounds['replyHeaderImageAssociations']
            require(sample['leadershipTermId'] == initial_term, 'Same leader reelected with a changed leadership term invalidates stationary arm')
            require(sample['leaderMemberId'] == 0 and sample['profileSha256'] == release['profileFingerprint']
                    and sample['lineageId'] == registry.registrations[cap]['lineage']
                    and sample['maintenanceEnabled'] is True and sample['mtuLength'] == 1248,
                    'Actual load leader/profile/maintenance/MTU differs')
            require(all(event['leaderMemberId'] == 0 and event['leadershipTermId'] == initial_term for event in sample['newLeaderEvents']),
                    'Observed leadership member/term change invalidates fixed leader sample')
        require(previous_associations > 0, 'Final actual egress Header associations missing')
        final_egress = functional['actualEgressBounds']
        require(max(image['largestObservedApplicationReplyBytes'] for image in final_egress['images']) <= actual_plan['largestReplyBytes'], 'Actual observed reply exceeds prospective codec-derived upper bound')
        require(validate_egress_progress(previous_bounds, final_egress)
                and final_egress['replyHeaderImageAssociations'] >= previous_associations
                and final_egress['replyHeaderImageAssociations'] == summary['physicalOfferTape']['recordedReplies']
                and final_egress['actualImageObservations'] >= 2, 'Terminal actual Image/raw reply association closure differs')
        final_position = json_bounded(base, root / 'final-position.json')
        require(functional['allThreeSnapshotLogsMatched'] is True and final_position['combinedSha256'] == functional['finalCombinedSha256'],
                'Functional final all-three checkpoint hash binding differs')
        log_reports = []
        for member in range(3):
            log = root / ('node-%d.log' % member)
            require(log.stat().st_size <= MAX_LOG, 'Stopped node log cap')
            original_log = log.read_bytes()
            text = original_log.decode('utf8', 'strict')
            role = 'window-%d-node-%d' % (cap, member)
            node_identity = next(row['identity'] for row in registry.records.values() if row['role'] == role)
            require('VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s' % (
                    member, node_identity['pid'], release['profileFingerprint'], registry.registrations[cap]['lineage'],
                    release['codeFingerprint']) in text and 'preparedArchiveCacheEnabled=true' in text,
                    'Actual node startup log identity/profile/code/prepared-cache differs')
            log_reports.append(classify_node_log(original_log, node=member, pid=node_identity['pid'],
                profile=release['profileFingerprint'], lineage=registry.registrations[cap]['lineage'],
                code=release['codeFingerprint'], final_hash=final_position['combinedSha256'],
                idle_actual=json_bounded(base, root / ('node-%d/idle-observations/idle-000.actual.json' % member))))
            if member == 0:
                require('VECTOR_V3_ROLE role=LEADER' in text, 'Actual node0 leader role was not observed')
            # Follower roles during clean shutdown are outside the load window. The owner
            # transport's initial/final observations and all onNewLeader callbacks gate it.
        arms.append({'batchCap': 4, 'archiveChunkBytes': 6144, 'readWindow': cap, 'maximumParkNs': selected_park_ns(), 'idleAttestation': idle_actual, 'nodeLogClassifications': log_reports, 'retainedPostCheckpointEosWarningPairs': sum(r['warningPairCount'] for r in log_reports), 'completion': completion, 'functional': functional})
    return {'passed': True, 'arms': arms, 'functionalPilotOnly': True, 'capacityOrEnduranceProven': False}


def collect_stopped(base, release):
    # Caller must already have independently closed every registered process and checked global idle.
    strict_idle(base)
    require(shutil.disk_usage(ROOT).free >= GIB + MAX_ARCHIVE, 'Stopped archive lacks 1GiB floor plus full 256MiB archive reserve')
    inventory = base.scan(PAIR, True)
    require(len(inventory['files']) + len(inventory['directories']) <= MAX_PATHS, 'Stopped pilot closure path cap')
    require(inventory['logicalBytes'] <= MAX_LOGICAL, 'Stopped 12GiB logical-byte cap')
    archive = JOB / 'pilot-after-clean-stop.tar.gz'
    with archive.open('xb') as raw, tarfile.open(fileobj=base.CappedArchive(raw, MAX_ARCHIVE), mode='w:gz', compresslevel=1) as out:
        out.add(str(PAIR), arcname='idle-arm', recursive=True)
    require(shutil.disk_usage(ROOT).free >= GIB, 'Post-archive free space below explicit 1GiB floor')
    return {'inventory': inventory, 'archive': {'path': str(archive), 'bytes': archive.stat().st_size,
            'sha256': digest(archive)}, 'fullLogicalBytesIncluded': True, 'originalsRetained': True,
            'sameHostReadback': verify_archive_members(archive, inventory, prefix='idle-arm'),
            'requiresIndependentCollectorStreamReadback': True, 'extracted': False,
            'independentStorageDurabilityProven': False}


def execute(base, release, release_path):
    before = preflight(base, release)
    base.enable_pidfd()
    JOB.mkdir(mode=0o700)
    base.save(JOB / 'before.json', before)
    for source, name in [(Path(__file__), 'controller-source.py'), (HERE / 'owned_linux_base_8eeb.py', 'owned_linux_base_8eeb.py'),
                         (release_path, 'release.json')]:
        shutil.copy2(source, JOB / name)
    initial = allocated_scan(base, JOB)['allocatedBytes']
    registry = Registry(base, release, JOB)
    args = parent_argv(release)
    errors, parent, cleaning = [], None, False
    samples = []
    previous = {}
    def interrupted(signum, frame):
        if not cleaning:
            raise InterruptedError('Controller signal ' + str(signum))
    for signum in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        previous[signum] = signal.signal(signum, interrupted)
    started = time.monotonic()
    telemetry = Telemetry(base, JOB, started)
    try:
        with (JOB / 'parent.log').open('xb') as log:
            parent = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                cwd=str(JOB), env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
                'VECTOR_AERON_MTU_LENGTH': '1248'}, start_new_session=True)
        # Direct child is retained before any fallible read/write/identity check.
        base.save(JOB / 'parent-launch-handle.json', {'pid': parent.pid, 'expectedArguments': args,
            'expectedCommandSha256': base.argv_digest(args), 'observedExecIdentityVerified': False})
        actual = base.process_identity(parent.pid)
        require(actual is not None, 'Parent exited before kernel identity capture')
        registry.record(actual, 'pilot-parent', 'independent-direct-child-proc')
        require(actual['arguments'] == args and actual['commandSha256'] == base.argv_digest(args), 'Parent kernel argv differs')
        while True:
            observation = monitor(base, registry, release, initial)
            telemetry.sample(registry)
            if len(samples) < 360:
                samples.append(dict(observation, elapsedSeconds=time.monotonic() - started,
                                    freeBytes=shutil.disk_usage(ROOT).free))
            if parent.poll() is not None:
                break
            require(time.monotonic() - started < EXECUTE_SECONDS, 'Execution deadline 240s; reserve 120s clean closure in overall 360s')
            time.sleep(0.5)
        require(parent.returncode == 0, 'Pilot parent failed; retain partial raw attempt')

    except BaseException as error:
        errors.append({'phase': 'execution', 'error': repr(error)})
    finally:
        cleaning = True
        try:
            closure = clean_all(base, registry, parent, args, started + TOTAL_SECONDS) if parent is not None else {
                'allOwnedStopped': True, 'reports': [], 'errors': [], 'noParentLaunched': True, 'forcedKill': False}
        except BaseException as error:
            closure = {'allOwnedStopped': False, 'errors': [{'error': repr(error)}], 'forcedKill': False}
        try:
            telemetry.sample(registry, phase='after-clean-stop-observation', force=True)
            base.save(JOB / 'telemetry-receipt.json', telemetry.close(closure['allOwnedStopped']))
        except BaseException as error:
            errors.append({'phase': 'telemetry-close', 'error': repr(error)})
            if not telemetry.stream.closed:
                telemetry.stream.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    base.save(JOB / 'monitor-samples.json', {'samples': samples, 'sampleCap': 360, 'pollSeconds': 0.5,
        'preservedOnExecutionFailure': True})
    base.save(JOB / 'python-owned-stop.json', closure)
    if not closure['allOwnedStopped']:
        base.save(JOB / 'BENCHMARK_BLOCKED.json', {'atUtc': base.now(), 'errors': errors + closure['errors'],
            'reason': 'Owned clean stop unconfirmed; no forced kill, no active-native hashing/archive, no next run'})
        raise RuntimeError('BENCHMARK_BLOCKED: strict owned clean shutdown unconfirmed')
    after_protected = protected_state(base, release)
    result = None
    try:
        if not errors:
            result = validate_result(base, registry, release)
    except BaseException as error:
        errors.append({'phase': 'proof-validation', 'error': repr(error)})
    archived = collect_stopped(base, release) if PAIR.exists() else {'noArmCreated': True}
    base.save(JOB / 'after-clean-stop.json', {'archive': archived, 'protectedOriginal': after_protected})
    base.save(JOB / 'completion.json', {'passed': not errors and result is not None, 'result': result, 'errors': errors,
        'allOwnedStopped': True, 'functionalPilotOnly': True, 'capacityOrEnduranceProven': False,
        'arm': ARM, 'maximumParkNs': selected_park_ns(), 'frozenReleaseSha256': FROZEN_RELEASE_SHA, 'noNewResources': True, 'hardKernelDeadlineGuaranteed': False, 'atUtc': base.now()})
    require(not errors and result is not None, 'Functional pilot failed; complete stopped raw attempt retained; no rerun')
    return {'passed': True, 'job': str(JOB), 'arm': ARM, 'maximumParkNs': selected_park_ns(), 'functionalPilotOnly': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--arm', type=int, choices=[1], required=True)
    parser.add_argument('--release', type=Path, default=PREP / 'release/release.json')
    parser.add_argument('--release-sha256', help='Explicit SHA from root independent release freeze')
    parser.add_argument('--start-new', action='store_true', help='One root-reviewed frozen attempt; default preflight only')
    options = parser.parse_args(argv)
    configure_arm(options.arm)
    global FROZEN_RELEASE_SHA
    FROZEN_RELEASE_SHA = options.release_sha256
    base = load_base()
    release = runtime_manifest(base, options.release, options.release_sha256)
    result = execute(base, release, options.release) if options.start_new else preflight(base, release)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
