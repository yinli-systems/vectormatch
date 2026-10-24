from pathlib import Path
import sys,json,hashlib,socket
root=Path('/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1');sys.path.insert(0,str(root));import cpu_read_window32_abab as c
base=c.load_base();release=json.loads((root/'release/release.json').read_text());c.validate_release(release);protected=c.protected_state(base,release)
try:idle=c.strict_idle(base);state='IDLE_READY_FOR_SEPARATE_PREFLIGHT';error=None
except RuntimeError as e:idle=None;state='WAITING_FOR_FOREIGN_JVM_NATURAL_EXIT';error=str(e)
p=base.process_identity(5669)
print(json.dumps(dict(passedReadOnlyChecks=True,host=socket.gethostname(),state=state,protected=protected,strictIdle=idle,strictIdleRejection=error,gradleIdentity=None if p is None else{k:p[k]for k in['pid','startTicks','commandSha256']},originalOwnershipBaseSha256=hashlib.sha256((root/'owned_linux_base_8eeb.py').read_bytes()).hexdigest(),releaseSha256=hashlib.sha256((root/'release/release.json').read_bytes()).hexdigest(),noWorkloadLaunch=True,noSignals=True)))
