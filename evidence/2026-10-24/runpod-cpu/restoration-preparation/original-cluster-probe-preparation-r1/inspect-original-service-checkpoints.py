#!/usr/bin/env python3
"""LOCAL ONLY: hash original archives; retain bounded prefixes; decode latest service checkpoints."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import tarfile
import datetime

PREP = Path(__file__).resolve().parent
ROOT = PREP.parents[3]
BACKUPS = ROOT / 'runtime/cloud/optimization-20261024/gpu-to-cpu/backups'
LIB = ROOT / 'runtime/cloud/cpu-20261024/app-restore-build/bundle/dist/cluster/lib'
ARCHIVE_SHA = [
    '066c3b54a445e16461115f7324f6f9201d1cb4a33195246d0fab4134579a418a',
    'd3458616f0e59d8861b5ba6a073db51fe6bac7656f627d78d8ca5821fe0e180b',
    'dd04517a84ec035f0a804979cc4d45b0f67192a7729c907ba2f367f35a03105b',
]
MAX_PREFIX = 16 * 1024**2


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            h.update(chunk)
    return h.hexdigest()


def require(ok, why):
    if not ok:
        raise ValueError(why)


def main():
    output = PREP / 'offline-checkpoints-r1'
    require(not output.exists(), 'New attempt only; no overwrites')
    frozen = json.loads((PREP / 'frozen-sources-r1.json').read_text())
    for name, info in frozen.items():
        require(sha(PREP / name) == info['sha256'], 'Frozen helper source differs')
    require(sha(LIB / 'aeron-all-1.53.3.jar') == '4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2', 'Pinned Aeron differs')
    source_worktree = ROOT / 'runtime/cloud/cpu-20261024/app-restore-worktree'
    require(subprocess.check_output(['git', '-C', str(source_worktree), 'rev-parse', 'HEAD'], text=True).strip()
            == 'e1db2e755a834234efb60b7a1ed291b31ce33c16', 'Original source revision differs')
    require(not subprocess.check_output(['git', '-C', str(source_worktree), 'status', '--porcelain'], text=True).strip(), 'Original source dirty')
    output.mkdir()
    rows = []
    classpath = str(PREP / 'classes') + ':' + ':'.join(str(p) for p in sorted(LIB.glob('*.jar')))
    for node in range(3):
        archive = BACKUPS / ('node%d-original-state.tar.gz' % node)
        require(sha(archive) == ARCHIVE_SHA[node], 'Original archive SHA differs')
        inventory = ROOT / ('evidence/2026-10-23/runpod-optimization/gpu-to-cpu/node%d-pre-stop-state.json' % node)
        state = json.loads(inventory.read_text())
        require(state['allOwnedStopped'] and state['originalRolesStopped'], 'Original stop receipt missing')
        native_name = 'runtime/cloud-20261023-01/node-%d/archive/7-0.rec' % node
        expected = state['files'][native_name]
        node_out = output / ('node%d' % node)
        node_out.mkdir()
        data = None
        with tarfile.open(archive, 'r|gz') as stream:
            for member in stream:
                if member.name != native_name:
                    continue
                require(member.isreg() and member.size == 134217728 and member.size == expected['bytes'], 'Bounded original service recording required')
                h = hashlib.sha256()
                prefix = bytearray()
                with stream.extractfile(member) as source:
                    for chunk in iter(lambda: source.read(1024**2), b''):
                        h.update(chunk)
                        if len(prefix) < MAX_PREFIX:
                            prefix.extend(chunk[:MAX_PREFIX - len(prefix)])
                        else:
                            require(not any(chunk), 'Nonzero recording data beyond 16MiB bound')
                require(h.hexdigest() == expected['sha256'], 'Full selected native recording SHA differs')
                cursor = 0
                while cursor + 32 <= len(prefix):
                    length = struct.unpack_from('<i', prefix, cursor)[0]
                    if length == 0:
                        require(not any(prefix[cursor:]), 'Nonzero recording tail after zero frame')
                        data = bytes(prefix[:cursor + 32])
                        break
                    require(length >= 32 and length <= len(prefix) - cursor, 'Invalid bounded frame length')
                    cursor += (length + 31) & ~31
                require(data is not None, 'No terminal zero frame within bound')
                break
        require(data is not None, 'Exact selected recording missing')
        prefix_path = node_out / 'service-recording-7-bounded-prefix.bin'
        prefix_path.write_bytes(data)
        args = [str(ROOT / '.tools/jdk/bin/java'), '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED', '-Xmx128m',
                '-cp', classpath, 'io.vectormatch.cluster.ReadOriginalServiceCheckpoint', str(prefix_path), str(node_out / 'decoded')]
        result = subprocess.run(args, text=True, capture_output=True, timeout=60)
        (node_out / 'stdout.log').write_text(result.stdout)
        (node_out / 'stderr.log').write_text(result.stderr)
        require(result.returncode == 0, 'Offline Java decoder failed; failed output retained')
        decoded = json.loads((node_out / 'decoded/result.json').read_text())
        rows.append({'node': node, 'originalArchive': str(archive), 'originalArchiveSha256': ARCHIVE_SHA[node],
                     'stoppedInventorySha256': sha(inventory), 'selectedRecording': native_name,
                     'fullSelectedRecording': expected, 'prefixBytes': len(data), 'prefixSha256': sha(prefix_path),
                     'wholeSelectedRecordingSha256Verified': True, 'allBytesAfterPrefixAreZero': True,
                     'decoderArgv': args, 'decoderExitCode': result.returncode, 'decoded': decoded})
        print(json.dumps({'node': node, 'prefixBytes': len(data), 'decoded': decoded}), flush=True)
    for key in ['canonicalEngineSha256', 'combinedCheckpointSha256', 'stateHash', 'commandSeq', 'eventSeq', 'marketSeq',
                'outboxCapacity', 'exportedSeq', 'pendingEvents']:
        require(len({row['decoded'][key] for row in rows}) == 1, 'Replica latest checkpoint differs: ' + key)
    require(rows[0]['decoded']['commandSeq'] == 4539 and rows[0]['decoded']['eventSeq'] == 6106
            and rows[0]['decoded']['marketSeq'] == 6086 and rows[0]['decoded']['exportedSeq'] == 6106
            and rows[0]['decoded']['pendingEvents'] == 0 and rows[0]['decoded']['outboxCapacity'] == 65536,
            'Latest checkpoint differs from original final release metadata')
    receipt = {'schemaVersion': 1, 'inspectedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'passed': True, 'scope': 'LOCAL_OFFLINE_LATEST_SERVICE_CHECKPOINT_ONLY', 'allThreeCheckpointCanonicalBytesMatch': True,
               'sourceRevision': 'e1db2e755a834234efb60b7a1ed291b31ce33c16', 'nodes': rows,
               'businessApplied': False, 'ackSent': False, 'nodeOrAeronArchiveStarted': False, 'cloudAccessed': False,
               'originalArchivesModified': False, 'recordingTailReplayProven': False,
               'limitations': 'Exact latest service checkpoint only. No actual CPU cluster boot, post-checkpoint consensus-log replay, current three-replica state, PostgreSQL comparison or performance proven.'}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'passed': True, 'allThreeCheckpointCanonicalBytesMatch': True}), flush=True)


if __name__ == '__main__':
    main()
