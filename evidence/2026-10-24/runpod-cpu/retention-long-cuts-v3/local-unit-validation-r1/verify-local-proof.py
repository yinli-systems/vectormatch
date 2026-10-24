"""Local read-only archive verification; no Java, Git, SSH, extraction or native operation."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import stat
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    unit = HERE / 'units-r1'
    frozen = read(HERE / 'SOURCE_FROZEN_R1.json')
    registered = read(unit / 'source-freeze.json')
    with zipfile.ZipFile(unit / 'registered-sources.zip') as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) == len(registered) == 109
        assert set(names) == set(registered)
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts
            body = archive.read(name)
            assert len(body) == registered[name]['bytes']
            assert hashlib.sha256(body).hexdigest() == registered[name]['sha256']
        for row in frozen['paths']:
            final = HERE / 'final-source' / row['path']
            assert final.stat().st_size == row['bytes'] and sha(final) == row['sha256']
            if row['path'].endswith('.java'):
                assert registered[row['path']]['sha256'] == row['sha256']
        old_doc = archive.read('cluster/RETENTION_LONG_CUTS_V3.md')
    correction = read(HERE / 'POST_UNIT_DOCUMENTATION_CORRECTION.json')['changes'][0]
    assert hashlib.sha256(old_doc).hexdigest() == correction['before']['sha256']
    assert sha(HERE / 'tested-document-before-correction.md') == correction['before']['sha256']
    assert sha(HERE / 'final-source/cluster/RETENTION_LONG_CUTS_V3.md') == correction['after']['sha256']
    artifacts = read(unit / 'artifact-capture.json')['files']
    assert len(artifacts) == 328
    xml = []
    for row in artifacts:
        path = unit / row['path']
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        assert oct(stat.S_IMODE(path.stat().st_mode)) == row['mode']
        if path.suffix == '.xml':
            xml.append(path)
    totals = {key: 0 for key in ['tests', 'failures', 'errors', 'skipped']}
    for path in xml:
        suite = ET.parse(path).getroot()
        for key in totals:
            totals[key] += int(suite.attrib.get(key, '0'))
    assert len(xml) == 8 and totals == {'tests': 53, 'failures': 0, 'errors': 0, 'skipped': 0}
    completion = read(unit / 'completion.json')
    assert completion['exitCode'] == 0 and completion['totals'] == totals
    assert completion['sourceUnchanged'] is True and completion['jdkUnchanged'] is True
    links = read(HERE / 'TEST_CLASSPATH_CLOSURE.json')['entries']
    for row in links:
        path = HERE / row['retainedRelativePath']
        assert path.is_file() and path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    observation = read(HERE / 'distribution-observation-r1/actual-distribution-observation.json')
    digest = hashlib.sha256()
    for row in observation['actualCodeSources']:
        path = unit / 'artifact-state/distribution/lib' / Path(row['path']).name
        assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
        # The Pilot's code-source observation is additional provenance. Node fingerprint's
        # established four-type formula starts at RetentionNodeMainV3.
        if row['class'] != 'io.vectormatch.cluster.RetentionCapacityAeronPilotV3':
            digest.update(row['class'].encode())
            digest.update(path.read_bytes())
    fingerprint = digest.hexdigest()
    assert fingerprint == observation['actualCodeFingerprint'] == '6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
    assert observation['noDriverOrClusterStarted'] is True
    old_linux = HERE / '../../retention-idle-v3/release-metadata-r1/idle-linux-metadata-r1/actual-linux-distribution-observation.json'
    assert sha(old_linux) == 'be6e47b6697f5518a846f6e2c720681761dcb1e10231507bd0d22470c198e60f'
    assert observation['workloads']['SHORT']['plan'] == read(old_linux)['plans']['8']
    long_plan = observation['workloads']['LONG_CUTS']
    assert (long_plan['arrivals'], long_plan['rate'], long_plan['fullCommandCuts'], long_plan['cycles']) == (33792, 500, 11, 12)
    assert long_plan['plan']['admitted'] is True
    assert long_plan['plan']['maximumRawTraceBytes'] < 2 * 1024**3
    assert long_plan['plan']['maximumAllocatedGrowthBytes'] < 5 * 1024**3 // 2
    root = read(HERE / 'root-review/ROOT_REVIEW.json')
    assert root['passed'] is True and root['actualXmlTotals'] == totals
    assert root['compiledArtifactsRehashed'] == len(artifacts)
    assert root['actualInstalledJarFingerprintIndependentlyRecomputed'] == fingerprint
    assert root['sourceFreezeSha256'] == sha(HERE / 'SOURCE_FROZEN_R1.json')
    local = read(HERE / 'LOCAL_VALIDATION_COMPLETE.json')
    assert local['actualCodeFingerprint'] == fingerprint and local['unitTotals'] == totals
    for key in ['sourceFreeze', 'unitCompletion', 'actualArtifactCapture', 'actualJarObservation', 'actualJarObservationCompletion']:
        row = local[key]
        relative = row['path'].removeprefix('runtime/long-cuts-local-validation/')
        assert (HERE / relative).stat().st_size == row['bytes'] and sha(HERE / relative) == row['sha256']
    print(json.dumps({'passed': True, 'testedRegisteredSourceMembers': 109,
                      'currentRootSourceReviewCount': root['unitSourceInputsCurrentlyRehashed'],
                      'artifactsRehashed': len(artifacts), 'xmlFiles': len(xml), 'xmlTotals': totals,
                      'classpathBodiesVerifiedOrExactShaLinked': len(links), 'actualCodeFingerprint': fingerprint,
                      'docBeforeAfterAndCorrectionPreserved': True, 'shortPlanExactOldLinux': True,
                      'longPlanAdmittedOnlyNotRuntimeProof': True, 'nativeOrCapacityProofClaimed': False,
                      'noJavaGitSshOrNativeExecuted': True}, sort_keys=True))


if __name__ == '__main__':
    main()
