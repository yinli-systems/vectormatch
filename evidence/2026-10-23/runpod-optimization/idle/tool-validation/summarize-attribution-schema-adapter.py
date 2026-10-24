#!/usr/bin/env python3
"""Explicit controller-archive schema adapter around the frozen idle/18k reader.

ROOT OUTPUT_JSON --experiment pipeline-capacity|node-idle [--cohorts formal|pilot]
Only an in-memory files/controllers key mapping is allowed. Original SHA checks
remain exact; original tools/plans/archive/raw are never edited or overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


WRAPPER_SHA = '1c6d3d478e07d304f0407cf409661a987ad2b7a64d3bedcf85858330a4aae033'
VALIDATION_SHA = '8ce2ad4bd8fac58bec78fd5c7c9ca4c29a4bfe1f4fc7f265a15193a425454668'
CONTROLLER_KEYS = {
    'pipeline-capacity': {'common.py', 'register.py', 'matrix.py', 'test_guards.py', 'postprocessor.py', 'build-postprocessor.py'},
    'node-idle': {'common.py', 'register.py', 'matrix.py', 'test_guards.py', 'build.py', 'bundle-node.py', 'deploy-node.py'},
}


def require(value, message):
    if not value: raise ValueError(message)


def digest(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Regular source required: ' + str(path))
    result = hashlib.sha256(); size = 0
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(data); size += len(data)
    return {'path': str(path), 'sha256': result.hexdigest(), 'bytes': size}


def normalize_controller_archive(value, registered, experiment):
    require(experiment in CONTROLLER_KEYS, 'Unknown controller schema experiment')
    expected_keys = CONTROLLER_KEYS[experiment]
    require(isinstance(registered, dict) and set(registered) == expected_keys, 'Registered controller key closure differs')
    present = {key for key in ('files', 'controllers') if isinstance(value, dict) and key in value}
    require(len(present) == 1, 'Require exactly one explicit files/controllers schema; no ambiguous fallback')
    key = next(iter(present)); entries = value[key]
    require(isinstance(entries, dict) and set(entries) == expected_keys, 'Archived controller key closure differs')
    checks = []
    for name in sorted(expected_keys):
        entry = entries[name]
        require(isinstance(entry, dict) and isinstance(entry.get('source'), str), 'Missing exact archived source: ' + name)
        require(isinstance(registered[name], str) and re.fullmatch('[0-9a-f]{64}', registered[name]), 'Invalid registered controller SHA')
        actual = hashlib.sha256(entry['source'].encode()).hexdigest()
        require(actual == entry.get('sha256') == registered[name], 'Controller source SHA changed: ' + name)
        checks.append({'name': name, 'registeredSha256': registered[name], 'archivedSha256': entry['sha256'],
                       'computedSourceSha256': actual, 'matched': True})
    normalized = dict(value)
    if key != 'files':
        normalized['files'] = normalized.pop(key)
    return normalized, {'sourceKey': key, 'targetKey': 'files', 'mappedInMemory': key != 'files',
                        'exactControllerCount': len(expected_keys), 'controllerShaChecks': checks}


def frozen_wrapper():
    path = Path(__file__).with_name('summarize-idle-attribution.py')
    identity = digest(path)
    require(identity['sha256'] == WRAPPER_SHA, 'Original frozen wrapper changed')
    spec = importlib.util.spec_from_file_location('frozen_idle_attribution_with_schema_adapter', path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    validation = digest(path.with_name('attribution-wrapper-validation.json'))
    require(validation['sha256'] == VALIDATION_SHA, 'Original source validation receipt changed')
    receipt = json.loads(Path(validation['path']).read_text())
    dependencies = []
    for expected in receipt['pinnedSourceDependencies']:
        actual = digest(expected['path'])
        require(actual['sha256'] == expected['expectedSha256'] == expected['sha256'], 'Original dependency changed: ' + expected['path'])
        dependencies.append(actual)
    return value, identity, validation, dependencies


def summarize(root, experiment, pilot):
    wrapper, identity, validation, dependencies = frozen_wrapper()
    original_factory = wrapper.frozen_reader
    adaptations = []

    def reader_factory(reader_root, requested_experiment, requested_pilot):
        reader, reader_identity, prior_changes, cohorts = original_factory(reader_root, requested_experiment, requested_pilot)
        original_optional_json = reader.optional_json
        target = (reader_root / 'tool-validation/controller-sources.json').resolve()
        plan_path = reader_root / ('pilot-plan.json' if requested_pilot else 'plan.json')
        plan = json.loads(plan_path.read_text())

        def optional_json(path, core, inputs):
            value = original_optional_json(path, core, inputs)
            if Path(path).resolve() != target:
                return value
            normalized, detail = normalize_controller_archive(value, plan['controllerSha256'], requested_experiment)
            # The frozen core already recorded the original bytes' SHA before this
            # in-memory view is returned; do not hash normalized JSON as evidence.
            detail['originalArchive'] = digest(path)
            detail['registeredPlan'] = digest(plan_path)
            adaptations.append(detail)
            return normalized

        reader.optional_json = optional_json
        return reader, reader_identity, prior_changes, cohorts

    wrapper.frozen_reader = reader_factory
    result = wrapper.summarize(root, experiment, pilot)
    require(len(adaptations) == 1, 'Require exactly one observed controller archive schema mapping')
    result['reusedIdleWrapperSha256'] = result.pop('scriptSha256')
    result['scriptSha256'] = digest(Path(__file__))['sha256']
    result['tools'].update(frozenIdleWrapper=identity, originalWrapperValidation=validation,
                           controllerSchemaAdapter=digest(Path(__file__)))
    result['controllerArchiveSchemaAdapter'] = {'adaptations': adaptations, 'originalDependencySources': dependencies,
        'scope': 'Only the top-level files/controllers key is normalized in memory after exact registered/archived/computed source SHA validation. '
                 'Original archive bytes, plan, source tools and raw evidence remain unchanged. No SHA check is skipped or replaced by normalized JSON hashing.'}
    result['generatedAt'] = datetime.now(timezone.utc).isoformat()
    return result


def self_test():
    names = CONTROLLER_KEYS['pipeline-capacity']
    entries = {name: {'source': '# source ' + name + '\n'} for name in names}
    for value in entries.values(): value['sha256'] = hashlib.sha256(value['source'].encode()).hexdigest()
    registered = {name: value['sha256'] for name, value in entries.items()}
    original = {'controllers': entries}; before = json.dumps(original, sort_keys=True)
    normalized, detail = normalize_controller_archive(original, registered, 'pipeline-capacity')
    assert set(normalized) == {'files'} and len(detail['controllerShaChecks']) == 6 and detail['mappedInMemory']
    assert json.dumps(original, sort_keys=True) == before
    unchanged, detail = normalize_controller_archive({'files': entries}, registered, 'pipeline-capacity')
    assert unchanged['files'] == entries and not detail['mappedInMemory']
    cases = []
    cases.append(({'files': entries, 'controllers': entries}, registered))
    cases.append(({}, registered))
    cases.append(({'controllers': {k: v for k, v in entries.items() if k != 'common.py'}}, registered))
    cases.append(({'controllers': {**entries, 'unregistered.py': entries['common.py']}}, registered))
    cases.append(({'controllers': entries}, {**registered, 'common.py': '0' * 64}))
    for field, changed in [('source', '# altered'), ('sha256', '0' * 64)]:
        damaged = json.loads(json.dumps(entries)); damaged['common.py'][field] = changed
        cases.append(({'controllers': damaged}, registered))
    for archive, expected in cases:
        try: normalize_controller_archive(archive, expected, 'pipeline-capacity')
        except ValueError: pass
        else: raise AssertionError('Ambiguous/missing/extra/changed source must be refused')
    idle_entries = {name: {'source': '# idle ' + name + '\n'} for name in CONTROLLER_KEYS['node-idle']}
    for entry in idle_entries.values(): entry['sha256'] = hashlib.sha256(entry['source'].encode()).hexdigest()
    _, idle_detail = normalize_controller_archive({'controllers': idle_entries},
        {name: entry['sha256'] for name, entry in idle_entries.items()}, 'node-idle')
    assert idle_detail['exactControllerCount'] == 7
    _, identity, _, dependencies = frozen_wrapper()
    assert identity['sha256'] == WRAPPER_SHA and len(dependencies) == 9
    print(json.dumps({'status': 'PASS', 'checks': ['exact-six-capacity-controller-keys', 'three-way-source-SHA',
        'files-schema-supported', 'controllers-schema-supported', 'original-object-unchanged', 'ambiguous-schema-rejected',
        'missing-extra-keys-rejected', 'changed-registered-source-SHA-rejected', 'changed-archived-SHA-rejected',
        'changed-source-bytes-rejected', 'idle-seven-key-schema-explicit', 'original-wrapper-nine-dependencies-pinned'],
        'actualMetricsSummarizationExecuted': False}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?'); parser.add_argument('output_json', type=Path, nargs='?')
    parser.add_argument('--experiment', choices=('node-idle', 'pipeline-capacity'), default='node-idle')
    parser.add_argument('--cohorts', choices=('formal', 'pilot'), default='formal')
    parser.add_argument('--self-test', action='store_true'); args = parser.parse_args()
    if args.self_test: self_test(); return
    if args.root is None or args.output_json is None: parser.error('ROOT OUTPUT_JSON required')
    require(not args.output_json.exists(), 'Frozen output exists; never overwrite')
    result = summarize(args.root, args.experiment, args.cohorts == 'pilot')
    result['reproduction'] = {'argv': [sys.executable, '-B', str(Path(__file__).resolve()), str(args.root), str(args.output_json),
                                     '--experiment', args.experiment, '--cohorts', args.cohorts]}
    data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n'
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open('x') as stream: stream.write(data)
    print(json.dumps({'output': str(args.output_json), 'included': result['includedTerminalAttemptCount'],
                     'allRequestedIncluded': result['allRegisteredRequestedAttemptsIncluded'], 'sha256': digest(args.output_json)['sha256'],
                     'scriptSha256': result['scriptSha256']}))


if __name__ == '__main__': main()
