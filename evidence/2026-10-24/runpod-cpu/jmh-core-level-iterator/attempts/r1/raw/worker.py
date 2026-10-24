"""Immutable A/B/A/B core experiment. Importing this module never launches a job."""
import ctypes
import datetime
import hashlib
import itertools
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
import traceback
import zipfile

BASE = Path('/opt/vectormatch-cpu')
REVISIONS = {'A': '987f6526b8a0b3c3516ee668a239990cc79fbd8f',
             'B': '7a4cf09be5055fa48c4246b21679d9038bbbfd5f'}
LIBRARIES = {'lib/' + n for n in ('commons-math3-3.6.1.jar', 'core-0.1.0-SNAPSHOT.jar',
    'jmh-core-1.37.jar', 'jopt-simple-5.0.4.jar', 'vectormatch-core-jmh-0.1.0-SNAPSHOT.jar')}
CORE_JAR = 'lib/core-0.1.0-SNAPSHOT.jar'
CORE_CLASS = 'io/vectormatch/core/MatchingEngine.class'
FORK_MAIN = 'org.openjdk.jmh.runner.ForkedMain'
PIDFD_SOURCE_SHA = '89a5517c0fbe7998512208554630b3a34286ee3524bad27e226a75dedbaadd98'
SUPERVISOR_SHA = '98e98ffa30a631d1ee1080c8a9065e89215bde20144df79598786de547405b1d'
SUPERVISOR = BASE / 'releases/433f02bebe2f3109ec363291fa562d5c509c0723/deploy/remote_service.py'
POLL_SECONDS = 0.01
MAX_OWNED = 128  # 1 runner + 45 measured JVMs, with room to report unexpected extra forks.


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def command_sha(arguments):
    return hashlib.sha256(b''.join(os.fsencode(a) + b'\0' for a in arguments)).hexdigest()


def expected_cases():
    prefix = 'io.vectormatch.bench.jmh.'
    cases = {(prefix + 'FreshMatchingBenchmark.matchBatch',
              (('initialPriceLevels', str(d)), ('tradesPerCommand', str(t))))
             for d, t in itertools.product((1, 100, 10000), (1, 10, 100))}
    return cases | {(prefix + 'FreshPlaceCancelBenchmark.lifecycleBatch',
                     (('action', a), ('initialPriceLevels', str(d))))
                    for a, d in itertools.product(('PLACE', 'CANCEL'), (1, 100, 10000))}


def verify_rows(rows):
    require(isinstance(rows, list) and len(rows) == 15, 'Exactly 15 fresh cases required')
    keys = [(r['benchmark'], tuple(sorted(r.get('params', {}).items()))) for r in rows]
    require(len(set(keys)) == len(keys), 'Duplicate benchmark/parameter case')
    require(set(keys) == expected_cases(), 'Missing/unexpected benchmark/parameter case')
    for row in rows:
        for key, value in (('forks', 3), ('threads', 1), ('warmupIterations', 500),
                           ('measurementIterations', 10), ('warmupBatchSize', 1), ('measurementBatchSize', 1)):
            require(type(row.get(key)) is int and row[key] == value, 'Incorrect ' + key)
        require(row.get('mode') == 'ss' and row.get('jmhVersion') == '1.37'
                and row.get('jdkVersion') == '21.0.13', 'Mode/JMH/JDK differs')
        require(row.get('jvmArgs') == ['-Xms2g', '-Xmx2g'], 'Fork JVM arguments differ')
        metric = row['primaryMetric']
        require(metric['scoreUnit'] == 'us/op', 'Expected batch-mean microseconds/command')
        raw = metric['rawData']
        require(len(raw) == 3 and all(len(fork) == 10 for fork in raw), 'Missing raw fork observations')
        values = [v for fork in raw for v in fork]
        require(all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in values),
                'Nonfinite/nonpositive raw measurement')
        score = metric['score']
        require(type(score) in (int, float) and math.isfinite(score)
                and math.isclose(sum(values) / len(values), score, rel_tol=1e-10), 'Raw mean differs')
    return {'cases': 15, 'forksPerCase': 3, 'measurementsPerFork': 10,
            'allObservationsRetained': True, 'measurementUnit': '64-command normalized batch mean; not individual-order p99'}


def jar_entries(path):
    with zipfile.ZipFile(path) as jar:
        names = jar.namelist()
        require(len(names) == len(set(names)), 'Duplicate JAR entry: ' + str(path))
        return {name: hashlib.sha256(jar.read(name)).hexdigest() for name in names}


def audit_artifacts(plan):
    require(set(plan['distributions']) == {'A', 'B'}, 'Exactly two distributions required')
    entries, manifests = {}, {}
    for group, expected_revision in REVISIONS.items():
        dist = plan['distributions'][group]
        require(dist['revision'] == expected_revision, 'Source revision differs: ' + group)
        root = Path(dist['root'])
        require(root.is_dir() and not root.is_symlink(), 'Missing/symlink distribution root')
        found = {}
        for path in root.rglob('*'):
            require(not path.is_symlink(), 'Symlink in distribution: ' + str(path))
            if path.is_file():
                found[path.relative_to(root).as_posix()] = sha(path)
        require(set(found) == LIBRARIES and set(dist['files']) == LIBRARIES,
                'Distribution must contain the exact five registered JARs; extra files rejected')
        require(found == dist['files'], 'Distribution file SHA differs: ' + group)
        manifests[group] = found
        entries[group] = {name: jar_entries(root / name) for name in sorted(LIBRARIES)}
    changed = {}
    for name in sorted(LIBRARIES):
        a, b = entries['A'][name], entries['B'][name]
        require(set(a) == set(b), 'A/B JAR entry set differs: ' + name)
        different = [n for n in sorted(a) if a[n] != b[n]]
        require(different == ([CORE_CLASS] if name == CORE_JAR else []),
                'Unexpected A/B entry changes: ' + name + ' ' + repr(different))
        changed[name] = {n: {'A': a[n], 'B': b[n]} for n in different}
    return {'passed': True, 'distributions': manifests, 'changedJarEntries': changed,
            'scope': 'Exact file manifests and every JAR entry; only MatchingEngine.class may differ. Container ZIP metadata may differ.'}


def enable_pidfd():
    """Process-local Python3.8 adapter copied from frozen capacity_v2 enable_pidfd.

    Source controller SHA is PIDFD_SOURCE_SHA. No kill(pid)/killpg fallback.
    https://github.com/torvalds/linux/blob/v6.6/arch/x86/entry/syscalls/syscall_64.tbl
    """
    native = callable(getattr(os, 'pidfd_open', None)) and callable(getattr(signal, 'pidfd_send_signal', None))
    if not native:
        require(platform.system() == 'Linux' and platform.machine() == 'x86_64',
                'Python3.8 pidfd adapter supports only Linux x86_64')
        libc = ctypes.CDLL(None, use_errno=True)
        libc.syscall.restype = ctypes.c_long
        def syscall(number, *arguments):
            result = libc.syscall(ctypes.c_long(number), *arguments)
            if result < 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            return int(result)
        def pidfd_open(pid, flags=0):
            require(type(pid) is int and pid > 1 and flags == 0, 'Invalid pidfd_open arguments')
            descriptor = syscall(434, ctypes.c_int(pid), ctypes.c_uint(0))
            os.set_inheritable(descriptor, False)
            return descriptor
        def pidfd_send_signal(descriptor, signum, siginfo=None, flags=0):
            require(type(descriptor) is int and descriptor >= 0 and siginfo is None and flags == 0,
                    'Unsupported pidfd_send_signal arguments')
            syscall(424, ctypes.c_int(descriptor), ctypes.c_int(int(signum)), ctypes.c_void_p(), ctypes.c_uint(0))
        if not callable(getattr(os, 'pidfd_open', None)):
            os.pidfd_open = pidfd_open
        if not callable(getattr(signal, 'pidfd_send_signal', None)):
            signal.pidfd_send_signal = pidfd_send_signal
    descriptor = os.pidfd_open(os.getpid())
    try:
        signal.pidfd_send_signal(descriptor, 0)
    finally:
        os.close(descriptor)
    return {'mode': 'python-native' if native else 'linux-x86_64-syscall-python38',
            'selfPidfdSignalZeroProbePassed': True, 'sourceControllerSha256': PIDFD_SOURCE_SHA,
            'originalSupervisorSourceSha256': SUPERVISOR_SHA, 'supervisorSourceChanged': False,
            'mapping': {'pidfd_open': 434, 'pidfd_send_signal': 424} if not native else None}


class ProcReader:
    def __init__(self, root=Path('/proc')):
        self.root = Path(root)

    def identity(self, pid):
        require(type(pid) is int and pid > 1, 'Invalid owned PID')
        path = self.root / str(pid)
        try:
            first = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            require(len(first) >= 20, 'Malformed owned stat')
            if first[0] == 'Z':
                return None
            command = (path / 'cmdline').read_bytes()
            second = (path / 'stat').read_text().rsplit(')', 1)[1].split()
            require(len(second) >= 20 and first[19] == second[19], 'PID reused during identity read')
            if second[0] == 'Z' or not command:
                return None
            arguments = [os.fsdecode(value) for value in command.rstrip(b'\0').split(b'\0')]
            return {'pid': pid, 'startTicks': int(second[19]), 'commandSha256': hashlib.sha256(command).hexdigest(),
                    'arguments': arguments, 'parentPid': int(second[1]), 'processGroupId': int(second[2]),
                    'sessionId': int(second[3])}
        except (FileNotFoundError, ProcessLookupError):
            return None

    def children(self, pid):
        try:
            values = (self.root / str(pid) / 'task' / str(pid) / 'children').read_text().split()
            result = [int(value) for value in values]
            require(len(result) <= MAX_OWNED and all(value > 1 for value in result), 'Owned children list exceeds bound')
            return result
        except (FileNotFoundError, ProcessLookupError):
            return []


def loopback_host(value):
    if value == 'localhost':
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def same_identity(record, actual):
    return actual is not None and all(record[key] == actual[key] for key in ('pid', 'startTicks', 'commandSha256'))


def safe_signal(record, reader, signum):
    """Validate twice around pidfd_open; the signal is tied to that identity, never a numeric kill."""
    first = reader.identity(record['pid'])
    if first is None:
        return {'pid': record['pid'], 'alreadyStopped': True}
    require(same_identity(record, first), 'PID identity differs before pidfd; refusing signal')
    try:
        descriptor = os.pidfd_open(record['pid'])
    except ProcessLookupError:
        return {'pid': record['pid'], 'alreadyStopped': True}
    try:
        second = reader.identity(record['pid'])
        if second is None:
            return {'pid': record['pid'], 'alreadyStopped': True}
        require(same_identity(record, second), 'PID identity differs after pidfd; refusing signal')
        try:
            signal.pidfd_send_signal(descriptor, signum)
        except ProcessLookupError:
            return {'pid': record['pid'], 'alreadyStopped': True}
        return {'pid': record['pid'], 'startTicks': record['startTicks'], 'commandSha256': record['commandSha256'],
                'signal': int(signum), 'identityChecks': [first, second], 'pidfdBound': True}
    finally:
        os.close(descriptor)


class OwnedTracker:
    """Only follows children of the exact runner and already identified JMH ForkedMain JVMs."""
    def __init__(self, reader, runner, java, classpath, event=lambda value: None):
        self.reader, self.java, self.classpath, self.event = reader, str(Path(java).resolve()), set(classpath), event
        self.runner = runner
        self.records = {runner['pid']: dict(runner, kind='runner', observedSamples=0, stopped=False)}
        self.active = {runner['pid']}
        self.candidates = {}
        self.errors = []
        self.event({'event': 'discovered', 'atUtc': now(), **self.records[runner['pid']]})

    def is_fork(self, actual, parent):
        args = actual['arguments']
        if args.count(FORK_MAIN) != 1 or not args or str(Path(args[0]).resolve()) != self.java:
            return False
        main = args.index(FORK_MAIN)
        if args.count('-cp') != 1 or args.index('-cp') + 2 != main or len(args) != main + 3:
            return False
        cp = args[main - 1].split(os.pathsep)
        return (set(cp) == self.classpath and len(cp) == len(self.classpath)
                and args.count('-Xms2g') == args.count('-Xmx2g') == 1
                and actual['parentPid'] == parent['pid']
                and actual['sessionId'] == actual['processGroupId'] == self.runner['pid']
                and loopback_host(args[-2])
                and args[-1].isdigit() and 0 < int(args[-1]) < 65536)

    def sample(self):
        try:
            self._sample()
        except Exception as error:
            message = type(error).__name__ + ': ' + str(error)
            if message not in self.errors:
                self.errors.append(message)
            raise

    def _sample(self):
        for pid in list(self.active):
            record = self.records[pid]
            actual = self.reader.identity(pid)
            if actual is None:
                record['stopped'] = True
                self.active.remove(pid)
                self.event({'event': 'stopped', 'pid': pid, 'startTicks': record['startTicks'], 'atUtc': now()})
                continue
            require(same_identity(record, actual), 'Owned PID changed identity: ' + str(pid))
            record['observedSamples'] += 1
            for child_pid in self.reader.children(pid):
                if child_pid in self.records:
                    known_child = self.reader.identity(child_pid)
                    require(known_child is None or same_identity(self.records[child_pid], known_child),
                            'Previously observed child PID reused')
                    continue
                child = self.reader.identity(child_pid)
                if child is None:
                    self.candidates.pop(child_pid, None)
                    continue
                require(len(self.records) < MAX_OWNED, 'Owned process coverage exceeds bound')
                if child_pid not in self.candidates:
                    require(len(self.records) + len(self.candidates) < MAX_OWNED, 'Owned candidate coverage exceeds bound')
                    self.candidates[child_pid] = {'pid': child_pid, 'startTicks': child['startTicks'],
                        'parentPid': pid, 'firstObservedMonotonic': time.monotonic()}
                candidate = self.candidates[child_pid]
                require(candidate['startTicks'] == child['startTicks'], 'Candidate PID reused')
                if self.is_fork(child, record):
                    # Second identity read also checks the parent/session after fork/exec completed.
                    second = self.reader.identity(child_pid)
                    if not (same_identity(child, second) and self.is_fork(second, record)):
                        raise ValueError('Fork changed during discovery')
                    self.records[child_pid] = dict(second, kind='fork', observedSamples=1, stopped=False)
                    self.active.add(child_pid)
                    self.candidates.pop(child_pid, None)
                    self.event({'event': 'discovered', 'atUtc': now(), **self.records[child_pid]})
                else:
                    require(time.monotonic() - candidate['firstObservedMonotonic'] < 2,
                            'Unverified owned descendant still running; no signal authorized')
        # Previously seen spawn helpers may have exited; never treat them as verified JVMs.
        for pid in list(self.candidates):
            if self.reader.identity(pid) is None:
                self.candidates.pop(pid)

    def summary(self):
        return {'records': list(self.records.values()), 'unverifiedCandidates': list(self.candidates.values()),
                'errors': self.errors, 'forkIdentitiesObserved': sum(r['kind'] == 'fork' for r in self.records.values()),
                'samplingIntervalSeconds': POLL_SECONDS,
                'scope': 'Sampled explicit runner/owned ForkedMain descendants only; no namespace enumeration. Missing fork coverage fails the stage.'}

    def ensure_stopped(self):
        self.sample()
        require(not self.active and not self.candidates and not self.errors, 'Owned cleanup cannot be proved complete')

    def cleanup(self, term_seconds=3, kill_seconds=3):
        actions, errors = [], []
        # Stop the runner first so it cannot intentionally launch the next measured fork.
        for signum, grace in ((signal.SIGTERM, term_seconds), (signal.SIGKILL, kill_seconds)):
            sent = set()
            deadline = time.monotonic() + grace
            while True:
                try:
                    self.sample()
                except Exception as error:
                    errors.append(str(error))
                for pid in sorted(self.active, key=lambda value: value != self.runner['pid']):
                    if pid in sent:
                        continue
                    try:
                        actions.append(safe_signal(self.records[pid], self.reader, signum))
                    except Exception as error:
                        errors.append(str(error))
                    sent.add(pid)
                if not self.active and not self.candidates:
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(POLL_SECONDS)
            if not self.active and not self.candidates:
                break
        try:
            self.ensure_stopped()
        except Exception as error:
            errors.append(str(error))
        self.errors.extend(errors)
        return {'passed': not self.errors and not self.active and not self.candidates, 'actions': actions,
                'errors': list(self.errors), 'processes': self.summary(), 'usedPidfdOnly': True}


def await_runner(child, arguments, reader):
    deadline = time.monotonic() + 2
    expected = command_sha(arguments)
    while True:
        record = reader.identity(child.pid)
        if record is not None and record['commandSha256'] == expected:
            second = reader.identity(child.pid)
            require(same_identity(record, second), 'Runner changed during identity capture')
            require(second['parentPid'] == os.getpid() and second['sessionId'] == second['processGroupId'] == child.pid,
                    'Runner parent/session differs')
            return second
        require(child.poll() is None and time.monotonic() < deadline, 'Owned runner exec identity failed')
        time.sleep(POLL_SECONDS)


def stage_arguments(dist, out, java):
    return [str(java), '-cp', str(Path(dist['root']) / 'lib/*'), 'org.openjdk.jmh.Main',
            'io.vectormatch.bench.jmh.Fresh.*', '-f', '3', '-wi', '500', '-i', '10',
            '-bs', '1', '-wbs', '1', '-foe', 'true', '-rf', 'json', '-rff', str(out)]


def run_stage(stage, dist, root, stop, java=BASE / 'tools/jdk/bin/java', timeout=1800):
    name = stage['id']
    out = root / (name + '.json')
    arguments = stage_arguments(dist, out, java)
    reader, child, tracker = ProcReader(), None, None
    started, cpu_start, wall_start = now(), time.process_time(), time.monotonic()
    failure = None
    cleanup = None
    summary = {'stage': name, 'group': stage['group'], 'sourceRevision': dist['revision'],
               'startedAtUtc': started, 'passed': False, 'arguments': arguments}
    with (root / (name + '-owned-processes.jsonl')).open('x') as events, (root / (name + '.log')).open('x') as log:
        def event(value):
            events.write(json.dumps(value, allow_nan=False) + '\n')
            events.flush()
        try:
            require(not stop['signal'], 'Stop requested before stage launch')
            child = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record = await_runner(child, arguments, reader)
            record.update(expectedCommandSha256=command_sha(arguments), actualCommandSha256=record['commandSha256'])
            save_new(root / (name + '-process.json'), record)
            classpath = [str(Path(dist['root']) / p) for p in sorted(LIBRARIES)]
            tracker = OwnedTracker(reader, record, java, classpath, event)
            deadline = time.monotonic() + timeout
            while True:
                tracker.sample()
                code = child.poll()
                if code is not None:
                    break
                require(not stop['signal'], 'Worker interrupted by signal ' + str(stop['signal']))
                require(time.monotonic() < deadline, 'Stage exceeded bounded deadline')
                time.sleep(POLL_SECONDS)
            summary['exitCode'] = code
            require(code == 0, 'JMH runner failed: ' + str(code))
            tracker.ensure_stopped()
            require(tracker.summary()['forkIdentitiesObserved'] == 45, 'Missing/extra measured fork identity coverage; expected45')
            summary['caseVerification'] = verify_rows(json.loads(out.read_text()))
            cleanup = {'passed': True, 'actions': [], 'naturalExit': True, 'processes': tracker.summary()}
            summary['passed'] = True
        except BaseException as error:
            failure = error
            summary.update(errorType=type(error).__name__, error=str(error), traceback=traceback.format_exc())
            if tracker is not None:
                cleanup = tracker.cleanup()
            elif child is not None:
                # Never signal an uncaptured PID. A fork/exec ownership failure is terminal, with manual review needed.
                cleanup = {'passed': child.poll() is not None, 'ownershipNotEstablished': True,
                           'scope': 'No signal sent because exact runner identity was not captured'}
            if child is not None:
                try:
                    summary['lateExitCode'] = child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    summary['unresolvedRunner'] = True
            if cleanup is None:
                cleanup = {'passed': True, 'noChildLaunched': True}
        finally:
            summary.update(completedAtUtc=now(), observerCpuSeconds=time.process_time() - cpu_start,
                           observerElapsedSeconds=time.monotonic() - wall_start,
                           cleanup=cleanup, interruptedSignal=stop['signal'])
            summary['rawFilesSha256'] = {p.name: sha(p) for p in (out, root / (name + '.log'),
                root / (name + '-process.json')) if p.is_file()}
            if out.is_file():
                summary['resultSha256'] = sha(out)
            summary['logSha256'] = sha(root / (name + '.log'))
            if tracker is not None:
                process_summary = root / (name + '-owned-process-summary.json')
                save_new(process_summary, tracker.summary())
                summary['rawFilesSha256'][process_summary.name] = sha(process_summary)
            events.flush()
            event_file = root / (name + '-owned-processes.jsonl')
            summary['rawFilesSha256'][event_file.name] = sha(event_file)
            save_new(root / (name + '-verification.json'), summary)
    require(failure is None and summary['passed'] and cleanup['passed'], 'Stage failed/cleanup incomplete: ' + name)
    return summary


def validate_plan(plan):
    require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9-]{0,99}', plan['jobId']) is not None, 'Invalid job ID')
    require(plan['hostname'] == 'ed6c0673f5cb', 'CPU hostname differs')
    stages = plan['stages']
    require(len(stages) == 4 and [s['group'] for s in stages] == ['A', 'B', 'A', 'B'], 'ABAB stages required')
    require([s['id'] for s in stages] == ['A1', 'B1', 'A2', 'B2'], 'Stage IDs must be exactly A1/B1/A2/B2')
    for stage in stages:
        for key, value in (('expectedCases', 15), ('forks', 3), ('warmup', 500), ('measurement', 10)):
            require(type(stage.get(key)) is int and stage[key] == value, 'Stage plan field differs: ' + key)
    return plan


def run_stages(plan, root, stop):
    receipt = {'jobId': plan['jobId'], 'startedAtUtc': now(), 'passed': False, 'stages': []}
    try:
        for stage in plan['stages']:
            receipt['activeStage'] = stage['id']
            require(not stop['signal'], 'Stop requested; no next stage')
            # Recheck the complete pair immediately before every next-stage launch.
            audit = audit_artifacts(plan)
            save_new(root / (stage['id'] + '-artifact-audit.json'), audit)
            result = run_stage(stage, plan['distributions'][stage['group']], root, stop)
            require(result['passed'] and result['cleanup']['passed'], 'No next stage after failed cleanup')
            post_audit = audit_artifacts(plan)
            require(post_audit == audit, 'Artifacts changed during stage; no next stage')
            post_path = root / (stage['id'] + '-artifact-audit-after.json')
            save_new(post_path, post_audit)
            result['postArtifactAuditSha256'] = sha(post_path)
            receipt['stages'].append(result)
        receipt['passed'] = True
    except BaseException as error:
        receipt.update(errorType=type(error).__name__, error=str(error), traceback=traceback.format_exc())
    finally:
        receipt.update(completedAtUtc=now(), interruptedSignal=stop['signal'])
        save_new(root / 'receipt.json', receipt)
    return receipt


def main():
    control = Path(__file__).resolve().parent
    plan = validate_plan(json.loads((control / 'plan.json').read_text()))
    require(sha(__file__) == plan['workerSha256'], 'Registered worker changed')
    require(platform.system() == 'Linux' and platform.node() == plan['hostname'], 'Wrong OS/host')
    require(not any(os.environ.get(k) for k in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS')),
            'Hidden JVM options rejected')
    require(sha(SUPERVISOR) == SUPERVISOR_SHA, 'Deployed original supervisor source changed')
    pidfd = enable_pidfd()
    root = BASE / 'runs' / plan['jobId']
    root.mkdir(exist_ok=False)
    save_new(root / 'plan.json', plan)
    with (root / 'worker.py').open('xb') as stream:
        stream.write(Path(__file__).read_bytes())
    java = BASE / 'tools/jdk/bin/java'
    save_new(root / 'environment.json', {'timestamp': now(), 'allowedCpuIds': sorted(os.sched_getaffinity(0)),
        'hostname': platform.node(), 'javaVersion': subprocess.check_output([str(java), '-version'], stderr=subprocess.STDOUT, text=True),
        'javaExecutableSha256': sha(java.resolve()), 'pidfdCompatibility': pidfd,
        'originalSupervisorPath': str(SUPERVISOR), 'affinityChanged': False, 'osTuningPerformed': False})
    stop = {'signal': None}
    def interrupted(signum, frame):
        stop['signal'] = int(signum)  # Cleanup remains bounded and is not interrupted by a second request.
    previous = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        result = run_stages(plan, root, stop)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    print(json.dumps(result, allow_nan=False), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
