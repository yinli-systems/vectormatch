from pathlib import Path
import hashlib, json, subprocess, sys, datetime

ROOT = Path(__file__).resolve().parents[4]
PREP = ROOT / 'runtime/cloud/cpu-20261024/owner-poll-native-preparation-r1'
OUT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

assert sha(PREP / 'SOURCE_FROZEN.json') == 'efdb34e749e01d8a9edbf12f9209aa9213080c8dc65e175a3710d5625d126b90'
assert sha(PREP / 'PARSER_SOURCE_FROZEN.json') == 'a918ccfea558ea67c993910d1dcdbe12d15e5c0b9f81afda4bd3f6013a2df85a'
freeze = json.loads((PREP / 'SOURCE_FROZEN.json').read_text())
for name, row in freeze['sourceFiles'].items():
    path = PREP / name
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
assert sha(PREP / 'capture_closed_pair.py') == '0785cd0ee77d052bd4071deeea03c46ed286d6f3c5f0c9b37f94a899b15c6ef1'
assert sha(PREP / 'audit_closed_pair.py') == 'e73da21c369c433c0942647e378455a51bfef1a7e74fb16f16d78ffb14e60303'
save(OUT / 'REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
     rootReviewed=True, sourceFreezeSha256=sha(PREP / 'SOURCE_FROZEN.json'),
     parserFreezeSha256=sha(PREP / 'PARSER_SOURCE_FROZEN.json'), sourceFilesRehashed=len(freeze['sourceFiles']),
     scope='ONE closed fullTAR capture/readback then ONE independent local SHORT raw audit; no Java/SSH/signals/replay'))
steps = []
for script in ['capture_closed_pair.py', 'audit_closed_pair.py']:
    argv = [sys.executable, '-B', str(PREP / script), '--config', str(PREP / 'INPUTS_DRAFT.json'),
            '--config-sha256', '8dcdb4dfac6a9373083bbfca7c9f7673fce73fc327639b3da810de4b5a61001c']
    with (OUT / (script + '.stdout')).open('x') as stdout, (OUT / (script + '.stderr')).open('x') as stderr:
        result = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr)
    step = dict(script=script, exitCode=result.returncode)
    steps.append(step)
    print(json.dumps(step), flush=True)
    if result.returncode:
        break
passed = len(steps) == 2 and all(row['exitCode'] == 0 for row in steps)
save(OUT / 'completion.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
     steps=steps, passed=passed, automaticRetry=False))
raise SystemExit(0 if passed else 1)
