#!/usr/bin/env python3
"""Install portable PostgreSQL test binaries from Maven Central; never installs a system service."""
import hashlib
import io
import pathlib
import platform
import subprocess
import tarfile
import zipfile

root = pathlib.Path(__file__).resolve().parent.parent
tools = root / ".tools"
tools.mkdir(exist_ok=True)
system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
arch = "arm64v8" if platform.machine() in ("arm64", "aarch64") else "amd64"
if system is None:
    raise SystemExit("Portable PostgreSQL bootstrap currently supports macOS and Linux.")
artifact = "embedded-postgres-binaries-" + system + "-" + arch
version = "18.6.0"
base = "https://repo.maven.apache.org/maven2/io/zonky/test/postgres/" + artifact + "/" + version + "/" + artifact + "-" + version + ".jar"
jar = tools / "postgres-binaries.jar"
checksum = tools / "postgres-binaries.sha256"
for url, output in ((base, jar), (base + ".sha256", checksum)):
    subprocess.run(["curl", "-fsSL", "--connect-timeout", "20", "--retry", "3", url, "-o", str(output)], check=True)
digest = hashlib.sha256(jar.read_bytes()).hexdigest()
if digest != checksum.read_text().strip():
    raise SystemExit("PostgreSQL artifact checksum mismatch")
target = tools / "postgres"
target.mkdir(exist_ok=True)
with zipfile.ZipFile(jar) as bundle:
    name = next(name for name in bundle.namelist() if name.endswith(".txz"))
    with tarfile.open(fileobj=io.BytesIO(bundle.read(name)), mode="r:xz") as archive:
        for item in archive.getmembers():
            if not (target / item.name).resolve().is_relative_to(target.resolve()):
                raise SystemExit("Unsafe archive member")
        archive.extractall(target)
print("PostgreSQL test binaries ready:", version, digest)
