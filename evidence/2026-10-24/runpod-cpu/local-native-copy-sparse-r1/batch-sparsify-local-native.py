#!/usr/bin/env python3
"""Serial byte-identical reallocation of completed local native evidence copies."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]
SOURCE = BASE / 'sparsify-local-native-copy.py'
PROOF = REPO / 'evidence/2026-10-24/runpod-cpu/local-native-copy-sparse-r1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    PROOF.mkdir(exist_ok=False)
    shutil.copy2(SOURCE, PROOF / SOURCE.name)
    shutil.copy2(Path(__file__), PROOF / Path(__file__).name)
    shutil.copy2(BASE / 'local-native-sparse-pilot.json', PROOF / 'pilot.json')
    spec = importlib.util.spec_from_file_location('sparse_local', SOURCE)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    paths = sorted(helper.ROOT.glob('cpu-*/raw/state/node-*/archive/*.rec'))
    before_free = shutil.disk_usage(REPO).free
    plan = {'createdAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'sourceSha256': digest(SOURCE), 'batchSourceSha256': digest(Path(__file__)),
            'pilotSha256': digest(PROOF / 'pilot.json'),
            'scope': 'Stopped LOCAL archival copies only; all logical bytes and original complete archives retained. Not cloud state, Aeron retention, or service compaction.',
            'beforeFreeBytes': before_free,
            'paths': [str(p.relative_to(REPO)) for p in paths]}
    (PROOF / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    results = []
    with (PROOF / 'progress.jsonl').open('x') as log:
        for path in paths:
            _, before, entry = helper.prepare(path)
            if before.st_blocks * 512 < before.st_size:
                record = {'path': str(path.relative_to(REPO)), 'action': 'already-sparse-verified',
                          'bytes': before.st_size, 'allocatedBytes': before.st_blocks * 512,
                          'sha256': entry['sha256']}
            else:
                command = [sys.executable, '-B', str(SOURCE), str(path), '--execute']
                outcome = subprocess.run(command, capture_output=True, text=True, timeout=120)
                if outcome.returncode:
                    failure = {'path': str(path.relative_to(REPO)), 'exitCode': outcome.returncode,
                               'stdout': outcome.stdout, 'stderr': outcome.stderr,
                               'partialRetained': True, 'noAutomaticRetry': True}
                    (PROOF / 'failure.json').write_text(json.dumps(failure, indent=2) + '\n')
                    raise RuntimeError('reallocation failed; original/partial retained: ' + str(path))
                record = json.loads(outcome.stdout)
                # Independently reread the original compressed archive, original inventory,
                # and the entire replaced local copy after the atomic replacement.
                _, after, after_entry = helper.prepare(path)
                if after_entry != entry or after.st_size != before.st_size:
                    raise RuntimeError('post-replacement independent archive/readback failed')
                record['postReplacementOriginalArchiveManifestAndFullCopyReverified'] = True
            results.append(record)
            log.write(json.dumps(record) + '\n'); log.flush(); os.fsync(log.fileno())
            print(json.dumps({'completed': len(results), 'total': len(paths),
                              'path': record['path'], 'savedBytes': record.get('savedBytes', 0)}), flush=True)
    result = {'completedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'complete': True, 'filesVerified': len(results),
              'convertedThisBatch': sum(x.get('executed') is True for x in results),
              'savedBytesThisBatch': sum(x.get('savedBytes', 0) for x in results),
              'afterFreeBytes': shutil.disk_usage(REPO).free,
              'progressSha256': digest(PROOF / 'progress.jsonl'),
              'logicalBytesRemoved': 0, 'uniqueEvidenceDeleted': False,
              'sourceSha256': plan['sourceSha256'], 'batchSourceSha256': plan['batchSourceSha256']}
    (PROOF / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
