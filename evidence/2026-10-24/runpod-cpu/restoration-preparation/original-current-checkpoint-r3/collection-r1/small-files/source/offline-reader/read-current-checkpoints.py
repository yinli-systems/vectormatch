#!/usr/bin/env python3
"""Offline manifest-bound current original checkpoint reader. No network/Aeron/SQL/business calls."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

PREP = Path(__file__).absolute().parent
REVISION = 'e1db2e755a834234efb60b7a1ed291b31ce33c16'
EXPECTED = {'canonicalEngineSha256': 'ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65',
            'commandSeq': 4609, 'eventSeq': 6214, 'marketSeq': 6194, 'exportedSeq': 6214,
            'pendingEvents': 0, 'outboxCapacity': 65536}
MAX_PREFIX = 16 * 1024 * 1024
LIB_SHA = {'aeron-all-1.53.3.jar': '4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2',
           'agrona-2.6.1.jar': '84c07eb02695c06bfda3d6c3a20c1984e3ff1bbd617b2f8e678140baf973fa28',
           'cluster-0.1.0-SNAPSHOT.jar': 'd96060bfae3b79fae04200ae48e78891231f1831650a72bd20f69da89de22fa3',
           'core-0.1.0-SNAPSHOT.jar': 'c2bd990ce8a2ed7780d80646d174a9c309d689e521ff18f371b6588d5c7b6427'}
SELECTED_KEYS = ('recordingId', 'leadershipTermId', 'termBaseLogPosition', 'logPosition', 'timestamp',
                 'serviceEntryIndex', 'consensusRecordingId', 'consensusEntryIndex')

def require(ok, why):
    if not ok:
        raise ValueError(why)

def keys(obj, names, why):
    require(isinstance(obj, dict) and set(obj) == set(names), why)

def integer(value, lo, hi, why):
    require(type(value) is int and lo <= value <= hi, why)
    return value

def no_symlink(path):
    path = Path(path).absolute()
    require('..' not in path.parts, 'parent traversal path component')
    require(not any(p.is_symlink() for p in (path,) + tuple(path.parents)), 'symlink path component')
    return path

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'invalid SHA256')
    return value

def pairs(values):
    result = {}
    for key, value in values:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result

def json_read(path, limit):
    path = no_symlink(path)
    require(path.is_file() and path.stat().st_size <= limit, 'bounded regular JSON required')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs)

def relative_file(base, description, limit):
    keys(description, ('path', 'bytes', 'sha256'), 'file descriptor keys')
    name = description['path']
    require(isinstance(name, str) and name and '\\' not in name and not name.startswith('/')
            and all(part not in ('', '.', '..') for part in name.split('/')), 'strict relative path required')
    path = no_symlink(base / name)
    require(path.is_relative_to(base) if hasattr(path, 'is_relative_to') else str(path).startswith(str(base) + os.sep), 'input outside manifest root')
    size = integer(description['bytes'], 1, limit, 'file byte bound')
    require(path.is_file() and path.stat().st_size == size and sha(path) == digest(description['sha256']), 'file size/SHA mismatch')
    return path

def validate_manifest(manifest_path):
    manifest_path = no_symlink(manifest_path)
    require(manifest_path.is_file() and manifest_path.stat().st_size <= 65536, 'bounded manifest file required')
    manifest = json_read(manifest_path, 65536)
    keys(manifest, ('schemaVersion', 'scope', 'allOwnedStopped', 'sourceRevision', 'expected', 'stopReceipt', 'nodes'), 'manifest keys')
    require(type(manifest['schemaVersion']) is int and manifest['schemaVersion'] == 1
            and manifest['scope'] == 'STOPPED_CURRENT_ORIGINAL_CHECKPOINT'
            and manifest['allOwnedStopped'] is True and manifest['sourceRevision'] == REVISION, 'manifest scope/source/stopped mismatch')
    require(manifest['expected'] == EXPECTED and all(type(manifest['expected'][k]) is type(v) for k, v in EXPECTED.items()), 'expected R2 canonical frontier differs')
    base = manifest_path.parent
    stop = relative_file(base, manifest['stopReceipt'], 1024 * 1024)
    stopped = json_read(stop, 1024 * 1024)
    require(stopped.get('allOwnedStopped') is True and stopped.get('errors') == [], 'successful clean stopped receipt required')
    stops = stopped.get('stops')
    require(isinstance(stops, list) and 3 <= len(stops) <= 16 and all(isinstance(s, dict) and s.get('stopped') is True for s in stops), 'all registered stop entries must be stopped')
    require({'node-0', 'node-1', 'node-2'}.issubset({s.get('role') for s in stops}), 'three original node stops required')
    require(stopped.get('forcedKill') is False, 'forced kill is not clean checkpoint stop')
    require(isinstance(manifest['nodes'], list) and len(manifest['nodes']) == 3, 'three nodes required')
    checked, all_paths = [], {stop}
    for number, node in enumerate(manifest['nodes']):
        keys(node, ('node', 'preflightMaxSnapshotEntryIndex', 'recordingLog', 'selected', 'recording'), 'node keys')
        require(type(node['node']) is int and node['node'] == number, 'nodes ordered uniquely 0,1,2')
        maximum = integer(node['preflightMaxSnapshotEntryIndex'], -1, 1024, 'preflight index bound')
        log = relative_file(base, node['recordingLog'], 65536)
        require(log.stat().st_size >= 64 and log.stat().st_size % 64 == 0, 'recording.log aligned size')
        selected = node['selected']
        keys(selected, SELECTED_KEYS, 'selected metadata keys')
        for k in SELECTED_KEYS:
            integer(selected[k], 0, 2**63 - 1, 'selected nonnegative int64')
        for k in ('serviceEntryIndex', 'consensusEntryIndex'):
            integer(selected[k], maximum + 1, 1024, 'NEW snapshot entry required')
        require(selected['recordingId'] != selected['consensusRecordingId']
                and selected['logPosition'] >= selected['termBaseLogPosition'] and selected['logPosition'] % 32 == 0,
                'selected snapshot identities/position')
        rec = node['recording']
        keys(rec, ('filename', 'bytes', 'sha256', 'prefix', 'zeroTailBeyondPrefixVerified'), 'recording descriptor keys')
        require(rec['filename'] == str(selected['recordingId']) + '-0.rec', 'selected recording filename mismatch')
        integer(rec['bytes'], 64, 1024 * 1024 * 1024, 'full recording byte bound')
        digest(rec['sha256'])
        require(rec['zeroTailBeyondPrefixVerified'] is True, 'full recording zero-tail verification assertion missing')
        prefix = relative_file(base, rec['prefix'], MAX_PREFIX)
        require(64 <= prefix.stat().st_size <= rec['bytes'] and prefix.stat().st_size % 32 == 0, 'aligned recording prefix bound')
        require(log not in all_paths and prefix not in all_paths and log != prefix, 'duplicate input file path')
        all_paths.update((log, prefix))
        checked.append((node, log, prefix))
    cohort = ('leadershipTermId', 'termBaseLogPosition', 'logPosition', 'timestamp')
    require(all(len({n[0]['selected'][k] for n in checked}) == 1 for k in cohort), 'snapshot cohort metadata differs across nodes')
    return manifest, checked, sorted(all_paths)

def frozen_artifacts():
    frozen = json_read(PREP / 'PREPARATION.json', 128 * 1024)
    require(frozen.get('sourceRevision') == REVISION and frozen.get('cloudAccessed') is False, 'preparation binding')
    require(set(p.name for p in (PREP / 'lib').iterdir()) == set(LIB_SHA), 'exact four pinned libraries required')
    for name, expected in LIB_SHA.items():
        require(sha(no_symlink(PREP / 'lib' / name)) == expected, 'pinned library differs')
    for name, info in frozen['frozenFiles'].items():
        require(isinstance(name, str) and name and not name.startswith('/') and '\\' not in name
                and all(part not in ('', '.', '..') for part in name.split('/')), 'strict frozen relative path')
        path = no_symlink(PREP / name)
        require(path.stat().st_size == info['bytes'] and sha(path) == info['sha256'], 'frozen reader preparation differs')
    return frozen

def prepare_inputs(manifest_path, output_dir, java_executable):
    """Validate all inputs before writes; return exact argv for caller-owned sequential launches. No process starts."""
    frozen_artifacts()
    manifest_path = no_symlink(manifest_path)
    manifest, checked, inputs = validate_manifest(manifest_path)
    before = {str(p): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in inputs + [manifest_path]}
    output = no_symlink(output_dir)
    require(output.parent.is_dir() and not output.exists(), 'existing parent and NEW output required')
    require(not any(p == output or output in p.parents for p in inputs + [manifest_path]), 'output overlaps input')
    java = Path(java_executable)
    require(java.is_absolute() and java.is_file() and os.access(str(java), os.X_OK)
            and java.name == 'java' and '\n' not in str(java), 'explicit absolute executable java required')
    output.mkdir(mode=0o700)
    (output / 'input-manifest.json').write_bytes(manifest_path.read_bytes())
    classpath = os.pathsep.join([str(PREP / 'original-current-checkpoint-reader-r3.jar')] + [str(PREP / 'lib' / n) for n in sorted(LIB_SHA)])
    nodes = []
    for node, log, prefix in checked:
        node_out = output / ('node%d' % node['node'])
        node_out.mkdir(mode=0o700)
        disposable = node_out / 'disposable-recording-log'
        disposable.mkdir(mode=0o700)
        shutil.copyfile(log, disposable / 'recording.log')
        require(sha(disposable / 'recording.log') == node['recordingLog']['sha256'], 'disposable recording.log copy SHA mismatch')
        args = [str(java), '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED', '-Xmx128m',
                '-cp', classpath, 'io.vectormatch.cluster.ReadCurrentOriginalCheckpointsR3', str(disposable), str(prefix), str(node_out / 'decoded'),
                str(node['preflightMaxSnapshotEntryIndex'])] + [str(node['selected'][k]) for k in SELECTED_KEYS]
        (node_out / 'argv.json').write_text(json.dumps(args, indent=2) + '\n')
        nodes.append({'node': node['node'], 'argv': args, 'selected': node['selected'], 'decodedDir': str(node_out / 'decoded'),
                      'fullNativeRecordingProducerAssertion': node['recording']})
    plan = {'schemaVersion': 1, 'outputDir': str(output), 'manifestPath': str(manifest_path), 'manifestSha256': sha(manifest_path),
            'preparationSha256': sha(PREP / 'PREPARATION.json'), 'inputsBefore': before, 'nodes': nodes,
            'launchesPerformed': False, 'requiresCallerOwnedPidSupervisor': True}
    (output / 'reader-plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    return plan

def finish_outputs(plan, child_results):
    """Validate caller-owned exit records and all decoded bytes. No process starts/stops."""
    frozen_artifacts()
    output = no_symlink(plan['outputDir'])
    require(json_read(output / 'reader-plan.json', 65536) == plan, 'reader plan differs')
    require(plan['preparationSha256'] == sha(PREP / 'PREPARATION.json'), 'preparation changed since prepare')
    manifest_path = no_symlink(plan['manifestPath'])
    require(sha(manifest_path) == plan['manifestSha256'], 'manifest changed since prepare')
    _, checked, inputs = validate_manifest(manifest_path)
    require(isinstance(child_results, list) and len(child_results) == 3
            and all(isinstance(r, dict) and type(r.get('node')) is int and r['node'] == i
                    and type(r.get('exitCode')) is int and r['exitCode'] == 0 for i, r in enumerate(child_results)),
            'three ordered successful caller-owned reader exit results required')
    require(len(json.dumps(child_results)) <= 65536, 'child result size cap')
    rows = []
    for number, node in enumerate(plan['nodes']):
        require(node['node'] == number, 'plan node order')
        decoded_dir = no_symlink(output / ('node%d/decoded' % number))
        require(str(decoded_dir) == node['decodedDir'], 'decoded path differs from plan')
        decoded = json_read(decoded_dir / 'result.json', 65536)
        require(decoded.get('passed') is True and all(decoded.get(k) == v for k, v in EXPECTED.items()), 'decoded current R2 frontier differs')
        result_keys = {'recordingId': 'recordingId', 'leadershipTermId': 'leadershipTermId', 'termBaseLogPosition': 'termBaseLogPosition',
                       'logPosition': 'checkpointLogPosition', 'timestamp': 'timestamp', 'serviceEntryIndex': 'serviceEntryIndex',
                       'consensusRecordingId': 'consensusRecordingId', 'consensusEntryIndex': 'consensusEntryIndex'}
        require(all(decoded.get(result_keys[k]) == node['selected'][k] for k in SELECTED_KEYS), 'decoded snapshot identity differs')
        canonical = no_symlink(decoded_dir / 'canonical-engine.bin')
        combined = no_symlink(decoded_dir / 'cluster-checkpoint.bin')
        require(canonical.is_file() and combined.is_file() and canonical.stat().st_size <= 8 * 1024 * 1024 and combined.stat().st_size <= 8 * 1024 * 1024
                and sha(canonical) == decoded['canonicalEngineSha256'] and sha(combined) == decoded['combinedCheckpointSha256'], 'decoded artifact SHA bound')
        rows.append({'node': number, 'selected': node['selected'], 'decoded': decoded,
                     'callerOwnedChildResult': child_results[number], 'fullNativeRecordingProducerAssertion': node['fullNativeRecordingProducerAssertion']})
    for name in ('canonical-engine.bin', 'cluster-checkpoint.bin'):
        data = (output / 'node0/decoded' / name).read_bytes()
        require(all((output / ('node%d/decoded' % n) / name).read_bytes() == data for n in (1, 2)), 'three replica canonical bytes differ')
    require(plan['inputsBefore'] == {str(p): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in inputs + [manifest_path]}, 'input source changed during read')
    receipt = {'schemaVersion': 1, 'passed': True, 'scope': 'OFFLINE_NEW_STOPPED_ORIGINAL_CHECKPOINT_ONLY',
               'sourceRevision': REVISION, 'manifestSha256': sha(manifest_path), 'preparationSha256': sha(PREP / 'PREPARATION.json'),
               'inputFilesBeforeAndAfterMatch': True, 'allThreeCanonicalEngineBytesEqual': True, 'allThreeCombinedCheckpointBytesEqual': True,
               'nodes': rows, 'businessApplied': False, 'ackSent': False, 'aeronOrSqlStarted': False, 'networkAccessed': False,
               'fullNativeRecordingHashesIndependentlyReadByThisReader': False,
               'limitations': 'Producer manifest binds full native hashes and verified zero tail; this reader independently hashes only bounded prefixes and recording.log copies. This proves selected stopped checkpoint bytes, not later tail replay, latency, throughput, or durability SLA.'}
    receipt_path = output / 'receipt.json'
    with receipt_path.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    return receipt

def main(argv):
    require(len(argv) == 3, 'LOCAL CLI: read-current-checkpoints.py <manifest> <NEW-output> <absolute-java>; CPU caller MUST use prepare_inputs/finish_outputs and own each JVM')
    plan = prepare_inputs(argv[0], argv[1], argv[2])
    children = []
    for node in plan['nodes']:
        node_out = Path(plan['outputDir']) / ('node%d' % node['node'])
        start = time.monotonic()
        result = subprocess.run(node['argv'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        (node_out / 'stdout.log').write_bytes(result.stdout)
        (node_out / 'stderr.log').write_bytes(result.stderr)
        require(len(result.stdout) <= 65536 and len(result.stderr) <= 65536, 'bounded decoder logs required')
        children.append({'node': node['node'], 'exitCode': result.returncode, 'wallSeconds': time.monotonic() - start})
        require(result.returncode == 0, 'offline reader failed; failed output retained')
    receipt = finish_outputs(plan, children)
    print(json.dumps({'passed': receipt['passed'], 'receipt': str(Path(plan['outputDir']) / 'receipt.json')}))

if __name__ == '__main__':
    main(sys.argv[1:])
