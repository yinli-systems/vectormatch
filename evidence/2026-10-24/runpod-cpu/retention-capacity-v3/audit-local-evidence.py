#!/usr/bin/env python3
"""Read-only independent audit; never extracts multi-GB native files or runs Java."""
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent
V = ROOT / 'validation'
CANDIDATE = '4102446b333573efde2b33a0eb53a8177575bad5'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def digest(stream):
    h = hashlib.sha256(); size = 0
    while True:
        part = stream.read(1024 * 1024)
        if not part: break
        h.update(part); size += len(part)
    return h.hexdigest(), size

def js(path):
    return json.loads(path.read_text())

def file_matches(path, expected):
    with path.open('rb') as stream: actual_sha, actual_bytes = digest(stream)
    assert actual_sha == expected['sha256'], str(path)
    assert actual_bytes == expected['bytes'], str(path)
    if 'mode' in expected: assert stat.S_IMODE(path.stat().st_mode) == expected['mode'], str(path)

def safe(name):
    p = PurePosixPath(name)
    assert name and not p.is_absolute() and '..' not in p.parts and str(p) == name, name
    return name

copy = js(ROOT / 'copy-receipt.json')
actual_files = {p.relative_to(V).as_posix() for p in V.rglob('*') if p.is_file()}
assert actual_files == set(copy['files'])
assert not any(p.is_symlink() for p in V.rglob('*'))
for name, expected in copy['files'].items(): file_matches(V / safe(name), expected)

validation = js(V / 'validation-manifest.json')
attempts = []
for record in validation['commandsAndAttempts']:
    path = V / record['directory']
    assert sha((path / 'gradle.log').read_bytes()) == record['stdoutSha256']
    if record.get('sourceArchiveSha256'):
        assert sha((path / 'source-at-failure.zip').read_bytes()) == record['sourceArchiveSha256']
        sources = js(path / 'source-sha256.json')['sources']
        with zipfile.ZipFile(path / 'source-at-failure.zip') as archive:
            assert set(archive.namelist()) == set(sources)
            for name, expected in sources.items(): assert sha(archive.read(safe(name))) == expected
    attempts.append({'directory':record['directory'], 'exitCode':record['exitCode'], 'stdoutSha256':record['stdoutSha256']})

artifact_root = V / 'native-r1/artifact-state'
manifest = js(artifact_root / 'manifest.json')
assert sha((artifact_root / 'manifest.json').read_bytes()) == validation['artifactCaptureManifestSha256']
for name, expected in manifest['files'].items(): file_matches(artifact_root / safe(name), expected)
class_counts = {}
for module, record in manifest['classes'].items():
    with zipfile.ZipFile(artifact_root / record['zip']) as archive:
        assert set(archive.namelist()) == set(record['classSha256'])
        for name, expected in record['classSha256'].items(): assert sha(archive.read(safe(name))) == expected
    class_counts[module] = len(record['classSha256'])
    with zipfile.ZipFile(artifact_root / 'lib' / (module+'-0.1.0-SNAPSHOT.jar')) as jar:
        actual_classes = {n for n in jar.namelist() if n.endswith('.class')}
        assert actual_classes == set(record['classSha256'])
        for name, expected in record['classSha256'].items(): assert sha(jar.read(safe(name))) == expected
for name, record in manifest['jars'].items(): file_matches(artifact_root / 'lib' / name, record)

sources = {}
with tarfile.open(artifact_root / 'source-state.tar.gz', 'r|gz') as archive:
    for item in archive:
        assert item.isfile(), item.name
        name = safe(item.name); assert name not in sources
        with archive.extractfile(item) as stream: h, size = digest(stream)
        assert h == manifest['sourceSha256'][name]
        sources[name] = {'sha256':h, 'bytes':size}
assert set(sources) == set(manifest['sourceSha256'])

distribution = js(V / 'distribution-r1/manifest.json')
assert distribution['sourceCommit'] == CANDIDATE
assert sha((V / 'distribution-r1/actual-observation.json').read_bytes()) == distribution['observationSha256']
for name, record in distribution['jars'].items(): file_matches(artifact_root / 'lib' / name, record)
# Exact reproduction of RetentionNodeMainV3.codeFingerprint's observed code-source order.
types = ['io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']
jar_by_type = ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','aeron-all-1.53.3.jar']
jar_hash = hashlib.sha256(); native_hash = hashlib.sha256()
for type_name, jar_name in zip(types, jar_by_type):
    jar_hash.update(type_name.encode()); jar_hash.update((artifact_root / 'lib' / jar_name).read_bytes())
    native_hash.update(type_name.encode())
    # Gradle native test loads cluster classes but MatchingEngine from its core JAR.
    # Artifact-inventory.json below independently binds this observed code-source layout.
    module = 'cluster' if 'cluster.RetentionNodeMain' in type_name else None
    if module:
        with zipfile.ZipFile(artifact_root / manifest['classes'][module]['zip']) as archive:
            for name in sorted(archive.namelist()): native_hash.update(name.encode()); native_hash.update(archive.read(name))
    else: native_hash.update((artifact_root / 'lib' / jar_name).read_bytes())
assert jar_hash.hexdigest() == distribution['observation']['actualDistributionCodeFingerprint']
assert native_hash.hexdigest() == distribution['nativeClassDirectoryFingerprint']

xml_reports = []
for name in ['focused-r3','native-r1']:
    counts = {key:0 for key in ['tests','failures','errors','skipped']}
    for path in sorted((V / name / 'xml').glob('*.xml')):
        tree = ET.parse(path).getroot()
        for key in counts: counts[key] += int(tree.attrib.get(key,0))
    expected = js(V / name / ('receipt.json' if name == 'focused-r3' else 'test-receipt.json'))
    for key in counts: assert counts[key] == expected[key]
    assert counts['failures'] == counts['errors'] == counts['skipped'] == 0
    xml_reports.append({'directory':name, **counts})

native = []
small = {}
for directory in sorted((V / 'native-archives').iterdir()):
    record = js(directory / 'manifest.json'); archive_path = directory / 'native-state.tar.gz'
    assert sha(archive_path.read_bytes()) == record['archiveSha256']
    assert archive_path.stat().st_size == record['archiveBytes']
    files = {}; directories = {}; total = 0
    with tarfile.open(archive_path,'r|gz') as archive:
        for item in archive:
            name = safe(item.name)
            assert name not in files and name not in directories
            if item.isdir():
                directories[name] = {'mode':item.mode}
                assert directories[name] == record['directories'][name]
            else:
                assert item.isfile(), name
                with archive.extractfile(item) as stream:
                    if item.size <= 1024*1024 and (name.endswith('.json') or name.endswith('.log')):
                        data = stream.read(); h, size = sha(data), len(data); small[name] = data
                    else: h, size = digest(stream)
                files[name] = {'sha256':h,'bytes':size,'mode':item.mode}
                assert files[name] == record['files'][name], name
                total += size
    assert files == record['files'] and directories == record['directories']
    assert len(files) == record['fileCount'] and len(directories) == record['directoryCount'] and total == record['logicalBytes']
    native.append({'directory':directory.name,'files':len(files),'directories':len(directories),'logicalBytes':total,'gzipBytes':record['archiveBytes'],'gzipSha256':record['archiveSha256'],'allFileBytesModesAndDirectoryClosurePassed':True})

arms = []
artifact_observations = 0
for cap in [1,4]:
    prefix = 'cap-'+str(cap)
    load = json.loads(small[prefix+'/load/load-result.json'])
    completion = json.loads(small[prefix+'/completion.json'])
    stopped = json.loads(small[prefix+'/owned-stop.json'])
    functional = json.loads(small[prefix+'/functional-result.json'])
    inventory = json.loads(small[prefix+'/artifact-inventory.json'])
    assert inventory['codeFingerprint'] == native_hash.hexdigest()
    expected_counts = dict(zip(types,[len(manifest['classes']['cluster']['classSha256']),1,1,1]))
    observed_counts = dict.fromkeys(types,0)
    for item in inventory['actualFiles']:
        kind = item['type']; observed_counts[kind] += 1
        if kind == types[0]:
            delimiter = '/cluster/build/classes/java/main/'
            assert delimiter in item['path']
            name = item['path'].split(delimiter,1)[1]
            assert item['sha256'] == manifest['classes']['cluster']['classSha256'][name]
            with zipfile.ZipFile(artifact_root / manifest['classes']['cluster']['zip']) as archive:
                assert len(archive.read(name)) == item['bytes']
        else:
            jar = 'core-0.1.0-SNAPSHOT.jar' if kind == types[1] else 'aeron-all-1.53.3.jar'
            assert Path(item['path']).name == jar
            assert item['sha256'] == manifest['jars'][jar]['sha256'] and item['bytes'] == manifest['jars'][jar]['bytes']
        artifact_observations += 1
    assert observed_counts == expected_counts
    assert load['scheduledArrivals'] == load['releasedArrivals'] == load['confirmedAcceptedUniqueOrders'] == 6400
    assert load['notSent'] == load['unknownFinal'] == load['serverRejected'] == load['duplicateOrOutOfRangeAcceptedOrderIds'] == 0
    assert load['maintenanceCycles'] == 3 and completion['allOwnedStopped'] and completion['passed'] and stopped['allOwnedStopped']
    assert functional['passed'] and functional['allThreeSnapshotLogsMatched'] and functional['noCapacityPromotion']
    assert load['allArrivalP99Ns'] == load['acceptedOrderConditionalP99Ns']
    assert load['schedulerTimingValid'] == (cap == 4)
    assert load['schedulerLatenessOver20ms'] == (5 if cap == 1 else 0)
    arms.append({'batchCap':cap,'arrivals':6400,'confirmedAcceptedUniqueOrders':6400,'notSent':0,'unknownFinal':0,'maintenanceCycles':3,
                 'schedulerTimingValid':load['schedulerTimingValid'],'schedulerLatenessOver20ms':load['schedulerLatenessOver20ms'],
                 'allArrivalP99Ns':load['allArrivalP99Ns'],'lastKnownReplyDrainNs':load['lastKnownReplyDrainNs'],'totalSourceDrainNs':load['totalSourceDrainNs'],
                 'arrivalWindowGoodputPerSecond':load['arrivalWindowGoodputPerSecond'],'allOwnedStopped':True})
report = {'schema':'independent-local-capacity-evidence-audit-v1','completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'candidateCommit':CANDIDATE,'exactCopyFiles':len(actual_files),'exactCopyBytes':copy['bytes'],'allCopiedFileShaBytesModesPassed':True,
          'attemptLogsAndFailedSourceZipInventoriesPassed':True,'classZipAndRuntimeJarContentsPassed':True,'classCounts':class_counts,
          'sourceArchiveInventoryFiles':len(sources),'sourceArchiveInventoryPassed':True,'actualArtifactManifestSha256':sha((artifact_root/'manifest.json').read_bytes()),
          'distributionManifestSha256':sha((V/'distribution-r1/manifest.json').read_bytes()),'nativeClassDirectoryFingerprint':native_hash.hexdigest(),
          'nativeLoadedArtifactObservationsReconciled':artifact_observations,
          'actualDistributionCodeFingerprint':jar_hash.hexdigest(),'attempts':attempts,'junitXmlRecount':xml_reports,'nativeArchives':native,'arms':arms,
          'scope':'Read-only artifact/raw preservation audit. No build/test/cloud execution. Local functional arms only; cap1 scheduler invalid and both arms have seconds of backlog/drain. No performance promotion, sustained capacity, external durability or 100M proof.'}
print(json.dumps(report,indent=2))
