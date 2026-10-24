#!/usr/bin/env python3
"""One bounded metadata-only observation, no application commands or signals."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import time

started = time.monotonic()
if socket.gethostname() != 'ed6c0673f5cb':
    raise RuntimeError('Unexpected existing CPU host')

def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError as error:
        return {'unavailable': type(error).__name__}

processes = []
scanned = 0
for folder in Path('/proc').iterdir():
    if not folder.name.isdigit():
        continue
    scanned += 1
    if scanned > 4096 or time.monotonic() - started > 15:
        raise RuntimeError('Bounded process inventory exceeded')
    try:
        comm = (folder / 'comm').read_text().strip()
        if comm not in ['java', 'javaw', 'postgres', 'postmaster']:
            continue
        stat = (folder / 'stat').read_text()
        arguments = (folder / 'cmdline').read_bytes()
        stat_after = (folder / 'stat').read_text()
        ticks = int(stat[stat.rfind(')') + 2:].split()[19])
        after_ticks = int(stat_after[stat_after.rfind(')') + 2:].split()[19])
        if ticks != after_ticks:
            raise RuntimeError('Process identity changed during observation')
        processes.append({'pid': int(folder.name), 'startTicks': ticks,
                          'commandSha256': hashlib.sha256(arguments).hexdigest(),
                          'comm': comm, 'fullArgumentsDisclosed': False})
    except FileNotFoundError:
        continue

cpu_model = next((line.split(':', 1)[1].strip() for line in
                  Path('/proc/cpuinfo').read_text().splitlines()
                  if line.startswith('model name')), None)
memory = {line.split(':', 1)[0]: line.split(':', 1)[1].strip()
          for line in Path('/proc/meminfo').read_text().splitlines()
          if line.startswith(('MemTotal:', 'MemAvailable:', 'SwapTotal:', 'SwapFree:'))}
cgroup_line = next((line[3:] for line in Path('/proc/self/cgroup').read_text().splitlines()
                    if line.startswith('0::')), None)
cgroup = Path('/sys/fs/cgroup') / (cgroup_line or '').lstrip('/')
disk = {}
for path in ['/opt/vectormatch-cpu', '/workspace', '/dev/shm']:
    usage = shutil.disk_usage(path)
    disk[path] = {'totalBytes': usage.total, 'usedBytes': usage.used, 'freeBytes': usage.free}
print(json.dumps({'schema': 'cpu-idle-campaign-readonly-resource-v1',
                  'atUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'hostname': socket.gethostname(), 'cpuModel': cpu_model,
                  'allowedLogicalCpus': sorted(os.sched_getaffinity(0)),
                  'memory': memory, 'disk': disk,
                  'cgroupPath': str(cgroup),
                  'cgroup': {name: read(cgroup / name) for name in
                             ['cpu.max', 'cpu.stat', 'memory.max', 'memory.current',
                              'memory.events', 'cpuset.cpus.effective']},
                  'javaAndPostgresIdentities': processes,
                  'allJavaAndPostgresAbsentAtSample': not processes,
                  'processesScanned': scanned,
                  'elapsedSeconds': time.monotonic() - started,
                  'readOnly': True, 'javaStarted': False, 'applicationStarted': False,
                  'noSignals': True, 'noSql': True,
                  'scope': 'One instant metadata observation; no reservation or exclusive-host guarantee'},
                 sort_keys=True))
