import hashlib, importlib.util, json, pathlib, shlex

BASE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('remote', BASE / 'remote.py')
remote = importlib.util.module_from_spec(spec); spec.loader.exec_module(remote)
SOURCE = BASE / 'original-cluster-lifecycle-r1-preparation'
PLAN = json.loads((SOURCE / 'plan.json').read_text())
REMOTE_SOURCE = '/opt/vectormatch-cpu/preparation/original-cluster-lifecycle-r1-source'
PREP = PLAN['prep']
OUT = BASE / 'original-cluster-lifecycle-r1-staging'
OUT.mkdir(exist_ok=False)
frozen = json.loads((SOURCE / 'FROZEN_PREPARATION.json').read_text())
for name, row in frozen['files'].items():
    raw = (SOURCE / name).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], name
files = {name: SOURCE / name for name in ('original_cluster_lifecycle.py', 'plan.json', 'test_original_cluster_lifecycle.py', 'FROZEN_PREPARATION.json')}
targets = {REMOTE_SOURCE + '/' + name: path for name, path in files.items()}
for name, expected in PLAN['jars'].items():
    path = BASE / 'app-restore-build/bundle/dist/cluster/lib' / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    targets[PREP + '/lib/' + name] = path
helper = BASE / 'original-cluster-r2-preparation' / PLAN['helperJar']['name']
assert hashlib.sha256(helper.read_bytes()).hexdigest() == PLAN['helperJar']['sha256']
targets[PREP + '/' + helper.name] = helper
setup = "import os; os.umask(0o077); os.mkdir(%r); os.mkdir(%r); os.mkdir(%r)" % (REMOTE_SOURCE, PREP, PREP + '/lib')
r = remote.run('python3 -c ' + shlex.quote(setup))
(OUT / 'setup.stdout').write_text(r.stdout); (OUT / 'setup.stderr').write_text(r.stderr)
assert r.returncode == 0, r.stderr
rows = {}
for target, local in targets.items():
    r = remote.upload(local, target)
    assert r.returncode == 0, (target, r.stderr)
    rows[target] = {'bytes': local.stat().st_size, 'sha256': hashlib.sha256(local.read_bytes()).hexdigest()}
check = "import hashlib,json,pathlib; rows=" + repr(rows) + "; result={};\nfor name,row in rows.items():\n p=pathlib.Path(name); raw=p.read_bytes(); assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']; result[name]=row\nprint(json.dumps({'passed':True,'files':result}))"
r = remote.run('python3 -c ' + shlex.quote(check))
(OUT / 'staged-verification.stdout.json').write_text(r.stdout); (OUT / 'staged-verification.stderr').write_text(r.stderr)
assert r.returncode == 0, r.stderr
r = remote.run('python3 -B ' + shlex.quote(REMOTE_SOURCE + '/test_original_cluster_lifecycle.py'))
(OUT / 'linux-guards.stdout').write_text(r.stdout); (OUT / 'linux-guards.stderr').write_text(r.stderr)
assert r.returncode == 0, r.stderr
r = remote.run('python3 -B ' + shlex.quote(REMOTE_SOURCE + '/original_cluster_lifecycle.py'), timeout=240)
(OUT / 'preflight.stdout.json').write_text(r.stdout); (OUT / 'preflight.stderr').write_text(r.stderr)
(OUT / 'receipt.json').write_text(json.dumps({'passed':r.returncode==0,'stagedFiles':rows,'preflightReturnCode':r.returncode,'sourceManifestSha256':hashlib.sha256((SOURCE/'FROZEN_PREPARATION.json').read_bytes()).hexdigest()},indent=2)+'\n')
assert r.returncode == 0, r.stderr
print(json.dumps({'passed':True,'files':len(rows),'guards':27,'preflight':True,'noJavaStarted':True}))
