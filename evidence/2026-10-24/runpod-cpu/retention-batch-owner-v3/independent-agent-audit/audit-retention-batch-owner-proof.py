#!/usr/bin/env python3
"""Independently verify preserved owner evidence. Local only; no source edits, extraction, or process control."""
from pathlib import Path, PurePosixPath
import datetime
import hashlib
import importlib.util
import json
import re
import shutil
import stat
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'runtime/cloud/cpu-20261024/retention-batch-v3-worktree'
OUT = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-batch-owner-v3'
AGENT = OUT / 'agent-owner-validation'
CAPTURE = AGENT / 'native-r1/artifact-state'
REV = '24c25c368340b54db1bfc8075b2bcffa5441b892'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def xml_counts(folder):
    total = {k: 0 for k in ['tests', 'failures', 'errors', 'skipped']}
    rows = []
    for p in sorted(folder.glob('TEST-*.xml')):
        suite = ET.parse(p).getroot()
        row = {k: int(suite.get(k, '0')) for k in total}
        for k in total:
            total[k] += row[k]
        rows.append({'path': str(p.relative_to(OUT)), 'sha256': sha(p), **row})
    return {'totals': total, 'suites': rows}


def artifact_state():
    state = json.loads((CAPTURE / 'manifest.json').read_text())
    require(sha(CAPTURE / 'manifest.json') == '3eb2d9637df0361e494f95608a96a138c64d4a1ebf21cf09bce7e1b617c9438c', 'Frozen capture manifest differs')
    for name, info in state['files'].items():
        p = CAPTURE / name
        require(not p.is_symlink() and p.stat().st_size == info['bytes'] and sha(p) == info['sha256'], 'Captured artifact differs: ' + name)
    class_counts = {}
    for module, info in state['classes'].items():
        with zipfile.ZipFile(CAPTURE / info['zip']) as classes, zipfile.ZipFile(CAPTURE / 'lib' / (module + '-0.1.0-SNAPSHOT.jar')) as jar:
            expected = info['classSha256']
            require(set(classes.namelist()) == set(expected), 'Captured class ZIP closure differs')
            require({n for n in jar.namelist() if n.endswith('.class')} == set(expected), 'Captured JAR class closure differs')
            for name, expected_sha in expected.items():
                raw = classes.read(name)
                require(digest(raw) == expected_sha and jar.read(name) == raw, 'Actual class/JAR bytes differ: ' + name)
        class_counts[module] = len(expected)
    seen = set()
    captured_differences = []
    with tarfile.open(CAPTURE / 'source-state.tar.gz', 'r|gz') as archive:
        for member in archive:
            name = member.name
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and member.isreg()
                    and name in state['sourceSha256'] and name not in seen and member.size <= 2 * 1024**2, 'Unsafe/unexpected captured source')
            raw = archive.extractfile(member).read()
            require(digest(raw) == state['sourceSha256'][name], 'Captured source SHA differs')
            current = WORK / name
            if not current.is_file() or sha(current) != digest(raw):
                captured_differences.append(name)
            seen.add(name)
    require(seen == set(state['sourceSha256']), 'Whole captured source closure differs')
    # Post-native forced distribution has different JAR container bytes; preserve and verify its own receipt.
    later = OUT / 'agent-core-dist-artifact'
    expected_dist = json.loads((AGENT / 'core-dist-r1/receipt.json').read_text())['distributionJars']
    for name, info in expected_dist.items():
        p = later / name
        require(p.stat().st_size == info['bytes'] and sha(p) == info['sha256'], 'Exact later distribution JAR missing/different')
    for module, info in state['classes'].items():
        with zipfile.ZipFile(later / (module + '-0.1.0-SNAPSHOT.jar')) as jar:
            require({n for n in jar.namelist() if n.endswith('.class')} == set(info['classSha256']), 'Later JAR class closure differs')
            for name, expected_sha in info['classSha256'].items():
                require(digest(jar.read(name)) == expected_sha, 'Later distribution class changed')
    return {'passed': True, 'capturedClassCounts': class_counts, 'capturedSources': len(seen),
            'capturedSourceDifferencesVsFinalWorktree': captured_differences,
            'allPreNativeClassesMatchPreNativeJars': True, 'allPostNativeDistClassesMatchPreNativeCapture': True,
            'preNativeJarContainersAndPostNativeDistJarContainersBothRetained': True}


def observed_binding(source, target):
    lines = (source / 'artifact-inventory.sha256').read_text().splitlines()
    require(len(lines) == 128, 'Unexpected owner runtime inventory entries')
    entries = []
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64}) ([0-9]+) (.+)', line)
        require(match is not None, 'Malformed observed artifact inventory')
        expected_sha, size, actual = match.groups()
        size = int(size)
        marker = '/cluster/build/classes/java/main/'
        if marker in actual:
            require(actual.startswith(str(WORK) + marker), 'Unexpected observed class path')
            name = actual.split(marker, 1)[1]
            with zipfile.ZipFile(CAPTURE / 'cluster-actual-classes.zip') as classes, zipfile.ZipFile(CAPTURE / 'lib/cluster-0.1.0-SNAPSHOT.jar') as jar:
                raw = classes.read(name)
                require(len(raw) == size and digest(raw) == expected_sha and jar.read(name) == raw, 'Observed runtime class differs')
            entries.append({'observed': actual, 'bytes': size, 'sha256': expected_sha, 'capturedClassZip': 'cluster-actual-classes.zip', 'entry': name})
        else:
            name = Path(actual).name
            p = CAPTURE / 'lib' / name
            require(name.endswith('.jar') and p.is_file() and p.stat().st_size == size and sha(p) == expected_sha, 'Observed runtime JAR differs')
            entries.append({'observed': actual, 'bytes': size, 'sha256': expected_sha, 'capturedJar': name})
    write(target, {'passed': True, 'inventorySha256': sha(source / 'artifact-inventory.sha256'), 'observedEntriesVerified': len(entries),
                   'preservedArtifactState': str(CAPTURE.relative_to(OUT)), 'entries': entries})
    return len(entries)


def main():
    require(subprocess.check_output(['git', '-C', str(WORK), 'rev-parse', 'HEAD'], text=True).strip() == REV, 'Frozen owner revision differs')
    require(not subprocess.check_output(['git', '-C', str(WORK), 'status', '--porcelain'], text=True).strip(), 'Frozen owner worktree dirty')
    mpath = OUT / 'source-validation/RETENTION_BATCH_OWNER_V3_VALIDATION.json'
    require(sha(mpath) == 'b9a55d5906d7fab2b624e285065bdb6bd0262968424ecac019e6368e6b1ca27f', 'Frozen owner validation differs')
    manifest = json.loads(mpath.read_text())
    target = OUT / 'independent-agent-audit'
    target.mkdir(exist_ok=False)
    primitives = ROOT / 'runtime/cloud/cpu-20261024/collect-retention-batch-proofs.py'
    require(sha(primitives) == 'c074efe4e31cb5833fc9af402e33fa6472f94e17cd0dee906bb997b9ffcd8b88', 'Frozen archival primitives differ')
    spec = importlib.util.spec_from_file_location('frozen_archive_primitives', primitives)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shutil.copy2(primitives, target / 'archive-primitives.py')
    state_result = artifact_state()
    write(target / 'artifact-state-audit.json', state_result)
    counts = {}
    for name, expected in [('focused-r1', 17), ('native-r1', 18), ('core-dist-r1', 33)]:
        result = xml_counts(AGENT / name)
        require(result['totals'] == {'tests': expected, 'failures': 0, 'errors': 0, 'skipped': 0}, 'Actual XML counts differ: ' + name)
        counts[name] = result
    write(target / 'test-audit.json', counts)
    rows = []
    for original in manifest['nativeArchives']:
        copied_manifest = AGENT / Path(original['manifest']).relative_to('build/owner-validation')
        require(sha(copied_manifest) == original['manifestSha256'], 'Original native manifest differs')
        record = json.loads(copied_manifest.read_text())
        source = Path(record['source']).resolve()
        require(source.parent == WORK / 'cluster/build/retention-batch-native-attempts' and source.name == original['attempt'], 'Exact owned attempt required')
        files, dirs, completion = module.tree_inventory(source)
        require(set(files) == set(record['files']) and set(dirs) == set(record['directories']), 'Whole native source closure differs')
        for name, info in record['files'].items():
            require(all(info[k] == files[name][k] for k in ['bytes', 'sha256', 'mode']), 'Native source differs from archived manifest')
        packed = copied_manifest.parent / record['archive']['path']
        require(packed.stat().st_size == record['archive']['bytes'] and sha(packed) == record['archive']['sha256'], 'Native archive size/SHA differs')
        checked = module.verify_tar(packed, source.name, files, dirs, stat.S_IMODE(source.stat().st_mode))
        arm_out = target / source.name
        arm_out.mkdir()
        entries = observed_binding(source, arm_out / 'observed-artifact-binding.json')
        result = json.loads((source / 'result.json').read_text())
        require(result['passed'] and result['logicalWorkers'] == 128 and result['businessSeq'] == 260
                and result['eventSeq'] == 516 and result['firstAcceptedPlaces'] == 258 and result['strictNoPhysicalResends'], 'Functional owner fixture result differs')
        require(result['physicalFramesPerRound'] == 128 // result['batchCap'], 'Owner frame grouping differs')
        proof = {'passed': True, 'sourceRevision': REV, 'originalSource': str(source),
                 'originalManifest': str(copied_manifest.relative_to(OUT)), 'originalManifestSha256': sha(copied_manifest),
                 'archive': record['archive'], 'nativeFiles': len(files), 'logicalBytes': sum(x['bytes'] for x in files.values()),
                 'fileInventory': files, 'directoryModes': dirs, 'completion': completion, 'result': result,
                 'streamReadback': checked, 'observedArtifactEntriesVerified': entries,
                 'originalDeleted': False, 'scope': 'Finite local one-host W128 functional owner fixture only; no capacity/endurance, external durability, persistent client recovery or independent hosts.'}
        write(arm_out / 'audit.json', proof)
        rows.append({k: proof[k] for k in ['originalSource', 'nativeFiles', 'logicalBytes', 'archive', 'observedArtifactEntriesVerified']})
        print(json.dumps({'attempt': source.name, 'passed': True, 'nativeFiles': len(files), 'logicalBytes': proof['logicalBytes'], 'artifactEntries': entries}), flush=True)
    unchanged = manifest['unchangedLegacyClient']
    require(sha(WORK / unchanged['path']) == unchanged['sha256']
            and (WORK / unchanged['path']).read_bytes() == subprocess.check_output(['git', '-C', str(WORK), 'show', manifest['baseCommit'] + ':' + unchanged['path']]), 'Legacy client changed')
    for name, expected_sha in manifest['modifiedSourceSha256'].items():
        require(sha(WORK / name) == expected_sha and sha(OUT / 'source-validation/source' / name) == expected_sha, 'Final modified source/copy differs')
    write(target / 'summary.json', {'passed': True, 'auditedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'sourceRevision': REV, 'agentNativeTrees': len(rows), 'nativeProofs': rows, 'artifactState': state_result,
                'finalNativeFocusedTests': 18, 'forcedCoreTests': 33,
                'earlierFocusedTests': {'count': 17, 'scope': 'Earlier local unit execution; its OwnerV3Test fixture source differs from final native suite. Production owner sources match; do not credit as extra final-source tests.'},
                'allCapturedAttemptLogsPreserved': True, 'failurePolicy': manifest['attemptPolicy'], 'legacyClientUnchangedVs973': True,
                'scope': 'Agent native fixtures only. Root actual forced fullcheck and new smoke trees must be archived separately after completion.'})
    shutil.copy2(Path(__file__), target / Path(__file__).name)
    print(json.dumps({'passed': True, 'agentNativeTrees': len(rows), 'nativeFiles': sum(x['nativeFiles'] for x in rows)}), flush=True)


if __name__ == '__main__':
    main()
