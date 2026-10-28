"""Pod-local ABAB: default sync2 recording versus opt-in sync1 recording data on initialized segments.

Mirrors the closed recording-initialization controller (same launch matrix, diagnostics, settling,
audit and selection rule) but executes on the pod itself. The only A/B difference is the B pair of
properties -Dvectormatch.stage.initializeRecording=true and -Dvectormatch.archive.dataSyncLevel=1.
Catalog and consensus remain sync2 in every arm. Large recording segments are deleted only after
their hashes are in MEMBER_MANIFEST.json and the audit has passed, to stay inside the root disk."""
from pathlib import Path
import concurrent.futures, fcntl, hashlib, json, os, shutil, subprocess, sys, time, traceback

ROOT = os.environ.get('VM_ROOT', '/opt/vectormatch-cpu/experiments/archive-sync1-20261027-r1')
P = Path(ROOT)
PLAN = json.loads((P / 'PLAN.json').read_text())
JAVA = json.loads((P / 'CANDIDATE.json').read_text())['javaPath']


def checked(code, timeout=60):
    r = subprocess.run(['python3', '-'], input=code, capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stdout + '\n' + r.stderr
    return json.loads(r.stdout)


def save(path, value):
    body = json.dumps(value, indent=2) + '\n'
    if path.exists():
        assert json.loads(path.read_text()) == value
    else:
        path.write_text(body)


def progress(value):
    value['epoch'] = time.time()
    (P / 'PROGRESS.json').write_text(json.dumps(value, indent=2) + '\n')
    with (P / 'PROGRESS.log').open('a') as log:
        log.write(json.dumps(value) + '\n')


def config(role, case, seconds):
    prefix = ROOT + '/experiments/' + case
    run = prefix + '/node%d-g0' % role
    spec = PLAN['cases'][case]
    env = dict(VECTOR_AERON_MTU_LENGTH='1248', VECTOR_CLUSTER_HOSTS='127.0.0.1,127.0.0.1,127.0.0.1',
               VECTOR_CLIENT_EGRESS_HOST='127.0.0.1', VECTOR_OUTBOX_CAPACITY='524288')
    state = prefix + ('/evidence' if role == 3 else '/state')
    telemetry = prefix + '/telemetry/node%d-g0' % role
    props = ['-Dvectormatch.stage.initializeRecording=' + str(spec['initializeRecording']).lower(),
             '-Dvectormatch.forceWait.enabled=' + str(spec['forceWait']).lower(),
             '-Dvectormatch.forceWait.library=' + ROOT + '/libvmforce.so',
             '-Dvectormatch.forceWait.directory=' + prefix + '/force-wait/node%d-g0' % role,
             '-Dvectormatch.stage.preallocate=' + str(spec['preallocate']).lower(),
             '-Dvectormatch.stage.clockLibrary=' + ROOT + '/libvmclock.so',
             '-Dvectormatch.stage.directory=' + prefix + '/stages/node%d-g0' % role,
             '-Dvectormatch.stage.capacity=2097152',
             '-Dvectormatch.stage.trace=' + str(spec['traceEnabled']).lower(),
             '-Daeron.cluster.max.sessions=256',
             '-Xlog:class+load=info:file=' + run + '/class-origins.log',
             '-javaagent:' + ROOT + '/soak-agent.jar=' + state + ',' + telemetry,
             '-Xlog:gc*,safepoint:file=' + run + '/gc.log:time,uptime,level,tags:filecount=2,filesize=10M']
    # Collector tuning applies to all four JVMs; process_agent places these after its fixed heap/collector flags.
    props += spec.get('jvmExtra', [])
    if role == 3:
        # Load-generator only (e.g. a young generation large enough that it never collects during the window).
        props += spec.get('sourceJvmExtra', [])
    if role < 3:
        props += ['-Daeron.cluster.appointed.leader.id=0', '-Dvectormatch.node.dataPathMaxParkNs=' + str(spec['maxParkNs'])]
        if spec['archiveDataSync1']:
            props += ['-Dvectormatch.archive.dataSyncLevel=1']
        args = ['io.vectormatch.cluster.ReplicatedPathProbeNode', spec['mode'], prefix + '/worker-%d.csv' % role, str(role),
                prefix + '/state', str(PLAN['portBase']), str(spec.get('sync', 2)), '524288', env['VECTOR_CLUSTER_HOSTS'], 'capacity-190k-v1', '131072', 'SHARED']
    else:
        args = ['io.vectormatch.cluster.ReplicatedPathProbe', prefix + '/evidence', str(PLAN['portBase']), str(spec['rate']), str(seconds), spec['mode']]
    return dict(root=ROOT, java=JAVA, boot=PLAN['boot'], host=PLAN['host'], case=case, generation='node%d-g0' % role,
                deadline=time.time() + seconds + 900, environment=env, properties=props, mainArgs=args, collector=spec.get('collector', 'G1'),
                cpus=spec.get('cpuSets', PLAN['cpuSets'])[role])


def start(cfg):
    control = P / 'control'
    control.mkdir(exist_ok=True)
    name = cfg['case'] + '-' + cfg['generation']
    launch = control / (name + '.launch.json')
    if launch.exists():
        return json.loads(launch.read_text())
    cf = control / (name + '.json')
    cf.open('x').write(json.dumps(cfg))
    log = (control / (name + '.log')).open('xb')
    with cf.open('rb') as inp:
        q = subprocess.Popen(['python3', str(P / 'process_agent.py')], stdin=inp, stdout=log, stderr=log, start_new_session=True)
    s = Path('/proc/' + str(q.pid) + '/stat').read_text().split(') ', 1)[1].split()
    v = {'pid': q.pid, 'startTicks': s[19]}
    launch.write_text(json.dumps(v))
    return v


def status(case):
    p = P / 'experiments' / case
    out = []
    for i in range(4):
        d = p / ('node%d-g0' % i)
        out.append({n: (d / n).read_text()[-6000:] if (d / n).exists() else None for n in ['LAUNCH.json', 'EXIT.json', 'stdout.log', 'stderr.log']})
    f = p / 'evidence/soak-minute-windows.csv'
    return {'roles': out, 'free': shutil.disk_usage(ROOT).free, 'minutes': f.read_text()[-1600:] if f.exists() else None}


def stop(role, case):
    p = P / 'experiments' / case / ('node%d-g0' % role)
    if not (p / 'LAUNCH.json').exists():
        return
    r = json.loads((p / 'LAUNCH.json').read_text())
    assert Path('/proc/sys/kernel/random/boot_id').read_text().strip() == r['boot']
    if not (p / 'EXIT.json').exists():
        fields = Path('/proc/%d/stat' % r['pid']).read_text().split(') ', 1)[1].split()
        assert fields[19] == r['startTicks']
        option = next(x for x in r['argv'] if x.startswith('-javaagent:'))
        dest = Path(option.split(',', 1)[1]) / 'final-buffered-tail.jfr'
        if not dest.exists():
            q = subprocess.run([str(Path(JAVA).with_name('jcmd')), str(r['pid']), 'JFR.dump', 'name=1', 'filename=' + str(dest)],
                               capture_output=True, text=True, timeout=30)
            (p / 'JFR_CONTROLLED_DUMP.json').write_text(json.dumps(dict(returncode=q.returncode, stdout=q.stdout, stderr=q.stderr), indent=2))
        (p / 'stop.json').write_text(json.dumps({'epoch': time.time()}))


def stop_all(case):
    ss = status(case)['roles']
    if ss[3]['LAUNCH.json'] and not ss[3]['EXIT.json']:
        stop(3, case)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda i: stop(i, case), range(3)))
    for _ in range(40):
        ss = status(case)['roles']
        if all(not s['LAUNCH.json'] or s['EXIT.json'] for s in ss):
            return
        time.sleep(1)
    raise RuntimeError('owned child closure not confirmed')


def java_processes():
    rows = []
    for f in Path('/proc').glob('[0-9]*/comm'):
        try:
            if f.read_text().strip() == 'java':
                rows.append(str(f))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rows


def capture_initialization(case):
    p = P / 'experiments' / case
    ready = time.monotonic_ns()
    assert not (p / 'node3-g0/LAUNCH.json').exists()
    time.sleep(30)
    started = time.monotonic_ns()
    rows = []
    for role in range(3):
        files = []
        for f in sorted((p / ('state/node-%d/archive' % role)).glob('*.rec')):
            assert not f.is_symlink()
            s = f.stat()
            h = hashlib.sha256()
            with f.open('rb') as inp:
                for b in iter(lambda: inp.read(1024 ** 2), b''):
                    h.update(b)
            files.append({'relative': str(f.relative_to(p)), 'logicalBytes': s.st_size, 'allocatedBytes': s.st_blocks * 512,
                          'device': s.st_dev, 'inode': s.st_ino, 'sha256BeforeSource': h.hexdigest()})
        assert len(files) == 1, files
        rows.append({'role': role, 'files': files, 'capturedEpoch': time.time(), 'capturedMonotonicNs': time.monotonic_ns()})
    v = {'beforeSourceLaunch': True, 'settleSeconds': 30, 'readyObservedMonotonicNs': ready, 'captureStartedMonotonicNs': started, 'roles': rows}
    (p / 'RECORDING_INITIALIZATION.json').open('x').write(json.dumps(v, indent=2) + '\n')
    save(P / (case + '-INITIALIZATION.json'), v)


def start_governor(case, spec):
    """Thread-level isolation: one CPU per data-path agent, other JVM threads on housekeeping CPUs."""
    settings = dict(cpuSets=spec['cpuSets'], housekeeping=spec['pinThreads']['housekeeping'],
                    expectedAgents=spec['pinThreads'].get('expectedAgents', {'node': 4, 'source': 3}),
                    compilerNice=spec['pinThreads'].get('compilerNice'),
                    roles=spec['pinThreads'].get('roles', [0, 1, 2, 3]))
    governor = subprocess.Popen(['python3', str(Path(__file__).with_name('pin_threads.py')),
                                 str(P / 'experiments' / case), json.dumps(settings)])
    time.sleep(1)
    if governor.poll() is not None:
        raise RuntimeError('thread governor exited at startup with %s' % governor.returncode)
    return governor


def stop_governor(case, governor):
    governor.terminate()
    try:
        governor.wait(timeout=30)
    except subprocess.TimeoutExpired:
        governor.kill()
        governor.wait()
    summary = P / 'experiments' / case / 'thread-pinning-summary.json'
    result = json.loads(summary.read_text()) if summary.exists() else None
    save(P / (case + '-THREAD_PINNING.json'), dict(returncode=governor.returncode, summary=result))


def run(case, seconds):
    progress({'stage': 'native_start', 'case': case, 'seconds': seconds})
    assert not java_processes() and shutil.disk_usage(ROOT).free > 1_800_000_000
    spec = PLAN['cases'][case]
    governor = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda i: start(config(i, case, seconds)), range(3)))
        for _ in range(100):
            ss = status(case)['roles'][:3]
            assert not any(s['EXIT.json'] for s in ss), ss
            if all('VECTOR_CLUSTER_STARTED' in (s['stdout.log'] or '') for s in ss):
                break
            time.sleep(.5)
        else:
            raise RuntimeError('cluster startup timeout')
        save(P / (case + '-nodes-ready.json'), ss)
        capture_initialization(case)
        if spec.get('pinThreads'):
            governor = start_governor(case, spec)
        start(config(3, case, seconds))
        until = time.monotonic() + seconds + 700
        next_progress = 0
        while time.monotonic() < until:
            state = status(case)
            s = state['roles'][3]
            if time.monotonic() >= next_progress:
                next_progress = time.monotonic() + 30
                progress({'stage': 'native_active', 'case': case, 'free': state['free']})
            assert state['free'] >= 512 * 1024 ** 2, 'disk floor; preserve original partial outcomes'
            assert not any(x['EXIT.json'] for x in state['roles'][:3]), 'replica exited'
            if s['EXIT.json']:
                save(P / (case + '-client-exit.json'), s)
                assert json.loads(s['EXIT.json'])['returncode'] == 0, s
                break
            time.sleep(5)
        else:
            raise RuntimeError('client watchdog')
    finally:
        if governor is not None:
            stop_governor(case, governor)
        stop_all(case)
    save(P / (case + '-closed.json'), status(case))
    progress({'stage': 'native_closed', 'case': case})


def sync_markers(case):
    """Every B replica announces recording data sync1 with catalog/consensus sync2; no A replica does."""
    spec = PLAN['cases'][case]
    p = P / 'experiments' / case
    lines = []
    for role in range(3):
        out = (p / ('node%d-g0' % role) / 'stdout.log').read_text().splitlines()
        marks = [l for l in out if l.startswith('VECTOR_ARCHIVE_DATA_SYNC ')]
        expected = ['VECTOR_ARCHIVE_DATA_SYNC node=%d recordingData=1 catalog=2 consensus=2' % role] if spec['archiveDataSync1'] else []
        assert marks == expected, (case, role, marks)
        argv = json.loads((p / ('node%d-g0' % role) / 'LAUNCH.json').read_text())['argv']
        assert ('-Dvectormatch.archive.dataSyncLevel=1' in argv) == spec['archiveDataSync1'], (case, role)
        lines += marks
    return {'archiveDataSync1': spec['archiveDataSync1'], 'markers': lines}


def close(case):
    p = P / 'experiments' / case
    for i in range(4):
        assert (p / ('node%d-g0' % i) / 'EXIT.json').is_file()
    assert (p / 'evidence/complete.json').is_file()
    host = p / 'host.json'
    if not host.exists():
        host.write_text(json.dumps({'bootId': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'clockTicksPerSecond': os.sysconf('SC_CLK_TCK')}))
    files = {}
    for f in sorted(p.rglob('*')):
        assert not f.is_symlink()
        if not f.is_file() or f.name in ['MEMBER_MANIFEST.json', 'AUDIT.json', 'AUDIT_RUN.json', 'complete.json']:
            continue
        h = hashlib.sha256()
        with f.open('rb') as inp:
            for b in iter(lambda: inp.read(1024 ** 2), b''):
                h.update(b)
        files[str(f.relative_to(p))] = {'bytes': f.stat().st_size, 'sha256': h.hexdigest()}
    save(p / 'MEMBER_MANIFEST.json', {'files': files})
    # sync0 has no per-write force, so only the base audit (every frame, outcome, replay and latency) applies.
    auditor = 'audit-replicated-path-probe.py' if PLAN['cases'][case].get('auditMode') == 'base' else 'audit-recording-initialization.py'
    q = subprocess.run(['python3', ROOT + '/' + auditor, str(p), '--jfr', str(Path(JAVA).with_name('jfr')),
                        '--output', str(p / 'AUDIT.json')], capture_output=True, text=True, timeout=600)
    (p / 'AUDIT_RUN.json').write_text(json.dumps({'returncode': q.returncode, 'stdout': q.stdout, 'stderr': q.stderr}, indent=2))
    assert q.returncode == 0, q.stderr
    audit = json.loads((p / 'AUDIT.json').read_text())
    audit['archiveDataSync'] = sync_markers(case)
    save(P / (case + '-AUDIT.json'), audit)
    retired = []
    for f in sorted((p / 'state').glob('node-*/archive/*.rec')):
        retired.append({'relative': str(f.relative_to(p)), 'sha256': files[str(f.relative_to(p))]['sha256']})
        f.unlink()
    save(P / (case + '-RETIRED_SEGMENTS.json'), {'reason': 'root disk headroom; hashes retained in MEMBER_MANIFEST.json', 'files': retired})
    progress({'stage': 'closed_audited', 'case': case, 'latency': audit['fullLatency'], 'gate': audit['registeredGatePass']})
    return audit


def main():
    with (P / 'CONTROLLER.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            audits = {}
            cases = list(PLAN['cases'])
            for case in cases[:6]:
                run(case, PLAN['cases'][case]['seconds'])
                audits[case] = close(case)
            final = {n: json.loads((P / 'experiments' / n / 'MEMBER_MANIFEST.json').read_text())['files']['evidence/cluster-final.bin']['sha256'] for n in cases[:6]}
            assert final[cases[0]] == final[cases[1]], 'functional final states differ'
            state_equal = len({final[n] for n in cases[2:6]}) == 1
            pairs = []
            for a, b in [(cases[2], cases[3]), (cases[4], cases[5])]:
                x, y = audits[a], audits[b]
                # fullLatency is null unless every original was accepted; such a pair cannot pass.
                measured = x['fullLatency'] is not None and y['fullLatency'] is not None
                q = y['fullLatency']['p99Us'] / x['fullLatency']['p99Us'] if measured else None
                qq = y['fullLatency']['p999Us'] / x['fullLatency']['p999Us'] if measured else None
                base_ok = all(v for k, v in x['gates'].items() if k not in ['p99AtMost25ms', 'p999AtMost100ms', 'everyMinuteP99AtMost25ms'])
                pairs.append(dict(a=a, b=b, p99Ratio=q, p999Ratio=qq, baselineLatencyGate=x['registeredGatePass'], baselineNonLatencyGates=base_ok,
                                  candidateGate=y['registeredGatePass'],
                                  passes=measured and state_equal and base_ok and y['registeredGatePass'] and q <= .90 and qq <= 1.0))
            selected = all(v['passes'] for v in pairs)
            save(P / 'SELECTION.json', dict(pairs=pairs, finalStateEqual=state_equal, candidateSelected=selected, rule=PLAN['selection']))
            progress({'stage': 'selection', 'pairs': pairs, 'candidateSelected': selected})
            if selected:
                case = cases[6]
                run(case, PLAN['cases'][case]['seconds'])
                audits[case] = close(case)
            save(P / 'COMPLETE.json', dict(cases=list(audits), candidateSelected=selected, sustainedExecuted=selected,
                                            sustainedGatePass=audits[cases[6]]['registeredGatePass'] if selected else None, defaultPromoted=False))
            progress({'stage': 'complete', 'candidateSelected': selected})
        except BaseException as e:
            save(P / ('FAILURE-' + str(time.time_ns()) + '.json'), {'error': repr(e), 'traceback': traceback.format_exc()})
            progress({'stage': 'failure', 'error': repr(e)})
            raise


if __name__ == '__main__':
    main()
