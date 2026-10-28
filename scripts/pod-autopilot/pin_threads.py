#!/usr/bin/env python3
"""Thread-level CPU isolation for the JVMs of one running case.

Busy-spinning data-path agents lose milliseconds whenever another thread of the same JVM (JIT compiler,
JFR stream, Aeron client conductor, VM housekeeping) is scheduled onto their CPU. This governor gives each
agent a CPU of its own, lets GC worker threads use the JVM's whole set (they run only while every Java
thread is stopped at a safepoint), and confines every other thread to the housekeeping CPUs.

Usage: pin_threads.py CASE_DIR CONFIG_JSON
CONFIG_JSON keys:
  cpuSets         [node0, node1, node2, source] CPU lists, as launched with taskset
  housekeeping    CPUs for non-agent threads; never given to an agent
  expectedAgents  optional {"node": n, "source": n}; a different count is logged once (thread naming drift)

Agent CPUs are sticky: an agent keeps its CPU for its whole life, and new agents take free CPUs in creation
(tid) order, so threads that exist when measurement starts win over later ones. An agent that finds no free CPU is confined to housekeeping and reported, so it cannot displace a pinned
one. Every pass (0.5 s) re-reads /proc, so threads created later are handled too. Each affinity change and
each distinct error is appended to CASE_DIR/thread-pinning.jsonl; CASE_DIR/thread-pinning-summary.json is
written on exit. SIGTERM stops the governor after the current pass."""
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


class PinningError(Exception):
    pass


def classify(role, pid, tid, name):
    """'agent', 'gc' or 'other' for one thread (name is the Linux comm, at most 15 characters)."""
    # The launcher's primordial thread (tid == pid) is also called 'java' but only waits for the VM to exit.
    if tid == pid:
        return 'other'
    # Aeron names the media driver's shared agent thread after its directory, so it starts with '/'.
    if name.startswith('/') or name in (SOURCE_AGENTS if role == SOURCE_ROLE else NODE_AGENTS):
        return 'agent'
    if name.startswith('GC Thread#'):
        return 'gc'
    return 'other'


def plan(role, pid, threads, cpus, housekeeping, previous):
    """Assign CPU sets to every (tid, name) of one JVM.

    previous maps agent tid -> CPU from the last pass; surviving agents keep their CPU. New agents take the
    lowest free non-housekeeping CPU in creation (tid) order. Returns (wanted, agents, overflow): wanted maps
    every tid to a frozenset, agents is the new sticky tid -> CPU map, overflow lists agents without a CPU."""
    housekeeping = frozenset(housekeeping)
    agent_cpus = sorted(set(cpus) - housekeeping)
    agents = sorted((tid, name) for tid, name in threads if classify(role, pid, tid, name) == 'agent')
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
    for tid, name in threads:
        if tid in kept:
            wanted[tid] = frozenset({kept[tid]})
        elif classify(role, pid, tid, name) == 'gc':
            wanted[tid] = frozenset(cpus)
        else:
            wanted[tid] = housekeeping
    return wanted, kept, overflow


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


class Governor:
    def __init__(self, case_dir, config, proc=Path('/proc'), set_affinity=None, log=None):
        # Resolved here, not as a default argument, so the module imports on platforms without it.
        set_affinity = set_affinity or getattr(os, 'sched_setaffinity', None)
        if set_affinity is None:
            raise PinningError('sched_setaffinity is unavailable on this platform')
        self.case_name = Path(case_dir).name
        self.cpu_sets = [sorted(c) for c in config['cpuSets']]
        self.housekeeping = frozenset(config['housekeeping'])
        self.expected = config.get('expectedAgents', {})
        if len(self.cpu_sets) != 4 or not self.housekeeping:
            raise PinningError('four CPU sets and at least one housekeeping CPU are required')
        self.proc, self.set_affinity, self.log = Path(proc), set_affinity, log
        self.applied = {}
        self.agents = {}
        self.reported = set()
        self.overflowed = set()
        self.counts = {'changes': 0, 'errors': 0, 'passes': 0, 'overflowAgents': 0}

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
            if role is not None:
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

    def step(self):
        """One pass over every JVM of the case; returns the number of affinity changes made."""
        changes = 0
        live_keys, live_pids = set(), set()
        for pid, role in sorted(self.jvms().items()):
            live_pids.add(pid)
            threads = self.threads(pid)
            wanted, self.agents[pid], overflow = plan(role, pid, threads, self.cpu_sets[role], self.housekeeping,
                                                      self.agents.get(pid, {}))
            expected = self.expected.get('source' if role == SOURCE_ROLE else 'node')
            found = len(self.agents[pid]) + len(overflow)
            if expected is not None and found != expected:
                self._error(pid, role, 'expected %d agents, found %d' % (expected, found))
            for tid, name in overflow:
                if (pid, tid) not in self.overflowed:
                    self.overflowed.add((pid, tid))
                    self.counts['overflowAgents'] += 1
                self._error(pid, role, 'agent %s (%d) has no free CPU; confined to housekeeping' % (name, tid))
            names = dict(threads)
            for tid, cpus in sorted(wanted.items()):
                key = (pid, tid, names[tid])
                live_keys.add(key)
                if self.applied.get(key) == cpus:
                    continue
                try:
                    self.set_affinity(tid, cpus)
                except ProcessLookupError:
                    continue
                except OSError as e:
                    self._error(pid, role, 'sched_setaffinity(%d, %s): %s' % (tid, sorted(cpus), e))
                    continue
                self.applied[key] = cpus
                changes += 1
                self._record({'pid': pid, 'role': role, 'tid': tid, 'thread': names[tid], 'cpus': sorted(cpus)})
        # Forget exited threads and processes so a reused TID is pinned again from scratch.
        self.applied = {k: v for k, v in self.applied.items() if k in live_keys}
        self.agents = {pid: v for pid, v in self.agents.items() if pid in live_pids}
        self.counts['changes'] += changes
        self.counts['passes'] += 1
        return changes

    def summary(self, config):
        return dict(self.counts, config=config, pinnedThreads=len(self.applied),
                    agentCpus={str(pid): {str(t): c for t, c in sorted(a.items())} for pid, a in sorted(self.agents.items())})


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
