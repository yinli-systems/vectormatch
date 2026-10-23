#!/usr/bin/env python3
"""Download portable official toolchains and verify published SHA-256 digests."""
import hashlib
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

machine = platform.machine()
system = platform.system()
if system not in ("Darwin", "Linux") or machine not in ("arm64", "aarch64", "x86_64", "AMD64"):
    raise RuntimeError("Supported portable toolchains: macOS/Linux on ARM64/x86-64")
arch = "aarch64" if machine in ("arm64", "aarch64") else "x64"
adoptium_os = "mac" if system == "Darwin" else "linux"

if not (TOOLS / "jdk").exists():
    name = "OpenJDK21U-jdk_" + arch + "_" + adoptium_os + "_hotspot_21.0.13_9.tar.gz"
    base = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/"
    checksum_file = TOOLS / "jdk-sha256.txt"
    fetch(base + name + ".sha256.txt", checksum_file)
    archive = TOOLS / "jdk.tar.gz"
    checked(base + name, checksum_file.read_text().split()[0], archive)
    extract = TOOLS / "jdk-extract"
    extract.mkdir(exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(extract)
    homes = list(extract.glob("*/Contents/Home")) if system == "Darwin" else list(extract.glob("*"))
    (TOOLS / "jdk").symlink_to(homes[0].relative_to(TOOLS), target_is_directory=True)

if not (TOOLS / "node").exists():
    node_os = "darwin" if system == "Darwin" else "linux"
    node_arch = "arm64" if arch == "aarch64" else "x64"
    base = "https://nodejs.org/dist/v24.22.1/"
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

