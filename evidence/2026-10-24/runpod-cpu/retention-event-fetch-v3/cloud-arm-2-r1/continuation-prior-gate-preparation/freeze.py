"""Root-executed only AFTER actual private push. Local validation and two new JSON receipts only."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, stat, subprocess, sys
sys.dont_write_bytecode = True
from contracts import *
ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runtime/cloud/cpu-20261024'
HERE = Path(__file__).resolve().parent
VISIBILITY = BASE / 'event-cloud-repository-visibility-r1/REPOSITORY.json'
VISIBILITY_SHA = '3c7a64e521a8133c490f70fd8602a458fe8208f460f59b9554ac8ec3e3f4b873'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def load(path):
    return json.loads(path.read_text())

def no_links(path):
    path = Path(path).absolute()
    need('..' not in path.parts and not any(x.is_symlink() for x in (path, *path.parents)), 'Canonical nonlinked local path')
    return path

def row(path):
    s = path.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'Independent regular local evidence')
    return dict(mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid, bytes=s.st_size, sha256=sha(path))

def snapshot(path):
    no_links(path)
    need(path.is_dir(), 'Existing directory')
    files = {}
    directories = {}
    for f in [path] + sorted(path.rglob('*')):
        need(not f.is_symlink(), 'No evidence symlink')
        s = f.lstat()
        name = str(f.relative_to(path))
        if stat.S_ISDIR(s.st_mode):
            directories[name] = dict(mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid)
        else:
            files[name] = row(f)
    return {'files': files, 'directories': directories}

def verify_archive(archive):
    inventory = load(archive / 'INVENTORY.json')
    closed = load(archive / 'CLOSED.json')
    need(closed['passed'] is True and closed['inventorySha256'] == sha(archive / 'INVENTORY.json'), 'Closed exact evidence manifest')
    need(closed['allOriginalCollectionAndBothCompleteTarsRetained'] is True and closed['sourceCopyBeforeAfterEqual'] is True
         and closed['fullShaSizeModeUidGidEmptyDirectoryClosureVerified'] is True and closed['allKnownMarkerScansPassed'] is True,
         'Complete archive/copy/metadata/marker closure')
    actual = snapshot(archive)
    actual['files'].pop('INVENTORY.json')
    actual['files'].pop('CLOSED.json')
    need(actual['files'] == inventory['files'] and actual['directories'] == inventory['directories'], 'Every full archive file and directory exact')
    need(len(actual['files']) <= 1500 and sum(r['bytes'] for r in actual['files'].values()) <= 512 * 1024**2,
         'Finite full evidence cap')
    return inventory, closed

def git(*args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
    result = subprocess.run(['git', *args], cwd=ROOT, env=env, capture_output=True, check=True, timeout=60)
    return result.stdout

def blob_sha1(path):
    h = hashlib.sha1()
    h.update(b'blob ' + str(path.stat().st_size).encode() + b'\x00')
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def verify_current_private_commit(archive, inventory, expected_commit):
    rel = str(archive.relative_to(ROOT))
    need(not git('status', '--porcelain', '--untracked-files=all', '--', rel).strip(), 'Full evidence must already be committed clean')
    need(git('rev-parse', '--show-object-format').strip() == b'sha1', 'Registered repository Git object format')
    tracked = {}
    for raw in git('ls-tree', '-r', '-z', 'HEAD', '--', rel).split(b'\0'):
        if not raw:
            continue
        head, name = raw.split(b'\t', 1)
        mode, kind, object_id = head.decode().split()
        need(kind == 'blob' and mode in ('100644', '100755'), 'Only regular committed evidence blobs')
        tracked[name.decode()] = (mode, object_id)
    expected = {rel + '/' + n for n in list(inventory['files']) + ['INVENTORY.json', 'CLOSED.json']}
    need(set(tracked) == expected, 'Exact committed full archive file set, no omissions/extras')
    for name, (mode, object_id) in tracked.items():
        local = ROOT / name
        need(blob_sha1(local) == object_id and bool(local.stat().st_mode & 0o111) == (mode == '100755'),
             'Every full current file matches actual committed Git blob')
    head = git('rev-parse', 'HEAD').decode().strip()
    remote = git('ls-remote', 'origin', 'refs/heads/main').decode().strip()
    origin = git('remote', 'get-url', 'origin').decode().strip()
    need(sha(VISIBILITY) == VISIBILITY_SHA, 'Actual private repository metadata receipt changed')
    validate_private_state(expected_commit, head, remote, origin, load(VISIBILITY))
    return head, remote

def write_new(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(encoded(value))
        output.flush()
        os.fsync(output.fileno())

def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--arm', type=int, choices=[1, 2, 3], required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--root-review', type=Path, required=True)
    parser.add_argument('--archive-root-review', type=Path, required=True)
    parser.add_argument('--archive-root-review-sha256', required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    archive = no_links(a.archive)
    expected_archive = ROOT / ('evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1' % a.arm)
    need(archive == expected_archive, 'Only exact complete current arm archive')
    review_path = no_links(a.root_review)
    need(review_path.is_relative_to(BASE), 'Explicit local root review receipt')
    archive_review_path = no_links(a.archive_root_review)
    need(archive_review_path.is_relative_to(BASE) and hexsha(a.archive_root_review_sha256)
         and sha(archive_review_path) == a.archive_root_review_sha256, 'Root-selected independent full archive review')
    output = no_links(a.output)
    need(output == BASE / ('event-cloud-arm-%d-prior-gate-r1' % a.arm)
         and not output.exists(), 'Fresh local current-arm output, no overwrite')
    run = BASE / ('cpu-event-fetch-arm-%d-collection-r1' % a.arm)
    inventory, closed = verify_archive(archive)
    validate_archive_review(load(archive_review_path), a.arm, sha(archive / 'INVENTORY.json'), sha(archive / 'CLOSED.json'), inventory)
    original = snapshot(run)
    mirror = snapshot(archive / 'actual-collection')
    need(original == mirror, 'Entire original collection mirrored byte/meta/emptydir exact, no excluded files')
    need(row(review_path) == row(archive / 'root-review/ROOT_REVIEW.json'), 'Actual root review mirror exact')
    review = load(review_path)
    for name, pin in review['inputs'].items():
        path = no_links(Path(name) if Path(name).is_absolute() else ROOT / name)
        need(path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], 'Actual independently reviewed input unchanged')
    success = load(run / 'SUCCESS.json')
    final_path = run / 'finalized/LOCAL_COLLECTION_COMPLETE.json'
    final = load(final_path)
    raw_path = run / 'raw/result.json'
    raw = load(raw_path)
    derived = validate_reports(success, final, raw, review, a.arm, sha(raw_path))
    for key, relative in [('rawResult', 'raw/result.json'), ('nativeResult', 'native/result.json'),
                          ('collectionReceipt', 'collection/collection-receipt.json')]:
        actual = run / relative
        pin = final['files'][key]
        need(pin['path'] == str(actual) and actual.stat().st_size == pin['bytes'] and sha(actual) == pin['sha256'],
             'Actual finalizer pointer SHA/size binding')
    head, remote = verify_current_private_commit(archive, inventory, a.expected_commit)
    need(snapshot(run) == original, 'Original collection changed during private-push verification')
    verify_archive(archive)
    need(sha(review_path) == sha(archive / 'root-review/ROOT_REVIEW.json'), 'Root review unchanged before receipt creation')
    need(sha(archive_review_path) == a.archive_root_review_sha256, 'Independent archive review unchanged before receipt creation')
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    push = dict(schemaVersion=1, scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH', repository=REPOSITORY, visibility='private',
                pushCompleted=True, remoteCommitVerified=True, commit=head, fullOriginalEvidencePushed=True,
                evidenceManifestSha256=sha(archive / 'INVENTORY.json'), evidenceClosedSha256=sha(archive / 'CLOSED.json'),
                evidencePath=str(archive.relative_to(ROOT)), closedArchiveSha256=final['closedArchiveSha256'],
                closedNativeInventorySha256=final['closedNativeInventorySha256'],
                repositoryMetadataReceiptSha256=sha(VISIBILITY), actualLsRemote=remote,
                rootIndependentReviewSha256=sha(review_path), archiveRootReviewSha256=sha(archive_review_path), atUtc=now)
    gate = dict(schemaVersion=2, scope='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION', collectionComplete=True,
                arm=a.arm, eventFetchCount=page(a.arm), ownerPollMaximumParkNs=1000000, serverDriverMaximumParkNs=100000,
                frozenReleaseSha256=RELEASE, controllerSha256=CONTROLLER, codeFingerprint=CODE,
                localFullMemberShaBytesModesOwnersEmptyDirsVerified=final['localFullMemberShaBytesModesOwnersEmptyDirsVerified'],
                allRawInputsAndFailuresRetained=final['allClosedRoundRawFilesAndErrorReceiptsRetained'],
                strictSchedulerTimingAdmission=raw['strictSchedulerTimingAdmission'], **derived,
                independentLocalCollectionReceiptSha256=sha(final_path), rawAuditSha256=sha(raw_path),
                closedArchiveSha256=final['closedArchiveSha256'], closedNativeInventorySha256=final['closedNativeInventorySha256'],
                privatePushReceiptSha256=digest(encoded(push)), rootIndependentReviewSha256=sha(review_path),
                archiveRootReviewSha256=sha(archive_review_path), sourceCommit=SOURCE, atUtc=now, sourceSha256=sha(Path(__file__)))
    validate_pair(gate, push, a.arm, digest(encoded(push)))
    output.mkdir(mode=0o700)
    write_new(output / 'private-push.json', push)
    write_new(output / 'collection-gate.json', gate)
    print(json.dumps(dict(passed=True, arm=a.arm, eventFetchCount=page(a.arm), commit=head,
                         gateSha256=sha(output / 'collection-gate.json'), privatePushSha256=sha(output / 'private-push.json'),
                         remoteAccessOrBusinessStarted=False)))

if __name__ == '__main__':
    main()
