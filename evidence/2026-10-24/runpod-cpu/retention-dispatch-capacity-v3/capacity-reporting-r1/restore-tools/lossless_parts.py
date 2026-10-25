"""Lossless Git-sized packaging. Original native collection files remain untouched."""
from pathlib import Path, PurePosixPath
import hashlib, json, os, stat

PART_BYTES = 32 * 1024**2

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()

def partition(package):
    package = Path(package)
    mapping = {}
    # Freeze the original file list before creating any parts.
    for original in sorted(package.rglob('*')):
        if not original.is_file() or original.stat().st_size <= PART_BYTES:
            continue
        assert not original.is_symlink()
        name = original.relative_to(package).as_posix()
        s = original.stat()
        original_hash = digest(original)
        part_root = package / '.large-file-parts' / hashlib.sha256(name.encode()).hexdigest()
        part_root.mkdir(parents=True)
        parts, offset, whole = [], 0, hashlib.sha256()
        with original.open('rb') as source:
            while block := source.read(PART_BYTES):
                target = part_root / ('part-%05d' % len(parts))
                with target.open('xb') as out:
                    out.write(block)
                target.chmod(0o644)
                h = hashlib.sha256(block).hexdigest()
                assert target.stat().st_size == len(block) and digest(target) == h
                parts.append(dict(path=target.relative_to(package).as_posix(), offset=offset,
                                  bytes=len(block), sha256=h))
                whole.update(block)
                offset += len(block)
        assert offset == s.st_size and whole.hexdigest() == original_hash == digest(original)
        mapping[name] = dict(bytes=s.st_size, sha256=original_hash,
                             mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid,
                             parts=parts)
        # Only delete the verified duplicate inside this fresh evidence package.
        # Original collected/runtime TARs, frames and decoder bodies are retained.
        original.unlink()
    document = dict(schema='lossless-original-file-parts-v1', partBytes=PART_BYTES,
                    originalNativeCollectionFilesUnchanged=True, files=mapping)
    (package / 'ORIGINAL_LARGE_FILES.json').write_text(json.dumps(document, indent=2, sort_keys=True)+'\n')
    verify(package)
    return document

def verify(package):
    package = Path(package)
    document = json.loads((package / 'ORIGINAL_LARGE_FILES.json').read_text())
    assert document['schema'] == 'lossless-original-file-parts-v1'
    all_parts = set()
    total = 0
    for name, row in document['files'].items():
        assert not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts
        assert not (package / name).exists() and row['parts']
        h, offset = hashlib.sha256(), 0
        for part in row['parts']:
            p = package / part['path']
            assert part['path'].startswith('.large-file-parts/') and '..' not in PurePosixPath(part['path']).parts
            assert part['path'] not in all_parts and part['offset'] == offset
            all_parts.add(part['path'])
            assert not p.is_symlink() and p.stat().st_size == part['bytes'] <= PART_BYTES
            assert digest(p) == part['sha256']
            with p.open('rb') as f:
                for block in iter(lambda: f.read(1024**2), b''):
                    h.update(block)
            offset += part['bytes']
        assert offset == row['bytes'] and h.hexdigest() == row['sha256']
        total += offset
    actual = {p.relative_to(package).as_posix() for p in (package/'.large-file-parts').rglob('*') if p.is_file()}
    assert actual == all_parts
    return dict(passed=True, logicalOriginalFiles=len(document['files']),
                logicalOriginalBytes=total, partFiles=len(all_parts), allOriginalBytesSha256Verified=True)

def restore(package, output):
    package, output = Path(package), Path(output)
    result = verify(package)
    assert not output.exists()
    output.mkdir(parents=True)
    document = json.loads((package / 'ORIGINAL_LARGE_FILES.json').read_text())
    for name, row in document['files'].items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as out:
            for part in row['parts']:
                with (package / part['path']).open('rb') as source:
                    for block in iter(lambda: source.read(1024**2), b''):
                        out.write(block)
        target.chmod(row['mode'])
        assert target.stat().st_size == row['bytes'] and digest(target) == row['sha256']
    return result

if __name__ == '__main__':
    import sys
    assert len(sys.argv) in (2, 3)
    print(json.dumps(restore(sys.argv[1], sys.argv[2]) if len(sys.argv)==3 else verify(sys.argv[1])))
