#!/usr/bin/env python3
"""One fixed original-clone recovery attempt. Default is read-only preflight; no SSH or resource creation."""
import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
PLAN_SHA = '332582f1168f0c092f93af76730d1bdf2f21ee3ddaef7beb8d0b5c0a8e6cd6f2'
ROOT = Path('/opt/vectormatch-cpu')
PROC = Path('/proc')


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def no_links(path):
    path = Path(path)
    for p in [path] + list(path.parents):
        require(not p.is_symlink(), 'Symlink ancestor refused: ' + str(p))


def load_plan():
    source = HERE / 'plan.json'
    require(sha(source) == PLAN_SHA, 'Frozen plan SHA differs')
    plan = json.loads(source.read_text())
    require(plan['host'] == 'ed6c0673f5cb' and sum(len(n['files']) for n in plan['nodes']) == 51,
            'Registered host/native closure differs')
    return plan


def argv_digest(args):
    return hashlib.sha256(b''.join(os.fsencode(x) + b'\0' for x in args)).hexdigest()


def process_identity(pid):
    try:
        folder = PROC / str(pid)
        raw_stat = (folder / 'stat').read_text()
        fields = raw_stat[raw_stat.rfind(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        raw = (folder / 'cmdline').read_bytes()
        require(raw.endswith(b'\0') and len(fields) > 19, 'Incomplete process identity')
        return {'pid': pid, 'startTicks': int(fields[19]), 'commandSha256': hashlib.sha256(raw).hexdigest(),
                'arguments': [os.fsdecode(x) for x in raw[:-1].split(b'\0')]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def matching_identity(expected):
    actual = process_identity(expected['pid'])
    if actual is None:
        return None
    require(all(actual[k] == expected[k] for k in ['pid', 'startTicks', 'commandSha256', 'arguments']),
            'Owned PID/startTicks/argv differs; no signal')
    require(expected['commandSha256'] == argv_digest(expected['arguments']), 'Record argv SHA inconsistent')
    return actual


def enable_pidfd():
    if not callable(getattr(os, 'pidfd_open', None)) or not callable(getattr(signal, 'pidfd_send_signal', None)):
        require(platform.system() == 'Linux' and platform.machine() == 'x86_64', 'Unsupported pidfd compatibility target')
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        def syscall(number, *args):
            result = libc.syscall(ctypes.c_long(number), *args)
            if result < 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code))
            return int(result)
        if not callable(getattr(os, 'pidfd_open', None)):
            def opening(pid, flags=0):
                require(type(pid) is int and pid > 1 and flags == 0, 'Invalid pidfd open')
                fd = syscall(434, ctypes.c_int(pid), ctypes.c_uint(0))
                os.set_inheritable(fd, False)
                return fd
            os.pidfd_open = opening
        if not callable(getattr(signal, 'pidfd_send_signal', None)):
            def sending(fd, signum, siginfo=None, flags=0):
                require(type(fd) is int and fd >= 0 and siginfo is None and flags == 0, 'Invalid pidfd signal')
                syscall(424, ctypes.c_int(fd), ctypes.c_int(int(signum)), ctypes.c_void_p(), ctypes.c_uint(0))
            signal.pidfd_send_signal = sending
    fd = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(fd, 0)
    finally:
        os.close(fd)


def stop_owned(expected, seconds):
    if matching_identity(expected) is None:
        return {'stopped': True, 'alreadyExited': True, 'record': expected}
    fd = os.pidfd_open(expected['pid'])
    try:
        # Recheck identity after pinning a stable kernel process handle.
        if matching_identity(expected) is None:
            return {'stopped': True, 'alreadyExited': True, 'record': expected}
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        ready = select.select([fd], [], [], seconds)[0]
        require(bool(ready), 'Clean SIGTERM shutdown exceeded deadline; no forced kill; benchmark blocked')
    finally:
        os.close(fd)
    require(process_identity(expected['pid']) is None, 'Owned process still alive after clean stop')
    return {'stopped': True, 'signal': 'SIGTERM', 'record': expected, 'atUtc': now()}


def scan(root, hash_files=False):
    root = Path(root)
    no_links(root)
    require(root.is_dir(), 'Registered directory missing: ' + str(root))
    files, dirs = {}, {}
    for p in [root] + sorted(root.rglob('*')):
        require(not p.is_symlink(), 'Symlink evidence refused')
        st = p.lstat()
        name = str(p.relative_to(root))
        mode = stat.S_IMODE(st.st_mode)
        require(mode & 0o7000 == 0, 'Special file permissions refused')
        if stat.S_ISDIR(st.st_mode):
            dirs[name] = {'mode': mode, 'uid': st.st_uid, 'gid': st.st_gid}
        else:
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= 512 * 1024**2,
                    'Nonregular/hardlinked/unbounded evidence file')
            files[name] = {'bytes': st.st_size, 'mode': mode, 'uid': st.st_uid, 'gid': st.st_gid,
                           'allocatedBytes': st.st_blocks * 512, 'mtimeNs': st.st_mtime_ns}
            if hash_files:
                files[name]['sha256'] = sha(p)
        require(len(files) + len(dirs) <= 4096, 'Owned evidence path-count cap')
    return {'files': files, 'directories': dirs, 'allocatedBytes': sum(x['allocatedBytes'] for x in files.values()),
            'logicalBytes': sum(x['bytes'] for x in files.values())}


def verify_pg(plan):
    baseline = Path(plan['pgBaseline'])
    no_links(baseline)
    require(sha(baseline) == plan['pgBaselineSha256'], 'Stopped post-r2 PG baseline differs')
    expected = json.loads(baseline.read_text())
    root = Path(plan['pgData'])
    require(not (root / 'postmaster.pid').exists(), 'PG postmaster.pid present; no cluster start')
    actual = scan(root, True)
    require(set(actual['files']) == set(expected['pgFiles']), 'Stopped PG file closure differs')
    require(set(actual['directories']) == {x['path'] if x['path'] else '.' for x in expected['pgDirectories']}, 'PG directory closure differs')
    for row in expected['pgDirectories']:
        name = row['path'] if row['path'] else '.'
        require(all(actual['directories'][name][k] == row[k] for k in ['mode', 'uid', 'gid']), 'Stopped PG directory owner/mode differs')
    for name, row in expected['pgFiles'].items():
        require(all(actual['files'][name][k] == row[k] for k in ['bytes', 'sha256', 'mode', 'uid', 'gid']), 'Stopped PG bytes/owner/mode differs')
    return {'passed': True, 'baselineSha256': plan['pgBaselineSha256'], 'files': len(actual['files']),
            'scope': 'Read-only full post-r2 PG baseline verification; no PG launch or writes.'}


def idle_check(allowed=()):
    allowed = {r['pid']: r for r in allowed}
    found = []
    for folder in PROC.iterdir():
        if not folder.name.isdigit() or int(folder.name) == os.getpid():
            continue
        try:
            raw = (folder / 'cmdline').read_bytes()
            args = [os.fsdecode(x) for x in raw.split(b'\0') if x]
            if not args:
                continue
            exe = Path(args[0]).name
            relevant = exe in ['postgres', 'postmaster'] or exe == 'java' and any('vectormatch' in a.lower() or 'ForcePathProbe' in a for a in args)
            if relevant:
                pid = int(folder.name)
                if pid in allowed:
                    matching_identity(allowed[pid])
                else:
                    identity = process_identity(pid)
                    if identity is not None:
                        found.append({k: identity[k] for k in ['pid', 'startTicks', 'commandSha256']})
        except (FileNotFoundError, ProcessLookupError):
            pass
    require(not found, 'PG/capacity/other VectorMatch JVM active: ' + json.dumps(found))
    return {'noUnownedPostgresOrVectorMatchJava': True, 'freshProcObservation': True, 'globalLockClaimed': False}


def port_check():
    opened = []
    try:
        for node in range(3):
            for offset in range(1, 6):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                opened.append(s)
                s.bind(('127.0.0.1', 19000 + node * 100 + offset))
    finally:
        for s in opened:
            s.close()
    return {'freshUdpBinds': 15, 'reuseEnabled': False, 'reservationHeld': False}


def memory_headroom():
    mem = dict((line.split(':', 1)[0], int(line.split()[1]) * 1024) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    available = mem['MemAvailable']
    group = Path('/sys/fs/cgroup')
    maximum = (group / 'memory.max').read_text().strip()
    current = int((group / 'memory.current').read_text())
    if maximum != 'max':
        available = min(available, int(maximum) - current)
    return available


def node_argv(plan, node, lib):
    cfg = plan['fixedConfiguration']
    base = Path(plan['nodes'][node]['base'])
    cp = ':'.join(str(Path(lib) / name) for name in sorted(plan['jars']))
    return [plan['java'], '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED', '--add-opens=java.base/java.util.zip=ALL-UNNAMED',
            '-Xmx1g', '-Dvm.process.identity=' + str(base), '-cp', cp, 'io.vectormatch.cluster.ClusterNodeMain',
            str(node), str(base.parent), '19000', '2', '65536', cfg['hosts']]


def probe_argv(plan, artifacts):
    cp = ':'.join(str(Path(artifacts) / 'lib' / name) for name in sorted(plan['jars'])) + ':' + str(Path(artifacts) / plan['helperJar']['name'])
    return [plan['java'], '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED', '--add-opens=java.base/java.util.zip=ALL-UNNAMED',
            '-Xmx128m', '-cp', cp, 'io.vectormatch.cluster.ProbeOriginalRestorationR2', plan['probeOutput']]


def preflight(plan):
    require(platform.system() == 'Linux' and platform.machine() == 'x86_64' and socket.gethostname() == plan['host'] and os.geteuid() == 0,
            'Exact Linux CPU host/root identity required')
    prep, job = Path(plan['prep']), Path(plan['job'])
    no_links(prep)
    require(prep.is_dir() and not job.exists() and not Path(plan['probeOutput']).exists(), 'Fresh registered attempt/output required; no rerun')
    no_links(plan['restorationReceipt'])
    require(sha(plan['restorationReceipt']) == plan['restorationReceiptSha256'], 'Original restoration receipt differs')
    require(Path(plan['java']).resolve() == Path(plan['javaReal']) and Path(plan['javaReal']).is_file(), 'Current registered JDK alias differs')
    release = Path(plan['javaReal']).parents[1] / 'release'
    require('JAVA_VERSION="21.0.13"' in release.read_text(), 'Registered JDK21 release differs')
    idle = idle_check()
    ports = port_check()
    bounds = plan['bounds']
    require(shutil.disk_usage(ROOT).free >= bounds['minimumInitialFreeBytes'], 'Initial root filesystem free below 3GiB')
    require(memory_headroom() >= bounds['minimumMemoryHeadroomBytes'], 'Cgroup/system memory headroom below 8GiB')
    require(set(p.name for p in (prep / 'lib').iterdir()) == set(plan['jars']), 'Exact four e1db JAR closure required')
    for name, expected in plan['jars'].items():
        no_links(prep / 'lib' / name)
        require(sha(prep / 'lib' / name) == expected, 'e1db JAR differs')
    helper = prep / plan['helperJar']['name']
    no_links(helper)
    require(helper.stat().st_size == plan['helperJar']['bytes'] and sha(helper) == plan['helperJar']['sha256'], 'Tail-aware R2 helper differs')
    nodes = []
    for row in plan['nodes']:
        require(sha(row['sourceArchive']) == row['sourceArchiveSha256'], 'Immutable original source archive differs')
        actual = scan(row['base'], True)
        require(set(actual['files']) == set(row['files']) and set(actual['directories']) == {'.', 'archive', 'cluster'}, 'Original native closure differs; do not erase active/stale marks')
        require(actual['logicalBytes'] <= bounds['maximumNativeLogicalBytes'], 'Native size bound')
        for name, expected in row['files'].items():
            require(all(actual['files'][name][k] == expected[k] for k in ['bytes', 'sha256']), 'Original native byte baseline differs')
            require(actual['files'][name]['uid'] == 0 and actual['files'][name]['mode'] & 0o022 == 0, 'Native owner/writable permissions changed')
        nodes.append(actual)
    pg = verify_pg(plan)
    return {'passed': True, 'atUtc': now(), 'idle': idle, 'ports': ports, 'nodes': nodes, 'pg': pg,
            'javaReal': plan['javaReal'], 'javaExecutableSha256': sha(plan['javaReal']), 'jdkReleaseSha256': sha(release),
            'minimumMemoryHeadroomBytes': bounds['minimumMemoryHeadroomBytes'], 'controllerSha256': sha(__file__),
            'noNodeOrProbeStarted': True}


def allocated(plan):
    paths = [Path(n['base']) for n in plan['nodes']] + [Path(plan['job']), Path(plan['probeOutput'])]
    return sum(scan(p)['allocatedBytes'] for p in paths if p.exists())


def monitor(plan, owned, initial, allow_exited_roles=()):
    idle_check([x['record'] for x in owned])
    for child in owned:
        require(matching_identity(child['record']) is not None or child['role'] in allow_exited_roles, 'Owned JVM exited unexpectedly')
        require(Path(child['log']).stat().st_size <= plan['bounds']['maximumLogBytesPerProcess'], 'Owned log size cap')
    require(shutil.disk_usage(ROOT).free >= plan['bounds']['minimumRuntimeFreeBytes'], 'Runtime free below 2.5GiB')
    require(allocated(plan) - initial <= plan['bounds']['maximumAllocatedGrowthBytes'], 'Owned allocation growth above 512MiB')


def launch(plan, role, args, owned, job):
    logfile = job / (role + '.log')
    recordfile = job / (role + '-process.json')
    with logfile.open('xb') as log:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                 cwd=str(job), env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
                                     'VECTOR_AERON_MTU_LENGTH': '1248'}, start_new_session=True)
    # Track the unreaped direct child before any fallible post-launch step.
    slot = {'role': role, 'child': child, 'args': args, 'log': str(logfile), 'record': None}
    owned.append(slot)
    save(job / (role + '-launch-handle.json'), {'pid': child.pid, 'role': role, 'expectedArguments': args,
         'expectedCommandSha256': argv_digest(args), 'observedExecIdentityVerified': False, 'atUtc': now()})
    actual = process_identity(child.pid)
    require(actual is not None and actual['arguments'] == args and actual['commandSha256'] == argv_digest(args), 'Actual launched identity differs')
    slot['record'] = actual
    save(recordfile, dict(actual, role=role, atUtc=now(), controllerSha256=sha(__file__)))
    return slot


class CappedArchive:
    def __init__(self, stream, maximum):
        self.stream, self.maximum, self.count = stream, maximum, 0
    def write(self, raw):
        require(self.count + len(raw) <= self.maximum, 'Native compressed archive cap')
        count = self.stream.write(raw)
        self.count += count
        return count
    def flush(self):
        self.stream.flush()
    def tell(self):
        return self.count


def after_native(plan, job):
    inventories = [scan(n['base'], True) for n in plan['nodes']]
    probe_output = Path(plan['probeOutput'])
    probe_inventory = scan(probe_output, True) if probe_output.exists() else None
    total = sum(x['logicalBytes'] for x in inventories) + (probe_inventory['logicalBytes'] if probe_inventory else 0)
    require(total <= plan['bounds']['maximumNativeLogicalBytes'], 'Post-stop logical archive cap')
    archive = job / 'native-after-clean-stop.tar.gz'
    with archive.open('xb') as raw, tarfile.open(fileobj=CappedArchive(raw, plan['bounds']['maximumCompressedArchiveBytes']), mode='w:gz', compresslevel=1) as stream:
        for node in plan['nodes']:
            stream.add(node['base'], arcname='node-' + str(node['node']), recursive=True)
        if probe_inventory is not None:
            stream.add(str(probe_output), arcname='probe-output', recursive=True)
    return {'inventories': inventories, 'probeOutputInventory': probe_inventory,
            'archive': {'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive)},
            'requiresIndependentCollectorStreamReadback': True, 'fullLogicalBytesIncluded': True, 'extracted': False,
            'originalDeleted': False}


def execute(plan):
    before = preflight(plan)
    enable_pidfd()  # Mandatory before any child can launch.
    job = Path(plan['job'])
    job.mkdir(mode=0o700)  # Atomic single-attempt registration; never reuse or overwrite.
    save(job / 'before.json', before)
    shutil.copy2(__file__, job / 'controller-source.py')
    shutil.copy2(HERE / 'plan.json', job / 'plan.json')
    artifacts = job / 'artifacts'
    (artifacts / 'lib').mkdir(parents=True)
    for name, expected in plan['jars'].items():
        shutil.copy2(Path(plan['prep']) / 'lib' / name, artifacts / 'lib' / name)
        require(sha(artifacts / 'lib' / name) == expected, 'Private artifact copy differs')
    helper = artifacts / plan['helperJar']['name']
    shutil.copy2(Path(plan['prep']) / plan['helperJar']['name'], helper)
    require(sha(helper) == plan['helperJar']['sha256'], 'Private R2 helper copy differs')
    initial = allocated(plan)
    owned, stops, errors, previous = [], [], [], {}
    cleaning = False
    def interrupted(signum, frame):
        if not cleaning:
            raise InterruptedError('Controller signal ' + str(signum))
    for sig in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        previous[sig] = signal.signal(sig, interrupted)
    result = None
    try:
        idle_check()
        port_check()
        started = time.monotonic()
        for node in range(3):
            launch(plan, 'node-' + str(node), node_argv(plan, node, artifacts / 'lib'), owned, job)
        deadline = started + plan['bounds']['startupSeconds']
        while True:
            monitor(plan, owned, initial)
            texts = [Path(x['log']).read_text(errors='replace') for x in owned]
            started_all = all('VECTOR_CLUSTER_STARTED node=' + str(n) in texts[n] and 'sync=2' in texts[n]
                              and 'VECTOR_SNAPSHOT_RESTORED hash=4450df5dc1a6662fec3c8addd55452657ee6fd1ccd0aeae92cc6dbb7e18c780b commands=4539' in texts[n]
                              for n in range(3))
            if started_all and any('VECTOR_CLUSTER_ROLE role=LEADER' in text for text in texts):
                break
            require(time.monotonic() < deadline, 'Original node startup exceeded 120s')
            time.sleep(0.25)
        save(job / 'startup-observed.json', {'atUtc': now(), 'allThreeOldCheckpointRestoreLogsObserved': True,
             'leaderRoleObserved': True, 'postTailCanonicalOrThreeCurrentReplicaStatesProven': False})
        probe = launch(plan, 'tail-probe-r2', probe_argv(plan, artifacts), owned, job)
        deadline = time.monotonic() + plan['bounds']['probeSeconds']
        while probe['child'].poll() is None:
            monitor(plan, owned, initial, ('tail-probe-r2',))
            require(time.monotonic() < deadline, 'R2 probe exceeded 180s')
            time.sleep(0.25)
        require(probe['child'].returncode == 0, 'Tail-aware R2 probe failed; partial raw output retained')
        result = json.loads((Path(plan['probeOutput']) / 'result.json').read_text())
        require(result['passed'] and result['eventSeq'] == 6214 and result['marketSeq'] == 6194
                and result['exportedSeq'] == 6214 and result['commandSeq'] >= 4539
                and result['businessApplied'] is False and result['ackSent'] is False,
                'Actual R2 proof result differs; old checkpoint cannot substitute')
    except BaseException as error:
        errors.append({'phase': 'startup-or-probe', 'type': type(error).__name__, 'message': str(error)})
    finally:
        cleaning = True
        for slot in reversed(owned):
            try:
                if slot['child'].poll() is not None:
                    stopped = {'stopped': True, 'alreadyExited': True, 'originalChildExitCode': slot['child'].returncode}
                elif slot['record'] is None:
                    # Direct unreaped child cannot have recycled its PID; still require exact argv identity.
                    identity = process_identity(slot['child'].pid)
                    require(identity is None or identity['arguments'] == slot['args'] and identity['commandSha256'] == argv_digest(slot['args']), 'Unrecorded direct child argv differs; no signal')
                    slot['record'] = identity
                    stopped = {'stopped': True, 'alreadyExited': True} if identity is None else stop_owned(identity, plan['bounds']['cleanStopSecondsPerProcess'])
                else:
                    stopped = stop_owned(slot['record'], plan['bounds']['cleanStopSecondsPerProcess'])
                slot['child'].wait(timeout=1)
                stops.append(dict(stopped, role=slot['role'], exitCode=slot['child'].returncode))
            except BaseException as error:
                errors.append({'phase': 'owned-clean-stop', 'role': slot['role'], 'type': type(error).__name__, 'message': str(error)})
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    all_stopped = len(stops) == len(owned) and all(x['stopped'] for x in stops)
    save(job / 'owned-stop.json', {'allOwnedStopped': all_stopped, 'stops': stops, 'errors': errors,
                                 'registeredHandles': [{'role': s['role'], 'pid': s['child'].pid, 'expectedArguments': s['args'], 'record': s['record']} for s in owned],
                                 'numericPidSignalFallback': False, 'forcedKill': False})
    if not all_stopped:
        save(job / 'BENCHMARK_BLOCKED.json', {'atUtc': now(), 'reason': 'Owned clean stop unconfirmed; inspect exact saved identities; no benchmark or forced kill', 'errors': errors})
        raise RuntimeError('Owned clean shutdown unconfirmed; benchmark blocked; no native after archive claimed')
    after = after_native(plan, job)
    save(job / 'after-native.json', after)
    pg = verify_pg(plan)
    idle = idle_check()
    save(job / 'completion.json', {'passed': not errors and result is not None, 'allOwnedStopped': True, 'result': result,
         'errors': errors, 'postPgBaselineVerified': pg, 'postIdle': idle, 'atUtc': now(),
         'businessSubmittedByController': False, 'ackSubmitted': False, 'threeCurrentReplicaStatesProven': False,
         'performanceProven': False, 'originalBackupsRetained': True, 'nativeWorkingCloneMayContainConsensusSessionWrites': True,
         'hardKernelDeadlineGuaranteed': False})
    require(not errors and result is not None, 'Recovery probe failed; complete raw attempt retained')
    return {'passed': True, 'job': str(job), 'allOwnedStopped': True, 'scope': 'Original clone boot and leader tail-aware observation only'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--start-new', action='store_true', help='Root-reviewed explicit single attempt; default only reads preflight')
    args = parser.parse_args(argv)
    plan = load_plan()
    print(json.dumps(execute(plan) if args.start_new else preflight(plan)), flush=True)


if __name__ == '__main__':
    main()
