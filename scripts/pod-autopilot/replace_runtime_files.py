"""Derive a runtime whose listed files are replaced and every other file is byte-identical.

Usage: replace_runtime_files.py OLD_RUNTIME NEW_RUNTIME NOTE NAME=SOURCE...
NAME is a path listed in OLD_RUNTIME/CANDIDATE.json files (for example audit-replicated-path-probe.py).
The candidate's file hashes are rewritten and the change is recorded under "patches"."""
from pathlib import Path
import hashlib, json, shutil, sys


def digest(path):
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


OLD, NEW, NOTE = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
replacements = dict(arg.split('=', 1) for arg in sys.argv[4:])
candidate = json.loads((OLD / 'CANDIDATE.json').read_text())
unknown = sorted(set(replacements) - set(candidate['files']))
assert replacements and not unknown, 'unknown runtime files: %s' % unknown
shutil.copytree(OLD, NEW)
for name, source in replacements.items():
    shutil.copyfile(source, NEW / name)
for name in candidate['files']:
    if name not in replacements:
        assert digest(OLD / name) == digest(NEW / name), name
candidate.setdefault('patches', []).append({'note': NOTE, 'replacedFiles': sorted(replacements),
                                            'sources': {Path(s).name: digest(s) for s in replacements.values()}})
candidate['files'] = {n: {'sha256': digest(NEW / n), 'bytes': (NEW / n).stat().st_size} for n in candidate['files']}
(NEW / 'CANDIDATE.json').write_text(json.dumps(candidate, indent=2) + '\n')
print(json.dumps({'runtime': str(NEW), 'replacedFiles': sorted(replacements),
                  'sha256': {n: candidate['files'][n]['sha256'] for n in sorted(replacements)}}))
