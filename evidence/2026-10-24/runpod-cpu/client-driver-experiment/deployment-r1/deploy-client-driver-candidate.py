#!/usr/bin/env python3
"""Stage the audited client-only classpath after the eight-point curve; starts no JVM."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import shlex

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
REVISION = 'ebede54c0cf46deabdd7d03a8a155a3a9e13b38a'
MANIFEST_SHA = '177819fe91de0952b8aeadee365b179d2f60f31b4f1b53056175b6bb4668ed69'
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    source = BASE / 'client-driver-prepared' / REVISION
    manifest_path = source / 'manifest.json'
    if sha(manifest_path) != MANIFEST_SHA:
        raise ValueError('pinned preparation manifest changed')
    manifest = json.loads(manifest_path.read_text())
    bundle = source / manifest['bundleName']
    if sha(bundle) != manifest['bundleSha256']:
        raise ValueError('candidate bundle changed')
    if not args.execute:
        print(json.dumps({'draftOnly': True, 'candidateRevision': REVISION,
                          'bundleSha256': manifest['bundleSha256'], 'remoteRoot': manifest['remoteRoot'],
                          'requirement': 'all eight frozen curve points complete and no active benchmark JVM',
                          'startsProcesses': False}, indent=2)); return
    reporter = BASE / 'report-park100-curve.py'
    spec = importlib.util.spec_from_file_location('strict_curve_deploy_gate', reporter)
    c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
    c.report()  # Full eight-point/archive/raw closure. Does not publish or mutate it.
    spec = importlib.util.spec_from_file_location('cpu_remote', BASE / 'remote.py')
    remote = importlib.util.module_from_spec(spec); spec.loader.exec_module(remote)
    control = '/workspace/vectormatch-cpu-control/client-driver-artifact-' + REVISION
    preflight = '''from pathlib import Path
import platform,json
assert platform.node()=='ed6c0673f5cb'
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:argv=(p/'cmdline').read_bytes().split(b'\\0')
 except FileNotFoundError:continue
 if argv and argv[0].split(b'/')[-1]==b'java':
  assert not any(a.startswith((b'io.vectormatch.',b'org.openjdk.jmh.')) for a in argv), 'active benchmark JVM'
target=Path(TARGET)
assert not target.exists() and not target.is_symlink(), 'candidate deployment already exists; no overwrite'
for p in [target]+list(target.parents):assert not p.is_symlink()
Path(CONTROL).mkdir(exist_ok=False)
print('idle existing CPU; new unique client-only target')
'''.replace('TARGET', repr(manifest['remoteRoot'])).replace('CONTROL', repr(control))
    p = remote.run('python3 -B -', input=preflight, timeout=30)
    if p.returncode: raise RuntimeError(p.stderr + p.stdout)
    for path in [bundle, manifest_path]:
        p = remote.upload(path, control + '/' + path.name)
        if p.returncode: raise RuntimeError(str(p.stderr))
    code = '''from pathlib import Path
import hashlib,json,os,shutil,tarfile,platform
control=Path(CONTROL)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert platform.node()=='ed6c0673f5cb'
assert sha(control/'manifest.json')==MANIFEST_SHA
m=json.loads((control/'manifest.json').read_text())
source=control/m['bundleName'];assert sha(source)==m['bundleSha256']
target=Path(m['remoteRoot']);assert not target.exists() and not target.is_symlink()
assert shutil.disk_usage('/opt/vectormatch-cpu').free>=3*1024**3
expected={x['path']:x for x in m['files']}
with tarfile.open(source,'r:') as t:
 members=t.getmembers()
 assert len(members)==len(expected)==4 and {x.name for x in members}==set(expected)
 assert all(x.isreg() and not x.issparse() and x.mode==0o644 and x.size==expected[x.name]['bytes'] for x in members)
 target.parent.mkdir(exist_ok=True)
 target.mkdir(mode=0o755)
 for item in members:
  p=target/item.name;p.parent.mkdir(parents=True,exist_ok=True)
  data=t.extractfile(item).read()
  assert len(data)==item.size and hashlib.sha256(data).hexdigest()==expected[item.name]['sha256']
  with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  os.chmod(p,0o444)
assert {str(p.relative_to(target)) for p in target.rglob('*') if p.is_file()}==set(expected)
actual={n:{'sha256':sha(target/n),'bytes':(target/n).stat().st_size} for n in expected}
assert all(actual[n]['sha256']==r['sha256'] and actual[n]['bytes']==r['bytes'] for n,r in expected.items())
receipt={'passed':True,'hostname':platform.node(),'candidateRevision':m['candidateRevision'],'nodeRevision':m['nodeRevision'],'remoteRoot':str(target),'preparationManifestSha256':MANIFEST_SHA,'bundleSha256':m['bundleSha256'],'files':actual,'processesStarted':False,'scope':'Audited client-only classpath staged on existing CPU after complete8point closure; existing node release and state unchanged. No benchmark or performance claim.'}
with (control/'deployment-receipt.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\\n')
print(json.dumps(receipt))
'''.replace('CONTROL', repr(control)).replace('MANIFEST_SHA', repr(MANIFEST_SHA))
    p = remote.run('python3 -B -', input=code, timeout=90)
    output = REPO / 'evidence/2026-10-24/runpod-cpu/client-driver-experiment/deployment-r1'
    output.mkdir(exist_ok=False)
    (output / 'deployment.log').write_text(p.stdout + p.stderr)
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    if p.returncode: raise RuntimeError('Candidate staging failed; preserve unique attempt; no automatic retry: ' + p.stderr)
    receipt = json.loads(p.stdout)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))

if __name__ == '__main__': main()
