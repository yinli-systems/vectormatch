#!/usr/bin/env python3
"""Thread-level CPU isolation for the JVMs of one running case.

Busy-spinning data-path agents lose milliseconds whenever another thread of the same JVM (JIT compiler,
JFR stream, Aeron client conductor, VM housekeeping) is scheduled onto their CPU. This governor gives each
agent a CPU of its own and confines every other thread to the housekeeping CPUs, with two exceptions that
keep stop-the-world pauses short: GC workers and the VM Thread may use the JVM's whole CPU set. They do
their work while every Java thread is stopped at a safepoint, when the agents' CPUs are idle anyway;
starving them on a crowded housekeeping CPU multiplied GC pause times.

JIT compiler threads stay on housekeeping at normal priority by default. Lowering it (compilerNice) is
available but harmful: a compiler thread must acknowledge safepoints whenever it is inside the VM, and at
nice 19 it waited up to 156 ms for CPU, holding every safepoint of its JVM for that long.

Run the JVMs with -XX:-UseDynamicNumberOfGCThreads so all GC workers exist, and are pinned, before
measurement: a worker created on demand inherits its creator's housekeeping affinity until the next pass.

Usage: pin_threads.py CASE_DIR CONFIG_JSON
CONFIG_JSON keys:
  cpuSets         [node0, node1, node2, source] CPU lists, as launched with taskset
  housekeeping    CPUs for non-agent threads; never given to an agent
  expectedAgents  optional {"node": n, "source": n}; more agents than expected are reported at once, and a
                  JVM whose peak agent count differs is listed as drift in the summary (thread naming drift)
  compilerNice    optional nice value for JIT compiler threads; absent or null leaves their priority alone
  roles           optional list of roles to govern (0-2 nodes, 3 source); default all four. Leaving the source
                  out keeps the load generator's safepoints independent of the nodes' housekeeping CPU

Agent CPUs are sticky: an agent keeps its CPU for its whole life, and new agents take free CPUs in creation
(tid) order, so threads that exist when measurement starts win over later ones. An agent that finds no free
CPU is confined to housekeeping and reported, so it cannot displace a pinned one. Every pass (0.5 s) re-reads
/proc, so threads created later are handled too. Each change and each distinct error is appended to
CASE_DIR/thread-pinning.jsonl; CASE_DIR/thread-pinning-summary.json is written on exit with every JVM's last
agent assignment, including JVMs that exited earlier. SIGTERM stops the governor after the current pass."""
from pathlib import Path
import json
import os
import signal
import sys
import time

NODE_AGENTS = frozenset({'archive-conduct', 'consensus-modul', 'clustered-servi'})
SOURCE_AGENTS = frozenset({'java', 'probe-absolute-'})
SOURCE_ROLE = 3
INTERVAL_SECONDS = 0.5
SYSCALLS = {'cpus': 'sched_setaffinity', 'nice': 'setpriority'}


class PinningError(Exception):
    pass


def classify(role, pid, tid, name):
    """'agent', 'stopped' (runs only while Java threads are stopped), 'compiler' or 'other' for one thread.

    name is the Linux comm, truncated to 15 characters."""
    # The launcher's primordial thread (tid == pid) is also called 'java' but only waits for the VM to exit.
    if tid == pid:
        return 'other'
    # Aeron names the media driver's shared agent thread after its directory, so it starts with '/'.
    if name.startswith('/') or name in (SOURCE_AGENTS if role == SOURCE_ROLE else NODE_AGENTS):
        return 'agent'
    if name.startswith('GC Thread#') or name == 'VM Thread':
        return 'stopped'
    if name.startswith(('C1 CompilerThre', 'C2 CompilerThre')):
        return 'compiler'
    return 'other'


def plan(role, pid, threads, cpus, housekeeping, previous):
    """Assign CPU sets to every (tid, name) of one JVM.

    previous maps agent tid -> CPU from the last pass; surviving agents keep their CPU. New agents take the
    lowest free non-housekeeping CPU in creation (tid) order. Returns (wanted, agents, overflow): wanted maps
    every tid to a frozenset, agents is the new sticky tid -> CPU map, overflow lists agents without a CPU."""
    housekeeping = frozenset(housekeeping)
    agent_cpus = sorted(set(cpus) - housekeeping)
    kinds = {tid: classify(role, pid, tid, name) for tid, name in threads}
    agents = sorted((tid, name) for tid, name in threads if kinds[tid] == 'agent')
    live = {tid for tid, _ in agents}
    kept = {tid: cpu for tid, cpu in previous.items() if tid in live and cpu in agent_cpus}
    free = [cpu for cpu in agent_cpus if cpu not in kept.values()]
    overflow = []
    for tid, name in agents:
        if tid in kept:
            continue
        if free:
            kept[tid] = free.pop(0)
        else:
            overflow.append((tid, name))
    wanted = {}
    for tid, _ in threads:
        if tid in kept:
            wanted[tid] = frozenset({kept[tid]})
        elif kinds[tid] == 'stopped':
            wanted[tid] = frozenset(cpus)
        else:
            wanted[tid] = housekeeping
    return wanted, kept, overflow


def compilers(role, pid, threads):
    """TIDs of JIT compiler threads, which run at reduced priority on the housekeeping CPUs."""
    return {tid for tid, name in threads if classify(role, pid, tid, name) == 'compiler'}


def role_of(cmdline, case_name):
    """Role of a JVM in this case from its command line, or None if it belongs to another case."""
    marker = '/' + case_name + '/'
    if marker not in cmdline:
        return None
    if 'io.vectormatch.cluster.ReplicatedPathProbe ' in cmdline:
        return SOURCE_ROLE
    after = cmdline.split(marker + 'node', 1)
    if len(after) == 2 and after[1][:1] in ('0', '1', '2'):
        return int(after[1][0])
    return None


def _renice(tid, value):
    os.setpriority(os.PRIO_PROCESS, tid, value)


class Governor:
    def __init__(self, case_dir, config, proc=Path('/proc'), set_affinity=None, set_nice=_renice, log=None):
        # Resolved here, not as a default argument, so the module imports on platforms without it.
        set_affinity = set_affinity or getattr(os, 'sched_setaffinity', None)
        if set_affinity is None:
            raise PinningError('sched_setaffinity is unavailable on this platform')
        self.case_name = Path(case_dir).name
        self.cpu_sets = [sorted(c) for c in config['cpuSets']]
        self.housekeeping = frozenset(config['housekeeping'])
        self.expected = config.get('expectedAgents', {})
        self.compiler_nice = config.get('compilerNice')
        self.roles = frozenset(config.get('roles', range(4)))
        if len(self.cpu_sets) != 4 or not self.housekeeping:
            raise PinningError('four CPU sets and at least one housekeeping CPU are required')
        self.proc, self.set_affinity, self.set_nice, self.log = Path(proc), set_affinity, set_nice, log
        self.applied = {}
        self.niced = set()
        self.agents = {}
        self.peak_agents = {}
        self.history = {}
        self.reported = set()
        self.overflowed = set()
        self.counts = {'changes': 0, 'errors': 0, 'passes': 0, 'overflowAgents': 0, 'nicedCompilers': 0}

    @staticmethod
    def _read(path):
        try:
            return path.read_bytes()
        except (FileNotFoundError, ProcessLookupError, PermissionError, NotADirectoryError):
            return None

    def jvms(self):
        found = {}
        for d in self.proc.iterdir():
            if not d.name.isdigit():
                continue
            comm, cmdline = self._read(d / 'comm'), self._read(d / 'cmdline')
            if comm is None or cmdline is None or comm.strip() != b'java':
                continue
            role = role_of(cmdline.replace(b'\0', b' ').decode(errors='replace'), self.case_name)
            if role in self.roles:
                found[int(d.name)] = role
        return found

    def threads(self, pid):
        try:
            entries = sorted((self.proc / str(pid) / 'task').iterdir(), key=lambda p: int(p.name))
        except (FileNotFoundError, ProcessLookupError, NotADirectoryError):
            return []
        out = []
        for t in entries:
            comm = self._read(t / 'comm')
            if comm is not None:
                out.append((int(t.name), comm.decode(errors='replace').strip()))
        return out

    def _record(self, event):
        if self.log is not None:
            event['utc'] = time.time()
            self.log.write(json.dumps(event, sort_keys=True) + '\n')

    def _error(self, pid, role, message):
        if (pid, message) not in self.reported:
            self.reported.add((pid, message))
            self.counts['errors'] += 1
            self._record({'pid': pid, 'role': role, 'error': message})

    def _apply(self, pid, role, tid, name, action, call, detail):
        """Run one system call for a thread; True if it took effect (a thread that just exited is skipped)."""
        try:
            call()
        except ProcessLookupError:
            return False
        except OSError as e:
            self._error(pid, role, '%s(%d, %s): %s' % (SYSCALLS[action], tid, detail, e))
            return False
        self._record({'pid': pid, 'role': role, 'tid': tid, 'thread': name, action: detail})
        return True

    def step(self):
        """One pass over every JVM of the case; returns the number of affinity changes made."""
        changes = 0
        live_keys, live_pids = set(), set()
        for pid, role in sorted(self.jvms().items()):
            live_pids.add(pid)
            threads = self.threads(pid)
            names = dict(threads)
            wanted, self.agents[pid], overflow = plan(role, pid, threads, self.cpu_sets[role], self.housekeeping,
                                                      self.agents.get(pid, {}))
            expected = self.expected.get('source' if role == SOURCE_ROLE else 'node')
            found = len(self.agents[pid]) + len(overflow)
            self.peak_agents[pid] = max(self.peak_agents.get(pid, 0), found)
            # Fewer agents are normal while a JVM is still starting threads; more can never become right.
            if expected is not None and found > expected:
                self._error(pid, role, 'expected %d agents, found %d' % (expected, found))
            self.history[pid] = {'role': role, 'agents': {str(t): [names[t], c] for t, c in sorted(self.agents[pid].items())}}
            for tid, name in overflow:
                if (pid, tid) not in self.overflowed:
                    self.overflowed.add((pid, tid))
                    self.counts['overflowAgents'] += 1
                self._error(pid, role, 'agent %s (%d) has no free CPU; confined to housekeeping' % (name, tid))
            for tid, cpus in sorted(wanted.items()):
                key = (pid, tid, names[tid])
                live_keys.add(key)
                if self.applied.get(key) != cpus and self._apply(
                        pid, role, tid, names[tid], 'cpus', lambda: self.set_affinity(tid, cpus), sorted(cpus)):
                    self.applied[key] = cpus
                    changes += 1
            for tid in sorted(compilers(role, pid, threads)) if self.compiler_nice is not None else ():
                key = (pid, tid, names[tid])
                if key not in self.niced and self._apply(
                        pid, role, tid, names[tid], 'nice', lambda: self.set_nice(tid, self.compiler_nice),
                        self.compiler_nice):
                    self.niced.add(key)
                    self.counts['nicedCompilers'] += 1
        # Forget exited threads and processes so a reused TID is handled again from scratch.
        self.applied = {k: v for k, v in self.applied.items() if k in live_keys}
        self.niced = {k for k in self.niced if k in live_keys}
        self.agents = {pid: v for pid, v in self.agents.items() if pid in live_pids}
        self.counts['changes'] += changes
        self.counts['passes'] += 1
        return changes

    def drift(self):
        """JVMs whose peak agent count differs from the expected count for their role."""
        out = []
        for pid, entry in sorted(self.history.items()):
            expected = self.expected.get('source' if entry['role'] == SOURCE_ROLE else 'node')
            if expected is not None and self.peak_agents[pid] != expected:
                out.append({'pid': pid, 'role': entry['role'], 'expected': expected, 'peak': self.peak_agents[pid]})
        return out

    def summary(self, config):
        return dict(self.counts, config=config, pinnedThreads=len(self.applied), drift=self.drift(),
                    agentHistory={str(pid): entry for pid, entry in sorted(self.history.items())})


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    case_dir, config = Path(argv[1]), json.loads(argv[2])
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    with (case_dir / 'thread-pinning.jsonl').open('a') as log:
        governor = Governor(case_dir, config, log=log)
        while not stopping:
            governor.step()
            log.flush()
            time.sleep(INTERVAL_SECONDS)
    (case_dir / 'thread-pinning-summary.json').write_text(json.dumps(governor.summary(config), indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main(sys.argv)
