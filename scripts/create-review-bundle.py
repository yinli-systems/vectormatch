#!/usr/bin/env python3
"""Export an immutable, small source snapshot without bulk experiment history."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

PREFIXES = {".github", "gradle", "core", "cluster", "server", "projector",
            "bench", "scripts", "deploy", "tools", "web", "docs"}
ROOT_FILES = {".gitignore", ".gitattributes", "README.md", "LICENSE",
              "build.gradle.kts", "settings.gradle.kts", "gradle.properties",
              "gradlew", "gradlew.bat"}
MAX_FILE = 10 * 1024**2
MAX_TOTAL = 64 * 1024**2


def selected(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid tracked path")
    return (name in ROOT_FILES or name == "evidence/index.json"
            or path.parts[0] in PREFIXES)


def export(repo, revision, output):
    repo, output = Path(repo), Path(output)
    if output.exists():
        raise ValueError("refusing to replace an existing export")
    commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", revision + "^{commit}"], cwd=repo,
        text=True).strip()
    tree = subprocess.check_output(
        ["git", "ls-tree", "-rz", "--full-tree", commit], cwd=repo)
    entries = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        header, raw_name = record.split(b"\t", 1)
        mode, kind, object_id = header.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if selected(name):
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("non-regular source member: " + name)
            entries.append((name, mode, object_id))
    if not entries:
        raise ValueError("empty source selection")
    output.mkdir()
    manifest = {"schema": "source-review-bundle-2", "sourceCommit": commit,
                "bulkEvidenceAndGitHistoryIncluded": False, "files": {}}
    total = 0
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        with zipfile.ZipFile(output / "source.zip", "x", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            for name, mode, object_id in sorted(entries):
                process.stdin.write((object_id + "\n").encode("ascii"))
                process.stdin.flush()
                actual_id, kind, raw_size = process.stdout.readline().split()
                size = int(raw_size)
                if (actual_id.decode() != object_id or kind != b"blob"
                        or size > MAX_FILE or total + size > MAX_TOTAL):
                    raise ValueError("source object or size bound refused: " + name)
                body = process.stdout.read(size)
                if len(body) != size or process.stdout.read(1) != b"\n":
                    raise ValueError("truncated git object: " + name)
                digest = hashlib.sha256(body).hexdigest()
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = int(mode, 8) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, body)
                manifest["files"][name] = {"bytes": size, "sha256": digest,
                                           "gitBlob": object_id, "mode": mode}
                total += size
            manifest["originalBytes"] = total
            manifest["fileCount"] = len(entries)
            info = zipfile.ZipInfo("SOURCE_MANIFEST.json", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, json.dumps(manifest, indent=2) + "\n")
        process.stdin.close()
        if process.wait(timeout=30) != 0:
            raise RuntimeError("git object reader failed")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=30)
        process.stdin.close()
        process.stdout.close()
    with zipfile.ZipFile(output / "source.zip") as archive:
        if archive.testzip() is not None:
            raise ValueError("export CRC verification failed")
        for name, item in manifest["files"].items():
            body = archive.read(name)
            if len(body) != item["bytes"] or hashlib.sha256(body).hexdigest() != item["sha256"]:
                raise ValueError("export byte verification failed: " + name)
    (output / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    bundle = output / "source.zip"
    receipt = {"sourceCommit": commit, "fileCount": len(entries), "originalBytes": total,
               "archiveBytes": bundle.stat().st_size,
               "archiveSha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
               "allMemberBytesVerified": True, "buildOrFunctionalTestsRun": False}
    (output / "EXPORT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision")
    parser.add_argument("new_output", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(export(args.repo, args.revision, args.new_output)))
