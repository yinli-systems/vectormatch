"""One SSH; exclusive prior JSON pair upload only. No launch, retry, cleanup or alternate remote path."""
from pathlib import Path
import argparse, base64, datetime, importlib.util, inspect, json, shlex, sys
sys.dont_write_bytecode = True
import contracts
from contracts import *
from freeze import BASE, HERE, no_links, row, sha, write_new
REMOTE_HELPER_SHA = '0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'

def program(payload, arm):
    validate_payload(payload, arm)
    values = {name: getattr(contracts, name) for name in ('SOURCE', 'CODE', 'RELEASE', 'CONTROLLER', 'PREP', 'REPOSITORY', 'PAGE_ORDER')}
    source = 'import base64,hashlib,json,os,pathlib,stat,platform\n'
    source += '\n'.join(name + '=' + repr(value) for name, value in values.items()) + '\n'
    for name in ('need', 'digest', 'hexsha', 'page', 'validate_pair', 'validate_payload', 'exclusive_write_pair'):
        source += inspect.getsource(getattr(contracts, name)) + '\n'
    source += 'payload=' + repr(payload) + '\narm=' + repr(arm) + '\n'
    source += '''
need(platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0,'Exact existing CPU host/root')
prep=pathlib.Path(PREP)
for path in (prep,*prep.parents,prep/'release',prep/'release/release.json',prep/'cpu_event_fetch_abab.py'):
 need(not path.is_symlink(),'No linked canonical deployment')
need(digest((prep/'release/release.json').read_bytes())==RELEASE,'Same actual ready release')
need(digest((prep/'cpu_event_fetch_abab.py').read_bytes())==CONTROLLER,'Same frozen controller')
print(json.dumps(exclusive_write_pair(prep,payload,arm)),flush=True)
'''
    return source

def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--arm', type=int, choices=[1, 2, 3], required=True)
    parser.add_argument('--prior-directory', type=Path, required=True)
    parser.add_argument('--collection-gate-sha256', required=True)
    parser.add_argument('--private-push-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    directory = no_links(a.prior_directory)
    need(directory == BASE / ('event-cloud-arm-%d-prior-gate-r1' % a.arm), 'Exact local current prior pair')
    payload = {}
    for leaf, expected in [('collection-gate.json', a.collection_gate_sha256), ('private-push.json', a.private_push_sha256)]:
        path = no_links(directory / leaf)
        pin = row(path)
        need(hexsha(expected) and pin['sha256'] == expected and pin['mode'] == 0o600 and pin['bytes'] <= 65536,
             'Root-selected exact original prior JSON')
        payload['release/arm-%d-%s' % (a.arm, leaf)] = dict(data=base64.b64encode(path.read_bytes()).decode(),
                                                            **{key: pin[key] for key in ('sha256', 'bytes', 'mode')})
    source = program(payload, a.arm)
    helper = no_links(BASE / 'remote.py')
    need(sha(helper) == REMOTE_HELPER_SHA, 'Single existing direct SSH helper pin')
    output = no_links(a.output)
    need(output.parent == BASE and output.name.startswith('event-cloud-arm-%d-prior-upload-r' % a.arm)
         and not output.exists(), 'Fresh upload observation, no overwrite/retry')
    output.mkdir(mode=0o700)
    write_new(output / 'REGISTRATION.json', dict(arm=a.arm, eventFetchCount=page(a.arm), atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
         sourceSha256=sha(Path(__file__)), contractsSha256=sha(HERE / 'contracts.py'), remoteHelperSha256=sha(helper),
         files={name: {key: value for key, value in pin.items() if key != 'data'} for name, pin in payload.items()},
         oneSshOnly=True, noLaunch=True, noOverwrite=True, noRetry=True))
    with (output / 'remote-program.py').open('x') as saved:
        saved.write(source)
    spec = importlib.util.spec_from_file_location('one_explicit_prior_pair_remote', helper)
    remote = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(remote)
    result = remote.run('python3 -B -c ' + shlex.quote(source), timeout=45)
    with (output / 'stdout.json').open('x') as f:
        f.write(result.stdout)
    with (output / 'stderr.txt').open('x') as f:
        f.write(result.stderr)
    write_new(output / 'COMPLETION.json', dict(exitCode=result.returncode, stdoutSha256=sha(output / 'stdout.json'),
                                              stderrSha256=sha(output / 'stderr.txt'), noAutomaticRetry=True, noBusinessStarted=True))
    need(result.returncode == 0, 'Upload failed/uncertain: preserve partial remote originals, inspect read-only; never automatically retry')
    receipt = json.loads(result.stdout)
    need(receipt['passed'] is True and receipt['uploaded'] == {name: pin['sha256'] for name, pin in payload.items()}
         and receipt['businessStarted'] is False, 'Exact two-file exclusive readback')
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
