"""Publish all retained optimization groups to the local evidence index; no remote action."""
import hashlib
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
base = root / 'evidence/2026-10-23/runpod-optimization'
spec = importlib.util.spec_from_file_location('export_capacity', root / 'scripts/export-capacity-ui.py')
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)
path = root / 'evidence/index.json'
before = path.read_bytes()
index = json.loads(before)
original_runs = json.dumps(index['runs'], sort_keys=True, separators=(',', ':'))
old_cohorts = {row['id']: row for row in index['capacityCohorts']}
groups = [
    ('window350k/w128', 'opt-350k-w128', '350k · W128 · 26k/s overload'),
    ('window350k/w256', 'opt-350k-w256', '350k · W256 · INVALID / retained unknown'),
    ('nak/pilot100us', 'opt-nak-pilot', 'NAK 100us · W256 · 10k/s pilot / overload'),
    ('nak/delay1000', 'opt-nak-1000', 'NAK 1us · W256 · two INVALID attempts'),
    ('nak/delay100000', 'opt-nak-100000', 'NAK 100us · W256 · two overload attempts'),
]
for relative, label in [('pipeline/pilot', 'pilot'), ('pipeline/direct', 'direct'), ('pipeline/multiplexed', 'multiplexed')]:
    if (base / relative / 'analysis/summary.json').is_file():
        groups.append((relative, 'opt-pipeline-' + label, 'Session ownership · W128 · ' + label))
inputs = []
for relative, identity, title in groups:
    source = base / relative / 'analysis/summary.json'
    summary = json.loads(source.read_text())
    scope = ('Private UDP three-node client+cluster test, appointed leader0 / sync2 / 2 GiB per node and load. '
             'capacity-350k-v1, retained360000, outbox800000, maxSessions256, fixed fixture. '
             'Load shares member2. Each curve contains one verified configuration; invalid/failed attempts remain visible. '
             'p99 includes schedule/FIFO delay and is conditional on accepted confirmations; all-offered p99 is null if any request is not accepted. '
             'Invalid goodput/latency are client-reported diagnostics, not validated capacity. Finite windows do not establish sustained capacity. ')
    if relative.startswith('nak/'):
        scope += 'Logical W256/Q64, physical256 sessions, one shared driver; only two-ended NAK delay differs across groups. '
    elif relative.startswith('pipeline/'):
        scope += 'Logical W128/Q64, FIFO8192, one shared driver, NAK1000ns. direct128 physical sessions vs multiplexed1/network-owner1. '
    else:
        scope += 'W128 or W256, Q64; physical session count equals workers. '
    capacity = export.make_capacity(summary, identity, title, scope, 'docs/OPTIMIZATION_RESULTS.md')
    export.update_index(index, capacity, identity)
    inputs.append({'summary': str(source.relative_to(root)), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                   'cohortId': identity, 'points': len(capacity['points'])})
assert json.dumps(index['runs'], sort_keys=True, separators=(',', ':')) == original_runs
new_cohorts = {row['id']: row for row in index['capacityCohorts']}
for identity, cohort in old_cohorts.items():
    assert new_cohorts[identity] == cohort, 'Historical cohort changed: ' + identity
encoded = (json.dumps(index, indent=2, allow_nan=False) + '\n').encode()
path.write_bytes(encoded)
out = base / 'restoration/tool-validation'
out.mkdir(parents=True, exist_ok=True)
receipt = {'passed': True, 'previousIndexSha256': hashlib.sha256(before).hexdigest(),
           'newIndexSha256': hashlib.sha256(encoded).hexdigest(), 'historicalRunsPreserved': len(index['runs']),
           'historicalCohortsPreserved': list(old_cohorts), 'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'inputs': inputs, 'scope': 'Summary export only; analyzers, raw data and configurations unchanged. No remote deployment.'}
(out / 'index-export.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
