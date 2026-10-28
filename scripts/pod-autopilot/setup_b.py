"""Create a pod-B campaign root from the verified runtime. Usage: setup_b.py ROOT CASES_JSON

Copies the hash-verified runtime, adapts only the host-specific overlay device check in the
initialization audit, points the candidate at this pod's verified JDK, and writes PLAN.json with
this pod's boot/host, physical-core CPU pairs and the supplied cases."""
from pathlib import Path
import hashlib, json, os, shutil, sys

RUNTIME = Path(os.environ.get('VM_RUNTIME', '/opt/vectormatch-b/runtime'))
ROOT = Path(sys.argv[1])
CASES = json.loads(Path(sys.argv[2]).read_text())
JAVA = '/root/tools/jdk-21.0.13+9/bin/java'
ROOT.mkdir(parents=True, exist_ok=False)
old = json.loads((RUNTIME / 'CANDIDATE.json').read_text())
for name in list(old['files']) + ['campaign.py']:
    target = ROOT / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RUNTIME / name if name != 'campaign.py' else Path(sys.argv[3]), target)

audit = ROOT / 'audit-recording-initialization.py'
s = audit.read_text()
host_check = "f['device']==48"
assert s.count(host_check) == 1
# Same intent as the original-host constant: the segment lives on the experiment's own filesystem.
audit.write_text(s.replace(host_check, "f['device']==__import__('os').stat(p).st_dev"))


def digest(path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


assert digest(Path(JAVA)) == old['javaBinarySha256']
candidate = dict(old)
candidate['javaPath'] = JAVA
candidate['adaptedForHost'] = {'file': 'audit-recording-initialization.py', 'change': host_check + ' -> same device as experiment root'}
candidate['files'] = {n: {'sha256': digest(ROOT / n), 'bytes': (ROOT / n).stat().st_size} for n in old['files']}
(ROOT / 'CANDIDATE.json').write_text(json.dumps(candidate, indent=2) + '\n')

plan = json.loads((RUNTIME / 'PLAN.json').read_text())
plan['boot'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
plan['host'] = Path('/etc/hostname').read_text().strip()
plan['cpuSets'] = json.loads(os.environ.get('VM_CPUSETS', '[[2, 98], [10, 106], [14, 110], [88, 184]]'))
plan['cases'] = CASES['cases']
plan['selection'] = CASES['selection']
plan['scope'] = CASES['scope']
(ROOT / 'PLAN.json').write_text(json.dumps(plan, indent=2) + '\n')
print(json.dumps({'root': str(ROOT), 'boot': plan['boot'], 'cases': list(plan['cases'])}))
