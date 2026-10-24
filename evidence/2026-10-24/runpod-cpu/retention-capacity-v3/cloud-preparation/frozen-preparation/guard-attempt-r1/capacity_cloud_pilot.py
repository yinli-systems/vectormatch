#!/usr/bin/env python3
"""Finite existing-host pilot. DRAFT: execution requires an independently frozen release.json."""
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
PREP = ROOT / 'preparation/capacity-cloud-pilot-r1'
JOB = PREP / 'attempt-r1'
PAIR = JOB / 'pilot-pair'
MAIN = 'io.vectormatch.cluster.RetentionCapacityAeronPilotV3'
NODE = 'io.vectormatch.cluster.RetentionNodeMainV3'
GIB = 1024**3
MAX_LOG = 4 * 1024**2
MAX_ARCHIVE = 256 * 1024**2
MAX_PATHS = 8192
EXECUTE_SECONDS = 240
TOTAL_SECONDS = 360


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
    require(release['host'] == HOST and release['job'] == str(JOB) and release['pairRoot'] == str(PAIR),
            'Fixed existing host/fresh attempt roots differ')
    require(isinstance(release['sourceCommit'], str) and len(release['sourceCommit']) == 40
            and all(c in '0123456789abcdef' for c in release['sourceCommit']), 'Frozen source commit required')
    for field in ['codeFingerprint', 'profileFingerprint', 'javaExecutableSha256', 'jdkReleaseSha256']:
        require(hex_digest(release[field]), 'Actual frozen SHA required: ' + field)
    cfg = release['configuration']
    require(cfg == {'arrivals': 6400, 'ratePerSecond': 500, 'batchCaps': [1, 4], 'appointedLeader': 0,
                    'sync': 2, 'workers': 128, 'queuePerWorker': 64, 'preparedArchiveCache': True,
                    'samePortsAcrossArms': True, 'mtu': 1248}, 'Fixed pilot configuration differs')
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
    require(set(release['derivedPlans']) == {'1', '4'}, 'Both codec-derived finite plans required')
    for arm, plan in release['derivedPlans'].items():
        require(plan['arrivals'] == 6400 and plan['batchCap'] == int(arm) and plan['admitted'] is True
                and plan['admissionRejections'] == [] and plan['minimumFreeRuntimeBytes'] == GIB,
                'Actual admitted finite plan differs')
        require(type(plan['maximumAllocatedGrowthBytes']) is int
                and 0 < plan['maximumAllocatedGrowthBytes'] <= 5 * GIB // 2, 'Finite owned allocation bound required')
    protection = release['protectedOriginalState']
    require(hex_digest(protection['manifestSha256']) and Path(protection['manifest']).parent == PREP / 'release',
            'Current stopped original-state manifest required; initial clone is not an updated tail baseline')
    require(release['parentJvmArguments'] == ['--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
            '--add-opens=java.base/java.util.zip=ALL-UNNAMED', '-Xmx256m'], 'Fixed parent JVM flags differ')
    return release


def parent_argv(release):
    return [release['java']] + release['parentJvmArguments'] + ['-cp', ':'.join(release['classPath']), MAIN, str(PAIR)]


def node_argv(release, cap, member, registration):
    return [release['java'], '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
            '--add-opens=java.base/java.util.zip=ALL-UNNAMED', '-Xmx256m',
            '-Daeron.cluster.appointed.leader.id=0', '-cp', ':'.join(release['nodeClassPath']), NODE,
            str(member), str(PAIR / ('cap-' + str(cap))), str(registration['ports']), '2',
            release['profileId'], registration['lineage'], release['profileFingerprint'],
            release['codeFingerprint'], 'bounded-maintenance-v1']


def validate_registration(release, cap, registration):
    require(registration['arrivals'] == 6400 and registration['rate'] == 500
            and registration['batchCap'] == cap and registration['appointedLeader'] == 0
            and registration['sync'] == 2 and registration['profileSha256'] == release['profileFingerprint']
            and registration['codeSha256'] == release['codeFingerprint'], 'Actual arm configuration/code/profile differs')
    require(type(registration['ports']) is int and 35000 <= registration['ports'] < 55000,
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
        for cap in [1, 4]:
            arm = PAIR / ('cap-' + str(cap))
            path = arm / 'registration.json'
            if not path.exists():
                continue
            registration = json_bounded(self.base, path)
            validate_registration(self.release, cap, registration)
            if cap in self.registrations:
                require(registration == self.registrations[cap], 'Arm registration mutated')
            self.registrations[cap] = registration
            if len(self.registrations) == 2:
                require(self.registrations[1]['ports'] == self.registrations[4]['ports'], 'Batch arms changed UDP ports')
                require(self.registrations[1]['lineage'] != self.registrations[4]['lineage'], 'Arms must use distinct fresh lineages')
            for member in range(3):
                identity_path = arm / ('node-%d-identity.json' % member)
                expected = node_argv(self.release, cap, member, registration)
                if identity_path.exists():
                    row = json_bounded(self.base, identity_path)
                    claimed = kernel_record_from_json(self.base, row, expected)
                    actual = self.base.process_identity(claimed['pid'])
                    # Persist the independent actual identity, including mismatches, before refusing it.
                    if actual is not None:
                        self.observe(actual, 'cap-%d-node-%d' % (cap, member), 'independent-proc-observation-unvalidated')
                        require(actual == claimed, 'Live node JSON/kernel PID/startTicks/argv differs; no signal')
                        self.record(actual, 'cap-%d-node-%d' % (cap, member), 'independent-proc-observation-validated')
                    else:
                        self.record(claimed, 'cap-%d-node-%d' % (cap, member), 'json-kernel-record-process-already-exited')
        # Independently recover nodes launched before Java writes node identity JSON.
        for folder in self.base.PROC.iterdir():
            if not folder.name.isdigit():
                continue
            actual = self.base.process_identity(int(folder.name))
            if actual is None or NODE not in actual['arguments']:
                continue
            args = actual['arguments']
            if not any(str(PAIR / ('cap-' + str(c))) in args for c in [1, 4]):
                continue
            # An unmatched observation is evidence only and must never enter the signal registry.
            self.observe(actual, 'candidate-node', 'fresh-root-proc-observation-unvalidated')
            matched = []
            for cap, registration in self.registrations.items():
                for member in range(3):
                    if args == node_argv(self.release, cap, member, registration):
                        matched.append('cap-%d-node-%d' % (cap, member))
            require(len(matched) == 1, 'Fresh-root node argv does not match one registered exact template; no signal')
            self.record(actual, matched[0], 'proc-scan-missing-json-window')
        return list(self.records.values())


def protected_state(base, release):
    row = release['protectedOriginalState']
    path = Path(row['manifest'])
    base.no_links(path)
    require(digest(path) == row['manifestSha256'], 'Current original-state manifest differs')
    manifest = json_bounded(base, path, 4 * 1024**2)
    require(manifest['scope'] == 'CURRENT_STOPPED_ORIGINAL_RESTORATION' and len(manifest['nativeTrees']) == 3,
            'Explicit current three-native-tree plus PG baseline required')
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
    files, allocated = 0, 0
    for root, directories, names in os.walk(str(path), followlinks=False):
        for name in directories + names:
            child = Path(root) / name
            base.no_links(child)
            st = child.lstat()
            require(st.st_nlink == 1 or child.is_dir(), 'Owned hardlink refused')
            require(child.is_dir() or child.is_file(), 'Owned special file refused')
            require(child.is_dir() or st.st_size <= 512 * 1024**2, 'Owned individual file cap')
            files += 1
            require(files <= MAX_PATHS, 'Owned path-count cap')
            if child.is_file():
                allocated += st.st_blocks * 512
                if child.suffix == '.log':
                    require(st.st_size <= MAX_LOG, 'Owned log cap')
    return {'paths': files, 'allocatedBytes': allocated}


def allocation_limit(release):
    return sum(p['maximumAllocatedGrowthBytes'] for p in release['derivedPlans'].values()) + 16 * 1024**2


def preflight(base, release):
    validate_release(release)
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
    idle = base.idle_check()
    minimum = max(3 * GIB, allocation_limit(release) + GIB + MAX_ARCHIVE)
    require(shutil.disk_usage(ROOT).free >= minimum, 'Initial free space below 3GiB or finite pair+archive+floor bound')
    require(base.memory_headroom() >= 8 * GIB, 'Initial memory headroom below 8GiB')
    return {'passed': True, 'atUtc': base.now(), 'idle': idle, 'protectedOriginal': protected_state(base, release),
            'minimumInitialFreeBytes': minimum, 'maximumAllocatedGrowthBytes': allocation_limit(release),
            'controllerSha256': digest(__file__), 'baseSha256': BASE_SHA, 'noJavaStarted': True}


def monitor(base, registry, release, initial):
    records = registry.discover()
    base.idle_check([r['identity'] for r in records])
    require(shutil.disk_usage(ROOT).free >= GIB, 'Runtime free space below 1GiB')
    observed = allocated_scan(base, JOB)
    require(observed['allocatedBytes'] - initial <= allocation_limit(release), 'Derived pair owned allocation cap')
    return observed


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
        base.idle_check()
    except BaseException as error:
        absent = False
        errors.append({'role': 'final-global-idle-observation', 'error': repr(error)})
    return {'allOwnedStopped': absent and parent.poll() is not None and not errors,
            'reports': reports, 'errors': errors, 'forcedKill': False, 'numericPidSignalFallback': False}


def validate_result(base, registry, release):
    registry.discover()
    require(set(registry.registrations) == {1, 4}, 'Both actual arm registrations required')
    require({r['role'] for r in registry.records.values()} == {'pilot-parent'} |
            {'cap-%d-node-%d' % (c, n) for c in [1, 4] for n in range(3)}, 'Six node identities plus parent required')
    result = json_bounded(base, PAIR / 'pair-completion.json')
    require(result['passed'] is True and result['arms'] == [1, 4], 'Parent pair did not complete')
    arms = []
    for cap in [1, 4]:
        root = PAIR / ('cap-' + str(cap))
        completion = json_bounded(base, root / 'completion.json')
        stop = json_bounded(base, root / 'owned-stop.json')
        functional = json_bounded(base, root / 'functional-result.json')
        require(completion['passed'] is True and completion['allOwnedStopped'] is True
                and completion['fixedLeader'] == 0 and stop['allOwnedStopped'] is True
                and functional['passed'] is True and functional['noCapacityPromotion'] is True,
                'Functional proof or Java owned-clean-stop receipt failed')
        arms.append({'batchCap': cap, 'completion': completion, 'functional': functional})
    return {'passed': True, 'arms': arms, 'functionalPilotOnly': True, 'capacityOrEnduranceProven': False}


def collect_stopped(base, release):
    # Caller must already have independently closed every registered process and checked global idle.
    base.idle_check()
    inventory = base.scan(PAIR, True)
    require(len(inventory['files']) + len(inventory['directories']) <= MAX_PATHS, 'Stopped pilot closure path cap')
    archive = JOB / 'pilot-after-clean-stop.tar.gz'
    with archive.open('xb') as raw, tarfile.open(fileobj=base.CappedArchive(raw, MAX_ARCHIVE), mode='w:gz', compresslevel=1) as out:
        out.add(str(PAIR), arcname='pilot-pair', recursive=True)
    return {'inventory': inventory, 'archive': {'path': str(archive), 'bytes': archive.stat().st_size,
            'sha256': digest(archive)}, 'fullLogicalBytesIncluded': True, 'originalsRetained': True,
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
        'noNewResources': True, 'hardKernelDeadlineGuaranteed': False, 'atUtc': base.now()})
    require(not errors and result is not None, 'Functional pilot failed; complete stopped raw attempt retained; no rerun')
    return {'passed': True, 'job': str(JOB), 'functionalPilotOnly': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--release', type=Path, default=HERE / 'release.json')
    parser.add_argument('--start-new', action='store_true', help='One root-reviewed frozen attempt; default preflight only')
    options = parser.parse_args(argv)
    base = load_base()
    release = validate_release(json_bounded(base, options.release))
    result = execute(base, release, options.release) if options.start_new else preflight(base, release)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
