#!/usr/bin/env python3
"""Bounded r1 byte-preserving proof capture; no extraction or source deletion."""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import gzip
import hashlib
import json
import os
import shutil
import tarfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
R1 = HERE.parent
WORK = R1.parents[2]
GIB = 1024 ** 3
FLOOR = GIB

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 ** 2), b''):
            h.update(block)
    return h.hexdigest()

def guard():
    free = shutil.disk_usage(HERE).free
    if free < FLOOR:
        raise RuntimeError('Global 1 GiB free-space floor reached: ' + str(free))
    return free

class GuardedWriter:
    def __init__(self, stream):
        self.stream = stream
        self.since_guard = 0
    def write(self, data):
        if self.since_guard == 0 or self.since_guard + len(data) > 4 * 1024 ** 2:
            if guard() - len(data) < FLOOR:
                raise RuntimeError('Archive write would cross free-space floor')
            self.since_guard = 0
        result = self.stream.write(data)
        self.since_guard += result
        return result
    def flush(self):
        return self.stream.flush()
    def tell(self):
        return self.stream.tell()

def checked(path):
    path = Path(path)
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('Symlink refused: ' + str(path))
    return path

def collect(roots):
    files, directories, sources = {}, {}, {}
    for label, root in roots:
        root = checked(root)
        if not root.exists():
            raise ValueError('Missing required proof path: ' + str(root))
        paths = [root, *sorted(root.rglob('*'))] if root.is_dir() else [root]
        for path in paths:
            checked(path)
            relative = path.relative_to(root) if path != root else Path()
            name = str(PurePosixPath(label, *relative.parts))
            if name in files or name in directories:
                if sources[name] == str(path):
                    continue
                raise ValueError('Archive name collision: ' + name)
            info = path.stat()
            sources[name] = str(path)
            mode = info.st_mode & 0o777
            if path.is_dir():
                directories[name] = {'mode': mode}
            elif path.is_file():
                files[name] = {'bytes': info.st_size, 'sha256': sha(path), 'mode': mode,
                               'allocatedBytes': getattr(info, 'st_blocks', 0) * 512}
            else:
                raise ValueError('Nonregular proof file refused: ' + str(path))
    return files, directories, sources

def archive(name, roots, extra=None, native=False):
    guard()
    files, directories, sources = collect(roots)
    logical = sum(item['bytes'] for item in files.values())
    if native and (logical > 8 * GIB or len(files) > 2048):
        raise ValueError('Native root exceeds 8 GiB / 2048-file bounds')
    if not native and (logical > GIB or len(files) > 8192):
        raise ValueError('Artifact capture exceeds conservative 1 GiB / 8192-file bounds')
    target = HERE / name
    target.mkdir(exist_ok=False)
    packed = target / 'full-tree.tar.gz'
    with packed.open('xb') as raw:
        guarded = GuardedWriter(raw)
        with gzip.GzipFile(filename='', mode='wb', fileobj=guarded, compresslevel=1, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|', format=tarfile.PAX_FORMAT) as tar:
                for member_name in sorted(sources):
                    source = Path(sources[member_name])
                    info = tar.gettarinfo(str(source), arcname=member_name)
                    if member_name in files:
                        with source.open('rb') as stream:
                            tar.addfile(info, stream)
                    else:
                        tar.addfile(info)
    seen, seen_dirs = set(), set()
    with tarfile.open(packed, mode='r|gz') as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsafe archive path')
            name_in_tar = str(path)
            if member.isdir():
                if name_in_tar not in directories or name_in_tar in seen_dirs or member.mode & 0o777 != directories[name_in_tar]['mode']:
                    raise ValueError('Directory closure or mode differs: ' + name_in_tar)
                seen_dirs.add(name_in_tar)
                continue
            if not member.isreg() or name_in_tar not in files or name_in_tar in seen:
                raise ValueError('File closure differs: ' + name_in_tar)
            entry = files[name_in_tar]
            if member.size != entry['bytes'] or member.mode & 0o777 != entry['mode']:
                raise ValueError('File length or mode differs: ' + name_in_tar)
            digest = hashlib.sha256()
            read = 0
            with tar.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024 ** 2), b''):
                    digest.update(block)
                    read += len(block)
            if read != entry['bytes'] or digest.hexdigest() != entry['sha256']:
                raise ValueError('File bytes differ: ' + name_in_tar)
            seen.add(name_in_tar)
    if seen != set(files) or seen_dirs != set(directories):
        raise ValueError('Complete file/directory closure differs')
    manifest = {'schemaVersion': 1, 'capturedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'roots': [{'archiveRoot': label, 'source': str(root)} for label, root in roots],
                'files': files, 'directoriesIncludingEmpty': directories, 'logicalBytes': logical,
                'allocatedBytesBeforeArchive': sum(item['allocatedBytes'] for item in files.values()),
                'archive': {'path': packed.name, 'bytes': packed.stat().st_size, 'sha256': sha(packed)},
                'everyLogicalFileByteSha256ReadBack': True, 'fileModesAndEmptyDirectoriesVerified': True,
                'extracted': False, 'originalDeleted': False, 'freeBytesAfterArchive': guard(),
                'archiveEncoding': 'Full logical tar+gzip level 1. Original sparse extents retained. Restore requires logical-space guard or reviewed zero-skipping extractor; no physical extent equivalence claim.',
                'scope': 'Local integration correctness artifacts only; no remote capacity, external durability, W128 retention credit, or 100M proof.'}
    if extra:
        manifest.update(extra)
    with (target / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'archive': str(packed), 'manifest': str(target / 'manifest.json'),
                      'files': len(files), 'logicalBytes': logical, 'archiveBytes': packed.stat().st_size,
                      'archiveSha256': manifest['archive']['sha256'], 'verified': True}), flush=True)
    return manifest

def artifacts():
    roots, expected = [], {}
    for record in sorted(R1.glob('*-test-classpath.json')):
        data = json.loads(record.read_text())
        for raw, entry in data['actualClasspath'].items():
            path = checked(raw)
            if 'files' in entry:
                actual_names = {str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()}
                if actual_names != set(entry['files']):
                    raise ValueError('Classpath directory file closure changed: ' + raw)
                entries = [(path / rel, spec) for rel, spec in entry['files'].items()]
            else:
                entries = [(path, entry)]
            for source, spec in entries:
                actual = {'bytes': source.stat().st_size, 'sha256': sha(source)}
                if actual != {'bytes': spec['bytes'], 'sha256': spec['sha256']}:
                    raise ValueError('Recorded r1 classpath changed: ' + str(source))
                expected[str(source)] = actual
            root_label = 'classpath/' + raw.lstrip('/')
            if (root_label, path) not in roots:
                roots.append((root_label, path))
    for module in ('bench', 'cluster'):
        for folder in ('test-results/test', 'reports/tests/test'):
            roots.append((module + '/' + folder, WORK / module / 'build' / folder))
    metadata = sorted(path for path in R1.iterdir() if path.is_file())
    roots.extend(('r1/' + path.name, path) for path in metadata)
    return archive('artifacts-before-source-fix', roots,
                   {'allRecordedClasspathFilesMatchedBeforeCapture': True,
                    'recordedClasspathFiles': expected,
                    'originalSourceZipPreserved': str(R1 / 'pre-run-source.zip')})

def native_roots():
    roots = []
    for category in ('retention-batch-native-attempts', 'retention-maintenance-native-attempts',
                     'retention-capacity-native-attempts', 'retention-chunk-native-attempts'):
        parent = WORK / 'cluster/build' / category
        for attempt in sorted(parent.iterdir()):
            if not attempt.is_dir() or not attempt.name.startswith('attempt-'):
                raise ValueError('Unexpected native attempt closure: ' + str(attempt))
            roots.append((category + '--' + attempt.name, attempt))
    xml = WORK / 'cluster/build/test-results/test/TEST-io.vectormatch.cluster.RetentionThreeJvmV3Test.xml'
    text = ET.parse(xml).getroot().findtext('system-out', '')
    matches = [line.split(' ', 1)[1].strip() for line in text.splitlines() if line.startswith('VECTOR_V3_TEST_EVIDENCE ')]
    if len(matches) != 1:
        raise ValueError('One explicit V3 evidence path required')
    v3 = Path(matches[0])
    # macOS exposes the real system temporary directory through the /var alias.
    # Permit only this known system alias; evidence-owned symlinks stay refused.
    if v3.is_relative_to('/var') and Path('/var').is_symlink() and Path('/var').resolve() == Path('/private/var'):
        v3 = Path('/private/var') / v3.relative_to('/var')
    v3 = checked(v3)
    if v3.name != 'fresh-lineage' or not v3.parent.name.startswith('vectormatch-v3-aeron-'):
        raise ValueError('Unexpected V3 temporary evidence root')
    roots.append(('retention-three-jvm-v3--' + v3.parent.name, v3.parent))
    return roots

def natives():
    roots = native_roots()
    completions, total = {}, 0
    inventories = []
    for label, root in roots:
        checked(root)
        paths = [*root.rglob('*')]
        files = [p for p in paths if p.is_file()]
        logical = sum(p.stat().st_size for p in files)
        if len(files) > 2048 or logical > 8 * GIB:
            raise ValueError('Native root exceeds registered bounds: ' + str(root))
        total += logical
        found = [p for p in files if p.name == 'completion.json']
        if not found:
            raise ValueError('Missing stopped-process receipt: ' + str(root))
        for path in found:
            receipt = json.loads(path.read_text())
            if receipt.get('allOwnedStopped') is not True:
                raise ValueError('Native attempt still owned: ' + str(path))
            completions[str(path)] = receipt
        inventories.append({'label': label, 'source': str(root), 'files': len(files), 'logicalBytes': logical})
    if total > 20 * GIB:
        raise ValueError('Native closure exceeds registered total 20 GiB bound')
    with (HERE / 'native-closure-inventory.json').open('x') as stream:
        json.dump({'roots': inventories, 'totalLogicalBytes': total, 'completionReceipts': completions,
                   'allCompletionAllOwnedStopped': True}, stream, indent=2)
        stream.write('\n')
    results = []
    for label, root in roots:
        results.append(archive(label, [(root.name, root)], {'nativeCompletionReceipts': {
            path: receipt for path, receipt in completions.items() if Path(path).is_relative_to(root)},
            'allCompletionAllOwnedStopped': True}, native=True))
    receipt = {'archives': [{'path': str(HERE / label / 'full-tree.tar.gz'),
                            'archiveSha256': item['archive']['sha256'], 'logicalBytes': item['logicalBytes']}
                           for (label, _), item in zip(roots, results)], 'archiveCount': len(results), 'totalLogicalBytes': total,
               'allEveryLogicalFileByteSha256ReadBack': all(item['everyLogicalFileByteSha256ReadBack'] for item in results),
               'allCompletionAllOwnedStopped': True, 'freeBytesAfterAllArchives': guard()}
    with (HERE / 'native-archives-complete.json').open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('phase', choices=['artifacts', 'native'])
    args = parser.parse_args()
    artifacts() if args.phase == 'artifacts' else natives()
