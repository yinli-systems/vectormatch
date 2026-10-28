"""Unattended pod-B pipeline: sweep -> pick -> ABAB confirm -> sync0 ladder -> durable ladder -> summary.

Usage: VM_LAYOUT='{"one": [...], "two": [...], "spinSource": [...]}' autopilot.py STAGING_DIR [SWEEP_ROOT|run]
With "run" (the default) the sync0 configuration sweep is the first stage; "abab:A:B" skips the sweep and
confirms configuration B against A, then runs the ladders on the winner. Every decision follows a fixed, logged rule. Each stage gets a fresh write-once root; a failing stage is
recorded and the pipeline continues with the stages that do not depend on it."""
from pathlib import Path
import glob, json, os, signal, subprocess, sys, time, traceback

STAGE = Path(sys.argv[1])
SWEEP_ARG = sys.argv[2] if len(sys.argv) > 2 else 'run'
EXPERIMENTS = Path('/opt/vectormatch-b/experiments')
RUNTIME = '/opt/vectormatch-b/runtime-r5'
STAMP = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
HOME = EXPERIMENTS / ('autopilot-' + STAMP)
LOG = HOME / 'AUTOPILOT.log'

LAYOUT = json.loads(os.environ['VM_LAYOUT'])
ONE, TWO = LAYOUT['one'], LAYOUT['two']
# Busy spin: node agents never park, and the source's driver and response loop spin, so the source gets two cores.
SPIN = TWO[:3] + [LAYOUT['spinSource']]
CONFIGS = {'c1p100': dict(cpuSets=ONE, maxParkNs=100000),
           'c2p100': dict(cpuSets=TWO, maxParkNs=100000),
           'c2p1': dict(cpuSets=TWO, maxParkNs=1000),
           'c2spin': dict(cpuSets=SPIN, maxParkNs=0, jvmExtra=['-Dvectormatch.client.driverMaxParkNs=0']),
           # Busy spin plus thread-level isolation: each data-path agent on its own CPU, other threads on housekeeping.
           'c2spinpin': dict(cpuSets=SPIN, maxParkNs=0, jvmExtra=['-Dvectormatch.client.driverMaxParkNs=0'],
                             pinThreads=dict(housekeeping=LAYOUT['spinSource'][-1:]))}
BASELINE = 'c1p100'
SYNC0 = dict(mode='MATCHING', traceEnabled=True, preallocate=False, forceWait=False, initializeRecording=True,
             archiveDataSync1=False, collector='G1', jvmExtra=[], sync=0, auditMode='base')
DURABLE = dict(mode='MATCHING', traceEnabled=True, preallocate=False, forceWait=True, initializeRecording=True,
               archiveDataSync1=True, collector='G1', jvmExtra=[], sync=2)
SYNC0_RATES = [1000, 2000, 5000, 8000, 12000, 20000, 30000, 50000]
DURABLE_RATES = [1000, 2000, 3000, 5000, 8000, 12000]
SELECTION = ("First six originals in order. Every A/B source/completion/correctness gate and exact joins must pass, states "
             "must agree. Both B latency gates must pass: p99<=25ms,p999<=100ms,every-minute-p99<=25ms. EACH pair B/A "
             "p99<=0.90,p999<=1.00. Only then run confirm-b1 (a third 22s B window at 8000/s). No default promotion.")
COMMON_SCOPE = ("pod " + os.environ.get('RUNPOD_POD_ID', 'unknown') + " cpu layout " + json.dumps(LAYOUT) + "; runtime-r5 (busy-spin option for node data path and client driver); "
                "three replicas and source on one host over loopback (no physical failure domain); 180,000-original probe bound")
VENDOR = [dict(source='AWS 2025 (Adaptive): Aeron Cluster Premium round trip', us=98,
               url='https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/'),
          dict(source='Google Cloud 2024 (Adaptive): Aeron open-source transport round trip', us=57,
               url='https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/')]


class SkipSweep(Exception):
    pass


def log(**event):
    event['utc'] = time.time()
    with LOG.open('a') as f:
        f.write(json.dumps(event) + '\n')
    print(json.dumps(event), flush=True)


def clean_jvms():
    """Stop leftover experiment JVMs (by PID, never by pattern from a shell) before a stage starts."""
    def owned():
        pids = []
        for d in glob.glob('/proc/[0-9]*'):
            try:
                cmd = Path(d, 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
                if Path(d, 'comm').read_text().strip() == 'java' and str(EXPERIMENTS) in cmd:
                    pids.append(int(Path(d).name))
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                pass
        return pids
    pids = owned()
    for sig, wait in [(signal.SIGTERM, 20), (signal.SIGKILL, 10)]:
        for p in pids:
            try:
                os.kill(p, sig)
            except ProcessLookupError:
                pass
        deadline = time.time() + wait
        while owned() and time.time() < deadline:
            time.sleep(1)
        pids = owned()
        if not pids:
            break
    if pids:
        raise RuntimeError('experiment JVMs survived SIGKILL: %s' % pids)


def running(fragment):
    for d in glob.glob('/proc/[0-9]*'):
        try:
            if fragment in Path(d, 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace'):
                return True
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
    return False


def case(base, config, rate, seconds):
    d = dict(base)
    d.update(CONFIGS[config])
    d.update(rate=rate, seconds=seconds)
    return d


def stage(name, cases, scope, runner):
    """Create a fresh root with setup_b.py and run campaign.py (ABAB) or ladder.py; return the root."""
    root = EXPERIMENTS / ('%s-%s' % (name, STAMP))
    spec = HOME / (name + '-cases.json')
    spec.write_text(json.dumps(dict(cases=cases, selection=SELECTION, scope=scope + '; ' + COMMON_SCOPE), indent=2) + '\n')
    clean_jvms()
    env = dict(os.environ, VM_RUNTIME=RUNTIME, VM_CPUSETS=json.dumps(ONE))
    subprocess.run(['python3', str(STAGE / 'setup_b.py'), str(root), str(spec), str(STAGE / 'campaign.py')],
                   env=env, check=True, capture_output=True, text=True)
    for helper in {runner, 'pin_threads.py'} - {'campaign.py'}:
        (root / helper).write_bytes((STAGE / helper).read_bytes())
    log(stage=name, event='start', root=str(root), cases=list(cases))
    with (root / (runner + '.out')).open('w') as out:
        rc = subprocess.run(['python3', str(root / runner)], cwd=root, env=dict(os.environ, VM_ROOT=str(root)),
                            stdout=out, stderr=subprocess.STDOUT).returncode
    clean_jvms()
    log(stage=name, event='finish', root=str(root), returncode=rc)
    return root


def read_rows(root, suffix):
    return [json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(root / ('*-' + suffix))))]


def pick(rows):
    """Rule: lowest p99 at 8000/s among configurations whose 8000/s case passed every gate; else at 1000/s."""
    for rate in (8000, 1000):
        passing = [r for r in rows if r['rate'] == rate and r.get('registeredGatePass')]
        if passing:
            best = min(passing, key=lambda r: r['latency']['p99Us'])
            return best['case'].rsplit('-r', 1)[0], rate, best['latency']['p99Us']
    return BASELINE, None, None


def ladder_cases(base, config, rates):
    cases = {}
    for rate in rates:
        seconds = min(60, 180000 // rate)
        cases['r%d' % rate] = case(base, config, rate, seconds)
        cases['r%d-repeat' % rate] = case(base, config, rate, seconds)
    return cases


def production(row):
    lat = row.get('latency')
    return bool(row.get('registeredGatePass') and lat and lat['p99Us'] <= 5000 and lat['p999Us'] <= 20000)


def summarize(state):
    lines = ['# Pod B autopilot summary (%s UTC)' % STAMP, '',
             'All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,',
             'outcome, matching replay and final canonical state verified by the audit. Latency is measured from each',
             "order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.", '']
    sweep = state.get('sweep', [])
    if sweep:
        lines += ['## Sync0 configuration sweep (exploratory)', '',
                  '| case | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | gates |', '|---|---|---|---|---|---|']
        for r in sweep:
            lat, rtt = r.get('latency') or r.get('latencyFromSamples') or {}, r.get('offerToReply') or {}
            lines.append('| %s | %s | %s | %s | %s | %s |' % (r['case'], lat.get('p50Us'), lat.get('p99Us'), lat.get('p999Us'),
                                                              rtt.get('p50Us'), 'pass' if r.get('registeredGatePass') else 'FAIL'))
        lines += ['', 'Pick rule: %s → **%s**' % (state['pickRule'], state['picked']), '']
    if 'abab' in state:
        lines += ['## Sync0 ABAB confirmation at 8000/s', '', '```', json.dumps(state['abab'], indent=2), '```', '']
    for key, title in [('sync0Ladder', 'Sync0 capacity ladder (Aeron default durability)'),
                       ('durableLadder', 'Durable capacity ladder (sync2 consensus/catalog, sync1 recording data)')]:
        rows = state.get(key)
        if rows is None:
            continue
        lines += ['## ' + title + ' — config ' + state['ladderConfig'], '',
                  '| rung | rate/s | p50 µs | p99 µs | p99.9 µs | offer→reply p50 µs | counts | 25 ms gates | production target (p99≤5 ms, p99.9≤20 ms) |',
                  '|---|---|---|---|---|---|---|---|---|']
        for r in rows:
            lat, rtt = r.get('latency') or r.get('latencyFromSamples') or {}, r.get('offerToReply') or {}
            lines.append('| %s | %d | %s | %s | %s | %s | %s | %s | %s |' % (
                r['case'], r['rate'], lat.get('p50Us'), lat.get('p99Us'), lat.get('p999Us'), rtt.get('p50Us'),
                r.get('counts'), 'pass' if r.get('registeredGatePass') else 'FAIL', 'yes' if production(r) else 'no'))
        lines.append('')
    lines += ['## Vendor reference points (not like-for-like)', '']
    lines += ['- %s: %d µs ([source](%s))' % (v['source'], v['us'], v['url']) for v in VENDOR]
    lines += ['', 'Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;',
              "our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.",
              'Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.',
              'Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.', '']
    (HOME / 'SUMMARY.md').write_text('\n'.join(lines))
    (HOME / 'SUMMARY.json').write_text(json.dumps(state, indent=2) + '\n')


def main():
    HOME.mkdir(parents=True, exist_ok=False)
    state = dict(stamp=STAMP, sweepArgument=SWEEP_ARG, runtime=RUNTIME, layout=LAYOUT, errors=[])
    log(event='autopilot_start', home=str(HOME))
    try:
        if SWEEP_ARG.startswith('abab:'):
            raise SkipSweep
        if SWEEP_ARG == 'run':
            sweep = {'%s-r%d' % (k, rate): case(SYNC0, k, rate, seconds) for rate, seconds in [(1000, 60), (8000, 22), (20000, 9)] for k in CONFIGS}
            SWEEP = stage('sync0-sweep', sweep, 'exploratory sync0 sweep of CPU layout and idle park; no selection', 'sweep.py')
        else:
            SWEEP = Path(SWEEP_ARG)
            while running(str(SWEEP) + '/sweep.py'):
                time.sleep(30)
        state['sweepRoot'] = str(SWEEP)
        state['sweep'] = read_rows(SWEEP, 'SWEEP_ROW.json')
        picked, at, p99 = pick(state['sweep'])
        state.update(picked=picked, pickRate=at, pickP99Us=p99,
                     pickRule='lowest p99 at 8000/s among gate-passing configurations, else at 1000/s, else baseline')
        log(event='picked', config=picked, rate=at, p99Us=p99, sweepRows=len(state['sweep']))
    except SkipSweep:
        _, base, picked = SWEEP_ARG.split(':')
        state.update(baseline=base, picked=picked, pickRule='named on the command line; no sweep')
    except Exception:
        state['errors'].append(dict(stage='sweep', traceback=traceback.format_exc()))
        state.update(picked=BASELINE, pickRule='sweep unreadable; baseline')
    summarize(state)

    baseline = state.get('baseline', BASELINE)
    ladder_config = baseline
    if state['picked'] != baseline:
        a, b = baseline, state['picked']
        cases = {'functional-a': case(SYNC0, a, 10, 2), 'functional-b': case(SYNC0, b, 10, 2),
                 'ab-a1': case(SYNC0, a, 8000, 22), 'ab-b1': case(SYNC0, b, 8000, 22),
                 'ab-a2': case(SYNC0, a, 8000, 22), 'ab-b2': case(SYNC0, b, 8000, 22), 'confirm-b1': case(SYNC0, b, 8000, 22)}
        try:
            root = stage('sync0-abab', cases, 'sync0 ABAB; sole switch %s (A) vs %s (B)' % (a, b), 'campaign.py')
            selection = json.loads((root / 'SELECTION.json').read_text())
            state['abab'] = dict(root=str(root), a=a, b=b, **selection)
            if selection['candidateSelected']:
                ladder_config = b
        except Exception:
            state['errors'].append(dict(stage='sync0-abab', traceback=traceback.format_exc()))
    state['ladderConfig'] = ladder_config
    log(event='ladder_config', config=ladder_config)
    summarize(state)

    for key, name, base, rates, scope in [
            ('sync0Ladder', 'sync0-ladder', SYNC0, SYNC0_RATES, 'sync0 ladder (Aeron default durability: majority replication, no per-write force)'),
            ('durableLadder', 'durable-ladder', DURABLE, DURABLE_RATES, 'durable ladder: consensus/catalog sync2, recording data sync1, initialized segments')]:
        try:
            root = stage(name, ladder_cases(base, ladder_config, rates), scope + '; config ' + ladder_config, 'ladder.py')
            state[key] = read_rows(root, 'LADDER_ROW.json')
            state[key].sort(key=lambda r: (r['rate'], r['case'].endswith('-repeat')))
            state[key + 'Root'] = str(root)
        except Exception:
            state['errors'].append(dict(stage=name, traceback=traceback.format_exc()))
        summarize(state)
    log(event='autopilot_complete', summary=str(HOME / 'SUMMARY.md'), errors=len(state['errors']))


if __name__ == '__main__':
    main()
