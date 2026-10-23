#!/usr/bin/env python3
"""Download portable official toolchains and verify published SHA-256 digests."""
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import tarfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS = ROOT / ".tools"
TOOLS.mkdir(exist_ok=True)

def fetch(url, target):
    subprocess.run(["curl", "-fsSL", "--retry", "3", "--connect-timeout", "20", url, "-o", str(target)], check=True)

def checked(url, checksum, target):
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
        fetch(url, target)
    actual = hashlib.sha256(target.read_bytes()).hexdigest()
    if actual != checksum:
        raise RuntimeError("SHA-256 mismatch: " + target.name)
    print("verified", target.name, actual, flush=True)

def json_url(url):
    path = TOOLS / "metadata.json"
    fetch(url, path)
    return json.loads(path.read_text())

machine = platform.machine()
system = platform.system()
arch = "aarch64" if machine in ("arm64", "aarch64") else "x64"
adoptium_os = "mac" if system == "Darwin" else "linux"

if not (TOOLS / "jdk").exists():
    assets = json_url("https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=" + arch + "&image_type=jdk&os=" + adoptium_os + "&vendor=eclipse")
    package = assets[0]["binary"]["package"]
    archive = TOOLS / "jdk.tar.gz"
    checked(package["link"], package["checksum"], archive)
    extract = TOOLS / "jdk-extract"
    extract.mkdir(exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(extract)
    homes = list(extract.glob("*/Contents/Home")) if system == "Darwin" else list(extract.glob("*"))
    (TOOLS / "jdk").symlink_to(homes[0].relative_to(TOOLS), target_is_directory=True)

if not (TOOLS / "node").exists():
    node_os = "darwin" if system == "Darwin" else "linux"
    node_arch = "arm64" if arch == "aarch64" else "x64"
    base = "https://nodejs.org/dist/latest-v24.x/"
    sums = TOOLS / "node-sha256.txt"
    fetch(base + "SHASUMS256.txt", sums)
    suffix = "-" + node_os + "-" + node_arch + ".tar.gz"
    digest, name = next(line.split() for line in sums.read_text().splitlines() if line.endswith(suffix))
    archive = TOOLS / "node.tar.gz"
    checked(base + name, digest, archive)
    with tarfile.open(archive) as tf:
        tf.extractall(TOOLS)
    (TOOLS / "node").symlink_to(name[:-7], target_is_directory=True)

gradle_version = "8.14.3"
if not (TOOLS / "gradle").exists():
    base = "https://services.gradle.org/distributions/gradle-" + gradle_version + "-bin.zip"
    sums = TOOLS / "gradle-sha256.txt"
    fetch(base + ".sha256", sums)
    archive = TOOLS / "gradle.zip"
    checked(base, sums.read_text().strip(), archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(TOOLS)
    os.chmod(TOOLS / ("gradle-" + gradle_version) / "bin/gradle", 0o755)
    (TOOLS / "gradle").symlink_to("gradle-" + gradle_version, target_is_directory=True)

print("Toolchains ready. Source scripts/env.sh", flush=True)

