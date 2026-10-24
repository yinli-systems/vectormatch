from pathlib import Path
import json,time,os
p=Path('/proc/5669')
def sample():
 if not p.exists():return dict(absent=True)
 st=(p/'stat').read_text();f=st[st.rfind(')')+2:].split();raw=(p/'cmdline').read_bytes();return dict(pid=5669,startTicks=int(f[19]),cpuTicks=int(f[11])+int(f[12]),state=f[0],cwd=os.readlink(str(p/'cwd')),children=(p/'task/5669/children').read_text().strip(),argv=raw.rstrip(b'\0').decode().split('\0'))
a=sample();time.sleep(3);b=sample();print(json.dumps(dict(readOnly=True,first=a,second=b,noSignals=True,cgroupCpuMax=Path('/sys/fs/cgroup/cpu.max').read_text(),cgroupMemoryMax=Path('/sys/fs/cgroup/memory.max').read_text(),affinity=sorted(os.sched_getaffinity(0)))))
