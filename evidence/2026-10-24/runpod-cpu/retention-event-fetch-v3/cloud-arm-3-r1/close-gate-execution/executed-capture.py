"""Capture exactly one explicit command. Never retry or resume remote work."""
import argparse, datetime, hashlib, json, pathlib, shutil, subprocess, sys, time

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def save(p, value):
    with p.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')

p = argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--output', type=pathlib.Path, required=True)
p.add_argument('--pin', nargs=2, action='append', default=[])
p.add_argument('--minimum-free', type=int, default=1073741824)
p.add_argument('command', nargs=argparse.REMAINDER)
a = p.parse_args()
command = a.command[1:] if a.command[:1] == ['--'] else a.command
assert command and all(isinstance(x, str) and x for x in command)
assert not a.output.exists() and shutil.disk_usage(a.output.parent).free >= a.minimum_free
pins = {}
for name, expected in a.pin:
    source = pathlib.Path(name).resolve()
    assert source.is_file() and sha(source) == expected
    pins[str(source)] = dict(bytes=source.stat().st_size, sha256=expected)
a.output.mkdir(mode=0o700)
shutil.copy2(__file__, a.output / 'executed-capture.py')
save(a.output / 'REGISTRATION.json', dict(arguments=command, sourcePins=pins,
     atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(), oneAttemptOnly=True,
     automaticRetry=False, runnerSha256=sha(pathlib.Path(__file__))))
start = time.monotonic_ns()
with (a.output / 'stdout.json').open('xb') as out, (a.output / 'stderr').open('xb') as err:
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
unchanged = all(pathlib.Path(n).stat().st_size == r['bytes'] and sha(pathlib.Path(n)) == r['sha256'] for n, r in pins.items())
receipt = dict(exitCode=result.returncode, elapsedNs=time.monotonic_ns() - start,
     sourcePinsUnchanged=unchanged, stdoutSha256=sha(a.output / 'stdout.json'),
     stderrSha256=sha(a.output / 'stderr'), oneAttemptOnly=True)
save(a.output / 'EXECUTION.json', receipt)
print(json.dumps(receipt, sort_keys=True))
sys.exit(result.returncode if unchanged else 97)
