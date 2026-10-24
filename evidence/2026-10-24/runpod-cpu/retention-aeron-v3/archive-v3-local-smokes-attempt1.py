#!/usr/bin/env python3
"""Preserve and independently stream-verify all local functional smoke bytes."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import shutil
import tarfile
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
OUT=REPO/'evidence/2026-10-24/runpod-cpu/retention-aeron-v3'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()

def verify(directory):
    manifest=json.loads((directory/'manifest.json').read_text());archive=directory/'native-tree.tar.gz'
    assert archive.stat().st_size==manifest['archive']['bytes'] and sha(archive)==manifest['archive']['sha256']
    expected={v['path']:v for v in manifest['files']};actual={};total=0
    with tarfile.open(archive,'r|gz') as t:
        for m in t:
            p=PurePosixPath(m.name);assert p.parts[0]=='fresh-lineage' and '..' not in p.parts and not p.is_absolute()
            assert m.isdir() or m.isfile()
            if m.isdir():continue
            name=str(PurePosixPath(*p.parts[1:]));assert name in expected and name not in actual
            entry=expected[name];assert m.size==entry['bytes'];h=hashlib.sha256()
            with t.extractfile(m) as f:
                for b in iter(lambda:f.read(1024**2),b''):h.update(b)
            assert h.hexdigest()==entry['sha256'];actual[name]=entry;total+=m.size
    assert set(actual)==set(expected) and total==manifest['logicalBytes']
    with (directory/'root-archive-verification.json').open('x') as f:
        json.dump({'passed':True,'files':len(actual),'logicalBytes':total,'archiveSha256':sha(archive),
                   'fullTarReadbackEveryFileSha256':True,'extracted':False,'originalStateDeleted':False,
                   'scope':'Local singlehost threeJVM functional correctness only;not throughput,endurance or externalarchive durability'},f,indent=2)

for phase in ('smoke-r1','smoke-final'):
    original=BASE/'retention-aeron-v3'/phase;target=OUT/phase;target.mkdir()
    for file in original.iterdir():
        assert file.is_file() and not file.is_symlink() and file.stat().st_size<=16*1024**2
        shutil.copy2(file,target/file.name)
    verify(target)
    print('Verified '+phase,flush=True)

work=BASE/'core-retention-v3-worktree'
xml=work/'cluster/build/test-results/test/TEST-io.vectormatch.cluster.RetentionThreeJvmV3Test.xml'
suite=ET.parse(xml).getroot();stdout=suite.findtext('system-out')
root=Path(stdout.split('VECTOR_V3_TEST_EVIDENCE ',1)[1].splitlines()[0])
assert root.name=='fresh-lineage' and root.parent.name.startswith('vectormatch-v3-aeron-')
assert not any(p.is_symlink() for p in [root]+list(root.parents))
complete=json.loads((root/'completion.json').read_text());assert complete['passed'] and complete['allOwnedStopped']
target=OUT/'smoke-root-full-check';target.mkdir()
files=[]
for file in sorted(root.rglob('*')):
    assert not file.is_symlink()
    if file.is_dir():continue
    assert file.is_file() and file.stat().st_size<=512*1024**2
    files.append({'path':str(file.relative_to(root)),'bytes':file.stat().st_size,'sha256':sha(file)})
assert len(files)<200 and sum(x['bytes'] for x in files)<3*1024**3
archive=target/'native-tree.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as t:t.add(root,arcname='fresh-lineage')
manifest={'schema':'local-v3-smoke-whole-native-tree-v1','phase':'root-independent-full-check',
          'sourceRevision':'9fda247d392432761a670de7c4d8040c7caff283','sourceDirectory':str(root),
          'logicalBytes':sum(x['bytes'] for x in files),'files':files,
          'archive':{'path':archive.name,'bytes':archive.stat().st_size,'sha256':sha(archive)},
          'restoreGuard':'Full logical tar bytes. Use logicalspaceguard or reviewed sparse-safe extractor. Original temp tree retained.'}
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');shutil.copy2(xml,target/'test.xml')
for file in root.iterdir():
    if file.is_file():shutil.copy2(file,target/file.name)
verify(target)
shutil.copy2(Path(__file__),OUT/Path(__file__).name)
print('Verified root full-check smoke',flush=True)
