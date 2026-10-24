from pathlib import Path
import socket,json,os,hashlib
assert socket.gethostname()=='33ace3d92505'
roots=['/opt/vectormatch-cpu/restorations/original-native-r1','/opt/vectormatch-cpu/preparation','/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1']
for name in roots:
 p=Path(name)
 assert not p.exists() and not p.is_symlink(), 'Fresh protected absence differs: '+name
print(json.dumps(dict(schemaVersion=1,scope='CURRENT_CPU_CONTAINER_ABSENT_OLD_STATE_AND_FRESH_SYNTHETIC_NAMESPACE',host=socket.gethostname(),bootId=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),absentProtectedPaths=roots,old57AndPg989RestorationClaimed=False,newSyntheticNamespaceOnly=True,affinity=sorted(os.sched_getaffinity(0)),cpuMax=Path('/sys/fs/cgroup/cpu.max').read_text(),memoryMax=Path('/sys/fs/cgroup/memory.max').read_text()),sort_keys=True,indent=2))
