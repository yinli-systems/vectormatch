#!/usr/bin/env python3
"""Lossless, deterministic arrival evidence archives; original CSVs are never removed."""
import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import zlib


RAW = "arrivals.csv"
ARCHIVE = "arrivals.csv.gz"
MANIFEST = "arrivals-archive.json"
MAX_RAW_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "SHA-256 must be 64 lowercase hexadecimal characters")
    return value


@contextmanager
def directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def stable(descriptor, name, stream, before):
    require(identity(os.fstat(stream.fileno())) == identity(before), "Input changed while reading: " + name)
    linked = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    require(stat.S_ISREG(linked.st_mode) and identity(linked) == identity(before),
            "Input path changed while reading: " + name)


@contextmanager
def regular(descriptor, name):
    handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
    try:
        info = os.fstat(handle)
        require(stat.S_ISREG(info.st_mode), "Expected regular file: " + name)
        with os.fdopen(handle, "rb") as stream:
            handle = None
            yield stream, info
    finally:
        if handle is not None:
            os.close(handle)


def absent(descriptor, name):
    try:
        os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise FileExistsError("Refusing to overwrite existing path: " + name)


@contextmanager
def temporary(descriptor):
    # Only this invocation's O_EXCL-created temporary path is ever unlinked.
    name = ".arrivals-archive-" + secrets.token_hex(16) + ".tmp"
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=descriptor)
    try:
        with os.fdopen(handle, "wb") as stream:
            yield name, stream
    finally:
        os.unlink(name, dir_fd=descriptor)


def finish(stream):
    stream.flush()
    os.fsync(stream.fileno())


def publish(descriptor, temporary_name, name):
    # link(2), unlike rename/replace, never overwrites an existing destination.
    os.link(temporary_name, name, src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False)
    os.fsync(descriptor)


def digest_stream(stream, maximum):
    digest, size = hashlib.sha256(), 0
    while chunk := stream.read(CHUNK_BYTES):
        size += len(chunk)
        require(size <= maximum, "File exceeds size limit")
        digest.update(chunk)
    return size, digest.hexdigest()


def decoded_stream(stream, output=None):
    digest, size = hashlib.sha256(), 0
    with gzip.GzipFile(fileobj=stream, mode="rb") as decoded:
        while chunk := decoded.read(CHUNK_BYTES):
            size += len(chunk)
            require(size <= MAX_RAW_BYTES, "Decoded CSV exceeds 256 MiB limit")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
    return size, digest.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate manifest key")
        result[key] = value
    return result


def read_manifest(descriptor):
    with regular(descriptor, MANIFEST) as (stream, before):
        require(before.st_size <= MAX_MANIFEST_BYTES, "Manifest exceeds size limit")
        payload = stream.read(MAX_MANIFEST_BYTES + 1)
        require(len(payload) <= MAX_MANIFEST_BYTES, "Manifest exceeds size limit")
        stable(descriptor, MANIFEST, stream, before)
    result = json.loads(payload, object_pairs_hook=unique_object)
    require(isinstance(result, dict) and set(result) == {
        "schemaVersion", "format", "rawFile", "archiveFile", "rawBytes", "rawSha256",
        "compressedBytes", "compressedSha256", "gzip"}, "Invalid archive manifest fields")
    require(type(result["schemaVersion"]) is int and result["schemaVersion"] == 1, "Invalid archive schema")
    require(result["format"] == "gzip" and result["rawFile"] == RAW and result["archiveFile"] == ARCHIVE,
            "Archive manifest filenames/format must be fixed")
    policy = result["gzip"]
    require(isinstance(policy, dict) and policy == {"mtime": 0, "filename": "", "compressLevel": 9}
            and type(policy["mtime"]) is int and type(policy["compressLevel"]) is int, "Invalid gzip policy")
    for name, maximum in (("rawBytes", MAX_RAW_BYTES), ("compressedBytes", MAX_RAW_BYTES + CHUNK_BYTES)):
        require(type(result[name]) is int and 0 <= result[name] <= maximum, "Invalid archive size: " + name)
    sha256(result["rawSha256"])
    sha256(result["compressedSha256"])
    return result


def verify_archive(descriptor, name, expected, output=None):
    with regular(descriptor, name) as (stream, before):
        require(before.st_size == expected["compressedBytes"], "Compressed byte count differs")
        observed = digest_stream(stream, MAX_RAW_BYTES + CHUNK_BYTES)
        require(observed == (expected["compressedBytes"], expected["compressedSha256"]), "Compressed SHA-256 differs")
        stream.seek(0)
        require(decoded_stream(stream, output) == (expected["rawBytes"], expected["rawSha256"]),
                "Decoded CSV bytes/SHA-256 differ")
        stream.seek(0)
        require(digest_stream(stream, MAX_RAW_BYTES + CHUNK_BYTES) == observed, "Archive changed during decompression")
        stable(descriptor, name, stream, before)


def archive(run_directory, expected_sha256):
    expected_sha256 = sha256(expected_sha256)
    with directory(run_directory) as descriptor:
        absent(descriptor, ARCHIVE)
        absent(descriptor, MANIFEST)
        with regular(descriptor, RAW) as (raw, before), temporary(descriptor) as (packed_name, packed):
            require(before.st_size <= MAX_RAW_BYTES, "CSV exceeds 256 MiB limit")
            digest, size = hashlib.sha256(), 0
            with gzip.GzipFile(filename="", fileobj=packed, mode="wb", compresslevel=9, mtime=0) as encoded:
                while chunk := raw.read(CHUNK_BYTES):
                    size += len(chunk)
                    require(size <= MAX_RAW_BYTES, "CSV exceeds 256 MiB limit")
                    digest.update(chunk)
                    encoded.write(chunk)
            require(digest.hexdigest() == expected_sha256, "Input CSV SHA-256 differs from expected")
            stable(descriptor, RAW, raw, before)
            finish(packed)
            with regular(descriptor, packed_name) as (stream, info):
                compressed_size, compressed_sha = digest_stream(stream, MAX_RAW_BYTES + CHUNK_BYTES)
                stable(descriptor, packed_name, stream, info)
            result = {"schemaVersion": 1, "format": "gzip", "rawFile": RAW, "archiveFile": ARCHIVE,
                      "rawBytes": size, "rawSha256": expected_sha256, "compressedBytes": compressed_size,
                      "compressedSha256": compressed_sha, "gzip": {"mtime": 0, "filename": "", "compressLevel": 9}}
            verify_archive(descriptor, packed_name, result)
            stable(descriptor, RAW, raw, before)
            with temporary(descriptor) as (manifest_name, manifest):
                manifest.write((json.dumps(result, sort_keys=True, indent=2) + "\n").encode())
                finish(manifest)
                # A concurrent final-name creation fails closed. A rare second publication failure may
                # leave an orphan gzip, never a success manifest; existing files are never removed.
                publish(descriptor, packed_name, ARCHIVE)
                publish(descriptor, manifest_name, MANIFEST)
    return {"operation": "archive", "verified": True, **result}


def restore(run_directory):
    with directory(run_directory) as descriptor:
        expected = read_manifest(descriptor)
        try:
            info = os.stat(RAW, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            info = None
        if info is not None:
            require(stat.S_ISREG(info.st_mode), "Existing CSV must be a regular non-symlink file")
            verify_archive(descriptor, ARCHIVE, expected)
            with regular(descriptor, RAW) as (raw, before):
                require(digest_stream(raw, MAX_RAW_BYTES) == (expected["rawBytes"], expected["rawSha256"]),
                        "Existing CSV bytes/SHA-256 differ; refusing overwrite")
                stable(descriptor, RAW, raw, before)
            status = "already-present-verified"
        else:
            with temporary(descriptor) as (raw_name, raw):
                verify_archive(descriptor, ARCHIVE, expected, raw)
                finish(raw)
                publish(descriptor, raw_name, RAW)
            status = "restored"
    return {"operation": "restore", "verified": True, "status": status, **expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    compress = commands.add_parser("archive", help="Keep CSV and create verified deterministic gzip + manifest")
    compress.add_argument("run_directory", type=Path)
    compress.add_argument("--expected-sha256", required=True)
    expand = commands.add_parser("restore", help="Verify archive and exclusively restore missing CSV")
    expand.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    try:
        result = archive(args.run_directory, args.expected_sha256) if args.operation == "archive" else restore(args.run_directory)
    except (OSError, ValueError, EOFError, zlib.error) as error:
        parser.exit(1, "Arrival archive failed: " + str(error) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
