"""Only archive CLOSED metadata preparation/execution/reviews; do not execute JVM/SSH/tests/Git."""
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
TARGET = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/linux-metadata-r1'
LIMIT = 128 * 1024**2


def need(ok, message):
    if not ok:
        raise AssertionError(message)


def load(path):
    return json.loads(path.read_text())


def main():
    plan, freeze = load(HERE / 'COPY_PLAN.json'), load(HERE / 'SOURCE_FROZEN.json')
    for name, pin in freeze['sourceFiles'].items():
        need(p.row(HERE / name) == pin, 'Closed archival source changed')
    for text, pin in freeze['checkedPrimitiveInputs'].items():
        need(p.row(Path(text)) == pin, 'Existing checked copy/marker primitive changed')
    need(not TARGET.exists() and shutil.disk_usage(ROOT).free >= 1024**3 + LIMIT,
         'Fresh immutable archive with1GiB floor plus128MiB reserve')
    trees = {name: Path(row['source']) for name, row in plan['sourceTrees'].items()}
    for name, source in trees.items():
        need(source.is_absolute() and source.is_relative_to(BASE) and source.name == name and '..' not in source.parts
             and not any(q.is_symlink() for q in (source, *source.parents)), 'Explicit regular closed source scope')
        need(p.snapshot(source) == plan['sourceTrees'][name]['inventory'], 'Full closed source before-copy pin')
    prep = trees['read-window32-linux-metadata-preparation-r1']
    actual = trees['read-window32-linux-metadata-execution-r1']
    root_review = trees['read-window32-linux-metadata-root-review-r1']
    m, c = load(prep / 'INVENTORY.json'), load(prep / 'CLOSED.json')
    whole = plan['sourceTrees'][prep.name]['inventory']
    need(p.sha(prep / 'INVENTORY.json') == '64b0adf45d5966b5f7cdfafd6b4fc14eb280753c2672be0c304fda55e5a572a7'
         and p.sha(prep / 'CLOSED.json') == 'f9c4767d3516189fea98617a5ccb7d16d52b34bfabd1fb39a0f4edb41a7cc51c',
         'Original prepared-only closure, not rewritten after real Linux execution')
    payload = {name: pin for name, pin in whole['files'].items() if name not in ('INVENTORY.json', 'CLOSED.json')}
    need(payload == m['files'] and len(payload) == m['fileCount'] == 46
         and sum(pin['bytes'] for pin in payload.values()) == m['bytes'] == 15907739, 'Entire original46 payload exact closure')
    expected_dirs = {row['path']: {k: row[k] for k in ('mode', 'uid', 'gid')} for row in m['directories']}
    need(expected_dirs == {name: row for name, row in whole['directories'].items() if name != '.'}
         and len(expected_dirs) == m['directoryCount'] == 9, 'All9 original directories/meta')
    for row in m['directories']:
        need((not any((prep / row['path']).iterdir())) == row['empty'], 'Original empty-directory flag')
    need(c['compilerJvmExecuted'] is True and c['metadataJvmExecuted'] is False and c['linuxExecuted'] is False,
         'Historical preparation includes actual compiler JVM but no metadata main at that time')
    success, receipt, observation = [load(actual / name) for name in ('SUCCESS.json', 'remote-receipt.json', 'actual-linux-distribution-observation.json')]
    need(success['passed'] is True and success['linuxMetadataExecuted'] is True and success['metadataJvmExecuted'] is True
         and success['metadataJvmExited'] is True and success['strictOwnedPidAbsent'] is True
         and success['performanceEvidence'] is False and success['benchmarkExecuted'] is False,
         'Actual separate real Linux metadata JVM executed, exited and is not native performance')
    need(p.sha(actual / 'actual-linux-distribution-observation.json') == success['linuxObservationSha256'] == receipt['observationSha256']
         and p.sha(actual / 'remote-receipt.json') == success['receiptSha256'], 'Actual Linux observation/receipt full-body pins')
    need(observation['sourceCommit'] == '605eb43fcafd8fa0a6287304387c93c4d1bbddf6'
         and observation['actualCodeFingerprint'] == 'd0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
         and observation['fixedEventFetchCount'] == 32 and observation['nativeUdpOrBusinessSessionStarted'] is False
         and observation['performanceEvidence'] is False, 'Actual same candidate fixedpage32 metadata identity only')
    post = load(root_review / 'ROOT_REVIEW.json')
    need(post['passed'] is True and post['actualMetadataJvmExecuted'] is True
         and post['normalExit0AndStrictOwnedPidAbsenceVerified'] is True and post['nativeQualificationPending'] is True,
         'Closed independent root metadata post-execution receipt')
    independent = trees['read-window32-linux-metadata-independent-review-r1']
    independent_closed = load(independent / 'CLOSED.json')
    independent_report = load(independent / 'REVIEW.json')
    need(independent_closed['passed'] is True and independent_closed['sourceInputsUnchanged'] is True
         and independent_closed['reviewSha256'] == p.sha(independent / 'REVIEW.json')
         and independent_report['passed'] is True and independent_report['metadataOnly'] is True
         and independent_report['performanceEvidence'] is False,
         'Actual closed independent Linux metadata review source/logs preserved separately from author readbacks')
    need(independent_closed['files'] == {name: pin for name, pin in plan['sourceTrees'][independent.name]['inventory']['files'].items() if name != 'CLOSED.json'},
         'Full independent-review payload closure')
    portable = {}
    for original_text, pin in post['inputPins'].items():
        original = BASE / original_text
        need(original.is_relative_to(actual) and original.stat().st_size == pin['bytes'] and p.sha(original) == pin['sha256'],
             'Actual root metadata input body unchanged')
        portable[original_text] = dict(pin=pin, originalAbsolutePath=str(original),
            archivedAt=actual.name + '/' + str(original.relative_to(actual)))
    need(len(portable) == 9, 'All nine actual metadata root input bodies')
    reporting_push = load(trees['event-fetch-reporting-private-push-r1'] / 'PUSH_VERIFIED.json')
    need(reporting_push['passed'] is True and reporting_push['all700ChangedFileBodiesMatchCommittedGitBlobs'] is True,
         'Actual prior reporting private push, including original failure source')
    for reference in plan['sharedArchives']:
        for name, pin in reference['receipts'].items():
            need(p.row(Path(reference['path']) / name) == pin, 'Exact closed earlier unit/reporting reference')
    source_bytes = sum(pin['bytes'] for tree in plan['sourceTrees'].values() for pin in tree['inventory']['files'].values())
    need(source_bytes + 16 * 1024**2 <= LIMIT, '128MiB archive cap with16MiB metadata reserve')
    attempt = HERE / 'attempt-r1'
    attempt.mkdir()
    p.save(attempt / 'REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        archiverSourceSha256=p.sha(Path(__file__)), copyPlanSha256=p.sha(HERE / 'COPY_PLAN.json'),
        sourceBytes=source_bytes, target=str(TARGET), noJvmSshTestsAuditorComparatorGitRunByArchive=True,
        archivedEvidenceContainsActualCompilerAndLinuxMetadataJvmExecution=True))
    try:
        TARGET.mkdir(parents=True)
        for name, original in trees.items():
            p.copy_tree(original, TARGET / name, plan['sourceTrees'][name]['inventory'])
        p.save(TARGET / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])
        p.save(TARGET / 'ACTUAL_METADATA_ROOT_INPUT_PORTABLE_BINDINGS.json', dict(passed=True, inputs=portable,
            originalInputStringsUnchanged=True, allNineActualInputBodiesRetained=True, mappingOnlyNoMetadataOrReviewRerun=True))
        for row in portable.values():
            body = TARGET / row['archivedAt']
            need(body.stat().st_size == row['pin']['bytes'] and p.sha(body) == row['pin']['sha256'], 'Copied actual metadata input byte binding')
        p.save(TARGET / 'IMMUTABLE_SHARED_ARCHIVE_REFERENCES.json', dict(sharedArchives=plan['sharedArchives'],
            earlierFullUnitAndReportingBodiesNotDuplicated=True))
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
        need(not scan.HITS, 'Any known-marker hit retained as failure; no closure')
        for name, original in trees.items():
            need(p.snapshot(original) == plan['sourceTrees'][name]['inventory'], 'Closed source changed after copy/scan')
            need(p.snapshot(TARGET / name) == plan['sourceTrees'][name]['inventory'], 'Full source mirror differs after copy/scan')
        for reference in plan['sharedArchives']:
            for name, pin in reference['receipts'].items():
                need(p.row(Path(reference['path']) / name) == pin, 'Earlier archive receipt drift')
        p.save(TARGET / 'SOURCE_AFTER_COPY.json', dict(passed=True, allOriginalsUnchanged=True,
            sourceTrees={name: p.snapshot(original) for name, original in trees.items()}))
        inventory = p.snapshot(TARGET)
        total = sum(pin['bytes'] for pin in inventory['files'].values())
        need(total <= LIMIT, '128MiB final archive cap')
        p.save(TARGET / 'INVENTORY.json', dict(schemaVersion=1, files=inventory['files'], directories=inventory['directories'],
            payloadFiles=len(inventory['files']), payloadBytes=total, fullModeUidGidEmptyDirectoryClosure=True,
            excludedSelfAndClosure=['INVENTORY.json', 'CLOSED.json']))
        for name, pin in inventory['files'].items():
            need(p.row(TARGET / name) == pin, 'Final payload drift')
        result = dict(schemaVersion=1, passed=True, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            inventorySha256=p.sha(TARGET / 'INVENTORY.json'), payloadFiles=len(inventory['files']),
            directories=len(inventory['directories']), payloadBytes=total, sourceScopes=len(trees),
            original46PreparedOnlyPayloadPlusClosureReceiptsRetained=True,
            actualLinuxMetadataJvmExecutionBodiesRetained=True, sourceOnlyAndActualExecutionScopesKeptDistinct=True,
            allAvailableRootFailedSchemaAndPrivatePushReviewSourcesAndDiagnosticsRetained=True,
            archiveAuthorReadbackNotIndependentPeerEndorsement=True,
            actualClosedIndependentLinuxMetadataReviewSeparatelyRetained=True,
            allNineActualMetadataRootInputBodiesByteBound=True,
            allSourceCopyBeforeAfterAndFullMirrorsEqual=True, fullShaSizeModeUidGidAndEmptyDirectoryClosureVerified=True,
            allKnownMarkerScansPassed=True, noJvmSshTestsAuditorComparatorNetworkGitRunByArchive=True,
            archivedPrepCompilerJvmAndActualLinuxMetadataJvmReallyExecuted=True,
            nativeBusinessOrPerformanceQualificationClaimed=False, fullJdkRuntimeNotCaptured=True,
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
