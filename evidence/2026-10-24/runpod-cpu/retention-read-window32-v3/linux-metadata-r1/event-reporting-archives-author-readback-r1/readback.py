"""Archive AUTHOR secondary byte/meta readback; not an independent peer endorsement."""
from pathlib import Path
import datetime
import hashlib
import json
import stat

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
EVIDENCE = ROOT / 'evidence/2026-10-24/runpod-cpu'
COMPARISON = EVIDENCE / 'retention-event-fetch-v3/comparison-and-ui-r1'
UNIT = EVIDENCE / 'retention-read-window32-v3/local-unit-validation-r1'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(path.read_text())


def inventory(root, excluded=()):
    files, directories = {}, {}
    for path in [root] + sorted(root.rglob('*')):
        data = path.lstat()
        assert not path.is_symlink(), str(path)
        relative = str(path.relative_to(root))
        meta = dict(mode=stat.S_IMODE(data.st_mode), uid=data.st_uid, gid=data.st_gid)
        if stat.S_ISDIR(data.st_mode):
            directories[relative] = meta
        else:
            assert stat.S_ISREG(data.st_mode) and data.st_nlink == 1, str(path)
            if relative not in excluded:
                files[relative] = dict(meta, bytes=data.st_size, sha256=digest(path))
    return dict(files=files, directories=directories)


def closure(root, expected_inventory, expected_closed, expected_files, expected_dirs):
    assert digest(root / 'INVENTORY.json') == expected_inventory
    assert digest(root / 'CLOSED.json') == expected_closed
    manifest, closed = read(root / 'INVENTORY.json'), read(root / 'CLOSED.json')
    actual = inventory(root, ('INVENTORY.json', 'CLOSED.json'))
    assert closed['passed'] is True and closed['inventorySha256'] == expected_inventory
    assert actual['files'] == manifest['files'] and actual['directories'] == manifest['directories']
    assert len(actual['files']) == closed['payloadFiles'] == expected_files
    assert len(actual['directories']) == closed['directories'] == expected_dirs
    assert sum(row['bytes'] for row in actual['files'].values()) == closed['payloadBytes']
    before, after = read(root / 'SOURCE_BEFORE_COPY.json'), read(root / 'SOURCE_AFTER_COPY.json')
    assert after['passed'] is True and after['allOriginalsUnchanged'] is True
    assert set(before) == set(after['sourceTrees'])
    scopes = {}
    for name, row in before.items():
        assert row['inventory']['explicitCacheExclusions'] == []
        expected = {key: row['inventory'][key] for key in ('files', 'directories')}
        assert row['inventory'] == after['sourceTrees'][name]
        source = Path(row['source'])
        assert source.is_relative_to(BASE) and not any(q.is_symlink() for q in (source, *source.parents))
        assert inventory(source) == expected, ('original source drift', name)
        assert inventory(root / name) == expected, ('incomplete mirror', name)
        scopes[name] = dict(originalSource=str(source), files=len(expected['files']),
                            directories=len(expected['directories']), bytes=sum(x['bytes'] for x in expected['files'].values()))
    return dict(inventorySha256=expected_inventory, closedSha256=expected_closed,
                payloadFiles=expected_files, directories=expected_dirs, payloadBytes=closed['payloadBytes'],
                completeSourceMirrorScopes=scopes, originalAndCopiedFullInventoriesEqual=True)


comparison = closure(COMPARISON,
    'b96b4981aadebcbab1e0457f7e74bc28289fbcd41fe9d5da2900835debd706d7',
    '20c970cccfbed7f122ae66b84d9839ccd38395b751e4bca3a5edcea3bb7aeb51', 109, 33)
unit = closure(UNIT,
    '5c252b54653af6a8c8c5f2c3fe15bd680c56816f17a65e09a84a18cfec6c1ffb',
    'd8da7ba1add75cc01af081e362a4bbaecef51c0510027af297b7ba9b20b49aa8', 582, 263)
assert len(comparison['completeSourceMirrorScopes']) == 26
assert set(unit['completeSourceMirrorScopes']) == {'actual-preparation', 'independent-peer-review'}
assert unit['completeSourceMirrorScopes']['actual-preparation']['files'] == 559
assert unit['completeSourceMirrorScopes']['independent-peer-review']['files'] == 9
references = read(COMPARISON / 'IMMUTABLE_SHARED_ARCHIVE_REFERENCES.json')['sharedArchives']
assert len(references) == 5
allowed = [COMPARISON.resolve()]
shared_receipts = []
for reference in references:
    root = Path(reference['path'])
    assert root.is_relative_to(EVIDENCE)
    allowed.append(root.resolve())
    for name, pin in reference['receipts'].items():
        current = inventory(root / name)['files']['.']
        assert current == pin
    shared_receipts.append(dict(path=str(root), receipts=reference['receipts']))
receipt_inputs = {
    'independent-root-comparison': read(COMPARISON / 'event-fetch-comparison-abab-root-review-r1/ROOT_REVIEW.json')['inputs'],
    'actual-ui-derivation': read(COMPARISON / 'event-fetch-ui-derivation-r1/DERIVATION_RECEIPT.json')['inputs'],
}
bindings = read(COMPARISON / 'ROOT_COMPARISON_AND_UI_INPUT_PORTABLE_BINDINGS.json')['inputs']
assert set(bindings) == set(receipt_inputs)
assert {name: len(rows) for name, rows in bindings.items()} == {'independent-root-comparison': 17, 'actual-ui-derivation': 39}
mapped = {}
for receipt, inputs in receipt_inputs.items():
    assert set(bindings[receipt]) == set(inputs)
    mapped[receipt] = {}
    for original_text, pin in inputs.items():
        row = bindings[receipt][original_text]
        assert row['pin'] == pin
        original = Path(original_text)
        resolved_original = original if original.is_absolute() else ROOT / original
        assert row['originalAbsoluteResolvedPath'] == str(resolved_original)
        relative = Path(row['archivedAt'])
        assert not relative.is_absolute()
        body = (COMPARISON / relative).resolve()
        assert any(body.is_relative_to(root) for root in allowed)
        assert not body.is_symlink() and body.is_file()
        assert body.stat().st_size == pin['bytes'] and digest(body) == pin['sha256']
        if not row['originalPathCurrentlyMatchesRecordedPin']:
            assert resolved_original == ROOT / 'evidence/index.json'
            assert row['historicalUiBaselineMappedWithoutRewritingOriginalPath'] is True
        mapped[receipt][original_text] = dict(archivedAt=row['archivedAt'], **pin)
unit_bindings = read(UNIT / 'ROOT_INPUT_PINS.json')['independentReviewedInputsPortableBindings']
assert len(unit_bindings) == 3
for original_text, row in unit_bindings.items():
    original = Path(original_text)
    body = UNIT / row['archivedAt']
    assert body.resolve().is_relative_to(UNIT.resolve())
    assert inventory(body)['files']['.'] == row['pin'] == inventory(original)['files']['.']
unit_closed = read(UNIT / 'CLOSED.json')
assert unit_closed['scopedR2JUnitTemporaryRawBodiesNotRetained'] is True
assert unit_closed['scopedR2IsNotCompleteTemporaryRawEvidence'] is True
assert unit_closed['performanceOrNativeCloudEvidenceClaimed'] is False
result = dict(schemaVersion=1, passed=True, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='ARCHIVE_AUTHOR_SECONDARY_BYTE_METADATA_READBACK_NOT_INDEPENDENT_PEER_ENDORSEMENT',
    authorOfBothArchives=True, independentPeerEndorsement=False, independentRootVerificationStillSeparate=True,
    scriptSha256=digest(Path(__file__)), comparisonAndUi=comparison, localRead32Unit=unit,
    all26ComparisonScopeMirrorsAndBothUnitScopeMirrorsExact=True,
    all56ComparisonUiPortableBindingsVerified=True, portableBindingBodies=mapped,
    allThreeRead32ReviewedInputBodiesVerified=True, exactFiveSharedArchiveReceipts=shared_receipts,
    r2TemporaryRawGapStillExplicit=True, noNativeOrCapacityOrIndependentOracleClaim=True,
    noBusinessAuditComparatorTestsJvmMetadataSshNetworkGitExecuted=True)
with (HERE / 'READBACK.json').open('x') as output:
    json.dump(result, output, sort_keys=True, indent=2)
    output.write('\n')
print(json.dumps(dict(passed=True, authorSecondaryReadback=True, independentPeerEndorsement=False,
    readbackSha256=digest(HERE / 'READBACK.json'), comparisonPayloadFiles=109, unitPayloadFiles=582,
    exactComparisonScopeMirrors=26, exactUnitScopeMirrors=2, verifiedPortableBodies=56), sort_keys=True))
