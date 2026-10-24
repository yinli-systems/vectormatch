#!/usr/bin/env python3
"""Allowlisted, hash-checked sparse restoration. Never starts or initializes services."""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import tarfile

ARCHIVES = {
    0: '066c3b54a445e16461115f7324f6f9201d1cb4a33195246d0fab4134579a418a',
    1: 'd3458616f0e59d8861b5ba6a073db51fe6bac7656f627d78d8ca5821fe0e180b',
    2: 'dd04517a84ec035f0a804979cc4d45b0f67192a7729c907ba2f367f35a03105b',
}
MAX_FILES = 2000
MAX_FILE_BYTES = 256 * 1024 ** 2
MAX_LOGICAL_BYTES = 4 * 1024 ** 3
CHUNK = 64 * 1024
ZERO = b'\0' * CHUNK
MIN_FREE = 3 * 1024 ** 3

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def canonical(name):
    path = PurePosixPath(name)
    require(isinstance(name, str) and name and '\0' not in name and '\\' not in name
            and not path.is_absolute() and '..' not in path.parts and str(path) == name,
            'noncanonical or unsafe native member path')
    return path

def roots_for(node):
    roots = ['runtime/cloud-20261023-01/node-' + str(node) + '/archive',
             'runtime/cloud-20261023-01/node-' + str(node) + '/cluster']
    return roots + (['runtime/postgres18'] if node == 2 else [])

def inside(name, roots):
    return any(name == root or name.startswith(root + '/') for root in roots)

def validate_members(members, expected, roots):
    require(type(expected) is dict and 0 < len(expected) <= MAX_FILES, 'bounded expected file inventory required')
    for name, entry in expected.items():
        canonical(name)
        require(inside(name, roots) and type(entry) is dict
                and type(entry.get('bytes')) is int and 0 <= entry['bytes'] <= MAX_FILE_BYTES
                and re.fullmatch('[0-9a-f]{64}', entry.get('sha256', '')), 'invalid expected native file inventory')
    require(sum(x['bytes'] for x in expected.values()) <= MAX_LOGICAL_BYTES, 'native logical byte bound')
    require(len(members) <= MAX_FILES * 2, 'native member count bound')
    files, directories, names = {}, set(), set()
    allowed_dirs = set()
    for name in expected:
        allowed_dirs.update(str(p) for p in PurePosixPath(name).parents if str(p) != '.')
    for member in members:
        name = str(canonical(member.name))
        require(name not in names and (member.isdir() or member.isreg())
                and not member.issparse() and not (member.mode & 0o7000), 'duplicate/link/special/sparse/mode member')
        names.add(name)
        if member.isdir():
            require((name in allowed_dirs or inside(name, roots)) and member.size == 0,
                    'unexpected native directory')
            directories.add(name)
        else:
            require(name in expected and member.size == expected[name]['bytes'], 'native file allowlist/size mismatch')
            files[name] = member
    require(set(files) == set(expected), 'native file set differs from stopped inventory')
    for name in directories:
        allowed_dirs.add(name)
        allowed_dirs.update(str(p) for p in PurePosixPath(name).parents if str(p) != '.')
    require(not (set(files) & allowed_dirs), 'native file shadows a directory')
    return files, allowed_dirs

def no_symlinks(path):
    require(not any(p.is_symlink() for p in [path] + list(path.parents)), 'symlink destination ancestor')

def free_guard(path, minimum):
    available = shutil.disk_usage(path).free
    require(available >= minimum, 'native restoration free-space guard')
    return available

def extract_sparse(archive_path, expected, roots, destination, minimum_free=MIN_FREE):
    destination = Path(destination)
    no_symlinks(destination)
    require(not destination.exists(), 'native target must be new; no overwrite/retry/delete')
    free_guard(destination.parent, minimum_free)
    with tarfile.open(archive_path, 'r:gz') as archive:
        files, dirs = validate_members(archive.getmembers(), expected, roots)
        destination.mkdir(mode=0o700)
        for name in sorted(dirs, key=lambda x: (len(PurePosixPath(x).parts), x)):
            (destination / name).mkdir(mode=0o700)
        results = {}
        for name, member in files.items():
            free_guard(destination, minimum_free)
            target = destination / name
            no_symlinks(target)
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            source = archive.extractfile(member)
            if source is None:
                os.close(fd)
                raise ValueError('native file source absent')
            h, written = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as output, source:
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    h.update(block)
                    written += len(block)
                    if block == ZERO[:len(block)]:
                        output.seek(len(block), os.SEEK_CUR)
                    else:
                        output.write(block)
                output.truncate(written)
                output.flush()
                os.fsync(output.fileno())
            require(written == expected[name]['bytes'] and h.hexdigest() == expected[name]['sha256'],
                    'native source bytes differ from stopped inventory: ' + name)
            require(target.stat().st_size == written and digest(target) == h.hexdigest(),
                    'restored complete file readback differs: ' + name)
            os.chmod(target, member.mode & 0o777)
            os.utime(target, (member.mtime, member.mtime))
            results[name] = {'bytes': written, 'sha256': h.hexdigest(),
                             'allocatedBytes': target.stat().st_blocks * 512}
        free_guard(destination, minimum_free)
    # All data names exactly match; the receipt is written outside this cloned native tree.
    actual = {str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
    require(actual == set(expected), 'unexpected restored file set')
    return {'passed': True, 'files': results, 'logicalBytes': sum(x['bytes'] for x in results.values()),
            'allocatedBytes': sum(x['allocatedBytes'] for x in results.values()),
            'scope': 'Exact stopped native file bytes, sparse allocation only; no service/database/tool execution, ownership migration or recovery proof.'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    repository = args.repo.resolve()
    destination = args.destination.absolute()
    no_symlinks(destination)
    require(not destination.exists(), 'destination already exists')
    source = repository / 'runtime/cloud/optimization-20261024/gpu-to-cpu/backups'
    receipt_root = repository / 'evidence/2026-10-23/runpod-optimization/gpu-to-cpu'
    plans = []
    for node, expected_sha in ARCHIVES.items():
        path = source / ('node' + str(node) + '-original-state.tar.gz')
        receipt_path = receipt_root / ('node' + str(node) + '-pre-stop-state.json')
        receipt = json.loads(receipt_path.read_text())
        require(receipt['node'] == node and receipt['allOwnedStopped'] is True
                and receipt['originalRolesStopped'] is True, 'stopped native origin not proven')
        require(digest(path) == expected_sha, 'pinned native archive bytes differ')
        roots = roots_for(node)
        require(receipt['archivePaths'] == roots, 'stopped origin roots differ')
        with tarfile.open(path, 'r:gz') as archive:
            validate_members(archive.getmembers(), receipt['files'], roots)
        plans.append({'node': node, 'archive': str(path), 'archiveSha256': expected_sha,
                      'inventory': receipt['files'], 'inventoryReceiptSha256': digest(receipt_path),
                      'roots': roots, 'destination': str(destination / ('node' + str(node)))})
    plan = {'schemaVersion': 1, 'scriptSha256': digest(Path(__file__)), 'execute': args.execute,
            'minimumFreeBytes': MIN_FREE, 'nodes': plans}
    if args.execute:
        require(destination.parent.exists(), 'destination parent must already exist')
        free_guard(destination.parent, MIN_FREE)
        destination.mkdir(mode=0o700)
        # All originals were fully checked before creating the first destination.
        plan['results'] = [extract_sparse(p['archive'], p['inventory'], p['roots'], p['destination']) for p in plans]
        plan['completedAtUtc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (destination / 'restoration-receipt.json').open('x') as stream:
            json.dump(plan, stream, indent=2); stream.write('\n')
    print(json.dumps({'passed': True, 'execute': args.execute, 'nodes': len(plans),
                      'files': sum(len(p['inventory']) for p in plans),
                      'logicalBytes': sum(sum(x['bytes'] for x in p['inventory'].values()) for p in plans),
                      'destination': str(destination)}, indent=2))

if __name__ == '__main__':
    main()
