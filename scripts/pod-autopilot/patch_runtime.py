"""Derive a runtime whose cluster jar differs only by classes compiled from the supplied sources.

Usage: patch_runtime.py OLD_RUNTIME NEW_RUNTIME NOTE SOURCE.java...
Compiles with this pod's verified JDK against OLD's jars, replaces matching class entries, adds new
ones, proves every other entry is byte-identical, and rewrites CANDIDATE.json hashes."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, zipfile

OLD, NEW, NOTE, SOURCES = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], [Path(s) for s in sys.argv[4:]]
JAR = 'lib/cluster-0.1.0-SNAPSHOT.jar'
shutil.copytree(OLD, NEW)
candidate = json.loads((NEW / 'CANDIDATE.json').read_text())
java = Path(os.environ.get('VM_JAVA', '/root/tools/jdk-21.0.13+9/bin/java'))
assert hashlib.sha256(java.read_bytes()).hexdigest() == candidate['javaBinarySha256'], 'unverified JDK'
out = NEW / 'build-patch'
out.mkdir()
subprocess.run([str(java.with_name('javac')), '-nowarn', '-d', str(out), '-cp', ':'.join(str(p) for p in sorted((NEW / 'lib').glob('*.jar')))]
               + [str(s) for s in SOURCES], check=True)
compiled = {str(p.relative_to(out)): p.read_bytes() for p in sorted(out.rglob('*.class'))}
src, dst = OLD / JAR, NEW / JAR
replaced, added = [], []
with zipfile.ZipFile(src) as a, zipfile.ZipFile(str(dst) + '.tmp', 'w') as b:
    names = set(a.namelist())
    for info in a.infolist():
        if info.filename in compiled:
            b.writestr(info, compiled[info.filename]); replaced.append(info.filename)
        else:
            b.writestr(info, a.read(info.filename))
    for name, body in compiled.items():
        if name not in names:
            b.writestr(name, body); added.append(name)
Path(str(dst) + '.tmp').replace(dst)
with zipfile.ZipFile(src) as a, zipfile.ZipFile(dst) as b:
    for n in a.namelist():
        if n not in compiled:
            assert a.read(n) == b.read(n), n


def digest(path):
    h = hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()


candidate.setdefault('patches', []).append({'note': NOTE, 'replaced': sorted(replaced), 'added': sorted(added),
                                            'sources': {s.name: digest(s) for s in SOURCES}})
candidate['files'] = {n: {'sha256': digest(NEW / n), 'bytes': (NEW / n).stat().st_size} for n in candidate['files']}
(NEW / 'CANDIDATE.json').write_text(json.dumps(candidate, indent=2) + '\n')
shutil.rmtree(out)
print(json.dumps({'runtime': str(NEW), 'replaced': sorted(replaced), 'added': sorted(added), 'clusterJarSha256': candidate['files'][JAR]['sha256']}))
