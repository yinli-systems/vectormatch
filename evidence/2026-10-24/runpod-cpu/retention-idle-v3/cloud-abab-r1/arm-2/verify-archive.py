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
    assert gate['arm'] == 2 and gate['maximumParkNs'] == 100000
    assert gate['rootIndependentReviewSha256'] == sha(HERE / 'root-review/ROOT_REVIEW.json')
    assert gate['rootIndependentReviewSourceSha256'] == sha(HERE / 'root-review-source.py')
    assert gate['independentLocalCollectionReceiptSha256'] == sha(HERE / 'collection-run/finalized/LOCAL_COLLECTION_COMPLETE.json')
    assert read(HERE / 'collection-run/finalized/ROOT_GATE_CANDIDATE_NOT_APPROVED.json')['collectionComplete'] is False
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
    assert (len(files), len(directories), logical) == (163, 23, 1259958295)
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
    upload = read(HERE / 'root-review/GATE_UPLOAD_REGISTRATION.json')
    uploaded = read(HERE / 'root-review/gate-upload.stdout')
    assert upload['sourceSha256'] == sha(HERE / 'root-review/gate-upload-source.py')
    assert upload['gateSha256'] == uploaded['sha256'] == sha(HERE / 'root-review/ROOT_COLLECTION_GATE.json')
    assert uploaded['passed'] is True
    prior = HERE / 'config/inputs/arm-1-collection-gate.json'
    assert sha(prior) == 'f60593c37f3ae23e1368ba8b7d04882738979c654c6d965465f6bcd471019181'
    assert inventory['files']['source/release/arm-1-collection-gate.json']['sha256'] == sha(prior)
    assert read(HERE / 'launch/LAUNCH_ATTEMPT.json')['priorCollectionSha256'] == sha(prior)
    frozen = read(HERE / 'close-preparation-r2/PREPARATION_FROZEN.json')
    assert frozen['guardTests'] == 13 and frozen['guardExitCode'] == 0
    for name, row in frozen['files'].items():
        path = HERE / 'close-preparation-r2' / name
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        assert oct(path.stat().st_mode & 0o777) == row['mode']
    close = read(HERE / 'close-inspection/ROOT_CONTROLLER_CLOSED.json')
    assert close['arm'] == 2 and close['controllerIdentityGone'] is True and close['allOwnedStopped'] is True
    assert close['inspectionSourceSha256'] == frozen['sourceSha256'] == sha(HERE / 'close-inspection/executed-source.py')
    assert close['inspectionSha256'] == sha(HERE / 'close-inspection/stdout.json')
    print(json.dumps({'passed': True, 'outerFiles': len(files), 'outerDirectories': len(directories),
                      'outerLogicalBytes': logical, 'rawInputsRehashed': len(raw['inputs']),
                      'omittedDuplicateJarsFullyBound': len(bindings['omittedDuplicateJarsBoundToRetainedFullOuter']),
                      'rootGateCandidateRemainsFalse': True, 'rootGateAndUploadBindingsVerified': True,
                      'priorArm1GateBound': True, 'closedGenericProbeFrozenGuards': 13,
                      'sourceCodeFingerprint': raw['arms'][0]['config']['actualCodeSha256'],
                      'noExtractionNetworkJavaOrSignals': True, 'performanceRecalculatedByThisCopyCheck': False}, sort_keys=True))


if __name__ == '__main__':
    main()
