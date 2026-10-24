"""Add only explicit closed local scopes to a fresh copy plan; never copy/scan/business/SSH/Git."""
from pathlib import Path
import argparse
import datetime
import importlib.util
import json
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ARCHIVER = BASE / 'event-cloud-arm-archive-preparation-r2'
SPEC = importlib.util.spec_from_file_location('closed_archive_primitives', BASE / 'owner-cloud-arm-archive-preparation-r2/archive_arm.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)
p.EXCLUDED_PARTS = set()


def need(value, message):
    if not value:
        raise AssertionError(message)


def canonical(path):
    need(path.is_absolute() and path.is_relative_to(BASE) and '..' not in path.parts
         and not any(item.is_symlink() for item in (path, *path.parents)),
         'Explicit absolute regular source or fresh output below BASE')


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--arm', type=int, choices=(3, 4), required=True)
    parser.add_argument('--base-plan', type=Path, required=True)
    parser.add_argument('--base-plan-sha256', required=True)
    parser.add_argument('--scope', action='append', required=True,
                        help='Explicit new archive name=absolute CLOSED source directory; repeat in display order')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original, output = args.base_plan, args.output
    canonical(original)
    canonical(output)
    need(original.name == 'COPY_PLAN.json' and original.is_file()
         and p.sha(original) == args.base_plan_sha256, 'Actual untouched builder plan and explicit SHA')
    need(original.parent.name.startswith('event-cloud-arm-%d-archive-plan-r' % args.arm), 'Actual selected-arm builder plan')
    need(output.parent == BASE and output.name.startswith('event-cloud-arm-%d-archive-plan-r' % args.arm)
         and not output.exists(), 'Fresh selected-arm augmented plan only')
    value = json.loads(original.read_text())
    for name, pin in json.loads((HERE / 'SOURCE_FROZEN.json').read_text())['sourceFiles'].items():
        need(p.row(HERE / name) == pin, 'Closed augmentation source remains unchanged')
    need(value['schemaVersion'] == 2 and value['arm'] == args.arm
         and value['eventFetchCount'] == (16 if args.arm == 3 else 32), 'Selected actual arm/page')
    need(value['preparationSha256'] == p.sha(ARCHIVER / 'SOURCE_FROZEN.json'), 'Unchanged reviewed R2 archiver')
    for name, pin in json.loads((ARCHIVER / 'SOURCE_FROZEN.json').read_text())['sourceFiles'].items():
        need(p.row(ARCHIVER / name) == pin, 'Frozen R2 source remains unchanged')
    names = []
    for item in args.scope:
        name, separator, text = item.partition('=')
        need(separator == '=' and name and '/' not in name and '\\' not in name
             and name not in ('.', '..') and name not in value['sourceTrees'], 'Explicit unique new scope name')
        source = Path(text)
        canonical(source)
        need(source.is_dir() and not source.is_symlink(), 'Only actually present closed directory is snapshotted')
        value['sourceTrees'][name] = {'source': str(source), 'inventory': p.snapshot(source)}
        names.append(name)
    singles = [
        ('plan-augmentation/augment_plan.py', Path(__file__)),
        ('plan-augmentation/augmentation-SOURCE_FROZEN.json', HERE / 'SOURCE_FROZEN.json'),
        ('plan-augmentation/augmentation-README.md', HERE / 'README.md'),
        ('plan-augmentation/original-builder-COPY_PLAN.json', original),
        ('plan-augmentation/original-builder-REGISTRATION.json', original.parent / 'REGISTRATION.json'),
    ]
    for name, source in singles:
        need(name not in value['sourceFiles'], 'No existing source single is replaced')
        canonical(source)
        value['sourceFiles'][name] = {'source': str(source), 'pin': p.row(source)}
    need(p.sha(original) == args.base_plan_sha256, 'Original builder plan is still byte-identical')
    output.mkdir(mode=0o700)
    p.save(output / 'COPY_PLAN.json', value)
    p.save(output / 'REGISTRATION.json', dict(
        atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(), arm=args.arm,
        rootReviewSha256=value['rootReviewSha256'], originalBuilderPlanSha256=args.base_plan_sha256,
        augmentationSourceSha256=p.sha(Path(__file__)), sourceScopes=len(value['sourceTrees']),
        sourceSingleFiles=len(value['sourceFiles']), newlyAddedClosedScopes=names,
        originalPlanUnchanged=True, archiverSourceUnchanged=True,
        comparatorOrCopyOrScanBusinessAuditTestsSshGitExecuted=False))
    print(json.dumps(dict(passed=True, config=str(output / 'COPY_PLAN.json'),
                         configSha256=p.sha(output / 'COPY_PLAN.json'), arm=args.arm,
                         sourceScopes=len(value['sourceTrees']), sourceSingleFiles=len(value['sourceFiles']),
                         actualCopyOrScanExecuted=False)))


if __name__ == '__main__':
    main()
