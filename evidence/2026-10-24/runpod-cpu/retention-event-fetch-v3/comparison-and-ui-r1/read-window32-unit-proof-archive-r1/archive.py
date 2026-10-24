"""Copy only CLOSED read32 source/unit/peer evidence with checked existing primitives."""
from pathlib import Path
import datetime
import importlib.util
import json
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
SCANNER_ROOT = BASE / 'event-cloud-arm-archive-preparation-r2'
sys.path.insert(0, str(SCANNER_ROOT))
spec = importlib.util.spec_from_file_location('checked_event_recursive_archive_scanner', SCANNER_ROOT / 'archive.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
p = scan.p
p.EXCLUDED_PARTS = set()
TARGET = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/local-unit-validation-r1'
LIMIT = 128 * 1024**2
SOURCE = '605eb43fcafd8fa0a6287304387c93c4d1bbddf6'
CODE = 'd0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'


def need(ok, message):
    if not ok:
        raise AssertionError(message)


def load(path):
    return json.loads(path.read_text())


def main():
    plan = load(HERE / 'COPY_PLAN.json')
    freeze = load(HERE / 'SOURCE_FROZEN.json')
    for name, pin in freeze['sourceFiles'].items():
        need(p.row(HERE / name) == pin, 'Closed archiver source changed')
    for text, pin in freeze['checkedPrimitiveInputs'].items():
        need(p.row(Path(text)) == pin, 'Checked existing primitive source changed')
    need(not TARGET.exists() and shutil.disk_usage(ROOT).free >= 1024**3 + LIMIT,
         'Fresh archive only with1GiB floor plus128MiB reserve')
    trees = {name: Path(row['source']) for name, row in plan['sourceTrees'].items()}
    need(set(trees) == {'actual-preparation', 'independent-peer-review'}, 'Only actual closed source and peer trees')
    for name, source in trees.items():
        need(source.is_absolute() and source.is_relative_to(BASE) and '..' not in source.parts
             and not any(q.is_symlink() for q in (source, *source.parents)), 'Explicit regular local source')
        need(p.snapshot(source) == plan['sourceTrees'][name]['inventory'], 'Exact closed source tree before copy')
    source = trees['actual-preparation']
    peer = trees['independent-peer-review']
    m, c, report = load(source / 'INVENTORY.json'), load(source / 'CLOSED.json'), load(peer / 'REVIEW.json')
    need(p.sha(source / 'INVENTORY.json') == '602e464420c7f372bacb7280cf104dd79f492b40b18b5d29b83080973f92d965'
         and p.sha(source / 'CLOSED.json') == '7edce2f9bb8e23af8ec7ff512c7b9134669e291f23b39e8a61153589cb985b2b',
         'Actual immutable source closure receipts')
    need(c['sourceCommit'] == SOURCE and c['inventorySha256'] == p.sha(source / 'INVENTORY.json'), 'Actual source commit and closure')
    source_view = plan['sourceTrees']['actual-preparation']['inventory']
    payload = {n: row for n, row in source_view['files'].items() if n not in ('INVENTORY.json', 'CLOSED.json')}
    need(payload == m['files'] and len(payload) == m['fileCount'] == 557
         and sum(row['bytes'] for row in payload.values()) == m['bytes'] == 80249476, 'Original557 payload exact full bytes/meta')
    directories = {row['path']: {k: row[k] for k in ('mode', 'uid', 'gid')} for row in m['directories']}
    need(directories == {n: row for n, row in source_view['directories'].items() if n != '.'}
         and len(directories) == m['directoryCount'] == 258, 'Original empty directories and full directory metadata')
    for row in m['directories']:
        need((not any((source / row['path']).iterdir())) == row['empty'], 'Original empty-directory flags')
    need(p.sha(peer / 'REVIEW.json') == '402464dd7b3292a11d50d4ca79b53ea29748fd3f42f734cc86c93986279b48b9'
         and p.sha(peer / 'CLOSED.json') == 'fdf9f47a316ac909e76bfd2b10f421eff119a50d28e3cf0241e34f3016048a5e',
         'Actual selected closed independent review')
    peer_closed = load(peer / 'CLOSED.json')
    need(peer_closed['passed'] is True and peer_closed['sourceEvidenceUnchanged'] is True
         and peer_closed['r2TemporaryRawEvidenceGapExplicitlyQualified'] is True
         and peer_closed['files'] == {n: row for n, row in plan['sourceTrees']['independent-peer-review']['inventory']['files'].items() if n != 'CLOSED.json'},
         'Complete actual peer payload and explicit r2 evidence gap')
    need(report['passed'] is True and report['allInputsUnchanged'] is True and report['sourceCommit'] == SOURCE
         and report['actualCodeFingerprint'] == CODE and report['actualFinalDistinctPassingTests'] == 58
         and report['actualFinalXmlSuites'] == 10 and report['actualFinalFailureErrorSkipZero'] is True,
         'Closed same candidate58 final tests and actual local metadata receipt')
    need(report['performanceOrNativeCloudProof'] is False and report['testsGradleJvmSshGitExecutedByReviewer'] is False,
         'No performance/native or rerun claim')
    portable = {}
    for text, sha in report['inputs'].items():
        original = Path(text)
        need(original.is_relative_to(source) and p.sha(original) == sha, 'Actual independent-review input pin unchanged')
        portable[text] = dict(pin=p.row(original), archivedAt='actual-preparation/' + str(original.relative_to(source)))
    source_bytes = sum(row['bytes'] for tree in plan['sourceTrees'].values() for row in tree['inventory']['files'].values())
    need(source_bytes + 16 * 1024**2 <= LIMIT, '128MiB finite copy cap with16MiB metadata reserve')
    attempt = HERE / 'attempt-r1'
    attempt.mkdir()
    p.save(attempt / 'REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        archiverSourceSha256=p.sha(Path(__file__)), copyPlanSha256=p.sha(HERE / 'COPY_PLAN.json'),
        sourceBytes=source_bytes, target=str(TARGET), noTestsJvmMetadataSshNetworkGit=True,
        originalSourceInventorySha256=p.sha(source / 'INVENTORY.json'), originalSourceClosedSha256=p.sha(source / 'CLOSED.json')))
    try:
        TARGET.mkdir(parents=True)
        for name, original in trees.items():
            p.copy_tree(original, TARGET / name, plan['sourceTrees'][name]['inventory'])
        p.save(TARGET / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])
        p.save(TARGET / 'ROOT_INPUT_PINS.json', dict(passed=True, sourceTrees=plan['sourceTrees'],
            rootReviewReceipt=p.row(peer / 'REVIEW.json'), originalSourceClosedReceipt=p.row(source / 'CLOSED.json'),
            independentReviewedInputsPortableBindings=portable, originalAbsolutePathsUnchanged=True,
            allActualPreparationAndPeerBodiesCopiedWithoutExclusions=True))
        archiver = TARGET / 'archiver'
        archiver.mkdir()
        for name in ('archive.py', 'README.md', 'SOURCE_FROZEN.json', 'COPY_PLAN.json'):
            shutil.copy2(HERE / name, archiver / name)
        shutil.copy2(attempt / 'REGISTRATION.json', archiver / 'ATTEMPT_REGISTRATION.json')
        primitive_dir = archiver / 'checked-primitives'
        primitive_dir.mkdir()
        for name, original in [('event_recursive_archive.py', SCANNER_ROOT / 'archive.py'),
                               ('event_archive_contract.py', SCANNER_ROOT / 'archive_contract.py'),
                               ('event_SOURCE_FROZEN.json', SCANNER_ROOT / 'SOURCE_FROZEN.json'),
                               ('owner_snapshot_copy_primitives.py', scan.PRIMITIVES)]:
            shutil.copy2(original, primitive_dir / name)
        (TARGET / 'README.md').open('x').write((HERE / 'README.md').read_text())
        for original in sorted(TARGET.rglob('*')):
            if original.is_file():
                scan.scan_file(original, str(original.relative_to(TARGET)))
        p.save(TARGET / 'KNOWN_CREDENTIAL_MARKER_REVIEW.json', dict(passed=not scan.HITS,
            namedMarkerClasses=sorted(p.MARKERS), hits=scan.HITS, scannedObjects=len(scan.SCANNED),
            scannedBytesIncludingNested=scan.TOTAL, scanned=scan.SCANNED, containerMembers=scan.MEMBERS,
            allCopiedBytesAndRecursiveTarZipJarEntriesScanned=True, noExtraction=True,
            boundedKnownMarkerReviewNotUniversalSecretAbsence=True))
        need(not scan.HITS, 'Any marker hit retained as failure; no closure')
        for name, original in trees.items():
            need(p.snapshot(original) == plan['sourceTrees'][name]['inventory'], 'Original source changed after copy/scan')
            need(p.snapshot(TARGET / name) == plan['sourceTrees'][name]['inventory'], 'Full source mirror changed')
        p.save(TARGET / 'SOURCE_AFTER_COPY.json', dict(passed=True, allOriginalsUnchanged=True,
            sourceTrees={name: p.snapshot(original) for name, original in trees.items()}))
        inventory = p.snapshot(TARGET)
        total = sum(row['bytes'] for row in inventory['files'].values())
        need(total <= LIMIT, 'Finite128MiB final payload cap')
        p.save(TARGET / 'INVENTORY.json', dict(schemaVersion=1, files=inventory['files'], directories=inventory['directories'],
            payloadFiles=len(inventory['files']), payloadBytes=total, fullModeUidGidEmptyDirectoryClosure=True,
            excludedSelfAndClosure=['INVENTORY.json', 'CLOSED.json']))
        for name, pin in inventory['files'].items():
            need(p.row(TARGET / name) == pin, 'Final copied payload changed')
        result = dict(schemaVersion=1, passed=True, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            inventorySha256=p.sha(TARGET / 'INVENTORY.json'), payloadFiles=len(inventory['files']),
            directories=len(inventory['directories']), payloadBytes=total, sourceCommit=SOURCE, actualLocalMetadataFingerprint=CODE,
            originalSourcePayloadFiles557PlusBothClosureReceiptsCopied=True, finalDistinctPassingTests58NotSumOfAttempts=True,
            originalSourceCopyBeforeAfterEqual=True, fullShaSizeModeUidGidAndEmptyDirectoryClosureVerified=True,
            allRetainedFailuresAndPeerDiagnosticsCopied=True, scopedR2JUnitTemporaryRawBodiesNotRetained=True,
            scopedR2IsNotCompleteTemporaryRawEvidence=True, scopedR3R4R5RetainedRawTempBodiesCopied=True,
            allFourActualInstalledJarBodiesAnd17ClasspathBodiesPerCompletedAttemptRetained=True,
            fullJdkBodyNotCaptured=True, allKnownMarkerScansPassed=True,
            noTestsJvmMetadataBusinessAuditSshNetworkGitExecuted=True, performanceOrNativeCloudEvidenceClaimed=False,
            closureExcludes=['INVENTORY.json', 'CLOSED.json'])
        p.save(TARGET / 'CLOSED.json', result)
        result = dict(result, closedSha256=p.sha(TARGET / 'CLOSED.json'), scannedObjects=len(scan.SCANNED),
                      scannedBytesIncludingNested=scan.TOTAL, freeBytesAfter=shutil.disk_usage(ROOT).free)
        p.save(attempt / 'COMPLETION.json', result)
        print(json.dumps(result, sort_keys=True))
    except BaseException as error:
        import traceback
        p.save(attempt / 'FAILED.json', dict(passed=False, error=repr(error), traceback=traceback.format_exc(),
            partialArchiveAndSourcesPreserved=True, noAutomaticRetry=True))
        raise


if __name__ == '__main__':
    main()
