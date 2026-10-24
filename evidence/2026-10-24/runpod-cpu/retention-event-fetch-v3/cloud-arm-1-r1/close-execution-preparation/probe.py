from pathlib import Path
import argparse, hashlib, importlib.util, json, shlex, datetime

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runtime/cloud/cpu-20261024'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

p = argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--arm', type=int, choices=[1, 2, 3, 4], required=True)
p.add_argument('--attempt', type=int, required=True)
p.add_argument('--prior-collection-sha256')
a = p.parse_args()
assert a.attempt > 0
source = BASE / 'cpu-event-fetch-close-preparation-r1/inspect_closed_event_arm.py'
assert sha(source) == '67fcfe5bd15efb8bdc488d25b156534b34878ce6584e5cb2ec3cf95ebeb2b5f2'
launch_path = BASE / ('event-cloud-arm-%d-launch-r1/launch.stdout.json' % a.arm)
launch = json.loads(launch_path.read_text())
assert launch['observedExecArgvMatches'] and launch['stableStartTicks'] and launch['arm'] == a.arm
args = ['--arm', str(a.arm), '--release-sha256', launch['frozenReleaseSha256'],
        '--controller-sha256', 'eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100',
        '--controller-pid', str(launch['pid']), '--controller-start-ticks', str(launch['startTicks']),
        '--controller-argv-sha256', launch['observedCommandSha256']]
if a.arm > 1:
    assert a.prior_collection_sha256
    args += ['--prior-collection-sha256', a.prior_collection_sha256]
else:
    assert a.prior_collection_sha256 is None
helper = BASE / 'remote.py'
assert sha(helper) == '0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
spec = importlib.util.spec_from_file_location('root_owner_probe_remote', helper)
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)
out = BASE / ('event-cloud-arm-%d-close-inspection-r%d' % (a.arm, a.attempt))
out.mkdir()
(out / 'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    sourceSha256=sha(source), launchObservationSha256=sha(launch_path), arguments=args,
    rootReviewed=True, scope='One read-only bounded exact PID/control-plane probe; no raw/native audit, signals or writes'), indent=2) + '\n')
result = remote.run('python3 -B -c ' + shlex.quote(source.read_text()) + ' ' + shlex.join(args), timeout=45)
(out / 'stdout.json').write_text(result.stdout)
(out / 'stderr.txt').write_text(result.stderr)
(out / 'completion.json').write_text(json.dumps(dict(exitCode=result.returncode,
     observedAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat()), indent=2) + '\n')
value = json.loads(result.stdout)
print(json.dumps(dict(exitCode=result.returncode, state=value['state'], closedGate=value['closedGate'],
                      controlsRead=len(value.get('controlPlaneInputs', {})), output=str(out))))
raise SystemExit(result.returncode)
