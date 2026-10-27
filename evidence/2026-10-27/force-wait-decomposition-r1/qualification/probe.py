from pathlib import Path
import json,os,shutil,subprocess
out={'hostname':Path('/etc/hostname').read_text().strip(),'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'kernel':os.uname().release,'timeNamespace':os.readlink('/proc/self/ns/time'),'uid':os.getuid(),'freeBytes':shutil.disk_usage('/opt/vectormatch-cpu').free,'tools':{n:shutil.which(n)for n in ['perf','bpftrace','strace','iostat','pidstat','gcc']}}
paths=['/proc/sys/kernel/perf_event_paranoid','/proc/sys/kernel/unprivileged_bpf_disabled','/proc/sys/kernel/sched_schedstats','/proc/sys/kernel/task_delayacct','/proc/self/schedstat','/proc/self/cgroup','/sys/fs/cgroup/cpu.max','/sys/fs/cgroup/cpu.stat','/sys/fs/cgroup/io.stat','/sys/fs/cgroup/io.max','/proc/pressure/io','/proc/pressure/cpu']
for n in paths:
 try:out[n]=Path(n).read_text()
 except OSError as e:out[n]=str(e)
out['capabilities']=[s for s in Path('/proc/self/status').read_text().splitlines()if s.startswith(('Cap','Seccomp','Cpus_allowed_list'))]
out['tracefs']={n:{'exists':Path(n).exists(),'readable':os.access(n,os.R_OK),'writable':os.access(n,os.W_OK)}for n in ['/sys/kernel/tracing/trace','/sys/kernel/tracing/events/sched/sched_switch/enable','/sys/kernel/debug/tracing/trace','/sys/kernel/tracing/instances']}
out['mounts']=[s for s in Path('/proc/self/mountinfo').read_text().splitlines()if ' / 'in s or ' /opt 'in s or ' /workspace 'in s or 'tracefs'in s]
out['java']=[]
for f in Path('/proc').glob('[0-9]*/comm'):
 try:
  if f.read_text().strip()=='java':out['java'].append({'pid':f.parent.name,'command':(f.parent/'cmdline').read_bytes().replace(b'\0',b' ').decode()})
 except(FileNotFoundError,ProcessLookupError):pass
print(json.dumps(out))
