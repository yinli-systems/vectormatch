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

assert sha(PREP / 'SOURCE_FROZEN_R2.json') == '4a731bf6975bf16a832b7af5075a6071b81bab333eeedec556a9e0f09fa698ca'
assert sha(PREP / 'PARSER_SOURCE_FROZEN_R2.json') == '60d87ebc26752615d7f28fd25d72c8f6f5b4e41c08eb6665d9c81cdb11cd8b6d'
freeze = json.loads((PREP / 'SOURCE_FROZEN_R2.json').read_text())
for name, row in freeze['sourceFiles'].items():
    path = PREP / name
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
assert sha(PREP / 'capture_closed_pair_r2.py') == 'b9d836246273791e3b5035332a19d397df455891e775c290004a1d9c4cc11fa6'
assert sha(PREP / 'audit_closed_pair_r2.py') == 'b48dd3fb5e1878eac11ae1f83ef3357dced56e2f50f466099a4805192cfe6dc8'
save(OUT / 'REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
     rootReviewed=True, sourceFreezeSha256=sha(PREP / 'SOURCE_FROZEN_R2.json'),
     parserFreezeSha256=sha(PREP / 'PARSER_SOURCE_FROZEN_R2.json'), sourceFilesRehashed=len(freeze['sourceFiles']),
     scope='ONE closed fullTAR capture/readback then ONE independent local SHORT raw audit; no Java/SSH/signals/replay'))
steps = []
for script in ['capture_closed_pair_r2.py', 'audit_closed_pair_r2.py']:
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
