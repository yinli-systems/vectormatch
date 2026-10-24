#!/usr/bin/env python3
"""Archive four explicit, stopped, root fullcheck smoke trees without extraction or deletion."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import re
import shutil
import stat
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / 'runtime/cloud/cpu-20261024/retention-batch-v3-worktree'
OUT = ROOT / 'evidence/2026-10-24/runpod-cpu/retention-batch-owner-v3'
ART = OUT / 'root-artifact-state'
REV = '24c25c368340b54db1bfc8075b2bcffa5441b892'


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


class CappedOutput:
    def __init__(self, stream):
        self.stream = stream
        self.written = 0
    def write(self, block):
        require(self.written + len(block) <= 64 * 1024**2, 'Compressed archive hard limit')
        count = self.stream.write(block)
        self.written += count
        return count
    def flush(self):
        self.stream.flush()
    def tell(self):
        return self.written


def bindings(source):
    rows = []
    for line in (source / 'artifact-inventory.sha256').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64}) ([0-9]+) (.+)', line)
        require(match is not None, 'Malformed actual artifact record')
        digest, size, actual = match.groups()
        size = int(size)
        marker = '/cluster/build/classes/java/main/'
        if marker in actual:
            require(actual.startswith(str(WORK) + marker), 'Unexpected actual class path')
            entry = actual.split(marker, 1)[1]
            with zipfile.ZipFile(ART / 'cluster-actual-classes.zip') as z, zipfile.ZipFile(ART / 'lib/cluster-0.1.0-SNAPSHOT.jar') as jar:
                raw = z.read(entry)
                require(raw == jar.read(entry) and len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'Actual runtime class differs')
            rows.append({'observed': actual, 'bytes': size, 'sha256': digest, 'entry': entry, 'classZip': 'cluster-actual-classes.zip'})
        else:
            jar = ART / 'lib' / Path(actual).name
            require(jar.suffix == '.jar' and jar.is_file() and jar.stat().st_size == size and sha(jar) == digest, 'Actual runtime JAR differs')
            rows.append({'observed': actual, 'bytes': size, 'sha256': digest, 'jar': jar.name})
    require(len(rows) == 128, 'Expected 128 actual inventory observations')
    return {'passed': True, 'observations': rows, 'observedEntriesVerified': len(rows),
            'inventorySha256': sha(source / 'artifact-inventory.sha256'), 'artifactStateManifestSha256': sha(ART / 'manifest.json')}


def main():
    require(subprocess.check_output(['git', '-C', str(WORK), 'rev-parse', 'HEAD'], text=True).strip() == REV, 'Source revision differs')
    require(not subprocess.check_output(['git', '-C', str(WORK), 'status', '--porcelain'], text=True).strip(), 'Source worktree dirty')
    log = (OUT / 'root-fullcheck/gradle.log').read_text()
    require('22 actionable tasks: 22 executed' in log and 'UP-TO-DATE' not in log, 'Actual forced root task execution required')
    totals = {k: 0 for k in ['tests', 'failures', 'errors', 'skipped']}
    sources = []
    for p in sorted((OUT / 'root-fullcheck/tests').rglob('TEST-*.xml')):
        suite = ET.parse(p).getroot()
        for key in totals:
            totals[key] += int(suite.get(key, '0'))
        for line in suite.findtext('system-out', '').splitlines():
            if not line.startswith(('VECTOR_V3_TEST_EVIDENCE ', 'VECTOR_V3_BATCH_TEST_EVIDENCE ', 'VECTOR_V3_OWNER_TEST_EVIDENCE ')):
                continue
            require(all(int(suite.get(k, '0')) == 0 for k in ['failures', 'errors', 'skipped']), 'Successful source XML required')
            raw = line.split(' ', 1)[1]
            source = Path(raw).resolve()
            owned = source.parent == WORK / 'cluster/build/retention-batch-native-attempts' and source.name.startswith('attempt-')
            legacy = source.name == 'fresh-lineage' and source.parent.name.startswith('vectormatch-v3-aeron-')
            require(owned or legacy, 'Unexpected owned evidence source')
            if line.startswith('VECTOR_V3_OWNER_TEST_EVIDENCE '):
                label = 'root-owner-cap1' if source.name.startswith('attempt-owner-cap1-') else 'root-owner-cap4'
            elif line.startswith('VECTOR_V3_BATCH_TEST_EVIDENCE '):
                label = 'root-batch-reference'
            else:
                label = 'root-single-command-reference'
            sources.append((label, source, p))
    require(totals == {'tests': 223, 'failures': 0, 'errors': 0, 'skipped': 11}, 'Full root XML counts differ')
    require(len(sources) == len({x[0] for x in sources}) == len({x[1] for x in sources}) == 4, 'Exactly four distinct root native trees required')
    original = ROOT / 'runtime/cloud/cpu-20261024/collect-retention-batch-proofs.py'
    require(sha(original) == 'c074efe4e31cb5833fc9af402e33fa6472f94e17cd0dee906bb997b9ffcd8b88', 'Archival primitives differ')
    spec = importlib.util.spec_from_file_location('primitives', original)
    primitives = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(primitives)
    manifest = json.loads((ART / 'manifest.json').read_text())
    for name, info in manifest['jars'].items():
        require((ART / 'lib' / name).stat().st_size == info['bytes'] and sha(ART / 'lib' / name) == info['sha256'], 'Root JAR capture differs')
    for module, info in manifest['classes'].items():
        zip_path = ART / info['zip']
        require(sha(zip_path) == info['zipSha256'], 'Root classes ZIP differs')
        with zipfile.ZipFile(zip_path) as z, zipfile.ZipFile(ART / 'lib' / (module + '-0.1.0-SNAPSHOT.jar')) as jar:
            require(set(z.namelist()) == {n for n in jar.namelist() if n.endswith('.class')} == set(info['classInventory']), 'Root class closure differs')
            for name, expected in info['classInventory'].items():
                raw = z.read(name)
                require(len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'] and jar.read(name) == raw, 'Root class/JAR mismatch')
    output = OUT / 'root-native-proofs'
    output.mkdir(exist_ok=False)
    rows = []
    for label, source, xml in sources:
        target = output / label
        target.mkdir()
        files, dirs, completion = primitives.tree_inventory(source)
        require(shutil.disk_usage(target).free >= 1024**3, 'One GiB minimum archival space')
        packed = target / 'native-tree.tar.gz'
        with packed.open('xb') as raw, tarfile.open(fileobj=CappedOutput(raw), mode='w:gz', compresslevel=1) as archive:
            archive.add(source, arcname=label, recursive=True)
        checked = primitives.verify_tar(packed, label, files, dirs, stat.S_IMODE(source.stat().st_mode))
        binding = bindings(source)
        write(target / 'observed-artifact-binding.json', binding)
        result = json.loads((source / 'result.json').read_text())
        require(result['passed'], 'Native smoke result failed')
        record = {'passed': True, 'sourceRevision': REV, 'originalSource': str(source), 'rootXml': str(xml.relative_to(OUT)),
                  'rootXmlSha256': sha(xml), 'nativeFiles': len(files), 'logicalBytes': sum(x['bytes'] for x in files.values()),
                  'archive': {'path': packed.name, 'bytes': packed.stat().st_size, 'sha256': sha(packed)},
                  'files': files, 'directories': dirs, 'rootMode': stat.S_IMODE(source.stat().st_mode),
                  'completion': completion, 'result': result, 'streamReadback': checked,
                  'observedArtifactEntriesVerified': binding['observedEntriesVerified'], 'originalDeleted': False,
                  'scope': 'Actual root fullcheck local functional smoke; no cloud capacity, external durability, independent hosts, persistent owner recovery or 100M proof.'}
        write(target / 'manifest.json', record)
        rows.append({k: record[k] for k in ['originalSource', 'nativeFiles', 'logicalBytes', 'archive', 'observedArtifactEntriesVerified']})
        print(json.dumps({'label': label, 'passed': True, 'nativeFiles': len(files), 'logicalBytes': record['logicalBytes'], 'archiveBytes': packed.stat().st_size}), flush=True)
    write(output / 'summary.json', {'passed': True, 'sourceRevision': REV, 'collectedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'rootFullcheckTotals': totals, 'passedTests': 212, 'all22GradleTasksExecuted': True, 'distinctRootNativeTrees': len(rows),
                'nativeProofs': rows, 'rootClassCounts': {k: len(v['classInventory']) for k, v in manifest['classes'].items()},
                'scope': 'Four independent root smoke trees; two owner arms plus pre-existing batch/single-command reference fixtures. Separate synthetic lineages, no throughput aggregation.'})
    shutil.copy2(Path(__file__), output / Path(__file__).name)
    print(json.dumps({'passed': True, 'distinctRootNativeTrees': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
