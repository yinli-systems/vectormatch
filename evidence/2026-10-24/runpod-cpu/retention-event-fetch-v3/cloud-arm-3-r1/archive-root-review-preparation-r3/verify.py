"""Independent local closure and exact source-mirror verification; no business execution."""
from pathlib import Path
import argparse, datetime, hashlib, json, stat

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runtime/cloud/cpu-20261024'

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def read(p):
    return json.loads(p.read_text())

def inventory(p, excluded=()):
    files, dirs = {}, {}
    for f in [p] + sorted(p.rglob('*')):
        assert not f.is_symlink(), str(f)
        s = f.stat()
        n = str(f.relative_to(p))
        meta = dict(mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid)
        if f.is_dir():
            dirs[n] = meta
        else:
            assert f.is_file(), str(f)
            if n not in excluded:
                files[n] = dict(meta, bytes=s.st_size, sha256=sha(f))
    return dict(files=files, directories=dirs)

p = argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--arm', type=int, choices=[1, 2, 3, 4], required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
archive = ROOT / ('evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1' % a.arm)
m, c = read(archive / 'INVENTORY.json'), read(archive / 'CLOSED.json')
assert c['passed'] and c['arm'] == a.arm and c['inventorySha256'] == sha(archive / 'INVENTORY.json')
actual = inventory(archive, ('INVENTORY.json', 'CLOSED.json'))
assert actual['files'] == m['files'] and actual['directories'] == m['directories']
assert len(actual['files']) == c['payloadFiles'] and len(actual['directories']) == c['directories']
assert sum(x['bytes'] for x in actual['files'].values()) == c['payloadBytes']
before, after = read(archive / 'SOURCE_BEFORE_COPY.json'), read(archive / 'SOURCE_AFTER_COPY.json')
assert after['passed'] and after['allOriginalsUnchanged']
assert set(before) == set(after['sourceTrees'])
for name, row in before.items():
    source = Path(row['source'])
    expected = {k: row['inventory'][k] for k in ['files', 'directories']}
    assert after['sourceTrees'][name] == row['inventory']
    assert inventory(source) == expected, ('source changed', name)
    assert inventory(archive / name) == expected, ('incomplete mirror', name)
single_files = {}
if (archive / 'SOURCE_SINGLE_FILES_BEFORE_COPY.json').exists():
    single_files = read(archive / 'SOURCE_SINGLE_FILES_BEFORE_COPY.json')
    assert single_files == after['sourceFiles']
    for name, row in single_files.items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert inventory(Path(row['source']))['files']['.'] == row['pin']
        assert inventory(archive / name)['files']['.'] == row['pin']
collection = BASE / ('cpu-event-fetch-arm-%d-collection-r1' % a.arm)
assert inventory(collection) == inventory(archive / 'actual-collection')
review = read(archive / 'root-review/ROOT_REVIEW.json')
assert review['passed'] and review['arm'] == a.arm
assert review['sourceCommit'] == 'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
assert review['independent4AnchorCodeFingerprint'] == '87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
assert all(review[k] is True for k in ['allFullOuterMembersVerified', 'allRawInputsUnchanged', 'sameNewArtifactFunctionalQualified', 'allOriginalRawCanonicalAndThreeSnapshotsVerified'])
bindings = read(archive / 'ROOT_REVIEW_INPUT_PORTABLE_BINDINGS.json')['inputs']
assert set(bindings) == set(review['inputs'])
for name, row in review['inputs'].items():
    original = Path(name)
    assert original.stat().st_size == row['bytes'] and sha(original) == row['sha256']
    assert bindings[name]['bytes'] == row['bytes'] and bindings[name]['sha256'] == row['sha256']
    assert bindings[name]['archivedAt']
    for n in bindings[name]['archivedAt']:
        f = archive / n
        assert f.stat().st_size == row['bytes'] and sha(f) == row['sha256']
final = read(collection / 'finalized/LOCAL_COLLECTION_COMPLETE.json')
assert final['passed'] and final['arm'] == a.arm
assert final['eventFetchCount'] == [16, 32, 16, 32][a.arm - 1]
assert final['sameNewArtifactFunctionalQualified'] and final['allOriginalRawCanonicalAndThreeSnapshotsVerified']
assert c['allKnownMarkerScansPassed'] and c['allOriginalCollectionAndBothCompleteTarsRetained']
result = dict(passed=True, arm=a.arm, atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              scope='Independent local full archive/source-mirror SHA bytes modes UID GID empty-directory verification; no business audit rerun',
              inventorySha256=sha(archive / 'INVENTORY.json'), closedSha256=sha(archive / 'CLOSED.json'),
              payloadFiles=len(actual['files']), directories=len(actual['directories']),
              payloadBytes=c['payloadBytes'], explicitFullSourceScopes=len(before), explicitSingleFileSources=len(single_files),
              exactCompleteCollectionMirror=True, allSourceInventoriesUnchanged=True,
              allRootReviewInputBodiesBoundAndUnchanged=True,
              localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,
              scriptSha256=sha(Path(__file__)))
a.output.mkdir(parents=True, exist_ok=False)
with (a.output / 'ROOT_REVIEW.json').open('x') as f:
    json.dump(result, f, indent=2, sort_keys=True)
    f.write('\n')
print(json.dumps(result, sort_keys=True))
