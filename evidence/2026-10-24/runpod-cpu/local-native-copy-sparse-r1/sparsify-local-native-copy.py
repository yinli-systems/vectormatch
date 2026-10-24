#!/usr/bin/env python3
"""Byte-equivalent sparse reallocation of one stopped LOCAL evidence copy only."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
ROOT = REPO / 'evidence/2026-10-24/runpod-cpu/capacity'
CHUNK = 65536
ZERO = b'\0' * CHUNK

def require(ok, message):
    if not ok: raise ValueError(message)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()

def prepare(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in [path] + list(path.parents)), 'symlink copy ancestor')
    rel = path.relative_to(ROOT)
    require(re.fullmatch(r'cpu-[a-z0-9-]+/raw/state/node-[012]/archive/[0-9]+-[0-9]+\.rec', str(rel)), 'only exact local stopped evidence archive .rec copies')
    job = ROOT / rel.parts[0]
    complete = json.loads((job / 'completion.json').read_text())
    require(complete.get('archiveComplete') is True and complete.get('allOwnedProcessesStopped') is True,
            'complete archived/stopped receipt required')
    archive = job / (rel.parts[0] + '.tar.gz')
    require(sha(archive) == complete['archive']['sha256'], 'original complete archive unavailable or changed')
    manifest = job / 'raw/full-state-manifest.json'
    require(sha(manifest) == complete['archive']['fullStateManifestSha256'], 'full native inventory changed')
    entry = json.loads(manifest.read_text())['files'][str(path.relative_to(job / 'raw'))]
    stat = path.stat()
    require(stat.st_nlink == 1 and 0 < stat.st_size <= 256 * 1024 ** 2 and stat.st_size == entry['bytes'], 'bounded independent regular native file required')
    require(path.is_file() and sha(path) == entry['sha256'], 'native source differs from original manifest')
    return path, stat, entry

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    path, before, entry = prepare(args.file)
    result = {'path': str(path.relative_to(REPO)), 'bytes': before.st_size, 'sha256': entry['sha256'],
              'beforeAllocatedBytes': before.st_blocks * 512, 'executed': args.execute,
              'scope': 'Only byte-equivalent sparse reallocation of one stopped local archival copy. Original complete archive and original manifests unchanged. No remote command, native log deletion, service compaction or unique evidence loss.'}
    if args.execute:
        require(shutil.disk_usage(path.parent).free >= before.st_size + 1024 ** 3, 'local temporary-copy space margin')
        temp = path.with_name('.' + path.name + '.sparse-local-r1')
        require(not temp.exists() and not temp.is_symlink(), 'unique temp already exists; no retry/overwrite')
        source_hash = hashlib.sha256()
        # Any failure retains the original and its unique partial temporary copy.
        with path.open('rb') as source, temp.open('xb') as target:
            while True:
                block = source.read(CHUNK)
                if not block: break
                source_hash.update(block)
                if block == ZERO[:len(block)]: target.seek(len(block), os.SEEK_CUR)
                else: target.write(block)
            target.truncate(before.st_size); target.flush(); os.fsync(target.fileno())
        require(source_hash.hexdigest() == entry['sha256'] and temp.stat().st_size == before.st_size
                and sha(temp) == entry['sha256'], 'complete replacement readback mismatch; original retained')
        current = path.stat()
        require((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) ==
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns), 'source changed during copy')
        after_allocated = temp.stat().st_blocks * 512
        require(after_allocated < before.st_blocks * 512, 'filesystem provides no saving; original and verified temp retained')
        os.chmod(temp, before.st_mode & 0o777)
        os.utime(temp, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.replace(temp, path)
        require(path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], 'post-replace full bytes mismatch')
        result.update(afterAllocatedBytes=path.stat().st_blocks * 512, savedBytes=before.st_blocks * 512 - path.stat().st_blocks * 512,
                      fullReadbackPassed=True, originalArchiveAndManifestUnchanged=True)
    print(json.dumps(result))

if __name__ == '__main__': main()
