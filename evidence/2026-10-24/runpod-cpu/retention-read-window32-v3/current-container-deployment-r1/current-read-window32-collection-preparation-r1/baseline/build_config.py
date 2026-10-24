"""LOCAL ONLY bind real root stage/release/gates; no synthetic artifact witness."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
from common import require, sha, hexsha, load_config, relative


def no_links(path):
    path = Path(path)
    require(not any(p.is_symlink() for p in [path] + list(path.parents)), 'Symlink path refused')
    return path


def reference(path, expected):
    path = no_links(Path(path).absolute())
    require(hexsha(expected) and path.is_file() and path.stat().st_nlink == 1
            and sha(path) == expected, 'Explicit frozen file/SHA differs')
    return path


def save(path, value):
    with Path(path).open('x') as out:
        json.dump(value, out, indent=2, sort_keys=True)
        out.write('\n')


def build(arm, release, release_sha, stage, stage_sha, protected, protected_sha,
          gates, metadata, output):
    from cpu_read_window32_abab import validate_release, selected_park_ns, selected_owner_park_ns, selected_event_page, selected_read_window, configure_arm, PREP
    require(type(arm) is int and arm in(1,2,3,4), 'One explicit owner-poll long arm required')
    configure_arm(arm)
    release = reference(release, release_sha); stage = reference(stage, stage_sha)
    protected = reference(protected, protected_sha)
    actual = validate_release(json.loads(release.read_text()))
    require(actual['protectedOriginalState']['manifestSha256'] == protected_sha, 'Protected baseline differs')
    require(set(gates)==set(range(1,arm)), 'Exact preceding independently collected/private-pushed arm prefix required')
    for n, (path, expected, push, push_sha) in gates.items():
        reference(path, expected);reference(push,push_sha)
    no_links(output)
    require(not output.exists(), 'Refuse existing/failed config destination')
    output.mkdir(mode=0o700, parents=True)
    inputs = output / 'inputs'; inputs.mkdir()
    for source, name in [(release, 'release.json'), (stage, 'STAGE_SUCCESS.json'),
                         (protected, 'current-stopped-original-state.json')]:
        shutil.copy2(source, inputs / name)
    prior = {}
    for n, (path, expected, push, push_sha) in sorted(gates.items()):
        target = inputs / ('arm-%d-collection-gate.json' % n)
        target_push=inputs/('arm-%d-private-push.json'%n)
        shutil.copy2(path, target);shutil.copy2(push,target_push)
        prior[str(n)] = {'local': str(target.resolve()), 'sha256': expected,
            'privatePushLocal':str(target_push.resolve()),'privatePushSha256':push_sha}
    config = {'schemaVersion': 6, 'experiment':'retention-read-window32-long-v1', 'workloadPreset':'long-cuts-33792-v1', 'arm': arm,
              'maximumParkNs': selected_park_ns(),'serverDriverMaximumParkNs':selected_park_ns(),'ownerPollMaximumParkNs':selected_owner_park_ns(),
              'eventFetchCount':selected_event_page(), 'readWindow':selected_read_window(), 'remotePrep': str(PREP), 'host': actual['host'],
              'releaseLocal': str((inputs / 'release.json').resolve()), 'releaseSha256': release_sha,
              'stagingReceipt': str((inputs / 'STAGE_SUCCESS.json').resolve()), 'stagingReceiptSha256': stage_sha,
              'protectedReference': str((inputs / 'current-stopped-original-state.json').resolve()),
              'protectedReferenceSha256': protected_sha, 'priorGates': prior,
              'executionMetadata': metadata}
    path = output / 'collector-config.json'; save(path, config)
    _, _, expected, allow = load_config(path)
    save(output / 'CONFIG_BOUND.json', {'passed': True, 'createdAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'configSha256': sha(path), 'releaseSha256': release_sha, 'actualStageReceiptSha256': stage_sha,
         'arm': arm, 'sourceAllowlist': allow, 'expectedSourceFiles': expected,
         'noRemoteAccess': True, 'sourcePrepRecursivelyCollected': False})
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--arm', type=int, choices=[1,2,3,4], required=True)
    for name in ['release', 'stage', 'protected']:
        p.add_argument('--' + name, type=Path, required=True)
        p.add_argument('--' + name + '-sha256', required=True)
    p.add_argument('--prior-gate', nargs=5, action='append', metavar=('ARM', 'FILE', 'SHA256','PRIVATE_PUSH_FILE','PRIVATE_PUSH_SHA256'), default=[])
    p.add_argument('--execution-metadata', action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); gates = {}
    for number, name, expected, push, push_sha in a.prior_gate:
        n = int(number); require(n not in gates, 'Duplicate gate'); gates[n] = (Path(name), expected,Path(push),push_sha)
    result = build(a.arm, a.release, a.release_sha256, a.stage, a.stage_sha256,
                   a.protected, a.protected_sha256, gates, a.execution_metadata, a.output)
    print(json.dumps({'passed': True, 'config': str(result), 'sha256': sha(result), 'remoteAccessed': False}))


if __name__ == '__main__':
    main()
