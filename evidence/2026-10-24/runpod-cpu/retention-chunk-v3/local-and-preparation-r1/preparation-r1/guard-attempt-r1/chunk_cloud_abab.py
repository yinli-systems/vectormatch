#!/usr/bin/env python3
"""Finite source-only chunk ABAB lifecycle. DRAFT: requires a root-frozen release and one explicit round."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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
PREP = ROOT / 'preparation/chunk-cloud-abab-r1'
ROUND = 1
JOB = PREP / 'round-1'
PAIR = JOB / 'chunk-pair'
FROZEN_RELEASE_SHA = None
PRIOR_GATE_SHA = None
CHUNKS = [3072, 6144]
FIXED_PORTS = 42000

def configure_round(number):
    global ROUND, JOB, PAIR
    require(type(number) is int and number in [1, 2], 'Only pre-registered round 1 or 2 is supported')
    ROUND = number
    JOB = PREP / ('round-' + str(number))
    PAIR = JOB / 'chunk-pair'
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


def validate_release(release):
    require(release.get('schemaVersion') == 1 and release.get('releaseReady') is True,
            'Release is an unfrozen draft; code/profile/artifact manifest required')
    require(release['host'] == HOST and release['rounds'] == {str(n): {
        'job': str(PREP / ('round-' + str(n))),
        'pairRoot': str(PREP / ('round-' + str(n)) / 'chunk-pair')} for n in [1, 2]},
        'Fixed existing host/two fresh round roots differ')
    require(isinstance(release['sourceCommit'], str) and len(release['sourceCommit']) == 40
            and all(c in '0123456789abcdef' for c in release['sourceCommit']), 'Frozen source commit required')
    for field in ['codeFingerprint', 'profileFingerprint', 'javaExecutableSha256', 'jdkReleaseSha256', 'controllerSha256']:
        require(hex_digest(release[field]), 'Actual frozen SHA required: ' + field)
    cfg = release['configuration']
    require(cfg == {'arrivals': 6400, 'ratePerSecond': 500, 'batchCap': 4,
                    'archiveChunkBytesOrder': [3072, 6144, 3072, 6144], 'eventFetchCount': 16,
                    'appointedLeader': 0, 'sync': 2, 'workers': 128, 'queuePerWorker': 64,
                    'preparedArchiveCache': True, 'samePortsAcrossArms': True,
                    'fixedBasePorts': FIXED_PORTS, 'commonChunkEnvelope': True, 'mtu': 1248}, 'Fixed pilot configuration differs')
    require(release['java'] == '/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java', 'Actual canonical Java path differs')
    require(isinstance(release['profileId'], str) and release['profileId'], 'Actual profile ID required')
    require(isinstance(release['classPath'], list) and len(release['classPath']) in [3, 4]
            and len(set(release['classPath'])) == len(release['classPath']), 'Exact class-path closure required')
    require(isinstance(release['nodeClassPath'], list) and len(release['nodeClassPath']) in [3, 4]
            and len(set(release['nodeClassPath'])) == len(release['nodeClassPath'])
            and set(release['nodeClassPath']) <= set(release['classPath']), 'Actual class-source-derived node classpath required')
    artifact_root = PREP / 'release/lib'
    require(set(release['artifacts']) == set(release['classPath']), 'All and only loaded runtime JARs must be frozen')
    for path, row in release['artifacts'].items():
        require(Path(path).parent == artifact_root and Path(path).suffix == '.jar'
                and type(row['bytes']) is int and 0 < row['bytes'] <= 32 * 1024**2
                and hex_digest(row['sha256']), 'Unsafe/unfrozen artifact row')
    require(set(release['derivedPlans']) == {'3072', '6144'}, 'Both codec-derived finite plans required')
    for arm, plan in release['derivedPlans'].items():
        require(plan['arrivals'] == 6400 and plan['batchCap'] == 4
                and plan['archiveChunkBytes'] == int(arm) and plan['admitted'] is True
                and plan['admissionRejections'] == [] and plan['minimumFreeRuntimeBytes'] == GIB,
                'Actual admitted finite plan differs')
        require(type(plan['maximumAllocatedGrowthBytes']) is int
                and 0 < plan['maximumAllocatedGrowthBytes'] <= 5 * GIB // 2, 'Finite owned allocation bound required')
    selected_only = {'archiveChunkBytes', 'selectedMaximumLogicalMaintenanceRpcs', 'selectedMaximumArchiveChunkRpcs'}
    common = []
    for plan in release['derivedPlans'].values():
        require(plan['commonChunkEnvelope'] is True and plan['eventFetchCount'] == 16
                and plan['maximumSupportedArchiveChunkBytes'] == 6144
                and plan['maximumEncodedChunkReplyBytes'] == 6919, 'Common actual reply/RPC plan contract differs')
        common.append({k: v for k, v in plan.items() if k not in selected_only})
    require(common[0] == common[1], 'A/B operational envelopes must be identical; only selected request counts/chunk size may differ')
    protection = release['protectedOriginalState']
    require(hex_digest(protection['manifestSha256']) and Path(protection['manifest']).parent == PREP / 'release',
            'Current stopped original-state manifest required; initial clone is not an updated tail baseline')
    require(release['parentJvmArguments'] == ['--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
            '--add-opens=java.base/java.util.zip=ALL-UNNAMED', '-Xmx256m'], 'Fixed parent JVM flags differ')
    return release


def parent_argv(release):
    return [release['java']] + release['parentJvmArguments'] + ['-cp', ':'.join(release['classPath']),
        MAIN, str(PAIR), 'archive-chunks', str(FIXED_PORTS)]


def node_argv(release, cap, member, registration):
    return [release['java'], '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
            '--add-opens=java.base/java.util.zip=ALL-UNNAMED', '-Xmx256m',
            '-Daeron.cluster.appointed.leader.id=0', '-cp', ':'.join(release['nodeClassPath']), NODE,
            str(member), str(PAIR / ('chunk-' + str(cap))), str(registration['ports']), '2',
            release['profileId'], registration['lineage'], release['profileFingerprint'],
            release['codeFingerprint'], 'bounded-maintenance-v1']


def validate_registration(release, cap, registration):
    require(registration['arrivals'] == 6400 and registration['rate'] == 500
            and registration['batchCap'] == 4 and registration['archiveChunkBytes'] == cap
            and registration['eventFetchCount'] == 16 and registration['commonChunkEnvelope'] is True and registration['appointedLeader'] == 0
            and registration['sync'] == 2 and registration['profileSha256'] == release['profileFingerprint']
            and registration['codeSha256'] == release['codeFingerprint'], 'Actual arm configuration/code/profile differs')
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
        for cap in CHUNKS:
            arm = PAIR / ('chunk-' + str(cap))
            path = arm / 'registration.json'
            if not path.exists():
                continue
            registration = json_bounded(self.base, path)
            validate_registration(self.release, cap, registration)
            if cap in self.registrations:
                require(registration == self.registrations[cap], 'Arm registration mutated')
            else:
                self.base.save(self.job / ('chunk-%d-configuration-observed.json' % cap), {
                    'registration': registration, 'atUtc': self.base.now(),
                    'candidateLoopbackUdpPortsFromFrozenNodeArguments': [registration['ports'] + member * 100 + offset
                        for member in range(3) for offset in range(1, 6)],
                    'candidateAddress': '127.0.0.1', 'freshBindAfterNodeLaunchAttempted': False,
                    'independentPreLaunchPortAvailabilityProven': False,
                    'scope': 'Frozen Java ports() binds all 15 before registration, then releases; this observer verifies configured arguments without rebinding active sockets'})
            self.registrations[cap] = registration
            if len(self.registrations) == 2:
                require(self.registrations[3072]['ports'] == self.registrations[6144]['ports'], 'Batch arms changed UDP ports')
                require(self.registrations[3072]['lineage'] != self.registrations[6144]['lineage'], 'Arms must use distinct fresh lineages')
            for member in range(3):
                identity_path = arm / ('node-%d-identity.json' % member)
                expected = node_argv(self.release, cap, member, registration)
                if identity_path.exists():
                    row = json_bounded(self.base, identity_path)
                    claimed = kernel_record_from_json(self.base, row, expected)
                    actual = self.base.process_identity(claimed['pid'])
                    # Persist the independent actual identity, including mismatches, before refusing it.
                    if actual is not None:
                        self.observe(actual, 'chunk-%d-node-%d' % (cap, member), 'independent-proc-observation-unvalidated')
                        require(actual == claimed, 'Live node JSON/kernel PID/startTicks/argv differs; no signal')
                        self.record(actual, 'chunk-%d-node-%d' % (cap, member), 'independent-proc-observation-validated')
                    else:
                        self.record(claimed, 'chunk-%d-node-%d' % (cap, member), 'json-kernel-record-process-already-exited')
        # Independently recover nodes launched before Java writes node identity JSON.
        for folder in self.base.PROC.iterdir():
            if not folder.name.isdigit():
                continue
            actual = self.base.process_identity(int(folder.name))
            if actual is None or NODE not in actual['arguments']:
                continue
            args = actual['arguments']
            if not any(str(PAIR / ('chunk-' + str(c))) in args for c in CHUNKS):
                continue
            # An unmatched observation is evidence only and must never enter the signal registry.
            self.observe(actual, 'candidate-node', 'fresh-root-proc-observation-unvalidated')
            matched = []
            for cap, registration in self.registrations.items():
                for member in range(3):
                    if args == node_argv(self.release, cap, member, registration):
                        matched.append('chunk-%d-node-%d' % (cap, member))
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
                         if row['role'].startswith('chunk-') and row['available']})
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
    pg = base.verify_pg(manifest['postgres'])
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
    return sum(p['maximumAllocatedGrowthBytes'] for p in release['derivedPlans'].values()) + 16 * 1024**2


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


def verify_archive_members(archive, inventory, prefix='chunk-pair'):
    """Full SHA/bytes/mode/owners/empty-dir readback; streaming, no multi-GiB extraction."""
    require(Path(archive).stat().st_size <= MAX_ARCHIVE, 'Closed archive compressed byte cap')
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


def verify_prior_round_gate(base, release):
    """Second pair cannot start until root freezes a separate independent-collection attestation."""
    require(hex_digest(PRIOR_GATE_SHA), 'Round 2 requires explicit independently frozen collection gate SHA')
    gate_path = PREP / 'release/round-1-collection-gate.json'
    base.no_links(gate_path)
    require(digest(gate_path) == PRIOR_GATE_SHA, 'Root-frozen prior collection gate differs')
    gate = json_bounded(base, gate_path)
    require(gate['schemaVersion'] == 1 and gate['scope'] == 'ROOT_VERIFIED_CLOSED_CHUNK_ROUND_1_COLLECTION'
            and gate['collectionComplete'] is True and gate['round'] == 1
            and gate['frozenReleaseSha256'] == FROZEN_RELEASE_SHA
            and gate['controllerSha256'] == release['controllerSha256'], 'Prior collection is incomplete or from a different release/controller')
    require(hex_digest(gate['independentLocalCollectionReceiptSha256'])
            and gate['localFullMemberShaBytesModesOwnersEmptyDirsVerified'] is True
            and gate['allRawInputsAndFailuresRetained'] is True,
            'Root attestation must identify independently verified local evidence and retain failures')
    previous = PREP / 'round-1'
    completed = json_bounded(base, previous / 'completion.json')
    stopped = json_bounded(base, previous / 'python-owned-stop.json')
    after = json_bounded(base, previous / 'after-clean-stop.json', 4 * 1024**2)
    require(completed['passed'] is True and completed['allOwnedStopped'] is True
            and completed['round'] == 1 and completed['frozenReleaseSha256'] == FROZEN_RELEASE_SHA
            and stopped['allOwnedStopped'] is True, 'Prior exact pair did not close successfully')
    closure = after['archive']
    archive = previous / 'pilot-after-clean-stop.tar.gz'
    require(closure['archive']['path'] == str(archive) and archive.stat().st_size == closure['archive']['bytes']
            and digest(archive) == closure['archive']['sha256'] == gate['closedArchiveSha256'], 'Prior closed compressed artifact differs')
    inventory_raw = json.dumps(closure['inventory'], sort_keys=True, separators=(',', ':')).encode()
    require(hashlib.sha256(inventory_raw).hexdigest() == gate['closedNativeInventorySha256'], 'Prior exact native inventory differs')
    readback = verify_archive_members(archive, closure['inventory'])
    prior_pair = previous / 'chunk-pair'
    if prior_pair.exists():
        actual = base.scan(prior_pair, True)
        require(set(actual['files']) == set(closure['inventory']['files'])
                and actual['directories'] == closure['inventory']['directories'], 'Retained prior pair closure differs')
        for name, row in closure['inventory']['files'].items():
            require(all(actual['files'][name][key] == row[key] for key in ['bytes', 'sha256', 'mode', 'uid', 'gid']), 'Retained prior pair bytes/owner/mode differs')
    else:
        require(gate['rootReviewedExactOwnedNativeRemoval'] is True,
                'Missing prior owned native requires explicit root-reviewed exact-tree removal attestation')
    return {'passed': True, 'gateSha256': PRIOR_GATE_SHA, 'sameFrozenRelease': True,
            'archiveReadback': readback, 'retainedNativeStillPresent': prior_pair.exists(),
            'controllerDeletesAnyFile': False, 'localCollectionIndependentlyReperformedHere': False}


def preflight(base, release):
    validate_release(release)
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
    idle = strict_idle(base)
    prior_round = verify_prior_round_gate(base, release) if ROUND == 2 else {'notApplicableFirstRound': True}
    minimum = max(3 * GIB, allocation_limit(release) + GIB + MAX_ARCHIVE)
    require(shutil.disk_usage(ROOT).free >= minimum, 'Initial free space below 3GiB or finite pair+archive+floor bound')
    require(base.memory_headroom() >= 8 * GIB, 'Initial memory headroom below 8GiB')
    return {'passed': True, 'atUtc': base.now(), 'idle': idle, 'protectedOriginal': protected_state(base, release),
            'round': ROUND, 'priorRound': prior_round, 'minimumInitialFreeBytes': minimum, 'maximumAllocatedGrowthBytes': allocation_limit(release),
            'controllerSha256': digest(__file__), 'baseSha256': BASE_SHA, 'noJavaStarted': True}


def monitor(base, registry, release, initial):
    records = registry.discover()
    strict_idle(base, [r['identity'] for r in records])
    require(shutil.disk_usage(ROOT).free >= GIB, 'Runtime free space below 1GiB')
    observed = allocated_scan(base, JOB)
    require(observed['allocatedBytes'] - initial <= allocation_limit(release), 'Derived pair owned allocation cap')
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
    require(associations == bounds['replyHeaderImageAssociations']
            and min(limits) == bounds['minimumActualDerivedMaxMessageLength'], 'Actual Image aggregate counters differ')
    return identities


def validate_result(base, registry, release):
    registry.discover()
    require(set(registry.registrations) == set(CHUNKS), 'Both actual arm registrations required')
    require(len(registry.records) == 7 and {r['role'] for r in registry.records.values()} == {'pilot-parent'} |
            {'chunk-%d-node-%d' % (c, n) for c in CHUNKS for n in range(3)}, 'Six node identities plus parent required')
    result = json_bounded(base, PAIR / 'pair-completion.json')
    require(result['passed'] is True and result['archiveChunkBytes'] == CHUNKS and result['fixedBusinessBatchCap'] == 4, 'Parent pair did not complete')
    arms = []
    for cap in CHUNKS:
        root = PAIR / ('chunk-' + str(cap))
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
        require(actual_plan == release['derivedPlans'][str(cap)], 'Actual codec-derived plan differs from pre-registered arm bound')
        require(completion['passed'] is True and completion['allOwnedStopped'] is True
                and completion['fixedLeader'] == 0 and stop['allOwnedStopped'] is True
                and functional['passed'] is True and functional['noCapacityPromotion'] is True,
                'Functional proof or Java owned-clean-stop receipt failed')
        summary = functional['actualSourceSummary']
        require(summary['scheduledArrivals'] == 6400 and summary['releasedArrivals'] == 6400
                and summary['ratePerSecond'] == 500 and summary['batchCap'] == 4 and summary['archiveChunkBytes'] == cap
                and summary['arrivalClockPausedForMaintenance'] is False
                and summary['unknownFinal'] == 0 and summary['maintenanceCycles'] >= 2,
                'Functional source must close UNKNOWN and cross at least two maintenance cycles')
        observations = json_bounded(base, root / 'load/transport-observations.json')
        require(isinstance(observations, list) and observations, 'Actual load transport observations required')
        image_set = None
        previous_associations = -1
        for sample in observations:
            require(sample['archiveChunkBytes'] == cap, 'Actual requested archive chunk differs')
            bounds = sample['actualEgressBounds']
            actual_images = validate_egress(bounds)
            require(image_set is None or image_set == actual_images, 'Actual egress Image set/metadata drift across observations')
            image_set = actual_images
            require(bounds['replyHeaderImageAssociations'] >= previous_associations, 'Actual Header association counter regressed')
            previous_associations = bounds['replyHeaderImageAssociations']
            require(sample['leaderMemberId'] == 0 and sample['profileSha256'] == release['profileFingerprint']
                    and sample['lineageId'] == registry.registrations[cap]['lineage']
                    and sample['maintenanceEnabled'] is True and sample['mtuLength'] == 1248,
                    'Actual load leader/profile/maintenance/MTU differs')
            require(all(event['leaderMemberId'] == 0 for event in sample['newLeaderEvents']),
                    'Observed leadership change to another member invalidates fixed leader sample')
        require(previous_associations > 0, 'Final actual egress Header associations missing')
        final_egress = functional['actualEgressBounds']
        require(validate_egress(final_egress) == image_set
                and final_egress['replyHeaderImageAssociations'] == summary['physicalOfferTape']['recordedReplies']
                and final_egress['actualImageObservations'] >= 2, 'Terminal actual Image/raw reply association closure differs')
        for member in range(3):
            log = root / ('node-%d.log' % member)
            require(log.stat().st_size <= MAX_LOG, 'Stopped node log cap')
            text = log.read_text(errors='replace')
            role = 'chunk-%d-node-%d' % (cap, member)
            node_identity = next(row['identity'] for row in registry.records.values() if row['role'] == role)
            require('VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s' % (
                    member, node_identity['pid'], release['profileFingerprint'], registry.registrations[cap]['lineage'],
                    release['codeFingerprint']) in text and 'preparedArchiveCacheEnabled=true' in text,
                    'Actual node startup log identity/profile/code/prepared-cache differs')
            if member == 0:
                require('VECTOR_V3_ROLE role=LEADER' in text, 'Actual node0 leader role was not observed')
            # Follower roles during clean shutdown are outside the load window. The owner
            # transport's initial/final observations and all onNewLeader callbacks gate it.
        arms.append({'batchCap': 4, 'archiveChunkBytes': cap, 'completion': completion, 'functional': functional})
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
        out.add(str(PAIR), arcname='chunk-pair', recursive=True)
    require(shutil.disk_usage(ROOT).free >= GIB, 'Post-archive free space below explicit 1GiB floor')
    return {'inventory': inventory, 'archive': {'path': str(archive), 'bytes': archive.stat().st_size,
            'sha256': digest(archive)}, 'fullLogicalBytesIncluded': True, 'originalsRetained': True,
            'sameHostReadback': verify_archive_members(archive, inventory, prefix='chunk-pair'),
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
        samples = []
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
        base.save(JOB / 'monitor-samples.json', {'samples': samples, 'sampleCap': 360, 'pollSeconds': 0.5})
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
    archived = collect_stopped(base, release) if PAIR.exists() else {'noPairCreated': True}
    base.save(JOB / 'after-clean-stop.json', {'archive': archived, 'protectedOriginal': after_protected})
    base.save(JOB / 'completion.json', {'passed': not errors and result is not None, 'result': result, 'errors': errors,
        'allOwnedStopped': True, 'functionalPilotOnly': True, 'capacityOrEnduranceProven': False,
        'round': ROUND, 'frozenReleaseSha256': FROZEN_RELEASE_SHA, 'noNewResources': True, 'hardKernelDeadlineGuaranteed': False, 'atUtc': base.now()})
    require(not errors and result is not None, 'Functional pilot failed; complete stopped raw attempt retained; no rerun')
    return {'passed': True, 'job': str(JOB), 'round': ROUND, 'functionalPilotOnly': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--round', type=int, choices=[1, 2], required=True)
    parser.add_argument('--prior-collection-sha256', help='Round 2 only: independently root-frozen collection gate SHA')
    parser.add_argument('--release', type=Path, default=PREP / 'release/release.json')
    parser.add_argument('--release-sha256', help='Explicit SHA from root independent release freeze')
    parser.add_argument('--start-new', action='store_true', help='One root-reviewed frozen attempt; default preflight only')
    options = parser.parse_args(argv)
    configure_round(options.round)
    global FROZEN_RELEASE_SHA, PRIOR_GATE_SHA
    FROZEN_RELEASE_SHA, PRIOR_GATE_SHA = options.release_sha256, options.prior_collection_sha256
    require(ROUND == 2 or PRIOR_GATE_SHA is None, 'First round must not use a prior collection gate')
    base = load_base()
    release = runtime_manifest(base, options.release, options.release_sha256)
    result = execute(base, release, options.release) if options.start_new else preflight(base, release)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
