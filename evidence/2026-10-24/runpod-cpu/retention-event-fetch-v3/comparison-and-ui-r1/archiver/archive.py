"""Complete copy of explicit CLOSED comparison/UI/reporting scopes; no audit or benchmark rerun."""
from pathlib import Path
import datetime
import importlib.util
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
SCANNER_ROOT = BASE / 'event-cloud-arm-archive-preparation-r2'
sys.path.insert(0, str(SCANNER_ROOT))
spec = importlib.util.spec_from_file_location('checked_recursive_marker_scanner', SCANNER_ROOT / 'archive.py')
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
p = scan.p
p.EXCLUDED_PARTS = set()
TARGET = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/comparison-and-ui-r1'
LIMIT = 128 * 1024**2


def need(ok, message):
    if not ok:
        raise AssertionError(message)


def load(path):
    return json.loads(path.read_text())


def byte_pin(path):
    row = p.row(path)
    return {k: row[k] for k in ('bytes', 'sha256')}


def main():
    plan, freeze = load(HERE / 'COPY_PLAN.json'), load(HERE / 'SOURCE_FROZEN.json')
    for name, pin in freeze['sourceFiles'].items():
        need(p.row(HERE / name) == pin, 'Frozen archiver source changed')
    for text, pin in freeze['checkedPrimitiveInputs'].items():
        need(p.row(Path(text)) == pin, 'Existing checked primitives changed')
    need(not TARGET.exists() and shutil.disk_usage(ROOT).free >= 1024**3 + LIMIT,
         'Fresh archive with1GiB floor plus128MiB copy reserve')
    trees = {name: Path(row['source']) for name, row in plan['sourceTrees'].items()}
    need(len(trees) == 26 and plan['allExplicitClosedScopesWithoutExclusions'] is True, 'Exactly26 root-selected full closed scopes')
    for name, source in trees.items():
        need(source.is_absolute() and source.is_relative_to(BASE) and '..' not in source.parts
             and name == source.name and not any(q.is_symlink() for q in (source, *source.parents)), 'Explicit canonical closed scope')
        need(p.snapshot(source) == plan['sourceTrees'][name]['inventory'], 'Closed source before-copy full pin changed')
    need(len(plan['sharedArchives']) == 5, 'Four raw arms plus separate localread32 unit archive references')
    lookup = {}

    def index(pin, path):
        lookup.setdefault((pin['bytes'], pin['sha256']), []).append(path)

    for name, row in plan['sourceTrees'].items():
        for rel, pin in row['inventory']['files'].items():
            index(pin, TARGET / name / rel)
    for reference in plan['sharedArchives']:
        shared = Path(reference['path'])
        need(shared.is_relative_to(ROOT / 'evidence/2026-10-24/runpod-cpu'), 'Explicit prior evidence reference')
        for name, pin in reference['receipts'].items():
            need(p.row(shared / name) == pin, 'Immutable sibling archive receipt changed')
            index(pin, shared / name)
        manifest, closed = load(shared / 'INVENTORY.json'), load(shared / 'CLOSED.json')
        need(closed['passed'] is True and closed['inventorySha256'] == p.sha(shared / 'INVENTORY.json'), 'Closed sibling inventory binding')
        for rel, pin in manifest['files'].items():
            index(pin, shared / rel)
    comparison = load(trees['event-fetch-comparison-abab-r1'] / 'COMPARISON.json')
    root_review = load(trees['event-fetch-comparison-abab-root-review-r1'] / 'ROOT_REVIEW.json')
    derivation = load(trees['event-fetch-ui-derivation-r1'] / 'DERIVATION_RECEIPT.json')
    ui_closed = load(trees['event-fetch-ui-derivation-r1'] / 'CLOSED.json')
    browser = load(trees['event-fetch-ui-browser-validation-r1'] / 'BROWSER_VERIFIED.json')
    need(comparison['passed'] is True and comparison['allInputsUnchanged'] is True
         and root_review['passed'] is True and root_review['allFourArmsReviewed'] is True
         and root_review['comparisonSha256'] == p.sha(trees['event-fetch-comparison-abab-r1'] / 'COMPARISON.json'), 'Actual closed four-arm comparison and independent root review')
    need(ui_closed['passed'] is True and ui_closed['actualExporterInvocations'] == 1
         and ui_closed['allExplicitInputsUnchanged'] is True and ui_closed['old21ObjectsAndCapacityFieldsUnchanged'] is True,
         'Actual once-only closed25-record UI derivation')
    need(browser['passed'] is True and browser['localPassivePreview'] is True
         and browser['businessCommandsSent'] is False and browser['cloudLiveConnectionAdded'] is False
         and p.sha(trees['event-fetch-ui-browser-validation-r1'] / 'b2-detail.png') == browser['screenshotSha256']
         and p.sha(trees['event-fetch-ui-browser-validation-r1'] / 'b2-detail-ax.txt') == browser['actualAxSha256'],
         'Actual passive browser B2 screenshot/AX bodies')
    need(load(trees['event-cloud-arm-4-private-push-r1'] / 'private-push.json')['noNextArmGateManufactured'] is True,
         'Final raw arm actual private push does not manufacture a continuationgate4')
    need(load(trees['read-window32-root-source-review-r1'] / 'ROOT_REVIEW.json')['performanceProven'] is False,
         'Separate read32 candidate remains local correctness evidence')
    input_sets = {
        'independent-root-comparison': root_review['inputs'],
        'actual-ui-derivation': derivation['inputs'],
    }
    portable = {}
    for receipt_name, inputs in input_sets.items():
        portable[receipt_name] = {}
        for original_text, pin in inputs.items():
            candidates = lookup.get((pin['bytes'], pin['sha256']), [])
            need(candidates, 'Every recorded comparison/UI input has a real copied or sibling body: ' + original_text)
            original = Path(original_text)
            resolved = original if original.is_absolute() else ROOT / original
            # This is mapping/copy verification, not a recomputation of the underlying evidence.
            actual_matches = resolved.is_file() and resolved.stat().st_size == pin['bytes'] and p.sha(resolved) == pin['sha256']
            need(actual_matches or resolved == ROOT / 'evidence/index.json', 'Only intentionally applied historical UI index may differ live')
            selected = sorted(candidates, key=lambda q: (not q.is_relative_to(TARGET), len(str(q)), str(q)))[0]
            portable[receipt_name][original_text] = dict(pin=pin, originalAbsoluteResolvedPath=str(resolved),
                originalPathCurrentlyMatchesRecordedPin=actual_matches, archivedAt=os.path.relpath(selected, TARGET),
                copiedOrSiblingBody=True, historicalUiBaselineMappedWithoutRewritingOriginalPath=not actual_matches)
    source_bytes = sum(pin['bytes'] for row in plan['sourceTrees'].values() for pin in row['inventory']['files'].values())
    need(source_bytes + 16 * 1024**2 <= LIMIT, 'Bounded128MiB archive with16MiB metadata reserve')
    attempt = HERE / 'attempt-r1'
    attempt.mkdir()
    p.save(attempt / 'REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        archiverSourceSha256=p.sha(Path(__file__)), copyPlanSha256=p.sha(HERE / 'COPY_PLAN.json'), sourceBytes=source_bytes,
        target=str(TARGET), noBusinessAuditTestsComparatorJvmMetadataSshNetworkGit=True))
    try:
        TARGET.mkdir(parents=True)
        for name, original in trees.items():
            p.copy_tree(original, TARGET / name, plan['sourceTrees'][name]['inventory'])
        p.save(TARGET / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])
        p.save(TARGET / 'IMMUTABLE_SHARED_ARCHIVE_REFERENCES.json', dict(sharedArchives=plan['sharedArchives'],
            exactInventoryAndClosedPins=True, originalLargeRawNativeAndUnitBodiesNotDuplicated=True))
        for receipt_name, inputs in portable.items():
            for original_text, row in inputs.items():
                actual = TARGET / row['archivedAt']
                need(byte_pin(actual) == row['pin'], 'Actual portable copied/sibling input body binding')
        p.save(TARGET / 'ROOT_COMPARISON_AND_UI_INPUT_PORTABLE_BINDINGS.json', dict(passed=True, inputs=portable,
            originalInputStringsUnchanged=True, all56RecordedInputMappingsVerified=True,
            historicalAppliedLiveIndexIsExplicit=True, independentOracleOrRunnableHarnessClaimed=False,
            mappingOnlyNoBusinessOrComparisonReaudit=True))
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
            sharedNativeAndUnitBodyReferencesNotRescanned=True, boundedKnownMarkerReviewNotUniversalSecretAbsence=True))
        need(not scan.HITS, 'Marker hits retained as failures; no closure')
        for name, original in trees.items():
            need(p.snapshot(original) == plan['sourceTrees'][name]['inventory'], 'Closed source changed after copy/scan')
            need(p.snapshot(TARGET / name) == plan['sourceTrees'][name]['inventory'], 'Full source mirror changed')
        for reference in plan['sharedArchives']:
            for name, pin in reference['receipts'].items():
                need(p.row(Path(reference['path']) / name) == pin, 'Shared receipt changed after copy/scan')
        p.save(TARGET / 'SOURCE_AFTER_COPY.json', dict(passed=True, allOriginalsUnchanged=True,
            sourceTrees={name: p.snapshot(original) for name, original in trees.items()}))
        inventory = p.snapshot(TARGET)
        total = sum(pin['bytes'] for pin in inventory['files'].values())
        need(total <= LIMIT, 'Finite128MiB final archive cap')
        p.save(TARGET / 'INVENTORY.json', dict(schemaVersion=1, files=inventory['files'], directories=inventory['directories'],
            payloadFiles=len(inventory['files']), payloadBytes=total, fullModeUidGidEmptyDirectoryClosure=True,
            excludedSelfAndClosure=['INVENTORY.json', 'CLOSED.json']))
        for name, pin in inventory['files'].items():
            need(p.row(TARGET / name) == pin, 'Final payload drift')
        result = dict(schemaVersion=1, passed=True, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            inventorySha256=p.sha(TARGET / 'INVENTORY.json'), payloadFiles=len(inventory['files']),
            directories=len(inventory['directories']), payloadBytes=total, fullClosedSourceScopes=26,
            allSourceCopyBeforeAfterAndFullMirrorsEqual=True, fullShaSizeModeUidGidAndEmptyDirectoryClosureVerified=True,
            allActualComparisonUiBrowserControlsAndFailuresRetained=True, all56RecordedComparisonAndUiInputBodiesMapped=True,
            fourRawAndOneRead32UnitArchivesReferencedByExactClosure=True, largeNativeAndUnitBodiesNotDuplicated=True,
            read32OnlyLocal58TestsNotMixedWithPerformance=True, scopedR2TemporaryRawMissingExplicit=True,
            noTestsJvmMetadataComparatorBusinessAuditSshNetworkGitExecuted=True, allKnownMarkerScansPassed=True,
            noNewCapacityHardRealtime100MOrIndependentOracleClaim=True, closureExcludes=['INVENTORY.json', 'CLOSED.json'])
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
