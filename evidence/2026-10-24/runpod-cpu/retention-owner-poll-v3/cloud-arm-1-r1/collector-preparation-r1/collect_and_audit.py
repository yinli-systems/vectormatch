"""Default LOCAL dry-run; explicit read-only collection requires root process closure.

No Java, SQL, workload launch, remote writes, process signals, deletion or retries.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import build_config as b
from common import load_config

HERE = Path(__file__).resolve().parent
REMOTE_SHA = '0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'


def checked_config(path, expected):
    path = b.reference(path, expected)
    bound = json.loads((path.parent / 'CONFIG_BOUND.json').read_text())
    b.require(bound['passed'] is True and bound['configSha256'] == expected, 'Config builder receipt differs')
    c, r, rows, allow = load_config(path)
    b.require(allow == bound['sourceAllowlist'] and rows == bound['expectedSourceFiles'], 'Exact source allowlist differs')
    return c, r, allow


def closed_proof(path, expected, c, release):
    x = json.loads(b.reference(path, expected).read_text())
    b.require(x['schemaVersion'] == 2 and x['scope'] == 'ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_CONTROLLER'
              and x['rootVerified'] is True and x['arm'] == c['arm']
              and x['serverDriverMaximumParkNs'] == c['serverDriverMaximumParkNs']==100000
              and x['ownerPollMaximumParkNs'] == c['ownerPollMaximumParkNs']
              and x['frozenReleaseSha256'] == c['releaseSha256']
              and x['controllerSha256'] == release['controllerSha256']
              and x['job'] == c['remotePrep'] + '/arm-' + str(c['arm'])
              and x['controllerIdentityGone'] is True and x['allOwnedStopped'] is True,
              'Root must independently confirm this exact controller and all4 owned JVMs closed')
    for key in ['inspectionSha256', 'executedSourceSha256']:
        b.require(b.hexsha(x[key]), 'Root closure inspection source/result SHA required')
    return x


def preparation(expected):
    f = json.loads(b.reference(HERE / 'LOCAL_PREPARATION_FROZEN.json', expected).read_text())
    b.require(f['status'] == 'ROOT_REVIEWABLE_LOCAL_SOURCES_ONLY' and f['releaseReady'] is False,
              'Frozen local source preparation required')
    for name, row in f['sourceFiles'].items():
        p = b.reference(HERE / name, row['sha256'])
        b.require(p.stat().st_size == row['bytes'], 'Frozen preparation source size changed')
    return f


def invoke(args, output, label):
    with (output / (label + '.stdout')).open('xb') as out, (output / (label + '.stderr')).open('xb') as err:
        result = subprocess.run(args, stdout=out, stderr=err, timeout=1200)
    row = {'command': args, 'exitCode': result.returncode,
           'stdoutSha256': b.sha(output / (label + '.stdout')), 'stderrSha256': b.sha(output / (label + '.stderr'))}
    b.save(output / (label + '-execution.json'), row)
    return row


def execute(config, config_sha, output, proof, proof_sha, prep_sha, remote):
    preparation(prep_sha); c, release, allow = checked_config(config, config_sha)
    closed_proof(proof, proof_sha, c, release); remote = b.reference(remote, REMOTE_SHA)
    b.no_links(output); b.require(not output.exists(), 'Preserve failed/partial prior collection; new output required')
    output.mkdir(parents=True, mode=0o700)
    shutil.copy2(proof, output / 'root-controller-closed.json')
    b.save(output / 'REGISTRATION.json', {'arm': c['arm'], 'serverDriverMaximumParkNs': c['serverDriverMaximumParkNs'],
           'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],
           'configSha256': config_sha, 'rootClosureSha256': proof_sha, 'preparationSha256': prep_sha,
           'remoteHelperSha256': REMOTE_SHA, 'sourceAllowlist': allow, 'noAutomaticRetry': True})
    steps = []
    try:
        py = sys.executable; collected = output / 'collection'; native = output / 'native'; raw = output / 'raw'; full = output / 'all-outcome-bytes'
        steps.append(invoke([py, '-B', str(HERE / 'collect_closed_round.py'), '--config', str(config),
                            '--dest', str(collected), '--remote-helper', str(remote), '--collect-readonly'], output, 'collect-readonly'))
        b.require(steps[-1]['exitCode'] == 0, 'Read-only collection failed; retain partial evidence without retry')
        steps.append(invoke([py, '-B', str(HERE / 'verify_closed_archives.py'), '--collection', str(collected),
                            '--output', str(full)], output, 'full-native-byte-closure'))
        for label, script, dest in [('strict-native', 'audit_native_artifacts.py', native), ('strict-raw', 'audit_raw.py', raw)]:
            steps.append(invoke([py, '-B', str(HERE / script), '--config', str(config), '--collection', str(collected),
                                '--out', str(dest)], output, label))
        if all(s['exitCode'] == 0 for s in steps):
            steps.append(invoke([py, '-B', str(HERE / 'finalize_local_collection.py'), '--config', str(config),
                                '--collection', str(collected), '--native-audit', str(native), '--raw-audit', str(raw),
                                '--out', str(output / 'finalized')], output, 'finalize'))
        preparation(prep_sha)
        report = {'passed': len(steps) == 5 and all(s['exitCode'] == 0 for s in steps), 'arm': c['arm'],
                  'serverDriverMaximumParkNs':c['serverDriverMaximumParkNs'],'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],
                  'steps': steps, 'nextArmAuthorized': False,
                  'rootGateCreated': False, 'allFailuresRetained': True, 'cpuCapacityClaimed': False}
        b.save(output / ('SUCCESS.json' if report['passed'] else 'DIAGNOSTICS_ONLY.json'), report)
        return report
    except BaseException as error:
        b.save(output / 'FAILED.json', {'passed': False, 'error': repr(error), 'traceback': traceback.format_exc(),
               'steps': steps, 'allPartialRawAndFailuresRetained': True, 'noAutomaticRetry': True})
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--config', type=Path, required=True); p.add_argument('--config-sha256', required=True)
    p.add_argument('--output', type=Path); p.add_argument('--controller-closed-proof', type=Path)
    p.add_argument('--controller-closed-sha256'); p.add_argument('--preparation-sha256')
    p.add_argument('--remote-helper', type=Path); p.add_argument('--collect-readonly', action='store_true')
    a = p.parse_args(); c, r, allow = checked_config(a.config, a.config_sha256)
    if not a.collect_readonly:
        print(json.dumps({'localConfigValid': True, 'arm': c['arm'], 'remoteAccessed': False, 'sourceAllowlist': allow})); return
    b.require(all([a.output, a.controller_closed_proof, a.controller_closed_sha256, a.preparation_sha256, a.remote_helper]),
              'Explicit new destination, frozen sources and root controller-closed receipt required')
    result = execute(a.config, a.config_sha256, a.output, a.controller_closed_proof, a.controller_closed_sha256,
                     a.preparation_sha256, a.remote_helper)
    print(json.dumps(result)); raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
