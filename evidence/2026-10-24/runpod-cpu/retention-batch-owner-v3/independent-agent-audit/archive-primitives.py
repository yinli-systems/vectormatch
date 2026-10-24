#!/usr/bin/env python3
"""Bounded local proof collector. No extraction, process control, SSH, or source mutation."""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'runtime/cloud/cpu-20261024/retention-batch-v3-worktree'
VALID = WORK / 'build/batch-validation'
OUT = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-batch-v3'
REV = '973ff8f9bc4d9266c52d21866480dd45b31c39f9'
VALIDATION_SHA = 'ce211402aee2ac8dd7f52b87de3dc49dee5d5fb43ce2d15208d1041262598b41'
LIMIT = 3 * 1024**3


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def json_write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def regular(path, maximum=LIMIT):
    require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), 'Regular file required: ' + str(path))
    require(path.stat().st_size <= maximum, 'File exceeds bound: ' + str(path))


def copied(source, target):
    regular(source, 64 * 1024**2)
    target.parent.mkdir(parents=True, exist_ok=True)
    require(not target.exists(), 'Refuse overwrite: ' + str(target))
    before = {'bytes': source.stat().st_size, 'sha256': sha(source)}
    shutil.copy2(source, target)
    require(target.stat().st_size == before['bytes'] and sha(target) == before['sha256'], 'Copied bytes differ')
    return before


def tree_inventory(source):
    require(source.is_dir(), 'Native source missing')
    require(source.resolve() == source, 'Use canonical source paths')
    for parent in [source] + list(source.parents):
        require(not parent.is_symlink(), 'Symlink ancestor refused')
    completion = json.loads((source / 'completion.json').read_text())
    require(completion.get('passed') is True and completion.get('allOwnedStopped') is True,
            'Stopped successful owned attempt required')
    files, directories = {}, {}
    paths = sorted(source.rglob('*'))
    require(len(paths) <= 512, 'Too many native paths')
    for p in paths:
        rel = p.relative_to(source).as_posix()
        require(not p.is_symlink(), 'Native symlink refused')
        mode = stat.S_IMODE(p.stat().st_mode)
        require(mode & 0o7000 == 0, 'Special native permission bits refused')
        if p.is_dir():
            directories[rel] = {'mode': mode}
        else:
            regular(p, 512 * 1024**2)
            files[rel] = {'bytes': p.stat().st_size, 'sha256': sha(p), 'mode': mode,
                          'allocatedBytes': getattr(p.stat(), 'st_blocks', 0) * 512}
    require(len(files) <= 256 and sum(v['bytes'] for v in files.values()) <= LIMIT, 'Native tree exceeds bound')
    return files, directories, completion


def verify_tar(packed, prefix, files, directories, root_mode):
    seen, seen_dirs, root_seen = set(), set(), False
    with tarfile.open(packed, 'r|gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            require(not path.is_absolute() and '..' not in path.parts and path.parts[0] == prefix, 'Unsafe archive path')
            rel = PurePosixPath(*path.parts[1:]).as_posix()
            if member.isdir():
                if rel == '.':
                    require(not root_seen and stat.S_IMODE(member.mode) == root_mode, 'Duplicate/changed root directory')
                    root_seen = True
                else:
                    require(rel in directories and rel not in seen_dirs, 'Unexpected/duplicate directory')
                    require(stat.S_IMODE(member.mode) == directories[rel]['mode'], 'Directory mode changed')
                    seen_dirs.add(rel)
                continue
            require(member.isreg() and rel in files and rel not in seen, 'Unexpected/duplicate/nonregular native file')
            expected = files[rel]
            require(member.size == expected['bytes'] and stat.S_IMODE(member.mode) == expected['mode'], 'Native size/mode changed')
            digest = hashlib.sha256()
            with archive.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024**2), b''):
                    digest.update(block)
            require(digest.hexdigest() == expected['sha256'], 'Native full logical SHA differs')
            seen.add(rel)
    require(root_seen and seen == set(files) and seen_dirs == set(directories), 'Whole file/directory closure differs')
    return {'fullLogicalFileSha256Verified': len(seen), 'directoryModesVerified': len(seen_dirs) + 1,
            'emptyDirectoryClosureVerified': True, 'extracted': False}


def artifact_binding(source, artifact_dir):
    inventory = source / 'artifact-inventory.sha256'
    regular(inventory, 1024**2)
    entries = []
    for line in inventory.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) ([0-9]+) (.+)', line)
        require(match is not None, 'Malformed runtime artifact line')
        digest, size, observed = match.groups()
        size = int(size)
        marker = '/cluster/build/classes/java/main/'
        if marker in observed:
            require(observed.startswith(str(WORK) + marker), 'Unexpected class path')
            entry = observed.split(marker, 1)[1]
            require(entry.endswith('.class') and '..' not in PurePosixPath(entry).parts, 'Invalid runtime class entry')
            jar = artifact_dir / 'cluster-0.1.0-SNAPSHOT.jar'
            with zipfile.ZipFile(jar) as archive:
                raw = archive.read(entry)
            require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'Runtime class differs from preserved JAR: ' + entry)
            entries.append({'observed': observed, 'bytes': size, 'sha256': digest, 'preservedJar': jar.name, 'entry': entry})
        else:
            jar = artifact_dir / Path(observed).name
            require(jar.suffix == '.jar' and jar.is_file(), 'Unexpected runtime dependency')
            require(jar.stat().st_size == size and sha(jar) == digest, 'Runtime dependency differs from preserved JAR')
            entries.append({'observed': observed, 'bytes': size, 'sha256': digest, 'preservedJar': jar.name})
    require(len(entries) == 110, 'Unexpected observed artifact count')
    return {'inventorySha256': sha(inventory), 'entriesVerified': len(entries), 'entries': entries,
            'preservedArtifactDirectory': str(artifact_dir.relative_to(OUT))}


def archive_tree(source, proof_id, artifact_dir, provenance, existing=None):
    target = OUT / 'native-proofs' / proof_id
    target.mkdir(parents=True, exist_ok=False)
    files, directories, completion = tree_inventory(source)
    packed = target / 'native-tree.tar.gz'
    prefix = proof_id
    original_manifest = None
    if existing:
        original_manifest = json.loads((existing / 'manifest.json').read_text())
        require(original_manifest['attempt'] == source.name, 'Manifest attempt differs')
        require(set(original_manifest['files']) == set(files), 'Manifest native closure differs')
        for name, expected in original_manifest['files'].items():
            require(all(files[name][key] == expected[key] for key in ('bytes', 'sha256', 'mode')), 'Original manifest differs')
        require(set(original_manifest['directories']) == set(directories), 'Original directory manifest differs')
        archived = original_manifest['archive']
        before = existing / archived['path']
        require(before.stat().st_size == archived['bytes'] and sha(before) == archived['sha256'], 'Original archive digest differs')
        copied(before, packed)
        copied(existing / 'manifest.json', target / 'original-manifest.json')
        prefix = source.name
    else:
        require(shutil.disk_usage(target).free >= 1024**3, 'At least one GiB local free required')
        with packed.open('xb') as raw, tarfile.open(fileobj=raw, mode='w:gz', compresslevel=1) as archive:
            archive.add(source, arcname=prefix, recursive=True)
        require(packed.stat().st_size <= 64 * 1024**2, 'Compressed proof exceeds bound')
    checked = verify_tar(packed, prefix, files, directories, stat.S_IMODE(source.stat().st_mode))
    # Recheck the source file/directory closure and all small state files after streaming.
    after_paths = sorted(source.rglob('*'))
    require({p.relative_to(source).as_posix() for p in after_paths if p.is_file()} == set(files), 'Native file closure changed during collection')
    require({p.relative_to(source).as_posix() for p in after_paths if p.is_dir()} == set(directories), 'Native directory closure changed during collection')
    for name, record in files.items():
        p = source / name
        require(p.stat().st_size == record['bytes'] and stat.S_IMODE(p.stat().st_mode) == record['mode'], 'Native source changed during collection')
        if record['bytes'] <= 1024**2:
            require(sha(p) == record['sha256'], 'Small native state changed during collection')
    binding = artifact_binding(source, artifact_dir)
    json_write(target / 'artifact-binding.json', binding)
    manifest = {'schemaVersion': 1, 'collectedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'proofId': proof_id, 'originalSource': str(source), 'sourceRevision': REV, 'provenance': provenance,
                'completion': completion, 'logicalBytes': sum(v['bytes'] for v in files.values()),
                'files': files, 'directories': directories, 'rootMode': stat.S_IMODE(source.stat().st_mode),
                'archive': {'path': packed.name, 'bytes': packed.stat().st_size, 'sha256': sha(packed)},
                'streamReadback': checked, 'artifactEntriesVerified': binding['entriesVerified'],
                'originalDeleted': False, 'scope': 'Local three JVM correctness only; no capacity, independent hosts, external durability, W128 credit or 100M proof.'}
    json_write(target / 'manifest.json', manifest)
    print(json.dumps({'proofId': proof_id, 'files': len(files), 'logicalBytes': manifest['logicalBytes'],
                      'archiveBytes': packed.stat().st_size, 'sha256': manifest['archive']['sha256']}), flush=True)
    return {'proofId': proof_id, 'manifest': str((target / 'manifest.json').relative_to(OUT)),
            'manifestSha256': sha(target / 'manifest.json'), 'archive': manifest['archive'], 'logicalBytes': manifest['logicalBytes'],
            'files': len(files), 'provenance': provenance, 'artifactEntriesVerified': binding['entriesVerified']}


def xml_source(path, marker):
    suite = ET.parse(path).getroot()
    require(all(int(suite.get(k, '0')) == 0 for k in ('failures', 'errors', 'skipped')) and int(suite.get('tests')) == 1, 'Successful single-smoke XML required')
    matches = [line[len(marker):] for line in suite.findtext('system-out', '').splitlines() if line.startswith(marker)]
    require(len(matches) == 1, 'One exact smoke source path required')
    p = Path(matches[0])
    resolved = p.resolve()
    require(resolved.name == 'fresh-lineage' and resolved.parent.name.startswith('vectormatch-v3-aeron-')
            or resolved.parent == WORK / 'cluster/build/retention-batch-native-attempts' and resolved.name.startswith('attempt-'), 'Unexpected owned smoke source')
    return resolved


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--phase', choices=['agent', 'root'], required=True)
    parser.add_argument('--root-xml-dir', type=Path)
    args = parser.parse_args()
    require(subprocess.check_output(['git', '-C', str(WORK), 'rev-parse', 'HEAD'], text=True).strip() == REV, 'Frozen revision differs')
    require(not subprocess.check_output(['git', '-C', str(WORK), 'status', '--porcelain'], text=True).strip(), 'Frozen source worktree dirty')
    require(sha(WORK / 'docs/RETENTION_BATCH_V3_VALIDATION.json') == VALIDATION_SHA, 'Frozen validation manifest differs')
    proof = OUT / 'collector'
    proof.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.phase == 'agent':
        artifact_copy = OUT / 'agent-build-validation'
        artifact_copy.mkdir(exist_ok=False)
        inventory = {}
        paths = sorted(VALID.rglob('*'))
        require(len(paths) < 256, 'Agent proof source count exceeded')
        for p in paths:
            require(not p.is_symlink(), 'Agent proof symlink refused')
            if p.is_file():
                rel = p.relative_to(VALID)
                inventory[rel.as_posix()] = copied(p, artifact_copy / rel)
        json_write(proof / 'agent-build-copy.json', {'source': str(VALID), 'files': inventory, 'allCopiesSha256Verified': True})
        validation = json.loads((WORK / 'docs/RETENTION_BATCH_V3_VALIDATION.json').read_text())
        for item in validation['nativeAttempts']:
            original = Path(item['manifest'])
            require(sha(original) == item['manifestSha256'], 'Frozen native manifest SHA differs')
            record = json.loads(original.read_text())
            source = Path(record['source']).resolve()
            role = 'final-artifact' if source.name == 'attempt-a6320fa0-39d2-40f5-b61a-ca47ed1ba4c3' else 'pre-final-artifact'
            rows.append(archive_tree(source, source.name, artifact_copy / role,
                'Agent smoke; ' + role + '; independent root fullcheck later reused final suite results, not a new execution.', original.parent))
        for label, xml in [('agent-reference-suite-r1', VALID / 'core-cluster-suite-r1-results/cluster/TEST-io.vectormatch.cluster.RetentionThreeJvmV3Test.xml'),
                           ('agent-reference-final', VALID / 'final-results/cluster/TEST-io.vectormatch.cluster.RetentionThreeJvmV3Test.xml')]:
            source = xml_source(xml, 'VECTOR_V3_TEST_EVIDENCE ')
            role = 'pre-final-artifact' if label.endswith('r1') else 'final-artifact'
            rows.append(archive_tree(source, label, artifact_copy / role, 'Agent legacy single-command V3 smoke; ' + role + '; not a batch or root independent execution.'))
    else:
        require(args.root_xml_dir is not None, 'Explicit preserved root rerun XML directory required')
        xmls = args.root_xml_dir.resolve()
        require(xmls.is_relative_to(OUT.resolve()), 'Root XML must be already preserved inside owned evidence path')
        artifacts = OUT / 'root-rerun-artifact'
        artifacts.mkdir(exist_ok=False)
        jar_manifest = {}
        for p in sorted((WORK / 'cluster/build/install/cluster/lib').glob('*.jar')):
            jar_manifest[p.name] = copied(p, artifacts / p.name)
        require(len(jar_manifest) == 4, 'Exact four runtime JARs required')
        json_write(artifacts / 'manifest.json', {'sourceRevision': REV, 'files': jar_manifest})
        for name, marker, label in [('RetentionBatchThreeJvmV3Test', 'VECTOR_V3_BATCH_TEST_EVIDENCE ', 'root-rerun-batch'),
                                    ('RetentionThreeJvmV3Test', 'VECTOR_V3_TEST_EVIDENCE ', 'root-rerun-reference')]:
            found = list(xmls.rglob('TEST-io.vectormatch.cluster.' + name + '.xml'))
            require(len(found) == 1, 'Exact preserved root rerun smoke XML required')
            source = xml_source(found[0], marker)
            rows.append(archive_tree(source, label, artifacts, 'Explicit root --rerun-tasks independent local smoke execution; XML ' + str(found[0].relative_to(OUT))))
    json_write(proof / (args.phase + '-collection.json'), {'passed': True, 'sourceRevision': REV,
                'nativeProofs': rows, 'distinctNativeTrees': len({r['proofId'] for r in rows}),
                'initialCompileFailure': json.loads((VALID / 'initial-compile-failure.json').read_text()),
                'rootFirstFullcheck': 'core:test and cluster:test were UP-TO-DATE; reused final agent XML. New bench/projector/server tasks ran. No new smoke credited.',
                'scope': 'All local functional evidence; no capacity, independent host, external durability or 100M result.'})
    copyname = proof / ('collect-retention-batch-proofs-' + args.phase + '.py')
    copied(Path(__file__), copyname)
    print(json.dumps({'phase': args.phase, 'passed': True, 'distinctNativeTrees': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
