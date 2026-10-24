#!/usr/bin/env python3
"""Stage frozen access-only preparation and execute its read-only preflight once."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import shlex

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import remote

ROOT = HERE.parents[2]
SOURCE = HERE / 'pg-recovery-preparation/access-r1'
PROOF = ROOT / 'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-access-r1'
DEST = '/opt/vectormatch-cpu/preparation/pg-access-source-r1'
EXPECTED = '2b7dda36a4fd431aa2509e07e174ed989f0c7cf61f8be353ea93d702b087d9d1'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert sha(SOURCE / 'manifest.json') == EXPECTED
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    for name, item in manifest['files'].items():
        p = SOURCE / name
        assert p.stat().st_size == item['bytes'] and sha(p) == item['sha256']
    PROOF.mkdir(exist_ok=False)
    shutil.copytree(SOURCE, PROOF / 'frozen-access-source')
    shutil.copy2(__file__, PROOF / Path(__file__).name)
    setup = """import os,platform,pathlib
p=pathlib.Path(%r)
assert platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert not p.exists()
assert all(not x.is_symlink() for x in [p]+list(p.parents))
p.mkdir(mode=0o700)
print('NEW_FIXED_SOURCE_DIRECTORY_CREATED')
""" % DEST
    r = remote.run('python3 -B -', input=setup, timeout=30)
    (PROOF / 'stage-setup.stdout').write_text(r.stdout)
    (PROOF / 'stage-setup.stderr').write_text(r.stderr)
    assert r.returncode == 0, 'Stage setup failed; no automatic retry'
    for name in ['pg_recovery.py', 'expected-baseline.json', 'manifest.json']:
        r = remote.upload(SOURCE / name, DEST + '/' + name)
        assert r.returncode == 0, 'Stage upload failed; no automatic retry'
    code = """import pathlib,hashlib,json,subprocess,sys
p=pathlib.Path(%r)
expected=%r
assert all(not x.is_symlink() for x in [p]+list(p.parents))
for name,h in expected.items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==h
r=subprocess.run(['/usr/bin/python3','-B',str(p/'pg_recovery.py')],capture_output=True,text=True,timeout=160)
sys.stdout.write(r.stdout);sys.stderr.write(r.stderr);sys.exit(r.returncode)
""" % (DEST, {name: sha(SOURCE / name) for name in ['pg_recovery.py', 'expected-baseline.json', 'manifest.json']})
    (PROOF / 'actual-preflight-wrapper.py').write_text(code)
    r = remote.run('python3 -B -', input=code, timeout=180)
    (PROOF / 'preflight.stdout.json').write_text(r.stdout)
    (PROOF / 'preflight.stderr.log').write_text(r.stderr)
    summary = {'exitCode': r.returncode, 'controllerSha256': sha(SOURCE / 'pg_recovery.py'),
               'manifestSha256': EXPECTED, 'remoteSource': DEST, 'scope': 'Actual read-only access preflight; no account/ACL/chown/start'}
    if r.returncode == 0:
        d = json.loads(r.stdout)
        summary.update(pgFiles=d['pg']['files'], binaryEntries=d['binaries']['manifestEntries'],
                       blockedAccessPaths=len(d['access']['blocked']), freeBytes=d['freeBytes'],
                       accountExists=d['account']['exists'], postgresStarted=d['serverStarted'])
    (PROOF / 'preflight-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))
    assert r.returncode == 0, 'Preflight failed; no automatic retry'

if __name__ == '__main__':
    main()
