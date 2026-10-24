#!/usr/bin/env python3
"""Local-only immutable client candidate preparation; no SSH or deployment."""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
REVISION = 'ebede54c0cf46deabdd7d03a8a155a3a9e13b38a'
NODE_REVISION = '433f02bebe2f3109ec363291fa562d5c509c0723'
WORKTREE = BASE / 'client-driver-park-worktree'
BASELINE = REPO / 'runtime/cloud/optimization-20261024/mux-window' / ('load-' + NODE_REVISION) / 'dist/cluster/lib'
LIB = WORKTREE / 'cluster/build/install/cluster/lib'
OUT = BASE / 'client-driver-prepared' / REVISION
EVIDENCE = REPO / 'evidence/2026-10-24/runpod-cpu/client-driver-experiment/artifact-preparation'
JARS = {
    'aeron-all-1.53.3.jar': '4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2',
    'agrona-2.6.1.jar': '84c07eb02695c06bfda3d6c3a20c1984e3ff1bbd617b2f8e678140baf973fa28',
    'cluster-0.1.0-SNAPSHOT.jar': '2432dbc4503d21c95f65192f035c2dfc8b9e458aa455483a2e1afda901023419',
    'core-0.1.0-SNAPSHOT.jar': '1e61704a83b31dcfa8eb920caa0f04d09f7da538be122f357b7fa4e0e88ffba2',
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=WORKTREE).decode().strip()

def main():
    require(git('rev-parse', 'HEAD') == REVISION, 'Candidate revision differs')
    require(not git('status', '--porcelain', '--untracked-files=no'), 'Candidate tracked source dirty')
    require(set(p.name for p in LIB.iterdir()) == set(JARS), 'Unexpected candidate classpath entries')
    validation = json.loads((EVIDENCE.parent / 'source-validation/full-check-reviewed.json').read_text())
    require(validation['passed'] is True and validation['totals'] == {
        'discovered': 145, 'passed': 134, 'failed': 0, 'skipped': 11}, 'Configured check scope differs')
    for name, digest in validation['sourceFilesSha256'].items():
        require(sha((WORKTREE / name).read_bytes()) == digest, 'Validated source changed: ' + name)
    changed = []
    files = []
    payloads = {}
    allowed = re.compile(r'io/vectormatch/cluster/(ClusterClient|MultiplexedLoadTransports|RemoteCapacityExperiment)(\$[^/]*)?\.class')
    for name, baseline_digest in sorted(JARS.items()):
        old = (BASELINE / name).read_bytes()
        new = (LIB / name).read_bytes()
        require(sha(old) == baseline_digest, 'Original433 baseline jar changed: ' + name)
        with zipfile.ZipFile(io.BytesIO(old)) as a, zipfile.ZipFile(io.BytesIO(new)) as b:
            require(len(a.namelist()) == len(set(a.namelist())) and len(b.namelist()) == len(set(b.namelist())), 'Duplicate ZIP member')
            require(set(a.namelist()) == set(b.namelist()), 'Unexpected added/removed production entry: ' + name)
            for entry in sorted(a.namelist()):
                if entry.endswith('/'):
                    continue
                if a.read(entry) != b.read(entry):
                    require(name == 'cluster-0.1.0-SNAPSHOT.jar' and allowed.fullmatch(entry), 'Unexpected business class change: ' + entry)
                    changed.append({'jar': name, 'entry': entry, 'baselineSha256': sha(a.read(entry)), 'candidateSha256': sha(b.read(entry))})
        if name.startswith(('aeron-', 'agrona-')):
            require(old == new, 'Dependency bytes changed')
        payloads['dist/cluster/lib/' + name] = new
        files.append({'path': 'dist/cluster/lib/' + name, 'bytes': len(new), 'sha256': sha(new), 'baselineSha256': sha(old), 'jarBytesEqual': old == new})
    require(changed, 'No candidate change found')
    OUT.mkdir(parents=True, exist_ok=False)
    bundle = OUT / 'client-driver-dist.tar'
    with tarfile.open(bundle, 'x', format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(payloads.items()):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    manifest = {
        'schemaVersion': 1, 'passed': True, 'candidateRevision': REVISION,
        'nodeRevision': NODE_REVISION, 'deploymentScope': 'LOCAL_PREPARATION_ONLY_NOT_DEPLOYED',
        'remoteRoot': '/opt/vectormatch-cpu/client-releases/' + REVISION,
        'bundleName': bundle.name, 'bundleSha256': sha(bundle.read_bytes()), 'bundleBytes': bundle.stat().st_size,
        'files': files, 'changedEntries': changed,
        'sourceValidationSha256': sha((EVIDENCE.parent / 'source-validation/full-check-reviewed.json').read_bytes()),
        'preparerSha256': sha(Path(__file__).read_bytes()),
        'claim': 'Dependencies byte-identical; core and all other production entries byte-identical when uncompressed. Core JAR container bytes differ. Same complete candidate classpath is required for both future client idle arms; historical433 timings are not controls.',
    }
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    for target in (OUT / 'manifest.json', EVIDENCE / 'manifest.json'):
        target.write_text(json.dumps(manifest, indent=2) + '\n')
    (EVIDENCE / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(manifest, indent=2))

if __name__ == '__main__':
    main()
