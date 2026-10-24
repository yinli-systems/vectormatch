"""Read-only local closure verification. No extraction, network, JVM or process signal."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import tarfile

HERE = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    collection = HERE / 'collection-run/collection'
    raw = read(HERE / 'collection-run/raw/result.json')
    inventory = read(collection / 'remote-inventory.stdout.json')
    receipt = read(collection / 'collection-receipt.json')
    root_review = read(HERE / 'root-review/ROOT_REVIEW.json')
    gate = read(HERE / 'root-review/ROOT_COLLECTION_GATE.json')
    assert root_review['passed'] is True and raw['passed'] is True and gate['rootVerified'] is True
    assert gate['arm'] == 4 and gate['maximumParkNs'] == 100000
    assert gate['rootIndependentReviewSha256'] == sha(HERE / 'root-review/ROOT_REVIEW.json')
    assert gate['rootIndependentReviewSourceSha256'] == sha(HERE / 'root-review-source.py')
    assert gate['independentLocalCollectionReceiptSha256'] == sha(HERE / 'collection-run/finalized/LOCAL_COLLECTION_COMPLETE.json')
    assert not (HERE / 'collection-run/finalized/ROOT_GATE_CANDIDATE_NOT_APPROVED.json').exists()
    for name, key in [('full-closed-round.tar.gz', 'fullOuterArchive'),
                      ('pilot-after-clean-stop.tar.gz', 'nestedNativeArchive')]:
        path = collection / name
        assert path.stat().st_size == receipt[key]['bytes'] and sha(path) == receipt[key]['sha256']
    assert gate['closedArchiveSha256'] == receipt['nestedNativeArchive']['sha256']
    files, directories, logical = set(), set(), 0
    with tarfile.open(collection / 'full-closed-round.tar.gz', 'r|gz') as stream:
        for member in stream:
            name = member.name.rstrip('/')
            rel = PurePosixPath(name)
            assert str(rel) == name and not rel.is_absolute() and '..' not in rel.parts
            assert name not in files | directories
            if member.isdir():
                row = inventory['directories'][name]
                assert (member.mode, member.uid, member.gid) == (row['mode'], row['uid'], row['gid'])
                directories.add(name)
                continue
            assert member.isfile()
            row = inventory['files'][name]
            assert (member.size, member.mode, member.uid, member.gid) == (row['bytes'], row['mode'], row['uid'], row['gid'])
            digest, size = hashlib.sha256(), 0
            handle = stream.extractfile(member)
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
                size += len(block)
                assert size <= row['bytes']
            assert size == row['bytes'] and digest.hexdigest() == row['sha256']
            logical += size
            files.add(name)
    assert files == set(inventory['files']) and directories == set(inventory['directories'])
    assert (len(files), len(directories), logical) == (165, 23, 1259969876)
    assert logical == receipt['outerLogicalBytes'] == root_review['outerLogicalBytes']
    assert len(raw['inputs']) == 38
    for name, row in raw['inputs'].items():
        rel = PurePosixPath(name)
        assert str(rel) == name and not rel.is_absolute() and '..' not in rel.parts
        path = collection / name
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    bindings = read(HERE / 'SOURCE_COPY_BINDINGS.json')
    for row in bindings['omittedDuplicateJarsBoundToRetainedFullOuter']:
        assert row['outerMember'] in files
        original = inventory['files'][row['outerMember']]
        assert (row['bytes'], row['sha256']) == (original['bytes'], original['sha256'])
    native_inventory = read(collection / 'raw-files/job/after-clean-stop.json')['archive']['inventory']
    canonical = json.dumps(native_inventory, sort_keys=True, separators=(',', ':')).encode()
    assert hashlib.sha256(canonical).hexdigest() == gate['closedNativeInventorySha256']
    no_upload = read(HERE / 'root-review/NO_GATE_UPLOAD.json')
    assert no_upload['finalArm'] is True and no_upload['remoteGateUploaded'] is False
    assert gate['remoteGateUploaded'] is False and gate['nextArmAuthorized'] is False
    assert not (HERE / 'root-review/gate-upload-source.py').exists()
    prior_pins = {1: 'f60593c37f3ae23e1368ba8b7d04882738979c654c6d965465f6bcd471019181',
                  2: '353b5d0cee3754db758f3902beda163cbff434d4c58ae0bb4999fa1da90ddeaf',
                  3: 'e0645774d701e859df39338c9c3088089f172ce14e3e9c8bf3ad906e06a56a3e'}
    for number, expected in prior_pins.items():
        prior = HERE / ('config/inputs/arm-%d-collection-gate.json' % number)
        assert sha(prior) == expected
        assert inventory['files']['source/release/arm-%d-collection-gate.json' % number]['sha256'] == expected
    assert read(HERE / 'launch/LAUNCH_ATTEMPT.json')['priorCollectionSha256'] == prior_pins[3]
    frozen = read(HERE / '../arm-2/close-preparation-r2/PREPARATION_FROZEN.json')
    assert frozen['guardTests'] == 13 and frozen['guardExitCode'] == 0
    for name, row in frozen['files'].items():
        path = HERE / '../arm-2/close-preparation-r2' / name
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        assert oct(path.stat().st_mode & 0o777) == row['mode']
    close = read(HERE / 'close-inspection/ROOT_CONTROLLER_CLOSED.json')
    assert close['arm'] == 4 and close['controllerIdentityGone'] is True and close['allOwnedStopped'] is True
    assert close['inspectionSourceSha256'] == frozen['sourceSha256'] == sha(HERE / 'close-inspection/executed-source.py')
    assert close['inspectionSha256'] == sha(HERE / 'close-inspection/stdout.json')
    print(json.dumps({'passed': True, 'outerFiles': len(files), 'outerDirectories': len(directories),
                      'outerLogicalBytes': logical, 'rawInputsRehashed': len(raw['inputs']),
                      'omittedDuplicateJarsFullyBound': len(bindings['omittedDuplicateJarsBoundToRetainedFullOuter']),
                      'noNextArmCandidateEmitted': True, 'finalRootGateNoUploadVerified': True,
                      'allPriorGatesBound': 3, 'closedGenericProbeFrozenGuards': 13,
                      'sourceCodeFingerprint': raw['arms'][0]['config']['actualCodeSha256'],
                      'noExtractionNetworkJavaOrSignals': True, 'performanceRecalculatedByThisCopyCheck': False}, sort_keys=True))


if __name__ == '__main__':
    main()
