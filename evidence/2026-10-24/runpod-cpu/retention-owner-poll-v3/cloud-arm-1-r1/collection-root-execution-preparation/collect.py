from pathlib import Path
import argparse, datetime, hashlib, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runtime/cloud/cpu-20261024'
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, v):
    with p.open('x') as f:
        json.dump(v, f, indent=2, sort_keys=True); f.write('\n')

p = argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--arm', type=int, choices=[1,2,3,4], required=True)
p.add_argument('--close-attempt', type=int, required=True)
a = p.parse_args()
closed = BASE / ('owner-cloud-arm-%d-close-inspection-r%d' % (a.arm, a.close_attempt))
x = json.loads((closed / 'stdout.json').read_text())
reg = json.loads((closed / 'REGISTRATION.json').read_text())
assert json.loads((closed / 'completion.json').read_text())['exitCode'] == 0
close_sha = '852546a1525b015df1baf38bb43d16e6ab68d2717fb57be648775de7bae0f51e'
assert reg['sourceSha256'] == close_sha
assert sha(BASE / 'cpu-owner-poll-close-preparation-r1/inspect_closed_owner_arm.py') == close_sha
assert x['arm'] == a.arm and x['state'] == 'CLOSED_PASS_CONTROL_PLANE'
assert x['closedGate'] and x['safeForIndependentClosedCollection']
assert x['controller']['observation'] == 'PID_ABSENT'
assert len(x['ownership']) == 4 and all(v['observation'] == 'PID_ABSENT' for v in x['ownership'])
assert x['allFourOwnedJvmsStrictlyPidAbsent'] and x['allOwnedStoppedAtObservation']
assert x['protectedNative57Pg989ReceiptsExact'] and x['controllerFullSuccessReceiptPassed']
assert x['serverDriverMaximumParkNs'] == 100000
assert x['ownerPollMaximumParkNs'] == [1000000,100000,1000000,100000][a.arm-1]
out = BASE / ('owner-cloud-arm-%d-collection-execution-r1' % a.arm)
out.mkdir()
gate = dict(schemaVersion=2, scope='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_CONTROLLER',
    rootVerified=True, arm=a.arm, serverDriverMaximumParkNs=x['serverDriverMaximumParkNs'],
    ownerPollMaximumParkNs=x['ownerPollMaximumParkNs'], frozenReleaseSha256=x['frozenReleaseSha256'],
    controllerSha256=x['controllerSha256'], job=x['job'], controllerIdentityGone=True,
    allOwnedStopped=True, inspectionSha256=sha(closed/'stdout.json'), executedSourceSha256=close_sha,
    controllerExitCodeIndependentlyObserved=x['controllerExitCodeIndependentlyObserved'],
    observedAtUnixNs=x['observedAtUnixNs'], createdAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
proof = out/'ROOT_CONTROLLER_CLOSED.json'; save(proof, gate)
prep = BASE/'cpu-owner-poll-collection-preparation-r2'
prep_sha = '28f6865201389901f26b2c6a7c698622d5d8acc635bad24d09ddadff05777b56'
assert sha(prep/'LOCAL_PREPARATION_FROZEN.json') == prep_sha
config_dir = BASE / ('owner-cloud-arm-%d-config-r1' % a.arm)
config = config_dir/'collector-config.json'
assert sha(config) == json.loads((config_dir/'CONFIG_BOUND.json').read_text())['configSha256']
dest = BASE/('cpu-owner-poll-arm-%d-collection-r1' % a.arm)
assert not dest.exists()
command = [sys.executable,'-B',str(prep/'collect_and_audit.py'), '--config',str(config),
    '--config-sha256',sha(config),'--output',str(dest),'--controller-closed-proof',str(proof),
    '--controller-closed-sha256',sha(proof),'--preparation-sha256',prep_sha,
    '--remote-helper',str(BASE/'remote.py'),'--collect-readonly']
save(out/'REGISTRATION.json',dict(command=command, wrapperSha256=sha(Path(__file__)),
    startedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(), noAutomaticRetry=True))
with (out/'stdout.json').open('xb') as stdout, (out/'stderr.txt').open('xb') as stderr:
    result=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=1200)
save(out/'completion.json',dict(exitCode=result.returncode,stdoutSha256=sha(out/'stdout.json'),
    stderrSha256=sha(out/'stderr.txt'),finishedAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print(json.dumps(dict(arm=a.arm,exitCode=result.returncode,output=str(dest))))
raise SystemExit(result.returncode)
